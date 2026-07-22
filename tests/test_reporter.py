"""HTML report contracts, including timeline navigation and data retention."""

import html
import json

import pytest

from llm_trace_analyzer.analyzer import ChainAnalyzer
from llm_trace_analyzer.models import AnalysisResult, CallStatus
from llm_trace_analyzer.reporter import HTMLReporter
from tests.trace_factory import execution, request, response


@pytest.fixture
def report_result():
    child = "session-main_subagent_child"
    payload = "payload-that-must-remain-in-report"
    requests = {
        "session-main": [
            request(
                "main-call",
                10,
                session_id="session-main",
                messages=[
                    {"role": "system", "content": "system <unsafe>"},
                    {"role": "user", "content": payload},
                ],
                tools=[{"name": "bash<script>", "description": "full tool schema"}],
            ),
            request("request-only", 20, session_id="session-main", iteration=2),
        ],
        child: [request("child-call", 12, session_id=child)],
    }
    responses = {
        "session-main": [
            response(
                "main-call",
                11,
                session_id="session-main",
                content="answer </script><script>alert(1)</script>",
                tool_calls=[{"id": "tool-call", "name": "bash<script>"}],
                input_tokens=10,
                output_tokens=2,
            )
        ],
        child: [response("child-call", 13, session_id=child)],
    }
    result = ChainAnalyzer(
        requests,
        responses,
        tool_executions=[execution("tool-call", 0.25, tool_name="bash<script>", start_time=11)],
    ).analyze()
    result.diagnostics.update({"unmatched_tool_ends": 2, "request_json_errors": 1})
    return result


@pytest.fixture
def rendered_report(tmp_path, report_result):
    output = tmp_path / "report"
    reporter = HTMLReporter("synthetic.log")
    reporter.generate(report_result, str(output))
    return output


def session_page(report_dir):
    pages = list(report_dir.glob("session_*.html"))
    assert len(pages) == 1
    return pages[0]


def test_generate_writes_index_and_mapped_session_detail(rendered_report):
    assert sorted(path.name for path in rendered_report.iterdir()) == [
        "index.html",
        "session_session-main.html",
    ]


def test_index_exposes_quality_diagnostics_and_escaped_metadata(rendered_report):
    content = (rendered_report / "index.html").read_text(encoding="utf-8")
    assert "Data Quality Diagnostics" in content
    assert "unmatched tool ends" in content.lower()
    assert "request json errors" in content.lower()
    assert "payload-that-must-remain-in-report" in content
    assert "<script>alert(1)</script>" not in content


def test_session_page_retains_full_request_data_without_report_slimming(rendered_report):
    content = session_page(rendered_report).read_text(encoding="utf-8")
    assert "payload-that-must-remain-in-report" in content
    assert "full tool schema" in content
    assert "Copy Body" in content
    assert html.escape("system <unsafe>") in content


def test_timeline_blocks_have_valid_click_targets_and_no_zero_anchor(rendered_report):
    content = session_page(rendered_report).read_text(encoding="utf-8")
    assert 'data-global-iteration="0"' not in content
    assert "jumpToIteration(1)" in content
    assert 'data-global-iteration="1"' in content
    assert "jumpToIteration(2)" in content
    assert 'data-global-iteration="2"' in content
    assert "jumpToIteration(3)" in content
    assert 'data-global-iteration="3"' in content


def test_incomplete_call_and_measured_tool_are_visible(rendered_report):
    content = session_page(rendered_report).read_text(encoding="utf-8")
    assert CallStatus.REQUEST_ONLY.value in content
    assert "Incomplete/Invalid" in content
    assert "Measured" in content
    assert "250ms" in content


def test_embedded_json_escapes_script_terminators(rendered_report):
    detail = session_page(rendered_report).read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in detail
    assert json.dumps("answer </script><script>alert(1)</script>") not in detail


def test_colliding_short_session_ids_get_distinct_files(tmp_path):
    requests = {
        "first_same": [request("a", 1, session_id="first_same")],
        "second_same": [request("b", 2, session_id="second_same")],
    }
    responses = {
        "first_same": [response("a", 1.5, session_id="first_same")],
        "second_same": [response("b", 2.5, session_id="second_same")],
    }
    result = ChainAnalyzer(requests, responses).analyze()
    output = tmp_path / "report"

    HTMLReporter("synthetic.log").generate(result, str(output))

    details = sorted(output.glob("session_same*.html"))
    assert len(details) == 2
    index = (output / "index.html").read_text(encoding="utf-8")
    assert all(path.name in index for path in details)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "N/A"), (0.25, "250ms"), (15.5, "15.5s"), (120, "2m 0s"), (3723, "1h 2m")],
)
def test_duration_formatting(seconds, expected):
    assert HTMLReporter("synthetic.log")._format_duration(seconds) == expected


def test_percentile_interpolates_and_handles_empty_input():
    assert HTMLReporter._percentile([], 95) == 0
    assert HTMLReporter._percentile([1, 2, 3, 4], 50) == pytest.approx(2.5)


def test_new_tool_results_are_detected_by_call_id():
    reporter = HTMLReporter("synthetic.log")
    previous = [{"role": "tool", "tool_call_id": "old", "content": "old"}]
    current = previous + [{"role": "tool", "tool_call_id": "new", "content": "new"}]
    assert reporter._find_new_messages(current, previous) == [current[1]]


def test_openai_tool_conversion_preserves_complete_schema():
    body = {
        "messages": [{"role": "user", "content": "hello"}],
        "tools": [
            {
                "type": "function",
                "name": "bash",
                "description": "run",
                "parameters": {"type": "object"},
            }
        ],
    }
    converted = HTMLReporter("synthetic.log")._convert_tools_to_openai_format(body)
    assert converted["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": "run",
                "parameters": {"type": "object"},
            },
        }
    ]


def test_empty_analysis_still_generates_usable_index(tmp_path):
    output = tmp_path / "empty-report"
    HTMLReporter("synthetic.log").generate(AnalysisResult(), str(output))
    content = (output / "index.html").read_text(encoding="utf-8")
    assert "LLM Trace Index" in content
    assert "No sessions found" in content
