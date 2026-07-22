"""Unit tests for log ingestion and TelemetryRail correlation."""

import json

import pytest

from llm_trace_analyzer.loader import LogLoader, find_latest_log, find_rollover_files
from tests.trace_factory import (
    telemetry_end,
    telemetry_start,
    timestamp,
    trace_line,
    write_log,
)


def test_loads_text_trace_fields_and_fragment_metadata(tmp_path):
    path = write_log(
        tmp_path / "trace.log",
        [
            trace_line(
                0,
                "invoke_request",
                '{"messages":',
                event_id="evt",
                body_part=(1, 2),
            ),
            trace_line(0.1, "invoke_request", "[]}", event_id="evt", body_part=(2, 2)),
            trace_line(0.2, "reasoning_delta", "thinking", event_id="evt", reasoning_seq=7),
        ],
    )

    traces = LogLoader(str(path), load_rollover=False).load()

    assert [(trace["body_part"], trace["reasoning_seq"]) for trace in traces] == [
        ((1, 2), None),
        ((2, 2), None),
        (None, 7),
    ]
    assert set(traces[0]) == {
        "timestamp",
        "event",
        "event_id",
        "session_id",
        "request_id",
        "iteration",
        "model_name",
        "body_part",
        "reasoning_seq",
        "body_str",
    }
    assert traces[0]["event_id"] == "evt"
    assert traces[0]["model_name"] == "test-model"


def test_loads_json_log_and_process_scoped_telemetry(tmp_path):
    messages = [
        telemetry_start(0, "bash", "p10", process_id="10").split("test ", 1)[1],
        telemetry_start(0.2, "bash", "p20", process_id="20").split("test ", 1)[1],
        telemetry_end(1, "bash", 1, process_id="10").split("test ", 1)[1],
        telemetry_end(1.2, "bash", 1, process_id="20").split("test ", 1)[1],
    ]
    path = tmp_path / "trace.json"
    offsets = [0, 0.2, 1, 1.2]
    entries = [
        {
            "timestamp": timestamp(offsets[index]),
            "process_id": "10" if index in (0, 2) else "20",
            "message": message,
        }
        for index, message in enumerate(messages)
    ]
    path.write_text("\n".join(json.dumps(entry) for entry in entries), encoding="utf-8")

    loader = LogLoader(str(path), load_rollover=False)
    assert loader.load() == []

    executions = {item.tool_call_id: item for item in loader.tool_executions}
    assert executions["p10"].process_id == "10"
    assert executions["p20"].process_id == "20"
    assert executions["p10"].duration_seconds == pytest.approx(1)


def test_telemetry_supports_milliseconds_and_reports_unmatched_events(tmp_path):
    path = write_log(
        tmp_path / "telemetry.log",
        [
            telemetry_start(0, "bash", "matched"),
            telemetry_end(0.25, "bash", 250, unit="ms"),
            telemetry_start(2, "python", "orphan-start"),
            telemetry_end(20, "unknown", 1),
        ],
    )

    loader = LogLoader(str(path), load_rollover=False)
    loader.load()

    assert [(item.tool_call_id, item.duration_seconds) for item in loader.tool_executions] == [
        ("matched", pytest.approx(0.25))
    ]
    assert loader.diagnostics == {
        "duplicate_traces": 0,
        "unmatched_tool_starts": 1,
        "unmatched_tool_ends": 1,
    }


def test_session_filter_keeps_only_parent_and_descendants(tmp_path):
    path = write_log(
        tmp_path / "trace.log",
        [
            trace_line(0, "invoke_request", {}, session_id="wanted"),
            trace_line(1, "invoke_request", {}, session_id="wanted_subagent_a"),
            trace_line(2, "invoke_request", {}, session_id="wanted_subagent_a_fork_agent_b"),
            trace_line(3, "invoke_request", {}, session_id="other"),
            trace_line(4, "invoke_request", {}, session_id="wanted-but-not-child"),
        ],
    )

    traces = LogLoader(str(path), load_rollover=False).load(session_filter="wanted")

    assert {trace["session_id"] for trace in traces} == {
        "wanted",
        "wanted_subagent_a",
        "wanted_subagent_a_fork_agent_b",
    }


def test_rollover_merge_deduplicates_boundary_trace(tmp_path):
    duplicated = trace_line(0, "invoke_request", {"messages": []})
    write_log(tmp_path / "full_20260722_115900.log", [duplicated])
    current = write_log(
        tmp_path / "full.log",
        [duplicated, trace_line(1, "invoke_output", {"content": "ok"})],
    )

    loader = LogLoader(str(current))
    traces = loader.load()

    assert [trace["event"] for trace in traces] == ["invoke_request", "invoke_output"]
    assert loader.diagnostics["duplicate_traces"] == 1
    assert [path.name for path in find_rollover_files(current)] == [
        "full_20260722_115900.log",
        "full.log",
    ]


def test_load_is_idempotent_and_clears_previous_telemetry(tmp_path):
    path = write_log(
        tmp_path / "trace.log",
        [telemetry_start(0, "bash", "call"), telemetry_end(1, "bash", 1)],
    )
    loader = LogLoader(str(path), load_rollover=False)

    loader.load()
    first = list(loader.tool_executions)
    loader.load()

    assert loader.tool_executions == first
    assert loader.diagnostics["unmatched_tool_starts"] == 0


@pytest.mark.parametrize("contents", ["", "ordinary log line", "[LLM_IO_TRACE] malformed"])
def test_ignores_non_trace_input(tmp_path, contents):
    path = tmp_path / "empty.log"
    path.write_text(contents, encoding="utf-8")
    assert LogLoader(str(path), load_rollover=False).load() == []


def test_missing_file_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="日志文件不存在"):
        LogLoader(str(tmp_path / "missing.log"), load_rollover=False).load()


def test_find_latest_log_prefers_json_then_text_fallback(tmp_path):
    assert find_latest_log(tmp_path) is None
    text_log = tmp_path / "full.log"
    text_log.touch()
    assert find_latest_log(tmp_path) == text_log
    json_log = tmp_path / "full.json"
    json_log.touch()
    assert find_latest_log(tmp_path) == json_log
