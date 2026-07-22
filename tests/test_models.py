"""Contracts for request/response pairing and global numbering."""

from llm_trace_analyzer.models import build_global_num_map, pair_requests_responses
from tests.trace_factory import request, response


def test_pairing_uses_event_id_when_iterations_are_reused():
    requests = [request("slow", 1, iteration=0), request("fast", 2, iteration=0)]
    responses = [response("fast", 3, iteration=0), response("slow", 5, iteration=0)]

    pairs = pair_requests_responses(requests, responses)

    assert [(pair["request"].event_id, pair["response"].event_id) for pair in pairs] == [
        ("slow", "slow"),
        ("fast", "fast"),
    ]


def test_legacy_pairing_is_scoped_to_session():
    requests = [
        request("", 1, session_id="a", iteration=1),
        request("", 2, session_id="b", iteration=1),
    ]
    responses = [
        response("", 3, session_id="b", iteration=1),
        response("", 4, session_id="a", iteration=1),
    ]

    pairs = pair_requests_responses(requests, responses)

    assert [(pair["request"].session_id, pair["response"].session_id) for pair in pairs] == [
        ("a", "a"),
        ("b", "b"),
    ]


def test_unpaired_calls_are_preserved_and_numbered_in_time_order():
    pairs = pair_requests_responses(
        [request("request-only", 2)],
        [response("response-only", 1)],
    )

    assert [pair["timestamp"] for pair in pairs] == [1, 2]
    assert build_global_num_map(pairs) == {
        ("session-main", "response-only"): 1,
        ("session-main", "request-only"): 2,
    }
