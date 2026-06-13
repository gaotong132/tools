"""日志加载模块"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import DEFAULT_LOG_FILE, DEFAULT_LOG_FILE_FALLBACK, DEFAULT_LOGS_DIR, TRACE_MARKER


class LogLoader:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def load(self) -> List[Dict[str, Any]]:
        try:
            with open(self.file_path, encoding="utf-8") as f:
                if self.file_path.suffix == ".json":
                    return self._parse_json_file(f)
                else:
                    return self._parse_log_file(f)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"日志文件不存在: {self.file_path}") from e
        except UnicodeDecodeError:
            with open(self.file_path, encoding="gbk") as f:
                if self.file_path.suffix == ".json":
                    return self._parse_json_file(f)
                else:
                    return self._parse_log_file(f)

    def _parse_json_file(self, f) -> List[Dict[str, Any]]:
        traces: List[Dict[str, Any]] = []
        pattern = re.compile(
            r"^\[LLM_IO_TRACE\]\s+"
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
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            message = entry.get("message", "")
            if TRACE_MARKER not in message:
                continue

            match = pattern.match(message)
            if match:
                trace = self._extract_trace_from_match(match, entry)
                traces.append(trace)

        return traces

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

    def _extract_trace_from_match(self, match, entry: Dict[str, Any]) -> Dict[str, Any]:
        from datetime import datetime

        timestamp_str = entry.get("timestamp", "")
        if timestamp_str:
            try:
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f").timestamp()
            except ValueError:
                timestamp = 0.0
        else:
            timestamp = 0.0

        event = match.group(1)
        session_id = match.group(2)
        request_id = match.group(3)
        iteration = int(match.group(4))
        model_name = match.group(5)
        body_part_str = match.group(6)
        reasoning_seq_str = match.group(7)
        body_str = match.group(8)

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

    fallback_file = logs_dir / DEFAULT_LOG_FILE_FALLBACK
    if fallback_file.exists():
        return fallback_file

    return None
