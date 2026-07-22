"""Small deterministic builders used by unit tests."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional

from llm_trace_analyzer.models import LLMRequest, LLMResponse, ToolExecution

BASE_TIME = datetime(2026, 7, 22, 12, 0, 0)


def timestamp(offset: float) -> str:
    return (BASE_TIME + timedelta(seconds=offset)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def trace_line(
    offset: float,
    event: str,
    body: Any,
    *,
    event_id: str = "event-1",
    session_id: str = "session-main",
    request_id: str = "request-1",
    iteration: int = 0,
    model_name: str = "test-model",
    process_id: str = "1",
    body_part: Optional[tuple[int, int]] = None,
    reasoning_seq: Optional[int] = None,
) -> str:
    body_text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    event_id_field = f"event_id='{event_id}' " if event_id else ""
    part_field = f"body_part={body_part[0]}/{body_part[1]} " if body_part else ""
    seq_field = f"reasoning_seq={reasoning_seq} " if reasoning_seq is not None else ""
    return (
        f"{timestamp(offset)} [{process_id}] DEBUG test [LLM_IO_TRACE] event={event} "
        f"{event_id_field}session_id='{session_id}' request_id='{request_id}' "
        f"iteration={iteration} model_name='{model_name}' {part_field}{seq_field}body={body_text}"
    )


def telemetry_start(
    offset: float,
    tool: str,
    call_id: str,
    *,
    process_id: str = "1",
) -> str:
    return (
        f"{timestamp(offset)} [{process_id}] INFO test "
        f"[TelemetryRail] 工具调用开始: tool={tool}, tool_call_id={call_id}"
    )


def telemetry_end(
    offset: float,
    tool: str,
    duration: float,
    *,
    unit: str = "s",
    process_id: str = "1",
) -> str:
    return (
        f"{timestamp(offset)} [{process_id}] INFO test "
        f"[TelemetryRail] 工具调用完成: tool={tool}, duration={duration}{unit}"
    )


def write_log(path: Path, lines: Iterable[str]) -> Path:
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def request(
    event_id: str,
    timestamp_value: float,
    *,
    session_id: str = "session-main",
    iteration: int = 1,
    messages: Optional[list[dict]] = None,
    tools: Optional[list[dict]] = None,
    model_name: str = "test-model",
    call_kind: str = "agent",
) -> LLMRequest:
    messages = messages if messages is not None else [{"role": "user", "content": event_id}]
    tools = tools or []
    body = {"messages": messages, "tools": tools}
    return LLMRequest(
        session_id=session_id,
        iteration=iteration,
        model_name=model_name,
        timestamp=timestamp_value,
        body=body,
        messages=messages,
        tools=tools,
        event_id=event_id,
        call_kind=call_kind,
        is_internal=call_kind != "agent",
    )


def response(
    event_id: str,
    timestamp_value: float,
    *,
    session_id: str = "session-main",
    iteration: int = 1,
    tool_calls: Optional[list[dict]] = None,
    content: str = "done",
    model_name: str = "test-model",
    call_kind: str = "agent",
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> LLMResponse:
    return LLMResponse(
        session_id=session_id,
        iteration=iteration,
        model_name=model_name,
        timestamp=timestamp_value,
        content=content,
        tool_calls=tool_calls or [],
        event_id=event_id,
        call_kind=call_kind,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def execution(
    call_id: str,
    duration: float,
    *,
    tool_name: str = "bash",
    start_time: float = 10.0,
    process_id: str = "1",
) -> ToolExecution:
    return ToolExecution(
        tool_call_id=call_id,
        tool_name=tool_name,
        start_time=start_time,
        end_time=start_time + duration,
        duration_seconds=duration,
        process_id=process_id,
    )
