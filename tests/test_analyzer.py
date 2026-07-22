"""Behavioral tests for chain assembly and statistics."""

import pytest

from llm_trace_analyzer.analyzer import ChainAnalyzer
from llm_trace_analyzer.models import CallStatus
from tests.trace_factory import execution, request, response


def analyze(requests, responses, *, executions=None):
    return ChainAnalyzer(requests, responses, tool_executions=executions).analyze()


def test_nested_agents_are_merged_once_with_direct_parent_metadata():
    root = "root"
    child = "root_subagent_child"
    fork = "root_subagent_child_fork_agent_fork"
    requests = {
        root: [request("root-call", 1, session_id=root)],
        child: [request("child-call", 2, session_id=child)],
        fork: [request("fork-call", 3, session_id=fork)],
    }
    responses = {
        root: [response("root-call", 4, session_id=root)],
        child: [response("child-call", 5, session_id=child)],
        fork: [response("fork-call", 6, session_id=fork)],
    }

    result = analyze(requests, responses)
    chain = result.sessions[root]

    assert list(result.sessions) == [root]
    assert [(item.session_id, item.event_id) for item in chain.requests] == [
        (root, "root-call"),
        (child, "child-call"),
        (fork, "fork-call"),
    ]
    assert [(item.session_id, item.parent_session_id, item.depth) for item in chain.subagents] == [
        (child, root, 0),
        (fork, child, 1),
    ]
    assert chain.subagents[1].chain_path == ["Main", "Sub[child]", "Fork[fork]"]


def test_parallel_event_ids_produce_independent_durations():
    requests = {
        "root": [
            request("slow", 0, session_id="root", iteration=0),
            request("fast", 0.2, session_id="root", iteration=0),
        ]
    }
    responses = {
        "root": [
            response("fast", 1, session_id="root", iteration=0),
            response("slow", 5, session_id="root", iteration=0),
        ]
    }

    timings = analyze(requests, responses).sessions["root"].iteration_timings

    assert {item.event_id: item.llm_call_duration for item in timings} == pytest.approx(
        {"slow": 5, "fast": 0.8}
    )
    assert all(item.status is CallStatus.COMPLETE for item in timings)


def test_call_completeness_statuses_are_explicit_and_statistics_use_completed_calls():
    requests = {
        "root": [
            request("complete", 1, session_id="root", iteration=1),
            request("request-only", 2, session_id="root", iteration=2),
            request("invalid", 8, session_id="root", iteration=3),
        ]
    }
    responses = {
        "root": [
            response("complete", 3, session_id="root", iteration=1),
            response("response-only", 4, session_id="root", iteration=4),
            response("invalid", 7, session_id="root", iteration=3),
        ]
    }

    result = analyze(requests, responses)
    statuses = {
        timing.event_id: timing.status for timing in result.sessions["root"].iteration_timings
    }

    assert statuses == {
        "complete": CallStatus.COMPLETE,
        "request-only": CallStatus.REQUEST_ONLY,
        "response-only": CallStatus.RESPONSE_ONLY,
        "invalid": CallStatus.INVALID,
    }
    assert result.statistics.completed_calls == 1
    assert result.statistics.incomplete_calls == 2
    assert result.statistics.invalid_calls == 1
    assert result.statistics.avg_llm_time_seconds == pytest.approx(2)


def test_tool_duration_uses_telemetry_and_excludes_delegation_from_total():
    tool_calls = [
        {"id": "bash-call", "name": "bash"},
        {"id": "spawn-call", "name": "spawn_subagent"},
        {"id": "unmeasured", "name": "python"},
    ]
    result = analyze(
        {"root": [request("call", 1, session_id="root")]},
        {"root": [response("call", 2, session_id="root", tool_calls=tool_calls)]},
        executions=[
            execution("bash-call", 0.4, tool_name="bash"),
            execution("spawn-call", 10, tool_name="spawn_subagent"),
        ],
    )
    timing = result.sessions["root"].iteration_timings[0]

    assert [item.tool_call_id for item in timing.tool_executions] == ["bash-call", "spawn-call"]
    assert timing.tool_processing_duration == pytest.approx(0.4)
    assert result.statistics.total_tool_time_seconds == pytest.approx(0.4)
    assert result.statistics.tool_call_counts == {"bash": 1, "spawn_subagent": 1, "python": 1}


def test_chain_bounds_include_measured_tool_completion():
    result = analyze(
        {"root": [request("call", 10, session_id="root")]},
        {
            "root": [
                response(
                    "call",
                    12,
                    session_id="root",
                    tool_calls=[{"id": "tool", "name": "bash"}],
                )
            ]
        },
        executions=[execution("tool", 3, start_time=12)],
    )
    chain = result.sessions["root"]
    assert (chain.start_time, chain.end_time) == (10, 15)
    assert result.statistics.total_duration_seconds == 5


def test_last_iteration_is_marked_per_session_in_interleaved_chain():
    child = "root_subagent_child"
    result = analyze(
        {
            "root": [
                request("root-1", 1, session_id="root"),
                request("root-2", 5, session_id="root"),
            ],
            child: [
                request("child-1", 2, session_id=child),
                request("child-2", 3, session_id=child),
            ],
        },
        {
            "root": [
                response("root-1", 1.5, session_id="root"),
                response("root-2", 6, session_id="root"),
            ],
            child: [
                response("child-1", 2.5, session_id=child),
                response("child-2", 4, session_id=child),
            ],
        },
    )
    timings = result.sessions["root"].iteration_timings
    assert [item.event_id for item in timings if item.is_last_iteration] == ["child-2", "root-2"]


def test_standalone_legacy_subagent_has_complete_timing_statistics():
    session = "subagent_legacy"
    result = analyze(
        {session: [request("call", 1, session_id=session)]},
        {session: [response("call", 3, session_id=session)]},
    )
    chain = result.sessions[session]
    assert chain.is_subagent
    assert chain.total_iterations == 1
    assert chain.total_llm_duration_seconds == 2
    assert result.statistics.total_sessions == 0


def test_analyze_is_idempotent_without_duplicate_relations():
    child = "root_subagent_child"
    analyzer = ChainAnalyzer(
        {
            "root": [request("root", 1, session_id="root")],
            child: [request("child", 2, session_id=child)],
        },
        {
            "root": [response("root", 3, session_id="root")],
            child: [response("child", 4, session_id=child)],
        },
    )

    first = analyzer.analyze().sessions["root"]
    second = analyzer.analyze().sessions["root"]

    assert [item.task_id for item in first.subagents] == [child]
    assert [item.task_id for item in second.subagents] == [child]
    assert len(second.requests) == 2


def test_token_and_tool_failure_statistics_are_aggregated_once():
    tool_result = {
        "role": "tool",
        "tool_call_id": "failed",
        "content": "bash operation execution error, execution: run, reason: failed",
    }
    result = analyze(
        {
            "root": [
                request(
                    "second",
                    3,
                    session_id="root",
                    messages=[tool_result],
                )
            ]
        },
        {
            "root": [
                response(
                    "second",
                    4,
                    session_id="root",
                    tool_calls=[{"id": "failed", "name": "bash"}],
                    input_tokens=10,
                    output_tokens=5,
                )
            ]
        },
    )
    stats = result.statistics
    assert (stats.total_input_tokens, stats.total_output_tokens, stats.total_tokens) == (10, 5, 15)
    assert stats.failed_tool_calls == 1
    assert stats.tool_failure_counts == {"bash": 1}
