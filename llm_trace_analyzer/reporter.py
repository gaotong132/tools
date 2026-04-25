"""HTML报告生成器"""

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from .models import AnalysisResult, LLMChain, LLMRequest, LLMResponse, SubagentInfo
from .templates import (
    CONTENT_TEMPLATE,
    INDEX_TEMPLATE,
    ITERATION_DETAIL_TEMPLATE,
    JSON_BLOCK_TEMPLATE,
    REASONING_TEMPLATE,
    REQUEST_TEMPLATE,
    RESPONSE_TEMPLATE,
    SESSION_DETAIL_TEMPLATE,
    SESSION_ROW_TEMPLATE,
    SUBAGENT_NODE_TEMPLATE,
    SUBAGENT_TREE_TEMPLATE,
    SYSTEM_PROMPT_TEMPLATE,
    TOOL_CALLS_TEMPLATE,
    TOOL_NAME_ITEM_TEMPLATE,
    TOOLS_SECTION_TEMPLATE,
)


class HTMLReporter:
    _id_counter = 0

    def __init__(self, log_file_path: str):
        self.log_file_path = log_file_path

    def generate(self, result: AnalysisResult, output_path: str) -> None:
        output_dir = Path(output_path).parent
        output_name = Path(output_path).stem

        report_dir = output_dir / output_name
        report_dir.mkdir(parents=True, exist_ok=True)

        self._generate_index(result, report_dir)

        for chain in result.sorted_sessions:
            self._generate_session_detail(chain, report_dir)

        print(f"Report generated in: {report_dir}/")
        print("  - index.html (session list)")
        for chain in result.sorted_sessions:
            short_id = self._short_session_id(chain.session_id)
            print(f"  - session_{short_id}.html")

    def _generate_index(self, result: AnalysisResult, report_dir: Path) -> None:
        stats = result.statistics

        session_rows: List[str] = []
        for chain in result.sorted_sessions:
            short_id = self._short_session_id(chain.session_id)
            detail_file = f"session_{short_id}.html"

            row = SESSION_ROW_TEMPLATE.format(
                session_id_short=short_id,
                session_id=chain.session_id,
                model_name=chain.model_name,
                total_iterations=chain.total_iterations,
                start_time=self._format_timestamp(chain.start_time),
                end_time=self._format_timestamp(chain.end_time),
                detail_file=detail_file,
            )
            session_rows.append(row)

        index_html = INDEX_TEMPLATE.format(
            total_sessions=stats.total_sessions,
            total_requests=stats.total_requests,
            total_iterations=stats.total_iterations,
            session_rows="\n".join(session_rows),
        )

        with open(report_dir / "index.html", "w", encoding="utf-8") as f:
            f.write(index_html)

    def _generate_session_detail(self, chain: LLMChain, report_dir: Path) -> None:
        short_id = self._short_session_id(chain.session_id)
        detail_file = report_dir / f"session_{short_id}.html"

        iterations_html = self._generate_iterations_html(chain)
        subagents_tree_html = self._generate_subagents_tree_html(chain)

        html_content = SESSION_DETAIL_TEMPLATE.format(
            session_id_short=short_id,
            session_id=chain.session_id,
            model_name=chain.model_name,
            total_iterations=chain.total_iterations,
            start_time=self._format_timestamp(chain.start_time),
            end_time=self._format_timestamp(chain.end_time),
            iterations_html=iterations_html,
            subagents_tree_html=subagents_tree_html,
        )

        with open(detail_file, "w", encoding="utf-8") as f:
            f.write(html_content)

    def _generate_subagents_tree_html(self, chain: LLMChain) -> str:
        if not chain.subagents:
            return ""

        # 按深度和开始时间排序
        sorted_subagents = sorted(chain.subagents, key=lambda s: (s.depth, s.start_time))

        tree_nodes: List[str] = []
        for sa in sorted_subagents:
            # 计算 iterations 数量
            iterations = len(self._get_requests_for_subagent(chain, sa.session_id))

            node_html = SUBAGENT_NODE_TEMPLATE.format(
                depth=sa.depth,
                chain_label=" → ".join(sa.chain_path) if sa.chain_path else sa.task_id[:12],
                iterations=iterations,
            )
            tree_nodes.append(node_html)

        return SUBAGENT_TREE_TEMPLATE.format(
            subagent_count=len(chain.subagents),
            tree_nodes_html="\n".join(tree_nodes),
        )

    def _get_requests_for_subagent(self, chain: LLMChain, session_id: str) -> List[LLMRequest]:
        """获取特定 subAgent session 的请求"""
        return [r for r in chain.requests if r.session_id == session_id]

    def _short_session_id(self, session_id: str) -> str:
        if not session_id:
            return "unknown"
        parts = session_id.split("_")
        if len(parts) >= 2:
            return parts[-1][:12]
        return session_id[:12]

    def _next_id(self) -> str:
        self._id_counter += 1
        return f"content_{self._id_counter}"

    def _generate_iterations_html(self, chain: LLMChain) -> str:
        # 按 (session_id, iteration) 配对请求和响应
        paired_items: Dict[Tuple[str, int], Dict] = {}

        for req in chain.requests:
            key = (req.session_id, req.iteration)
            if key not in paired_items:
                paired_items[key] = {"request": None, "response": None, "timestamp": 0}
            paired_items[key]["request"] = req
            paired_items[key]["timestamp"] = req.timestamp

        for resp in chain.responses:
            key = (resp.session_id, resp.iteration)
            if key not in paired_items:
                paired_items[key] = {"request": None, "response": None, "timestamp": 0}
            paired_items[key]["response"] = resp
            # 如果没有 request，用 response 的 timestamp
            if paired_items[key]["timestamp"] == 0:
                paired_items[key]["timestamp"] = resp.timestamp

        # 按 timestamp 排序
        sorted_items = sorted(paired_items.values(), key=lambda x: x["timestamp"])

        iterations_parts: List[str] = []
        for i, item in enumerate(sorted_items):
            iteration_num = i + 1

            request_html = ""
            depth = 0
            depth_indicator = ""
            if item["request"]:
                request = item["request"]
                request_html = self._generate_request_html(request)
                if request.source == "subagent":
                    depth = self._calc_depth_from_label(request.source_label)

            response_html = ""
            if item["response"]:
                response = item["response"]
                response_html = self._generate_response_html(response)
                if response.source == "subagent":
                    depth = self._calc_depth_from_label(response.source_label)

            if depth > 0:
                depth_indicator = f"(Depth {depth})"

            iteration_html = ITERATION_DETAIL_TEMPLATE.format(
                iteration_num=iteration_num,
                depth=depth,
                depth_indicator=depth_indicator,
                request_html=request_html,
                response_html=response_html,
            )
            iterations_parts.append(iteration_html)

        return "\n".join(iterations_parts)

    def _calc_depth_from_label(self, label: str) -> int:
        """从 source_label 计算嵌套深度，如 'Parent → Sub[xxx] → Fork[xxx]' """
        if not label:
            return 0
        arrows = label.split(" → ")
        return len(arrows) - 1

    def _generate_request_html(self, request: LLMRequest) -> str:
        system_prompt_html = ""
        system_prompt_chars = 0
        other_messages = []

        for msg in request.messages:
            if msg.get("role") == "system" and not system_prompt_html:
                content = msg.get("content", "")
                if content:
                    system_prompt_chars = len(content)
                    content_id = self._next_id()
                    escaped_content = html.escape(content)
                    system_prompt_html = SYSTEM_PROMPT_TEMPLATE.format(
                        content_id=content_id,
                        system_prompt=escaped_content,
                        char_count=system_prompt_chars,
                    )
            else:
                other_messages.append(msg)

        messages_json = json.dumps(other_messages, indent=2, ensure_ascii=False)
        tools_json = json.dumps(request.tools, indent=2, ensure_ascii=False)
        messages_chars = len(messages_json)
        tools_chars = len(tools_json)

        messages_html = self._make_json_block(other_messages)
        tools_full_html = self._make_json_block(request.tools)
        tool_names_html = self._generate_tool_names_html(request.tools)
        timestamp_str = self._format_timestamp(request.timestamp)

        names_id = self._next_id()
        full_id = self._next_id()

        tools_section_html = TOOLS_SECTION_TEMPLATE.format(
            tool_count=len(request.tools),
            tools_chars=tools_chars,
            names_id=names_id,
            full_id=full_id,
            tool_names_html=tool_names_html,
            tools_html=tools_full_html,
        )

        request_chars = system_prompt_chars + messages_chars + tools_chars

        return REQUEST_TEMPLATE.format(
            timestamp=timestamp_str,
            request_chars=request_chars,
            source_class="subagent" if request.source == "subagent" else "",
            source_label=request.source_label,
            system_prompt_html=system_prompt_html,
            message_count=len(other_messages),
            messages_chars=messages_chars,
            messages_html=messages_html,
            tools_html=tools_section_html,
        )

    def _generate_tool_names_html(self, tools: List) -> str:
        """生成工具名网格 HTML"""
        items = []
        for tool in tools:
            name = tool.get("name", "")
            if name:
                items.append(TOOL_NAME_ITEM_TEMPLATE.format(name=name))
        return "\n".join(items)

    def _generate_response_html(self, response: LLMResponse) -> str:
        timestamp_str = self._format_timestamp(response.timestamp)

        reasoning_chars = 0
        reasoning_html = ""
        if response.reasoning_content:
            reasoning_chars = len(response.reasoning_content)
            content_id = self._next_id()
            escaped_content = html.escape(response.reasoning_content)
            reasoning_html = REASONING_TEMPLATE.format(
                content_id=content_id,
                reasoning_content=escaped_content,
                char_count=reasoning_chars,
            )

        content_chars = 0
        content_html = ""
        if response.content:
            content_chars = len(response.content)
            content_id = self._next_id()
            escaped_content = html.escape(response.content)
            content_html = CONTENT_TEMPLATE.format(
                content_id=content_id,
                content=escaped_content,
                char_count=content_chars,
            )

        tool_calls_chars = 0
        tool_calls_html = ""
        if response.tool_calls:
            tool_calls_json = json.dumps(response.tool_calls, indent=2, ensure_ascii=False)
            tool_calls_chars = len(tool_calls_json)
            tool_calls_html = self._make_json_block(
                response.tool_calls,
                tool_count=len(response.tool_calls),
                char_count=tool_calls_chars,
            )

        response_chars = reasoning_chars + content_chars + tool_calls_chars

        return RESPONSE_TEMPLATE.format(
            timestamp=timestamp_str,
            response_chars=response_chars,
            source_class="subagent" if response.source == "subagent" else "",
            source_label=response.source_label,
            reasoning_html=reasoning_html,
            content_html=content_html,
            tool_calls_html=tool_calls_html,
        )

    def _make_json_block(self, obj, tool_count: int = 0, char_count: int = 0) -> str:
        json_str = json.dumps(obj, indent=2, ensure_ascii=False)
        if char_count == 0:
            char_count = len(json_str)
        content_id = self._next_id()
        escaped_content = html.escape(json_str)

        if tool_count > 0:
            return TOOL_CALLS_TEMPLATE.format(
                content_id=content_id,
                tool_count=tool_count,
                char_count=char_count,
                tool_calls_json=escaped_content,
            )
        return JSON_BLOCK_TEMPLATE.format(content_id=content_id, content=escaped_content)

    def _format_timestamp(self, timestamp: float) -> str:
        if timestamp == 0:
            return "N/A"
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%H:%M:%S")
