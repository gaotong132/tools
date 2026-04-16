"""LLM_IO_TRACE 解析器 - 分片合并与JSON解析"""

import json
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from .constants import TraceEventType
from .models import LLMRequest, LLMResponse


class TraceParser:
    def __init__(self, traces: List[Dict[str, Any]]):
        self.traces = traces

    def parse(self) -> Tuple[Dict[str, List[LLMRequest]], Dict[str, List[LLMResponse]]]:
        grouped = self._group_traces()

        requests: Dict[str, List[LLMRequest]] = {}
        responses: Dict[str, List[LLMResponse]] = {}

        for session_id, session_traces in grouped.items():
            reqs, resps = self._parse_session(session_id, session_traces)
            if reqs:
                requests[session_id] = reqs
            if resps:
                responses[session_id] = resps

        return requests, responses

    def _group_traces(self) -> Dict[str, List[Dict[str, Any]]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for trace in self.traces:
            session_id = trace["session_id"]
            if session_id:
                grouped[session_id].append(trace)
        return dict(grouped)

    def _parse_session(
        self, session_id: str, traces: List[Dict[str, Any]]
    ) -> Tuple[List[LLMRequest], List[LLMResponse]]:
        by_iteration: Dict[int, Dict[str, List[Dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for trace in traces:
            iteration = trace["iteration"]
            event = trace["event"]
            by_iteration[iteration][event].append(trace)

        requests: List[LLMRequest] = []
        responses: List[LLMResponse] = []

        for iteration in sorted(by_iteration.keys()):
            iter_traces = by_iteration[iteration]

            if TraceEventType.STREAM_REQUEST.value in iter_traces:
                req = self._parse_request(
                    session_id, iteration, iter_traces[TraceEventType.STREAM_REQUEST.value]
                )
                if req:
                    requests.append(req)

            if TraceEventType.STREAM_OUTPUT.value in iter_traces:
                resp = self._parse_response(
                    session_id,
                    iteration,
                    iter_traces.get(TraceEventType.STREAM_OUTPUT.value, []),
                    iter_traces.get(TraceEventType.REASONING_DELTA.value, []),
                )
                if resp:
                    responses.append(resp)

        return requests, responses

    def _parse_request(
        self, session_id: str, iteration: int, traces: List[Dict[str, Any]]
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

        return LLMRequest(
            session_id=session_id,
            iteration=iteration,
            model_name=model_name,
            timestamp=timestamp,
            body=body_dict,
            messages=messages,
            tools=tools,
        )

    def _parse_response(
        self,
        session_id: str,
        iteration: int,
        output_traces: List[Dict[str, Any]],
        reasoning_traces: List[Dict[str, Any]],
    ) -> Optional[LLMResponse]:
        merged_body = self._merge_body_parts(output_traces)
        if not merged_body:
            return None

        try:
            body_dict = json.loads(merged_body)
        except json.JSONDecodeError:
            return None

        timestamp = output_traces[0]["timestamp"] if output_traces else 0
        model_name = output_traces[0]["model_name"] if output_traces else ""

        content = body_dict.get("content", "")
        reasoning_content = body_dict.get("reasoning_content", "") or ""

        reasoning_merged = self._merge_reasoning(reasoning_traces)
        if reasoning_merged:
            reasoning_content = reasoning_merged

        tool_calls = body_dict.get("tool_calls", [])

        return LLMResponse(
            session_id=session_id,
            iteration=iteration,
            model_name=model_name,
            timestamp=timestamp,
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
        )

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
            sorted_traces = sorted(with_seq, key=lambda t: t["reasoning_seq"])
            return "".join(str(t["body_str"]) for t in sorted_traces)

        merged_body = self._merge_body_parts(traces)
        if not merged_body:
            return ""

        try:
            body_dict = json.loads(merged_body)
            return body_dict.get("reasoning_content", "") or ""
        except json.JSONDecodeError:
            return ""
