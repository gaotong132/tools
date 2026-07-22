"""并发 event_id 配对和 TelemetryRail 工具耗时回归测试。"""

import json

import pytest

from llm_trace_analyzer.analyzer import ChainAnalyzer
from llm_trace_analyzer.loader import LogLoader
from llm_trace_analyzer.parser import TraceParser


def _trace_line(timestamp, event, event_id, body, body_part=""):
    part = f" body_part={body_part}" if body_part else ""
    return (
        f"2026-07-22 12:00:{timestamp} [1] DEBUG test "
        f"[LLM_IO_TRACE] event={event} event_id='{event_id}' "
        f"session_id='session-concurrent' request_id='shared' iteration=0 "
        f"model_name='test-model'{part} body={body}"
    )


def test_event_id_prevents_parallel_calls_from_being_cross_paired(tmp_path):
    memory_body = json.dumps(
        {
            "messages": [{"role": "system", "content": "You are a session memory updater"}],
            "tools": [],
        }
    )
    split_at = len(memory_body) // 2
    summary_body = json.dumps(
        {
            "messages": [{"role": "user", "content": "Summarize each numbered block below"}],
            "tools": [],
        }
    )
    memory_output = json.dumps(
        {
            "content": "memory done",
            "tool_calls": [{"id": "call-a", "name": "bash"}],
        }
    )
    summary_output = json.dumps({"content": "summary done", "tool_calls": []})

    lines = [
        _trace_line("00.000", "invoke_request", "event-a", memory_body[:split_at], "1/2"),
        _trace_line("00.200", "invoke_request", "event-b", summary_body),
        _trace_line("00.400", "invoke_request", "event-a", memory_body[split_at:], "2/2"),
        _trace_line("03.000", "invoke_output", "event-b", summary_output),
        _trace_line("05.000", "invoke_output", "event-a", memory_output),
        "2026-07-22 12:00:05.100 [1] INFO test "
        "[TelemetryRail] 工具调用开始: tool=bash, tool_call_id=call-a",
        "2026-07-22 12:00:05.350 [1] INFO test "
        "[TelemetryRail] 工具调用完成: tool=bash, duration=0.25s",
    ]
    log_file = tmp_path / "trace.log"
    log_file.write_text("\n".join(lines), encoding="utf-8")

    loader = LogLoader(str(log_file), load_rollover=False)
    traces = loader.load()
    requests, responses, metrics = TraceParser(traces).parse()

    assert {request.event_id for request in requests["session-concurrent"]} == {
        "event-a",
        "event-b",
    }
    assert {response.event_id for response in responses["session-concurrent"]} == {
        "event-a",
        "event-b",
    }
    assert [request.call_kind for request in requests["session-concurrent"]] == [
        "session_memory",
        "context_summary",
    ]

    result = ChainAnalyzer(
        requests, responses, metrics, tool_executions=loader.tool_executions
    ).analyze()
    timings = result.sessions["session-concurrent"].iteration_timings
    by_event = {timing.event_id: timing for timing in timings}

    assert by_event["event-a"].llm_call_duration == pytest.approx(5.0)
    assert by_event["event-b"].llm_call_duration == pytest.approx(2.8)
    assert by_event["event-a"].tool_processing_duration == pytest.approx(0.25)
    assert by_event["event-b"].tool_processing_duration == 0
    assert by_event["event-a"].tool_executions[0].tool_call_id == "call-a"
    assert all(timing.llm_call_duration >= 0 for timing in timings)
