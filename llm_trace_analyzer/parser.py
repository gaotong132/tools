"""LLM_IO_TRACE 解析器 - 分片合并与JSON解析"""

import json
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from .constants import TraceEventType
from .models import LLMRequest, LLMResponse, SystemMetrics

# 预编译 usage_metadata 正则
_USAGE_INT_NAME_RE = re.compile(r"(input_tokens|output_tokens|total_tokens|cache_tokens)=(\d+)")
_USAGE_FLOAT_NAME_RE = re.compile(r"(input_cost|output_cost|total_cost)=([\d.]+)")


class TraceParser:
    def __init__(self, traces: List[Dict[str, Any]]):
        self.traces = traces

    def parse(
        self,
    ) -> Tuple[
        Dict[str, List[LLMRequest]],
        Dict[str, List[LLMResponse]],
        Dict[Tuple[str, int], List[SystemMetrics]],
    ]:
        grouped = self._group_traces()

        requests: Dict[str, List[LLMRequest]] = {}
        responses: Dict[str, List[LLMResponse]] = {}
        system_metrics: Dict[Tuple[str, int], List[SystemMetrics]] = {}

        for session_id, session_traces in grouped.items():
            reqs, resps, metrics = self._parse_session(session_id, session_traces)
            if reqs:
                requests[session_id] = reqs
            if resps:
                responses[session_id] = resps
            if metrics:
                system_metrics.update(metrics)

        return requests, responses, system_metrics

    def _group_traces(self) -> Dict[str, List[Dict[str, Any]]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for trace in self.traces:
            session_id = trace["session_id"]
            if session_id:
                grouped[session_id].append(trace)
        return dict(grouped)

    def _parse_session(
        self, session_id: str, traces: List[Dict[str, Any]]
    ) -> Tuple[List[LLMRequest], List[LLMResponse], Dict[Tuple[str, int], List[SystemMetrics]]]:
        requests: List[LLMRequest] = []
        responses: List[LLMResponse] = []
        system_metrics: Dict[Tuple[str, int], List[SystemMetrics]] = {}

        request_events = {TraceEventType.STREAM_REQUEST.value, TraceEventType.INVOKE_REQUEST.value}
        output_events = {TraceEventType.STREAM_OUTPUT.value, TraceEventType.INVOKE_OUTPUT.value}
        call_traces = [
            t
            for t in traces
            if t["event"] in request_events | output_events | {TraceEventType.REASONING_DELTA.value}
        ]

        # 新日志以 event_id 标识一次真实模型调用。这是并发场景下唯一可靠的配对键。
        by_event_id: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        legacy_by_iteration: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for trace in call_traces:
            event_id = trace.get("event_id", "")
            if event_id:
                by_event_id[event_id].append(trace)
            else:
                legacy_by_iteration[trace["iteration"]].append(trace)

        call_groups: List[
            Tuple[float, str, List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]
        ] = []
        for event_id, event_traces in by_event_id.items():
            req = [t for t in event_traces if t["event"] in request_events]
            out = [t for t in event_traces if t["event"] in output_events]
            reasoning = [
                t for t in event_traces if t["event"] == TraceEventType.REASONING_DELTA.value
            ]
            start = min(t["timestamp"] for t in event_traces)
            call_groups.append((start, event_id, req, out, reasoning))

        # 兼容旧日志：没有 event_id 时保留原来的时间聚类策略。
        for _raw_iteration, iter_traces in legacy_by_iteration.items():
            request_groups = self._group_by_timestamp(
                [t for t in iter_traces if t["event"] in request_events]
            )
            output_groups = self._group_by_timestamp(
                [t for t in iter_traces if t["event"] in output_events]
            )
            reasoning_groups = self._group_by_seq_reset(
                [t for t in iter_traces if t["event"] == TraceEventType.REASONING_DELTA.value]
            )
            for index in range(max(len(request_groups), len(output_groups))):
                req = request_groups[index] if index < len(request_groups) else []
                out = output_groups[index] if index < len(output_groups) else []
                reference = min((t["timestamp"] for t in out or req), default=0.0)
                reasoning = min(
                    reasoning_groups,
                    key=lambda group: abs(
                        sum(t["timestamp"] for t in group) / len(group) - reference
                    ),
                    default=[],
                )
                start = min((t["timestamp"] for t in req or out or reasoning), default=0.0)
                call_groups.append((start, "", req, out, reasoning))

        for actual_iteration, (_, event_id, req_traces, out_traces, reason_traces) in enumerate(
            sorted(call_groups, key=lambda group: group[0]), start=1
        ):
            parsed_request = (
                self._parse_request(session_id, actual_iteration, req_traces, event_id=event_id)
                if req_traces
                else None
            )
            if parsed_request:
                requests.append(parsed_request)
            if out_traces or reason_traces:
                resp = self._parse_response(
                    session_id,
                    actual_iteration,
                    out_traces,
                    reason_traces,
                    event_id=event_id,
                    call_kind=parsed_request.call_kind if parsed_request else "agent",
                )
                if resp:
                    responses.append(resp)

        metrics_list = self._parse_system_metrics(traces)
        if metrics_list and requests:
            system_metrics[(session_id, requests[0].iteration)] = metrics_list

        return requests, responses, system_metrics

    @staticmethod
    def _parse_system_metrics(traces: List[Dict[str, Any]]) -> List[SystemMetrics]:
        metrics_list: List[SystemMetrics] = []
        for trace in traces:
            if trace["event"] != TraceEventType.SYSTEM_METRICS.value:
                continue
            try:
                body = json.loads(trace.get("body_str", ""))
            except json.JSONDecodeError:
                continue
            metrics_list.append(
                SystemMetrics(
                    phase=body.get("phase", ""),
                    cpu_percent=body.get("cpu_percent", 0.0),
                    memory_rss_mb=body.get("memory_rss_mb", 0.0),
                    memory_vms_mb=body.get("memory_vms_mb", 0.0),
                    read_bytes=body.get("read_bytes", 0),
                    write_bytes=body.get("write_bytes", 0),
                    timestamp=trace.get("timestamp", 0.0),
                )
            )
        return metrics_list

    def _group_by_timestamp(
        self, traces: List[Dict[str, Any]], threshold: float = 1.0
    ) -> List[List[Dict[str, Any]]]:
        """按时间戳聚类，同一 iteration 内时间差超过阈值的分开"""
        if not traces:
            return []

        sorted_traces = sorted(traces, key=lambda t: t["timestamp"])
        groups: List[List[Dict[str, Any]]] = []
        current_group: List[Dict[str, Any]] = [sorted_traces[0]]

        for trace in sorted_traces[1:]:
            if trace["timestamp"] - current_group[-1]["timestamp"] > threshold:
                groups.append(current_group)
                current_group = [trace]
            else:
                current_group.append(trace)

        groups.append(current_group)
        return groups

    def _parse_request(
        self,
        session_id: str,
        iteration: int,
        traces: List[Dict[str, Any]],
        event_id: str = "",
    ) -> Optional[LLMRequest]:
        merged_body = self._merge_body_parts(traces)
        if not merged_body:
            return None

        try:
            body_dict = json.loads(merged_body)
        except json.JSONDecodeError:
            return None

        timestamp = traces[0]["timestamp"] if traces else 0
        model_name = traces[0]["model_name"] if traces else ""

        messages = body_dict.get("messages", [])
        tools = body_dict.get("tools", [])

        call_kind = self._detect_call_kind(messages, tools)

        return LLMRequest(
            session_id=session_id,
            iteration=iteration,
            model_name=model_name,
            timestamp=timestamp,
            body=body_dict,
            messages=messages,
            tools=tools,
            is_internal=call_kind != "agent",
            event_id=event_id,
            call_kind=call_kind,
        )

    @staticmethod
    def _detect_call_kind(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> str:
        text = "\n".join(str(message.get("content", "")) for message in messages)
        if "You are a session memory updater" in text:
            return "session_memory"
        if "Summarize each numbered block" in text:
            return "context_summary"
        if "CRITICAL: Respond with TEXT ONLY" in text and not tools:
            return "context_compaction"
        internal_keywords = (
            "安全工具调用解析器",
            "file_guard.extract",
            "command_intent",
        )
        if not tools and any(keyword in text for keyword in internal_keywords):
            return "framework_internal"
        return "agent"

    def _parse_response(
        self,
        session_id: str,
        iteration: int,
        output_traces: List[Dict[str, Any]],
        reasoning_traces: List[Dict[str, Any]],
        event_id: str = "",
        call_kind: str = "agent",
    ) -> Optional[LLMResponse]:
        merged_body = self._merge_body_parts(output_traces)
        body_dict = {}
        if merged_body:
            try:
                body_dict = json.loads(merged_body)
            except json.JSONDecodeError:
                pass

        # 如果 output 和 reasoning 都为空，跳过
        reasoning_merged = self._merge_reasoning(reasoning_traces)
        if not body_dict and not reasoning_merged:
            return None

        timestamp = (
            max(t["timestamp"] for t in output_traces)
            if output_traces
            else (reasoning_traces[0]["timestamp"] if reasoning_traces else 0)
        )
        model_name = (
            output_traces[0]["model_name"]
            if output_traces
            else (reasoning_traces[0]["model_name"] if reasoning_traces else "")
        )

        content = body_dict.get("content", "")
        reasoning_content = body_dict.get("reasoning_content", "") or ""

        # 仅当 output body 未携带 reasoning_content 时，才回退到 reasoning_delta 合并结果。
        # body 中的 reasoning_content 是权威值；当 trace 共享 iteration=0 / 复用 request_id 时，
        # reasoning_delta 按时间戳聚类会错配到其他调用，直接覆盖会导致显示异常且与 token 统计不符。
        if not reasoning_content and reasoning_merged:
            reasoning_content = reasoning_merged

        tool_calls = body_dict.get("tool_calls", [])

        # 解析 usage_metadata
        usage_metadata = body_dict.get("usage_metadata", "")
        token_stats = self._parse_usage_metadata(usage_metadata)

        return LLMResponse(
            session_id=session_id,
            iteration=iteration,
            model_name=model_name,
            timestamp=timestamp,
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
            event_id=event_id,
            call_kind=call_kind,
            input_tokens=token_stats.get("input_tokens", 0),
            output_tokens=token_stats.get("output_tokens", 0),
            total_tokens=token_stats.get("total_tokens", 0),
            cache_tokens=token_stats.get("cache_tokens", 0),
            input_cost=token_stats.get("input_cost", 0.0),
            output_cost=token_stats.get("output_cost", 0.0),
            total_cost=token_stats.get("total_cost", 0.0),
        )

    def _parse_usage_metadata(self, usage_str: str) -> Dict[str, Any]:
        """解析 usage_metadata 字符串，提取 token 统计信息。

        格式: "code=0 err_msg='' prompt='' task_id='' model_name='glm-5.1'
               total_latency=0.0 first_token_time='******' request_start_time=''
               input_tokens=23661 output_tokens=3546 total_tokens=27207
               cache_tokens=0 input_cost=0.0 output_cost=0.0 total_cost=0.0"
        """
        if not usage_str:
            return {}

        result: Dict[str, Any] = {}
        for match in _USAGE_INT_NAME_RE.finditer(usage_str):
            result[match.group(1)] = int(match.group(2))
        for match in _USAGE_FLOAT_NAME_RE.finditer(usage_str):
            result[match.group(1)] = float(match.group(2))

        return result

    def _merge_body_parts(self, traces: List[Dict[str, Any]]) -> str:
        if not traces:
            return ""

        with_parts = [t for t in traces if t["body_part"] is not None]
        without_parts = [t for t in traces if t["body_part"] is None]

        if with_parts:
            sorted_traces = sorted(with_parts, key=lambda t: t["body_part"][0])
            merged = "".join(str(t["body_str"]) for t in sorted_traces)
            return merged

        if without_parts:
            return str(without_parts[0]["body_str"])

        return ""

    def _merge_reasoning(self, traces: List[Dict[str, Any]]) -> str:
        if not traces:
            return ""

        with_seq = [t for t in traces if t.get("reasoning_seq") is not None]
        if with_seq:
            # 按 seq 重置分组，再按 seq 排序合并
            groups = self._group_by_seq_reset(with_seq)
            merged_parts = []
            for group in groups:
                sorted_group = sorted(group, key=lambda t: t["reasoning_seq"])
                merged_parts.append("".join(str(t["body_str"]) for t in sorted_group))
            return "".join(merged_parts)

        merged_body = self._merge_body_parts(traces)
        if not merged_body:
            return ""

        try:
            body_dict = json.loads(merged_body)
            return body_dict.get("reasoning_content", "") or ""
        except json.JSONDecodeError:
            return ""

    def _group_by_seq_reset(self, traces: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """按 reasoning_seq 重置分组：seq 从高变低说明是新的一组"""
        if not traces:
            return []

        sorted_traces = sorted(traces, key=lambda t: t["timestamp"])
        groups: List[List[Dict[str, Any]]] = []
        current_group: List[Dict[str, Any]] = [sorted_traces[0]]

        for trace in sorted_traces[1:]:
            prev_seq = current_group[-1].get("reasoning_seq", 0)
            curr_seq = trace.get("reasoning_seq", 0)
            # seq 重置（从高变低）说明是新的一组
            if curr_seq < prev_seq:
                groups.append(current_group)
                current_group = [trace]
            else:
                current_group.append(trace)

        groups.append(current_group)
        return groups
