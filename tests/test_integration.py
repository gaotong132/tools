"""Slow contracts against a captured real trace.

These tests intentionally assert only stable, user-visible facts.  Detailed
edge cases belong to the synthetic unit tests.
"""

import pytest

from llm_trace_analyzer.reporter import HTMLReporter
from tests.conftest import SAMPLE_SESSION_ID, SAMPLE_SHORT_ID

pytestmark = pytest.mark.contract


def test_captured_log_pipeline_has_expected_exact_shape(captured_session):
    assert len(captured_session.traces) == 836
    assert sum(map(len, captured_session.requests.values())) == 37
    assert sum(map(len, captured_session.responses.values())) == 37

    result = captured_session.result
    assert list(result.sessions) == [SAMPLE_SESSION_ID]
    chain = result.sessions[SAMPLE_SESSION_ID]
    assert chain.model_name == "glm-5"
    assert len(chain.requests) == len(chain.responses) == chain.total_iterations == 37
    assert result.statistics.completed_calls == 37
    assert result.statistics.incomplete_calls == result.statistics.invalid_calls == 0


def test_captured_nested_sessions_are_unique(captured_session):
    chain = captured_session.result.sessions[SAMPLE_SESSION_ID]
    request_keys = [(item.session_id, item.event_id or item.iteration) for item in chain.requests]
    response_keys = [(item.session_id, item.event_id or item.iteration) for item in chain.responses]
    assert len(request_keys) == len(set(request_keys)) == 37
    assert len(response_keys) == len(set(response_keys)) == 37
    assert len(chain.subagents) == 6
    assert max(item.depth for item in chain.subagents) == 1


def test_captured_report_preserves_navigation_and_full_payload(captured_session, tmp_path):
    output = tmp_path / "report"
    HTMLReporter("captured.log").generate(captured_session.result, str(output))

    detail = output / f"session_{SAMPLE_SHORT_ID}.html"
    content = detail.read_text(encoding="utf-8")
    assert content.count('class="iteration-block') == 37
    assert 'data-global-iteration="0"' not in content
    assert 'data-global-iteration="37"' in content
    assert "Copy Body" in content
    assert "Timing (37 iterations)" in content
