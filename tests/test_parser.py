"""Contract tests for reconstructing model calls from trace events."""

import json

import pytest

from llm_trace_analyzer.loader import LogLoader
from llm_trace_analyzer.parser import TraceParser
from tests.trace_factory import trace_line, write_log


def parse_lines(tmp_path, lines):
    path = write_log(tmp_path / "trace.log", lines)
    traces = LogLoader(str(path), load_rollover=False).load()
    parser = TraceParser(traces)
    parsed = parser.parse()
    return parser, parsed


def test_fragmented_parallel_calls_are_paired_by_event_id(tmp_path):
    slow_body = json.dumps({"messages": [{"role": "user", "content": "slow"}], "tools": []})
    split = len(slow_body) // 2
    parser, (requests, responses, _) = parse_lines(
        tmp_path,
        [
            trace_line(0, "invoke_request", slow_body[:split], event_id="slow", body_part=(1, 2)),
            trace_line(
                0.1,
                "invoke_request",
                {"messages": [{"role": "user", "content": "fast"}]},
                event_id="fast",
            ),
            trace_line(0.2, "invoke_request", slow_body[split:], event_id="slow", body_part=(2, 2)),
            trace_line(1, "invoke_output", {"content": "fast-result"}, event_id="fast"),
            trace_line(3, "invoke_output", {"content": "slow-result"}, event_id="slow"),
        ],
    )

    assert [(item.iteration, item.event_id) for item in requests["session-main"]] == [
        (1, "slow"),
        (2, "fast"),
    ]
    assert {item.event_id: item.content for item in responses["session-main"]} == {
        "slow": "slow-result",
        "fast": "fast-result",
    }
    assert dict(parser.diagnostics) == {}


def test_incomplete_and_invalid_json_groups_are_diagnosed(tmp_path):
    parser, (requests, responses, _) = parse_lines(
        tmp_path,
        [
            trace_line(0, "invoke_request", '{"messages":', event_id="broken", body_part=(1, 2)),
            trace_line(1, "invoke_request", {"messages": []}, event_id="request-only"),
            trace_line(2, "invoke_output", {"content": "orphan"}, event_id="response-only"),
            trace_line(3, "invoke_output", "not-json", event_id="bad-response"),
        ],
    )

    assert [item.event_id for item in requests["session-main"]] == ["request-only"]
    assert [item.event_id for item in responses["session-main"]] == ["response-only"]
    assert parser.diagnostics == {
        "request_only_event_groups": 2,
        "response_only_event_groups": 2,
        "incomplete_body_groups": 1,
        "request_json_errors": 1,
        "response_json_errors": 1,
    }


def test_reasoning_only_response_uses_last_delta_timestamp(tmp_path):
    _, (requests, responses, _) = parse_lines(
        tmp_path,
        [
            trace_line(0, "invoke_request", {"messages": []}, event_id="reason"),
            trace_line(1, "reasoning_delta", "first", event_id="reason", reasoning_seq=0),
            trace_line(2, "reasoning_delta", " second", event_id="reason", reasoning_seq=1),
        ],
    )

    request = requests["session-main"][0]
    response = responses["session-main"][0]
    assert response.reasoning_content == "first second"
    assert response.timestamp - request.timestamp == pytest.approx(2)


def test_output_reasoning_is_authoritative_over_deltas(tmp_path):
    _, (_, responses, _) = parse_lines(
        tmp_path,
        [
            trace_line(0, "reasoning_delta", "stale", event_id="event", reasoning_seq=0),
            trace_line(
                1,
                "invoke_output",
                {"content": "answer", "reasoning_content": "authoritative"},
                event_id="event",
            ),
        ],
    )
    assert responses["session-main"][0].reasoning_content == "authoritative"


def test_usage_metadata_and_system_metrics_are_parsed(tmp_path):
    _, (requests, responses, metrics) = parse_lines(
        tmp_path,
        [
            trace_line(0, "invoke_request", {"messages": []}, event_id="usage"),
            trace_line(
                1,
                "invoke_output",
                {
                    "content": "ok",
                    "usage_metadata": "input_tokens=12 output_tokens=3 total_tokens=15 "
                    "cache_tokens=4 input_cost=0.1 output_cost=0.2 total_cost=0.3",
                },
                event_id="usage",
            ),
            trace_line(
                0.5,
                "system_metrics",
                {
                    "phase": "periodic",
                    "cpu_percent": 25,
                    "memory_rss_mb": 128,
                },
                event_id="metrics",
            ),
        ],
    )

    response = responses["session-main"][0]
    assert (response.input_tokens, response.output_tokens, response.total_tokens) == (12, 3, 15)
    assert response.total_cost == pytest.approx(0.3)
    assert metrics[("session-main", requests["session-main"][0].iteration)][0].cpu_percent == 25


@pytest.mark.parametrize(
    ("messages", "tools", "expected"),
    [
        (
            [{"role": "system", "content": "You are a session memory updater. Keep facts."}],
            [],
            "session_memory",
        ),
        (
            [{"role": "user", "content": "Summarize each numbered block below"}],
            [],
            "context_summary",
        ),
        (
            [{"role": "system", "content": "CRITICAL: Respond with TEXT ONLY now"}],
            [],
            "context_compaction",
        ),
        ([{"role": "system", "content": "安全工具调用解析器"}], [], "framework_internal"),
        (
            [
                {"role": "system", "content": "normal"},
                {"role": "user", "content": "Summarize each numbered block"},
            ],
            [],
            "agent",
        ),
        (
            [{"role": "user", "content": "Summarize each numbered block below"}],
            [{"name": "bash"}],
            "agent",
        ),
    ],
)
def test_call_kind_classification_is_structural(messages, tools, expected):
    assert TraceParser._detect_call_kind(messages, tools) == expected


def test_legacy_calls_with_reused_iteration_are_grouped_by_time(tmp_path):
    _, (requests, responses, _) = parse_lines(
        tmp_path,
        [
            trace_line(0, "invoke_request", {"messages": []}, event_id="", iteration=0),
            trace_line(0.5, "invoke_output", {"content": "one"}, event_id="", iteration=0),
            trace_line(10, "invoke_request", {"messages": []}, event_id="", iteration=0),
            trace_line(10.5, "invoke_output", {"content": "two"}, event_id="", iteration=0),
        ],
    )
    assert len(requests["session-main"]) == len(responses["session-main"]) == 2
    assert [item.content for item in responses["session-main"]] == ["one", "two"]


def test_parse_is_idempotent_and_resets_diagnostics(tmp_path):
    path = write_log(
        tmp_path / "trace.log",
        [trace_line(0, "invoke_request", "bad-json", event_id="bad")],
    )
    parser = TraceParser(LogLoader(str(path), load_rollover=False).load())
    first = parser.parse()
    first_diagnostics = dict(parser.diagnostics)
    second = parser.parse()

    assert second == first
    assert dict(parser.diagnostics) == first_diagnostics
