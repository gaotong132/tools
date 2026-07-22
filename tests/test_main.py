"""Application-service and CLI boundary tests."""

import pytest

from llm_trace_analyzer.main import LLMTraceAnalyzer, main
from tests.trace_factory import telemetry_end, telemetry_start, trace_line, write_log


@pytest.fixture
def multi_session_log(tmp_path):
    parent = "target"
    child = "target_subagent_child"
    lines = [
        trace_line(
            0,
            "invoke_request",
            {"messages": [{"role": "user", "content": "target prompt"}]},
            session_id=parent,
            event_id="target-call",
        ),
        trace_line(
            1,
            "invoke_output",
            {"content": "target result", "tool_calls": [{"id": "target-tool", "name": "bash"}]},
            session_id=parent,
            event_id="target-call",
        ),
        telemetry_start(1, "bash", "target-tool"),
        telemetry_end(1.2, "bash", 0.2),
        trace_line(0.2, "invoke_request", {"messages": []}, session_id=child, event_id="child"),
        trace_line(0.8, "invoke_output", {"content": "child"}, session_id=child, event_id="child"),
        trace_line(2, "invoke_request", {"messages": []}, session_id="other", event_id="other"),
        trace_line(3, "invoke_output", {"content": "other"}, session_id="other", event_id="other"),
    ]
    return write_log(tmp_path / "full.log", lines)


def test_run_builds_report_and_prints_exact_summary(multi_session_log, tmp_path, capsys):
    output = tmp_path / "report"

    success = LLMTraceAnalyzer(str(multi_session_log)).run(str(output), verbose=True)

    assert success
    assert (output / "index.html").exists()
    assert len(list(output.glob("session_*.html"))) == 2
    stdout = capsys.readouterr().out
    assert "Total sessions: 2" in stdout
    assert "Total iterations: 3" in stdout


def test_run_session_filter_includes_descendants_and_relevant_tool_only(
    multi_session_log, tmp_path
):
    output = tmp_path / "filtered"

    success = LLMTraceAnalyzer(str(multi_session_log)).run(str(output), session_filter="target")

    assert success
    index = (output / "index.html").read_text(encoding="utf-8")
    detail = next(output.glob("session_*.html")).read_text(encoding="utf-8")
    assert "target prompt" in index
    assert "other" not in index
    assert "child" in detail
    assert "200ms" in detail


@pytest.mark.parametrize("kind", ["missing", "empty"])
def test_run_returns_false_for_unusable_input(tmp_path, capsys, kind):
    path = tmp_path / "input.log"
    if kind == "empty":
        path.touch()

    success = LLMTraceAnalyzer(str(path)).run(str(tmp_path / "report"))

    assert not success
    expected = "No LLM_IO_TRACE" if kind == "empty" else "日志文件不存在"
    assert expected in capsys.readouterr().out


def test_cli_accepts_explicit_arguments_without_mutating_sys_argv(multi_session_log, tmp_path):
    output = tmp_path / "cli-report"
    exit_code = main([str(multi_session_log), "-o", str(output), "--session", "target", "-v"])
    assert exit_code == 0
    assert (output / "index.html").exists()


def test_cli_uses_default_output_beside_log(multi_session_log):
    exit_code = main([str(multi_session_log)])
    assert exit_code == 0
    assert (multi_session_log.parent / "llm_trace_report" / "index.html").exists()


def test_cli_returns_nonzero_when_default_log_cannot_be_found(monkeypatch, capsys):
    monkeypatch.setattr("llm_trace_analyzer.main.find_latest_log", lambda: None)
    assert main([]) == 1
    assert "No log file found" in capsys.readouterr().out


def test_cli_open_launches_generated_index(monkeypatch, multi_session_log, tmp_path):
    opened = []
    monkeypatch.setattr("llm_trace_analyzer.main.webbrowser.open", opened.append)
    output = tmp_path / "open-report"

    assert main([str(multi_session_log), "-o", str(output), "--open"]) == 0
    assert opened == [str(output / "index.html")]


def test_filter_helpers_require_exact_parent_prefix():
    analyzer = LLMTraceAnalyzer("unused.log")
    traces = [
        {"session_id": "root"},
        {"session_id": "root_subagent_a"},
        {"session_id": "root_subagent_a_fork_agent_b"},
        {"session_id": "root-other"},
        {"session_id": "other"},
    ]
    assert [item["session_id"] for item in analyzer._filter_traces_for_session(traces, "root")] == [
        "root",
        "root_subagent_a",
        "root_subagent_a_fork_agent_b",
    ]
