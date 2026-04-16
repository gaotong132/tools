"""HTML报告生成器"""

import html
import json
from datetime import datetime
from pathlib import Path
from typing import List

from .models import AnalysisResult, LLMChain, LLMRequest, LLMResponse
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
    SYSTEM_PROMPT_TEMPLATE,
    TOOL_CALLS_TEMPLATE,
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

        html_content = SESSION_DETAIL_TEMPLATE.format(
            session_id_short=short_id,
            session_id=chain.session_id,
            model_name=chain.model_name,
            total_iterations=chain.total_iterations,
            start_time=self._format_timestamp(chain.start_time),
            end_time=self._format_timestamp(chain.end_time),
            iterations_html=iterations_html,
        )

        with open(detail_file, "w", encoding="utf-8") as f:
            f.write(html_content)

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
        max_iterations = max(len(chain.requests), len(chain.responses))
        iterations_parts: List[str] = []

        for i in range(max_iterations):
            iteration_num = i + 1

            request_html = ""
            if i < len(chain.requests):
                request_html = self._generate_request_html(chain.requests[i])

            response_html = ""
            if i < len(chain.responses):
                response_html = self._generate_response_html(chain.responses[i])

            iteration_html = ITERATION_DETAIL_TEMPLATE.format(
                iteration_num=iteration_num,
                request_html=request_html,
                response_html=response_html,
            )
            iterations_parts.append(iteration_html)

        return "\n".join(iterations_parts)

    def _generate_request_html(self, request: LLMRequest) -> str:
        system_prompt_html = ""
        other_messages = []

        for msg in request.messages:
            if msg.get("role") == "system" and not system_prompt_html:
                content = msg.get("content", "")
                if content:
                    content_id = self._next_id()
                    escaped_content = html.escape(content)
                    system_prompt_html = SYSTEM_PROMPT_TEMPLATE.format(
                        content_id=content_id,
                        system_prompt=escaped_content,
                    )
            else:
                other_messages.append(msg)

        messages_html = self._make_json_block(
            other_messages if other_messages else request.messages
        )
        tools_html = self._make_json_block(request.tools)
        timestamp_str = self._format_timestamp(request.timestamp)

        return REQUEST_TEMPLATE.format(
            timestamp=timestamp_str,
            system_prompt_html=system_prompt_html,
            message_count=len(request.messages),
            tool_count=len(request.tools),
            messages_html=messages_html,
            tools_html=tools_html,
        )

    def _generate_response_html(self, response: LLMResponse) -> str:
        timestamp_str = self._format_timestamp(response.timestamp)

        reasoning_html = ""
        if response.reasoning_content:
            content_id = self._next_id()
            escaped_content = html.escape(response.reasoning_content)
            reasoning_html = REASONING_TEMPLATE.format(
                content_id=content_id,
                reasoning_content=escaped_content,
            )

        content_html = ""
        if response.content:
            content_id = self._next_id()
            escaped_content = html.escape(response.content)
            content_html = CONTENT_TEMPLATE.format(
                content_id=content_id,
                content=escaped_content,
            )

        tool_calls_html = ""
        if response.tool_calls:
            tool_calls_html = self._make_json_block(
                response.tool_calls, tool_count=len(response.tool_calls)
            )

        return RESPONSE_TEMPLATE.format(
            timestamp=timestamp_str,
            reasoning_html=reasoning_html,
            content_html=content_html,
            tool_calls_html=tool_calls_html,
        )

    def _make_json_block(self, obj, tool_count: int = 0) -> str:
        json_str = json.dumps(obj, indent=2, ensure_ascii=False)
        content_id = self._next_id()
        escaped_content = html.escape(json_str)

        if tool_count > 0:
            return TOOL_CALLS_TEMPLATE.format(
                content_id=content_id,
                tool_count=tool_count,
                tool_calls_json=escaped_content,
            )
        return JSON_BLOCK_TEMPLATE.format(content_id=content_id, content=escaped_content)

    def _format_timestamp(self, timestamp: float) -> str:
        if timestamp == 0:
            return "N/A"
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%H:%M:%S")
