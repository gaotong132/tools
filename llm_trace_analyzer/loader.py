"""日志加载模块"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

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