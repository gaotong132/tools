"""日志加载模块"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import DEFAULT_LOG_FILE, DEFAULT_LOGS_DIR, TRACE_MARKER


class LogLoader:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def load(self) -> List[Dict[str, Any]]:
        try:
            with open(self.file_path, encoding="utf-8") as f:
                return self._parse_log_file(f)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"日志文件不存在: {self.file_path}") from e
        except UnicodeDecodeError:
            with open(self.file_path, encoding="gbk") as f:
                return self._parse_log_file(f)

    def load_spawn_subagent_calls(self) -> Dict[str, List[Tuple[str, float]]]:
        try:
            with open(self.file_path, encoding="utf-8") as f:
                return self._parse_spawn_subagent_calls(f)
        except FileNotFoundError:
            return {}
        except UnicodeDecodeError:
            with open(self.file_path, encoding="gbk") as f:
                return self._parse_spawn_subagent_calls(f)

    def load_tool_call_events(self) -> List[Dict[str, Any]]:
        try:
            with open(self.file_path, encoding="utf-8") as f:
                return self._parse_tool_call_events(f)
        except FileNotFoundError:
            return []
        except UnicodeDecodeError:
            with open(self.file_path, encoding="gbk") as f:
                return self._parse_tool_call_events(f)

    def _parse_tool_call_events(self, f) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        # 解析所有 ToolCall 事件（spawn_subagent, fork_agent 等）
        pattern = re.compile(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s+"
            r"\[\d+\]\s+INFO\s+[^:]+:\d+:\s+"
            r"\[ToolCall\]\s+tool=(\w+)\s+"
            r"session=(\S+)"
        )

        for line in f:
            line = line.strip()
            if "[ToolCall]" not in line:
                continue

            match = pattern.match(line)
            if match:
                from datetime import datetime

                timestamp_str = match.group(1)
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f").timestamp()
                tool_name = match.group(2)
                session_id = match.group(3)

                # 对于 fork_agent，提取 task_id（session_id 中的后缀）
                task_id = None
                if tool_name == "fork_agent":
                    # fork_agent 启动后 subAgent session_id 格式：fork_fork_agent_xxxx
                    # 需要从后续日志中获取，这里先记录
                    task_id = None

                events.append(
                    {
                        "timestamp": timestamp,
                        "tool_name": tool_name,
                        "session_id": session_id,
                        "task_id": task_id,
                        "line": line,
                    }
                )

        return events

    def load_subagent_start_events(self) -> List[Dict[str, Any]]:
        try:
            with open(self.file_path, encoding="utf-8") as f:
                return self._parse_subagent_start_events(f)
        except FileNotFoundError:
            return []
        except UnicodeDecodeError:
            with open(self.file_path, encoding="gbk") as f:
                return self._parse_subagent_start_events(f)

    def _parse_subagent_start_events(self, f) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        pattern = re.compile(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s+"
            r"\[\d+\]\s+INFO\s+[^:]+:\d+:\s+"
            r"\[Subagent\]\s+Starting\s+execution,\s+task_id=(subagent_\w+)"
        )

        for line in f:
            line = line.strip()
            if "[Subagent]" not in line or "Starting execution" not in line:
                continue

            match = pattern.match(line)
            if match:
                from datetime import datetime

                timestamp_str = match.group(1)
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f").timestamp()
                task_id = match.group(2)

                events.append(
                    {
                        "timestamp": timestamp,
                        "task_id": task_id,
                        "line": line,
                    }
                )

        return events

    def load_spawn_subagent_calls(self) -> Dict[str, List[Tuple[str, float]]]:
        try:
            with open(self.file_path, encoding="utf-8") as f:
                return self._parse_spawn_subagent_calls(f)
        except FileNotFoundError:
            return {}
        except UnicodeDecodeError:
            with open(self.file_path, encoding="gbk") as f:
                return self._parse_spawn_subagent_calls(f)

    def load_subagent_starts(self) -> Dict[str, Tuple[float, float]]:
        try:
            with open(self.file_path, encoding="utf-8") as f:
                return self._parse_subagent_starts(f)
        except FileNotFoundError:
            return {}
        except UnicodeDecodeError:
            with open(self.file_path, encoding="gbk") as f:
                return self._parse_subagent_starts(f)

    def _parse_subagent_starts(self, f) -> Dict[str, Tuple[float, float]]:
        starts: Dict[str, Tuple[float, float]] = {}
        start_pattern = re.compile(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s+"
            r"\[\d+\]\s+INFO\s+[^:]+:\d+:\s+"
            r"\[Subagent\]\s+Starting\s+execution,\s+task_id=(subagent_\w+)"
        )
        end_pattern = re.compile(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s+"
            r"\[\d+\]\s+INFO\s+[^:]+:\d+:\s+"
            r"\[Subagent\]\s+Execution\s+completed,\s+task_id=(subagent_\w+)"
        )

        for line in f:
            line = line.strip()
            if "[Subagent]" not in line:
                continue

            start_match = start_pattern.match(line)
            if start_match:
                from datetime import datetime

                timestamp_str = start_match.group(1)
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f").timestamp()
                task_id = start_match.group(2)
                starts[task_id] = (timestamp, 0.0)

            end_match = end_pattern.match(line)
            if end_match:
                from datetime import datetime

                timestamp_str = end_match.group(1)
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f").timestamp()
                task_id = end_match.group(2)
                if task_id in starts:
                    starts[task_id] = (starts[task_id][0], timestamp)

        return starts

    def _parse_spawn_subagent_calls(self, f) -> Dict[str, List[Tuple[str, float]]]:
        calls: Dict[str, List[Tuple[str, float]]] = {}
        pattern = re.compile(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s+"
            r"\[\d+\]\s+INFO\s+[^:]+:\d+:\s+"
            r"\[ToolCall\]\s+tool=spawn_subagent\s+"
            r"session=(\S+)"
        )

        for line in f:
            line = line.strip()
            if "spawn_subagent" not in line:
                continue

            match = pattern.match(line)
            if match:
                from datetime import datetime

                timestamp_str = match.group(1)
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f").timestamp()
                parent_session = match.group(2)

                task_id = self._extract_task_id_from_line(line)
                if task_id and parent_session:
                    if parent_session not in calls:
                        calls[parent_session] = []
                    calls[parent_session].append((task_id, timestamp))

        return calls

    def _extract_task_id_from_line(self, line: str) -> Optional[str]:
        task_pattern = re.search(r"task_id=(subagent_\w+)", line)
        if task_pattern:
            return task_pattern.group(1)

        starting_pattern = re.search(
            r"\[Subagent\]\s+Starting\s+execution,\s+task_id=(subagent_\w+)", line
        )
        if starting_pattern:
            return starting_pattern.group(1)

        return None

    def _parse_log_file(self, f) -> List[Dict[str, Any]]:
        traces: List[Dict[str, Any]] = []
        pattern = re.compile(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s+"
            r"\[\d+\]\s+DEBUG\s+[^:]+:\d+:\s+"
            r"\[LLM_IO_TRACE\]\s+"
            r"event=(\w+)\s+"
            r"session_id='([^']*)'\s+"
            r"request_id='([^']*)'\s+"
            r"iteration=(\d+)\s+"
            r"model_name='([^']*)'\s+"
            r"(?:body_part=(\d+/\d+)\s+)?"
            r"(?:reasoning_seq=(\d+)\s+)?"
            r"body=(.*)$"
        )

        for line in f:
            line = line.strip()
            if TRACE_MARKER not in line:
                continue

            match = pattern.match(line)
            if match:
                trace = self._extract_trace(match)
                traces.append(trace)

        return traces

    def _extract_trace(self, match) -> Dict[str, Any]:
        timestamp_str = match.group(1)
        from datetime import datetime

        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f").timestamp()

        event = match.group(2)
        session_id = match.group(3)
        request_id = match.group(4)
        iteration = int(match.group(5))
        model_name = match.group(6)
        body_part_str = match.group(7)
        reasoning_seq_str = match.group(8)
        body_str = match.group(9)

        body_part = None
        if body_part_str:
            parts = body_part_str.split("/")
            body_part = (int(parts[0]), int(parts[1]))

        reasoning_seq = None
        if reasoning_seq_str:
            reasoning_seq = int(reasoning_seq_str)

        return {
            "timestamp": timestamp,
            "event": event,
            "session_id": session_id,
            "request_id": request_id,
            "iteration": iteration,
            "model_name": model_name,
            "body_part": body_part,
            "reasoning_seq": reasoning_seq,
            "body_str": body_str,
        }


def find_latest_log(logs_dir: Optional[Path] = None) -> Optional[Path]:
    if logs_dir is None:
        logs_dir = Path.home() / DEFAULT_LOGS_DIR

    log_file = logs_dir / DEFAULT_LOG_FILE
    if log_file.exists():
        return log_file

    return None
