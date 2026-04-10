"""Agent History Analyzer - 主入口"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from .analyzer import EventAnalyzer
from .loader import JSONLoader
from .models import AnalysisResult
from .reporter import HTMLReporter

DEFAULT_SESSIONS_DIR = Path.home() / ".jiuwenclaw" / "agent" / "sessions"


class AgentHistoryAnalyzer:
    """Agent历史分析器 - 高层封装"""

    def __init__(self, json_file_path: str):
        self.file_path = json_file_path
        self.loader = JSONLoader(json_file_path)
        self.analyzer = EventAnalyzer()
        self.reporter = HTMLReporter(json_file_path)
        self.analysis_result: Optional[AnalysisResult] = None

    def run(self, output_path: str = "report.html", verbose: bool = False) -> bool:
        """执行分析并生成报告"""
        try:
            history_data = self.loader.load()
        except (FileNotFoundError, ValueError) as e:
            print(f"错误: {e}")
            return False

        self.analysis_result = self.analyzer.analyze(history_data)

        if verbose:
            self._print_summary()

        assert self.analysis_result is not None
        self.reporter.generate(self.analysis_result, output_path)
        return True

    def _print_summary(self):
        """打印摘要信息"""
        if self.analysis_result is None:
            return
        stats = self.analysis_result.statistics
        print("\n=== Agent History Analysis Summary ===")
        print(f"总对话轮数: {stats.total_requests}")
        print(f"用户消息数: {stats.user_messages}")
        print(f"助手回复数: {stats.assistant_messages}")
        print(f"工具调用数: {stats.tool_calls}")
        print(f"上下文压缩: {stats.context_compressed} 次")
        print(f"总耗时: {stats.total_time:.2f} 秒")
        print(f"平均耗时: {stats.avg_request_time:.2f} 秒")

        print("\n工具使用统计:")
        for tool_name, tool_stats in self.analysis_result.tool_usage.items():
            count = tool_stats["count"]
            total_time = tool_stats["total_time"]
            avg_time = total_time / count if count > 0 else 0
            print(f"  - {tool_name}: {count} 次 (平均: {avg_time:.2f}s, 总计: {total_time:.2f}s)")
        print("=" * 40)


def find_latest_history(sessions_dir: Path = DEFAULT_SESSIONS_DIR) -> Optional[Path]:
    """在sessions目录下查找最新的history.json文件"""
    if not sessions_dir.exists():
        return None

    history_files = list(sessions_dir.rglob("history.json"))
    if not history_files:
        return None

    return max(history_files, key=lambda p: p.stat().st_mtime)


def main():
    """CLI入口"""
    parser = argparse.ArgumentParser(
        description="分析Agent会话历史并生成可视化报告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python -m agent_history_analyzer                    # 分析最新的会话
  python -m agent_history_analyzer history.json
  python -m agent_history_analyzer history.json --output my_report.html
  python -m agent_history_analyzer history.json --verbose
        """,
    )

    parser.add_argument(
        "json_file",
        nargs="?",
        help="JSON历史文件路径 (默认: 分析最新的会话)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="report.html",
        help="输出报告文件路径 (默认: report.html)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="在终端显示摘要信息")

    args = parser.parse_args()

    if args.json_file:
        json_path = Path(args.json_file)
    else:
        json_path = find_latest_history()
        if json_path is None:
            print(f"错误: 在 {DEFAULT_SESSIONS_DIR} 下未找到任何 history.json 文件")
            sys.exit(1)
        print(f"使用最新会话: {json_path}")

    analyzer = AgentHistoryAnalyzer(str(json_path))
    success = analyzer.run(output_path=args.output, verbose=args.verbose)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
