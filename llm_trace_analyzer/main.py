"""CLI主入口"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from .analyzer import ChainAnalyzer
from .loader import LogLoader, find_latest_log
from .models import AnalysisResult
from .parser import TraceParser
from .reporter import HTMLReporter


class LLMTraceAnalyzer:
    def __init__(self, log_file_path: str):
        self.file_path = log_file_path

    def run(
        self,
        output_path: str = "llm_trace_report.html",
        verbose: bool = False,
        session_filter: Optional[str] = None,
    ) -> bool:
        try:
            loader = LogLoader(self.file_path)
            traces = loader.load()
        except FileNotFoundError as e:
            print(f"Error: {e}")
            return False

        if session_filter:
            traces = self._filter_traces_for_session(traces, session_filter, loader)

        if not traces:
            print("No LLM_IO_TRACE entries found in log file.")
            return False

        parser = TraceParser(traces)
        requests, responses = parser.parse()

        tool_call_events = loader.load_tool_call_events()
        subagent_start_events = loader.load_subagent_start_events()

        analyzer = ChainAnalyzer(requests, responses, tool_call_events, subagent_start_events)
        result = analyzer.analyze()

        if session_filter:
            result = self._filter_result_for_session(result, session_filter)

        if verbose:
            self._print_summary(result)

        reporter = HTMLReporter(self.file_path)
        reporter.generate(result, output_path)
        print(f"Report generated: {output_path}")

        return True

    def _filter_traces_for_session(
        self, traces: list, session_filter: str, loader: LogLoader
    ) -> list:
        parent_traces = [t for t in traces if t["session_id"] == session_filter]

        tool_call_events = loader.load_tool_call_events()
        subagent_start_events = loader.load_subagent_start_events()

        subagent_session_ids = set()

        # 处理 spawn_subagent
        for event in tool_call_events:
            if (
                event.get("session_id") == session_filter
                and event.get("tool_name") == "spawn_subagent"
            ):
                spawn_time = event.get("timestamp", 0)
                for start_event in subagent_start_events:
                    start_time = start_event.get("timestamp", 0)
                    if abs(start_time - spawn_time) < 5.0:
                        task_id = start_event.get("task_id")
                        if task_id:
                            subagent_session_ids.add(f"subagent_{task_id}")

        # 处理 fork_agent
        for event in tool_call_events:
            if (
                event.get("session_id") == session_filter
                and event.get("tool_name") == "fork_agent"
            ):
                fork_time = event.get("timestamp", 0)
                # 在 traces 中找 fork_fork_agent session 的第一个请求时间
                for t in traces:
                    if t["session_id"].startswith("fork_fork_agent_"):
                        # 假设第一个 trace 的 timestamp 就是启动时间
                        if abs(t["timestamp"] - fork_time) < 5.0:
                            subagent_session_ids.add(t["session_id"])

        subagent_traces = [t for t in traces if t["session_id"] in subagent_session_ids]

        return parent_traces + subagent_traces

    def _filter_result_for_session(
        self, result: AnalysisResult, session_filter: str
    ) -> AnalysisResult:
        from .models import AnalysisResult

        filtered = AnalysisResult()
        if session_filter in result.sessions:
            filtered.sessions[session_filter] = result.sessions[session_filter]
        filtered.sorted_sessions = list(filtered.sessions.values())
        filtered.statistics = result.statistics
        return filtered

    def _print_summary(self, result: AnalysisResult) -> None:
        stats = result.statistics
        print("\n=== LLM Trace Analysis Summary ===")
        print(f"Total sessions: {stats.total_sessions}")
        print(f"Total requests: {stats.total_requests}")
        print(f"Total responses: {stats.total_responses}")
        print(f"Total iterations: {stats.total_iterations}")

        if stats.sessions_by_model:
            print("\nSessions by model:")
            for model, count in stats.sessions_by_model.items():
                print(f"  - {model}: {count} sessions")

        print("=" * 40)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze LLM_IO_TRACE logs and generate visualization report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  lt                              # Analyze latest app.log
  lt <log_file>                   # Analyze specific log file
  lt <log_file> -o my_report      # Specify output directory
  lt --session <session_id>       # Filter by session
  lt -v                           # Show verbose summary
        """,
    )

    parser.add_argument(
        "log_file",
        nargs="?",
        help="Log file path (default: find latest app.log)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="llm_trace_report",
        help="Output report directory name (default: llm_trace_report)",
    )
    parser.add_argument(
        "--session",
        "-s",
        help="Filter by session_id",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show verbose summary in terminal",
    )

    args = parser.parse_args()

    log_path: Path
    if args.log_file:
        log_path = Path(args.log_file)
    else:
        found_path = find_latest_log()
        if found_path is None:
            default_path = Path.home() / ".office-claw" / ".jiuwenclaw" / ".logs" / "app.log"
            print(f"Error: No log file found. Default path: {default_path}")
            sys.exit(1)
        log_path = found_path
        print(f"Using log file: {log_path}")

    analyzer = LLMTraceAnalyzer(str(log_path))
    success = analyzer.run(
        output_path=args.output,
        verbose=args.verbose,
        session_filter=args.session,
    )

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
