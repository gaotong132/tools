#!/usr/bin/env python3
"""
Agent History Analyzer - 分析Agent会话历史并生成可视化报告

功能：
- 解析JSON格式的Agent会话历史文件
- 分析对话流程、工具调用、上下文压缩等事件
- 计算各阶段耗时
- 生成HTML可视化报告（包含Chart.js时间线图表）
"""

import json
import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict


class AgentHistoryAnalyzer:
    def __init__(self, json_file_path: str):
        self.json_file_path = Path(json_file_path)
        self.history_data = []
        self.analysis_result = {}

    def load_json(self) -> bool:
        try:
            with open(self.json_file_path, "r", encoding="utf-8") as f:
                self.history_data = json.load(f)
            return True
        except FileNotFoundError:
            print(f"错误: 文件不存在 - {self.json_file_path}")
            return False
        except json.JSONDecodeError as e:
            print(f"错误: JSON格式错误 - {e}")
            return False

    def analyze(self) -> Dict[str, Any]:
        if not self.history_data:
            return {}

        result = {
            "total_events": len(self.history_data),
            "requests": {},
            "statistics": {
                "total_requests": 0,
                "user_messages": 0,
                "assistant_messages": 0,
                "tool_calls": 0,
                "context_compressed": 0,
                "total_time": 0,
                "avg_request_time": 0,
            },
            "tool_usage": defaultdict(lambda: {"count": 0, "total_time": 0.0}),
            "compression_events": [],
            "timeline": [],
        }

        current_request_id = None
        current_request_data = {}

        for event in self.history_data:
            request_id = event.get("request_id")
            event_type = event.get("event_type", "none")
            timestamp = event.get("timestamp")
            role = event.get("role")

            if request_id != current_request_id:
                if current_request_id and current_request_data:
                    self._finalize_request(current_request_data, result)
                current_request_id = request_id
                current_request_data = {
                    "request_id": request_id,
                    "start_time": timestamp,
                    "end_time": timestamp,
                    "events": [],
                    "user_input": "",
                    "assistant_response": "",
                    "execution_flow": [],  # 按时间顺序记录推理和工具调用
                    "tool_calls": [],
                    "tool_results": [],
                    "compression": None,
                    "duration": 0,
                }

            current_request_data["end_time"] = timestamp
            current_request_data["events"].append(event)

            self._process_event(event, current_request_data, result)

        if current_request_data:
            self._finalize_request(current_request_data, result)

        self._calculate_statistics(result)

        return result

    def _process_event(self, event: Dict, request_data: Dict, result: Dict):
        event_type = event.get("event_type", "none")
        timestamp = event.get("timestamp")
        content = event.get("content", "")

        if event["role"] == "user":
            request_data["user_input"] = content
            result["statistics"]["user_messages"] += 1

        elif event_type == "context.compressed":
            payload = event.get("event_payload", {})
            request_data["compression"] = {
                "timestamp": timestamp,
                "before": payload.get("before_compressed", 0),
                "after": payload.get("after_compressed", 0),
                "rate": payload.get("rate", 0),
            }
            result["compression_events"].append(
                {
                    "request_id": request_data["request_id"],
                    "timestamp": timestamp,
                    "before": payload.get("before_compressed", 0),
                    "after": payload.get("after_compressed", 0),
                    "rate": payload.get("rate", 0),
                }
            )
            result["statistics"]["context_compressed"] += 1

        elif event_type == "chat.delta":
            payload = event.get("event_payload", {})
            source_type = payload.get("source_chunk_type", "")
            if source_type == "llm_reasoning":
                # 检查是否需要创建新的推理片段或追加到现有片段
                if (
                    request_data["execution_flow"]
                    and request_data["execution_flow"][-1]["type"] == "reasoning"
                ):
                    # 追加到最后一个推理片段
                    request_data["execution_flow"][-1]["content"] += content
                else:
                    # 创建新的推理片段
                    request_data["execution_flow"].append(
                        {
                            "type": "reasoning",
                            "content": content,
                            "timestamp": timestamp,
                        }
                    )

        elif event_type == "chat.final":
            payload = event.get("event_payload", {})
            source_type = payload.get("source_chunk_type", "")
            if source_type == "answer":
                request_data["assistant_response"] = content
                result["statistics"]["assistant_messages"] += 1

        elif event_type == "chat.tool_call":
            payload = event.get("event_payload", {})
            tool_call = payload.get("tool_call", {})
            tool_call_data = {
                "name": tool_call.get("name"),
                "arguments": tool_call.get("arguments"),
                "tool_call_id": tool_call.get("tool_call_id"),
                "timestamp": timestamp,
                "start_time": timestamp,
                "duration": 0,
            }
            request_data["tool_calls"].append(tool_call_data)

            # 添加到执行流程
            request_data["execution_flow"].append(
                {
                    "type": "tool_call",
                    "tool_call_id": tool_call.get("tool_call_id"),
                    "name": tool_call.get("name"),
                    "arguments": tool_call.get("arguments"),
                    "timestamp": timestamp,
                    "duration": 0,
                }
            )

            result["statistics"]["tool_calls"] += 1
            tool_name = tool_call.get("name")
            if tool_name:
                result["tool_usage"][tool_name]["count"] += 1

        elif event_type == "chat.tool_result":
            payload = event.get("event_payload", {})
            tool_call_id = payload.get("tool_call_id")
            tool_name = payload.get("tool_name")
            result_content = payload.get("result")

            # 找到对应的tool_call并计算耗时
            duration = 0
            for tool_call in request_data["tool_calls"]:
                if tool_call["tool_call_id"] == tool_call_id:
                    duration = timestamp - tool_call["start_time"]
                    tool_call["duration"] = duration

                    # 更新tool_usage的耗时统计
                    if tool_name and tool_name in result["tool_usage"]:
                        result["tool_usage"][tool_name]["total_time"] += duration
                    break

            # 更新execution_flow中的工具调用
            for flow_item in request_data["execution_flow"]:
                if flow_item["type"] == "tool_call" and flow_item["tool_call_id"] == tool_call_id:
                    flow_item["duration"] = duration
                    flow_item["result"] = result_content
                    break

            request_data["tool_results"].append(
                {
                    "tool_name": payload.get("tool_name"),
                    "tool_call_id": payload.get("tool_call_id"),
                    "result": result_content,
                    "timestamp": timestamp,
                }
            )

    def _finalize_request(self, request_data: Dict, result: Dict):
        request_data["duration"] = request_data["end_time"] - request_data["start_time"]
        result["requests"][request_data["request_id"]] = request_data
        result["timeline"].append(request_data)
        result["statistics"]["total_requests"] += 1

    def _calculate_statistics(self, result: Dict):
        if result["statistics"]["total_requests"] > 0:
            total_time = sum(r["duration"] for r in result["timeline"])
            result["statistics"]["total_time"] = total_time
            result["statistics"]["avg_request_time"] = (
                total_time / result["statistics"]["total_requests"]
            )

    def generate_html_report(self, output_path: str = "report.html"):
        if not self.analysis_result:
            print("错误: 没有分析数据")
            return

        html_content = self._build_html()

        output_file = Path(output_path)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"报告已生成: {output_file.absolute()}")

    def _build_html(self) -> str:
        stats = self.analysis_result["statistics"]
        tool_usage = self.analysis_result["tool_usage"]
        timeline = self.analysis_result["timeline"]

        html = self._get_html_start()
        html += self._get_css_section()
        html += self._get_html_body_start()
        html += self._get_header_section()
        html += self._get_stats_section(stats)
        html += self._get_timeline_section(timeline)
        html += self._get_tool_table_section(tool_usage)
        html += self._get_metadata_section(self.analysis_result)
        html += self._get_html_body_end()
        html += self._get_js_section()
        html += self._get_html_end()

        return html

    def _get_html_start(self) -> str:
        return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent History Analysis Report</title>"""

    def _get_css_section(self) -> str:
        return """
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #f5f7fa;
            color: #333;
            line-height: 1.6;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 20px;
            text-align: center;
            border-radius: 10px;
            margin-bottom: 30px;
        }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .header p { font-size: 1.1em; opacity: 0.9; }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }
        .stat-card:hover { transform: translateY(-5px); }
        .stat-value {
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 10px;
        }
        .stat-label { font-size: 1em; color: #666; }
        
        .section {
            background: white;
            border-radius: 10px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .section-title {
            font-size: 1.8em;
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
        }
        
        .timeline-item {
            border-left: 4px solid #667eea;
            padding-left: 20px;
            margin-bottom: 30px;
            position: relative;
        }
        .timeline-item::before {
            content: '';
            position: absolute;
            left: -8px;
            top: 0;
            width: 16px;
            height: 16px;
            background: #667eea;
            border-radius: 50%;
        }
        
        .request-header {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .request-header:hover { background: #e9ecef; }
        .request-id { font-weight: bold; color: #667eea; }
        .request-duration { color: #666; }
        
        .request-details {
            display: none;
            padding: 15px;
            background: #fafafa;
            border-radius: 8px;
            margin-top: 10px;
        }
        .request-details.active { display: block; }
        
        .message-box {
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 15px;
            margin: 10px 0;
        }
        .user-message { border-left: 4px solid #2196F3; }
        .assistant-message { border-left: 4px solid #4CAF50; }
        .tool-call { border-left: 4px solid #FF9800; }
        .compression { border-left: 4px solid #F44336; }
        
        .message-label {
            font-weight: bold;
            color: #666;
            margin-bottom: 10px;
        }
        .message-content { color: #333; }
        
        .tool-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        .tool-table th, .tool-table td {
            border: 1px solid #e0e0e0;
            padding: 12px;
            text-align: left;
        }
        .tool-table th { background: #667eea; color: white; }
        .tool-table tr:hover { background: #f5f5f5; }
        
        .collapsible-header {
            background: #f0f0f0;
            padding: 10px;
            cursor: pointer;
            border-radius: 5px;
            margin: 10px 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .collapsible-header:hover { background: #e0e0e0; }
        .collapsible-content {
            display: none;
            padding: 15px;
            background: #fafafa;
            border-radius: 5px;
            max-height: 500px;
            overflow-y: auto;
        }
        .collapsible-content.active { display: block; }
        
        .arrow { transition: transform 0.3s; }
        .arrow.rotated { transform: rotate(180deg); }
        
        .badge {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
        }
        .badge-blue { background: #e3f2fd; color: #1976d2; }
        .badge-green { background: #e8f5e9; color: #388e3c; }
        .badge-orange { background: #fff3e0; color: #f57c00; }
        .badge-red { background: #ffebee; color: #d32f2f; }
        
        .metadata {
            font-size: 0.9em;
            color: #999;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
        }
    </style>
</head>"""

    def _get_html_body_start(self) -> str:
        return """
<body>
    <div class="container">"""

    def _get_header_section(self) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"""
        <div class="header">
            <h1>Agent History Analysis Report</h1>
            <p>生成时间: {timestamp}</p>
        </div>"""

    def _get_stats_section(self, stats: Dict) -> str:
        return f"""
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{stats["total_requests"]}</div>
                <div class="stat-label">总对话轮数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats["user_messages"]}</div>
                <div class="stat-label">用户消息数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats["assistant_messages"]}</div>
                <div class="stat-label">助手回复数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats["tool_calls"]}</div>
                <div class="stat-label">工具调用数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats["context_compressed"]}</div>
                <div class="stat-label">上下文压缩次数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats["avg_request_time"]:.2f}s</div>
                <div class="stat-label">平均耗时</div>
            </div>
        </div>"""

    def _get_tool_table_section(self, tool_usage: Dict) -> str:
        rows = []
        for tool_name, stats in tool_usage.items():
            count = stats["count"]
            total_time = stats["total_time"]
            avg_time = total_time / count if count > 0 else 0
            rows.append(
                f"<tr><td><span class='badge badge-orange'>{tool_name}</span></td>"
                f"<td>{count}</td>"
                f"<td>{avg_time:.2f}s</td>"
                f"<td>{total_time:.2f}s</td></tr>"
            )

        return f"""
        <div class="section">
            <h2 class="section-title">工具调用详情</h2>
            <table class="tool-table">
                <thead>
                    <tr>
                        <th>工具名称</th>
                        <th>调用次数</th>
                        <th>平均耗时</th>
                        <th>总耗时</th>
                    </tr>
                </thead>
                <tbody>
                    {"\n".join(rows)}
                </tbody>
            </table>
        </div>"""

    def _get_timeline_section(self, timeline: List) -> str:
        items = []
        for i, request in enumerate(timeline, 1):
            timestamp_str = datetime.fromtimestamp(request["start_time"]).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            details = self._generate_request_details(request)

            items.append(f"""<div class="timeline-item">
                <div class="request-header" onclick="toggleRequest(this)">
                    <div>
                        <span class="request-id">#{i} - {request["request_id"]}</span>
                        <span class="badge badge-blue">{timestamp_str}</span>
                    </div>
                    <div>
                        <span class="request-duration">耗时: {request["duration"]:.2f}秒</span>
                        <span class="arrow">▼</span>
                    </div>
                </div>
                <div class="request-details">
                    {details}
                </div>
            </div>""")

        return f"""
        <div class="section">
            <h2 class="section-title">完整对话历史</h2>
            {"\n".join(items)}
        </div>"""

    def _generate_request_details(self, request: Dict) -> str:
        details = []

        if request["user_input"]:
            details.append(f"""<div class="message-box user-message">
                <div class="message-label"><span class="badge badge-blue">用户输入</span></div>
                <div class="message-content">{self._escape_html(request["user_input"])}</div>
            </div>""")

        # 按照execution_flow的顺序生成内容
        for flow_item in request.get("execution_flow", []):
            if flow_item["type"] == "reasoning":
                # 推理片段
                details.append(f"""<div class="message-box assistant-message">
                    <div class="message-label"><span class="badge badge-green">推理过程</span></div>
                    <div class="message-content">{self._escape_html(flow_item["content"])}</div>
                </div>""")
            elif flow_item["type"] == "tool_call":
                # 工具调用
                tool_name = flow_item.get("name", "unknown")
                arguments = flow_item.get("arguments", "{}")
                timestamp_str = datetime.fromtimestamp(flow_item["timestamp"]).strftime("%H:%M:%S")
                duration = flow_item.get("duration", 0)
                result_content = flow_item.get("result", "")

                duration_str = (
                    f"<span style='color: #999; font-size: 0.85em;'>(耗时: {duration:.2f}s)</span>"
                    if duration > 0
                    else ""
                )

                result_html = ""
                if result_content:
                    result_html = f"""<div class="collapsible-content">
                        <pre style="white-space: pre-wrap; word-wrap: break-word;">{self._escape_html(result_content)}</pre>
                    </div>"""

                details.append(f"""<div class="message-box tool-call">
                    <div class="message-label">
                        <span class="badge badge-orange">工具调用: {tool_name}</span>
                        <span style="font-size: 0.9em; color: #999;">{timestamp_str}</span>
                        {duration_str}
                    </div>
                    <div class="collapsible-header" onclick="toggleCollapsible(this)">
                        <div><strong>参数:</strong> {self._escape_html(arguments)}</div>
                        <span class="arrow">▼</span>
                    </div>
                    {result_html}
                </div>""")

        if request["assistant_response"]:
            details.append(f"""<div class="message-box assistant-message">
                <div class="message-label"><span class="badge badge-green">助手回复</span></div>
                <div class="message-content">{self._escape_html(request["assistant_response"])}</div>
            </div>""")

        if request["compression"]:
            details.append(f"""<div class="message-box compression">
                <div class="message-label"><span class="badge badge-red">上下文压缩</span></div>
                <div class="message-content">
                    压缩前: {request["compression"]["before"]} tokens → 
                    压缩后: {request["compression"]["after"]} tokens 
                    (压缩率: {request["compression"]["rate"] / 100:.1%})
                </div>
            </div>""")

        return "\n".join(details)

    def _get_metadata_section(self, result: Dict) -> str:
        stats = result["statistics"]
        return f"""
        <div class="metadata">
            <p>文件路径: {self.json_file_path}</p>
            <p>总事件数: {result["total_events"]}</p>
            <p>总耗时: {stats["total_time"]:.2f}秒</p>
        </div>"""

    def _get_html_body_end(self) -> str:
        return """
    </div>"""

    def _get_js_section(self) -> str:
        return """
    <script>
        function toggleCollapsible(header) {
            const content = header.nextElementSibling;
            const arrow = header.querySelector('.arrow');
            
            if (content.classList.contains('active')) {
                content.classList.remove('active');
                arrow.classList.remove('rotated');
            } else {
                content.classList.add('active');
                arrow.classList.add('rotated');
            }
        }
        
        function toggleRequest(header) {
            const details = header.nextElementSibling;
            if (details.classList.contains('active')) {
                details.classList.remove('active');
            } else {
                details.classList.add('active');
            }
        }
    </script>"""

    def _get_html_end(self) -> str:
        return """
</body>
</html>"""

    def _escape_html(self, text: str) -> str:
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def run(self, output_path: str = "report.html", verbose: bool = False):
        if not self.load_json():
            return False

        self.analysis_result = self.analyze()

        if verbose:
            self._print_summary()

        self.generate_html_report(output_path)
        return True

    def _print_summary(self):
        stats = self.analysis_result["statistics"]
        print("\n=== Agent History Analysis Summary ===")
        print(f"总对话轮数: {stats['total_requests']}")
        print(f"用户消息数: {stats['user_messages']}")
        print(f"助手回复数: {stats['assistant_messages']}")
        print(f"工具调用数: {stats['tool_calls']}")
        print(f"上下文压缩: {stats['context_compressed']} 次")
        print(f"总耗时: {stats['total_time']:.2f} 秒")
        print(f"平均耗时: {stats['avg_request_time']:.2f} 秒")
        print("\n工具使用统计:")
        for tool_name, tool_stats in self.analysis_result["tool_usage"].items():
            count = tool_stats["count"]
            total_time = tool_stats["total_time"]
            avg_time = total_time / count if count > 0 else 0
            print(f"  - {tool_name}: {count} 次 (平均: {avg_time:.2f}s, 总计: {total_time:.2f}s)")
        print("=" * 40)


def main():
    parser = argparse.ArgumentParser(
        description="分析Agent会话历史并生成可视化报告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python analyze_agent_history.py history.json
  python analyze_agent_history.py history.json --output my_report.html
  python analyze_agent_history.py history.json --verbose
        """,
    )

    parser.add_argument("json_file", help="JSON历史文件路径")

    parser.add_argument(
        "--output",
        "-o",
        default="report.html",
        help="输出报告文件路径 (默认: report.html)",
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="在终端显示摘要信息")

    args = parser.parse_args()

    analyzer = AgentHistoryAnalyzer(args.json_file)
    success = analyzer.run(output_path=args.output, verbose=args.verbose)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
