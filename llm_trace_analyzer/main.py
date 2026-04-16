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
            traces = [t for t in traces if t["session_id"] == session_filter]

        if not traces:
            print("No LLM_IO_TRACE entries found in log file.")
            return False

        parser = TraceParser(traces)
        requests, responses = parser.parse()

        analyzer = ChainAnalyzer(requests, responses)
        result = analyzer.analyze()

        if verbose:
            self._print_summary(result)

        reporter = HTMLReporter(self.file_path)
        reporter.generate(result, output_path)
        print(f"Report generated: {output_path}")

        return True

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
