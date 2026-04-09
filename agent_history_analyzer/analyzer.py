"""数据分析模块"""

from typing import Any, Dict, List, Optional, cast

from .constants import SOURCE_CHUNK_TYPES, EventType, FlowItemType
from .models import (
    AnalysisResult,
    CompressionData,
    FlowItem,
    RequestData,
    ToolCallData,
    ToolResultData,
    TopDurationStep,
)


class EventAnalyzer:
    """事件分析器"""

    def analyze(self, history_data: List[Dict[str, Any]]) -> AnalysisResult:
        """分析历史数据"""
        if not history_data:
            return AnalysisResult()

        result = AnalysisResult()
        result.total_events = len(history_data)

        current_request_id = None
        current_request_data = None

        for event in history_data:
            request_id = cast(str, event.get("request_id"))

            if request_id != current_request_id:
                if current_request_data:
                    self._finalize_request(current_request_data, result)

                current_request_id = request_id
                current_request_data = self._init_request_data(event)

            assert current_request_data is not None
            current_request_data.end_time = cast(float, event.get("timestamp"))
            current_request_data.events.append(event)

            self._process_event(event, current_request_data, result)

        if current_request_data:
            self._finalize_request(current_request_data, result)

        self._calculate_statistics(result)
        self._calculate_top_duration_steps(result)

        return result

    def _init_request_data(self, event: Dict[str, Any]) -> RequestData:
        """初始化请求数据"""
        return RequestData(
            request_id=cast(str, event.get("request_id")),
            start_time=cast(float, event.get("timestamp")),
            end_time=cast(float, event.get("timestamp")),
            events=[],
        )

    def _process_event(
        self,
        event: Dict[str, Any],
        request_data: RequestData,
        result: AnalysisResult,
    ):
        """处理单个事件"""
        event_type = event.get("event_type")
        timestamp = cast(float, event.get("timestamp"))
        content = event.get("content", "")
        role = event.get("role")

        if role == "user":
            request_data.user_input = content
            result.statistics.user_messages += 1
            return

        if event_type == EventType.CONTEXT_COMPRESSED:
            self._handle_compression(event, request_data, result, timestamp)

        elif event_type == EventType.CHAT_DELTA:
            self._handle_delta(event, request_data, timestamp, content)

        elif event_type == EventType.CHAT_FINAL:
            self._handle_final(event, request_data, result, timestamp, content)

        elif event_type == EventType.TOOL_CALL:
            self._handle_tool_call(event, request_data, result, timestamp)

        elif event_type == EventType.TOOL_RESULT:
            self._handle_tool_result(event, request_data, result, timestamp)

    def _handle_compression(
        self,
        event: Dict[str, Any],
        request_data: RequestData,
        result: AnalysisResult,
        timestamp: float,
    ):
        """处理压缩事件"""
        payload = event.get("event_payload", {})

        compression_data = CompressionData(
            timestamp=timestamp,
            before=payload.get("before_compressed", 0),
            after=payload.get("after_compressed", 0),
            rate=payload.get("rate", 0),
        )
        request_data.compressions.append(compression_data)

        result.compression_events.append(
            {
                "request_id": request_data.request_id,
                "timestamp": timestamp,
                "before": compression_data.before,
                "after": compression_data.after,
                "rate": compression_data.rate,
            }
        )
        result.statistics.context_compressed += 1

        request_data.execution_flow.append(
            FlowItem(
                type=FlowItemType.COMPRESSION,
                timestamp=timestamp,
                before=compression_data.before,
                after=compression_data.after,
                rate=compression_data.rate,
            )
        )

    def _handle_delta(
        self,
        event: Dict[str, Any],
        request_data: RequestData,
        timestamp: float,
        content: str,
    ):
        """处理增量事件"""
        payload = event.get("event_payload", {})
        source_type = payload.get("source_chunk_type")

        if source_type != SOURCE_CHUNK_TYPES["LLM_REASONING"]:
            return

        if request_data.execution_flow:
            last_item = request_data.execution_flow[-1]
            if last_item.type == FlowItemType.REASONING:
                if last_item.content is None:
                    last_item.content = content
                else:
                    last_item.content += content
                last_item.end_timestamp = timestamp
                return

        request_data.execution_flow.append(
            FlowItem(
                type=FlowItemType.REASONING,
                content=content,
                timestamp=timestamp,
                start_timestamp=timestamp,
                end_timestamp=timestamp,
            )
        )

    def _handle_final(
        self,
        event: Dict[str, Any],
        request_data: RequestData,
        result: AnalysisResult,
        timestamp: float,
        content: str,
    ):
        """处理最终事件"""
        payload = event.get("event_payload", {})
        source_type = payload.get("source_chunk_type")

        if source_type != SOURCE_CHUNK_TYPES["ANSWER"]:
            return

        request_data.assistant_response = content
        result.statistics.assistant_messages += 1

        start_timestamp = self._get_response_start_time(request_data)

        request_data.execution_flow.append(
            FlowItem(
                type=FlowItemType.ASSISTANT_RESPONSE,
                content=content,
                timestamp=timestamp,
                start_timestamp=start_timestamp,
                end_timestamp=timestamp,
            )
        )

    def _handle_tool_call(
        self,
        event: Dict[str, Any],
        request_data: RequestData,
        result: AnalysisResult,
        timestamp: float,
    ):
        """处理工具调用"""
        payload = event.get("event_payload", {})
        tool_call = payload.get("tool_call", {})

        tool_call_data = ToolCallData(
            name=tool_call.get("name"),
            arguments=tool_call.get("arguments"),
            tool_call_id=tool_call.get("tool_call_id"),
            timestamp=timestamp,
            start_time=timestamp,
        )
        request_data.tool_calls.append(tool_call_data)

        request_data.execution_flow.append(
            FlowItem(
                type=FlowItemType.TOOL_CALL,
                tool_call_id=tool_call.get("tool_call_id"),
                name=tool_call.get("name"),
                arguments=tool_call.get("arguments"),
                timestamp=timestamp,
            )
        )

        result.statistics.tool_calls += 1
        tool_name = tool_call.get("name")
        if tool_name:
            result.tool_usage[tool_name]["count"] += 1

    def _handle_tool_result(
        self,
        event: Dict[str, Any],
        request_data: RequestData,
        result: AnalysisResult,
        timestamp: float,
    ):
        """处理工具结果"""
        payload = event.get("event_payload", {})
        tool_call_id = payload.get("tool_call_id")
        tool_name = payload.get("tool_name")
        result_content = payload.get("result")

        duration = 0.0
        for tool_call in request_data.tool_calls:
            if tool_call.tool_call_id == tool_call_id:
                duration = timestamp - tool_call.start_time
                tool_call.duration = duration

                if tool_name and tool_name in result.tool_usage:
                    result.tool_usage[tool_name]["total_time"] += duration
                break

        for flow_item in request_data.execution_flow:
            if flow_item.type == FlowItemType.TOOL_CALL and flow_item.tool_call_id == tool_call_id:
                flow_item.duration = duration
                flow_item.result = result_content
                break

        request_data.tool_results.append(
            ToolResultData(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                result=result_content,
                timestamp=timestamp,
            )
        )

    def _get_response_start_time(self, request_data: RequestData) -> float:
        """获取响应开始时间"""
        if not request_data.execution_flow:
            return request_data.start_time

        last_item = request_data.execution_flow[-1]
        if last_item.type == FlowItemType.TOOL_CALL:
            return last_item.timestamp + last_item.duration
        elif last_item.type == FlowItemType.REASONING:
            return last_item.end_timestamp or last_item.timestamp
        elif last_item.type == FlowItemType.COMPRESSION:
            return last_item.timestamp

        return request_data.start_time

    def _finalize_request(
        self,
        request_data: RequestData,
        result: AnalysisResult,
    ):
        """完成请求处理"""
        request_data.duration = request_data.end_time - request_data.start_time

        for flow_item in request_data.execution_flow:
            if flow_item.type == FlowItemType.REASONING:
                if flow_item.start_timestamp and flow_item.end_timestamp:
                    flow_item.duration = flow_item.end_timestamp - flow_item.start_timestamp

        result.requests[request_data.request_id] = request_data
        result.timeline.append(request_data)
        result.statistics.total_requests += 1

    def _calculate_statistics(self, result: AnalysisResult):
        """计算统计数据"""
        if result.statistics.total_requests > 0:
            total_time = sum(r.duration for r in result.timeline)
            result.statistics.total_time = total_time
            result.statistics.avg_request_time = total_time / result.statistics.total_requests

    def _calculate_top_duration_steps(self, result: AnalysisResult):
        """计算耗时排行"""
        all_steps: List[TopDurationStep] = []
        flow_item_index = 0

        for request in result.timeline:
            request_id = request.request_id
            user_input = request.user_input

            # 用户输入卡片也算一个流程项
            if request.user_input:
                flow_item_index += 1

            for flow_item in request.execution_flow:
                step = self._create_step_from_flow_item(
                    flow_item, request_id, user_input, flow_item_index
                )
                if step:
                    all_steps.append(step)
                flow_item_index += 1

        all_steps.sort(key=lambda x: x.duration, reverse=True)
        result.top_duration_steps = all_steps[:20]

    def _create_step_from_flow_item(
        self,
        flow_item: FlowItem,
        request_id: str,
        user_input: str,
        flow_item_index: int,
    ) -> Optional[TopDurationStep]:
        """从流程项创建步骤"""
        duration = flow_item.duration

        if flow_item.type == FlowItemType.REASONING:
            content = flow_item.content or ""
            summary = f"推理: {content[:100]}{'...' if len(content) > 100 else ''}"
            return TopDurationStep(
                request_id=request_id,
                type="推理",
                duration=duration,
                summary=summary,
                user_input=user_input[:50] + ("..." if len(user_input) > 50 else ""),
                flow_item_index=flow_item_index,
            )

        elif flow_item.type == FlowItemType.TOOL_CALL:
            return TopDurationStep(
                request_id=request_id,
                type="工具调用",
                duration=duration,
                summary=f"工具: {flow_item.name or 'unknown'}",
                user_input=user_input[:50] + ("..." if len(user_input) > 50 else ""),
                flow_item_index=flow_item_index,
            )

        elif flow_item.type == FlowItemType.ASSISTANT_RESPONSE:
            content = flow_item.content or ""
            summary = f"回复: {content[:100]}{'...' if len(content) > 100 else ''}"
            return TopDurationStep(
                request_id=request_id,
                type="助手回复",
                duration=duration,
                summary=summary,
                user_input=user_input[:50] + ("..." if len(user_input) > 50 else ""),
                flow_item_index=flow_item_index,
            )

        return None
