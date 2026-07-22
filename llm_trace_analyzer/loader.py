"""日志加载模块"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import DEFAULT_LOG_FILE, DEFAULT_LOG_FILE_FALLBACK, DEFAULT_LOGS_DIR, TRACE_MARKER
from .models import ToolExecution

# 预编译正则表达式（模块级常量）
_TRACE_BODY_PATTERN = (
    r"event=(\w+)\s+"
    r"(?:event_id='([^']*)'\s+)?"
    r"session_id='([^']*)'\s+"
    r"request_id='([^']*)'\s+"
    r"iteration=(\d+)\s+"
    r"model_name='([^']*)'\s+"
    r"(?:body_part=(\d+/\d+)\s+)?"
    r"(?:reasoning_seq=(\d+)\s+)?"
    r"body=(.*)$"
)

JSON_LINE_PATTERN = re.compile(r"^\[LLM_IO_TRACE\]\s+" + _TRACE_BODY_PATTERN)
LOG_LINE_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s+"
    r"\[\d+\]\s+DEBUG\s+.*?"
    r"\[LLM_IO_TRACE\]\s+" + _TRACE_BODY_PATTERN
)
ROLLOVER_PATTERN = re.compile(r"^full_\d{8}_\d{6}\.log$")
_LINE_TIMESTAMP_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s+\[(\d+)\]")
_TOOL_START_PATTERN = re.compile(
    r"\[TelemetryRail\]\s+工具调用开始:\s*tool=([^,]+),\s*tool_call_id=([^,\s]+)"
)
_TOOL_END_PATTERN = re.compile(
    r"\[TelemetryRail\]\s+工具调用完成:\s*tool=([^,]+),\s*duration=([\d.]+)(ms|s)"
)


def find_rollover_files(log_path: Path) -> List[Path]:
    """查找同一目录下的所有绕接日志文件

    绕接文件命名模式: full_YYYYMMDD_HHMMSS.log
    返回按文件名排序的文件列表（包含当前文件）
    """
    if not log_path.exists():
        return [log_path]

    parent_dir = log_path.parent

    # 查找所有匹配 full_YYYYMMDD_HHMMSS.log 或 full.log 的文件
    all_files = []
    for file_path in parent_dir.glob("full*.log"):
        # 只匹配 full.log 或 full_YYYYMMDD_HHMMSS.log
        if file_path.name == "full.log" or ROLLOVER_PATTERN.match(file_path.name):
            all_files.append(file_path)

    # 按文件名排序（时间戳在文件名中，排序后即为时间顺序）
    # Rotated files contain older entries; the live full.log belongs last.
    all_files.sort(key=lambda p: (p.name == "full.log", p.name))

    return all_files if all_files else [log_path]


class LogLoader:
    def __init__(self, file_path: str, load_rollover: bool = True):
        self.file_path = Path(file_path)
        self.load_rollover = load_rollover
        self.tool_executions: List[ToolExecution] = []
        self._tool_starts: List[Tuple[float, str, str, str]] = []
        self._tool_ends: List[Tuple[float, str, float, str]] = []
        self.diagnostics: Dict[str, int] = {}

    def load(self, session_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        self.tool_executions = []
        self._tool_starts = []
        self._tool_ends = []
        self.diagnostics = {}
        # 查找所有绕接文件
        if self.load_rollover:
            log_files = find_rollover_files(self.file_path)
            if len(log_files) > 1:
                print(f"Found {len(log_files)} rollover log files, merging...")
        else:
            log_files = [self.file_path]

        all_traces = []
        for log_file in log_files:
            try:
                traces = self._load_single_file(log_file)
                if session_filter:
                    traces = [
                        trace
                        for trace in traces
                        if self._belongs_to_session(trace.get("session_id", ""), session_filter)
                    ]
                all_traces.extend(traces)
            except FileNotFoundError as e:
                if log_file == self.file_path:
                    raise FileNotFoundError(f"日志文件不存在: {self.file_path}") from e
                # 绕接文件不存在时跳过
                continue

        # rollover 边界可能重复写入同一条 trace，按轻量签名去重。
        deduplicated = []
        seen = set()
        for trace in all_traces:
            signature = (
                trace.get("timestamp"),
                trace.get("event"),
                trace.get("event_id"),
                trace.get("session_id"),
                trace.get("request_id"),
                trace.get("body_part"),
                trace.get("reasoning_seq"),
                trace.get("body_str", ""),
            )
            if signature in seen:
                continue
            seen.add(signature)
            deduplicated.append(trace)
        self.diagnostics["duplicate_traces"] = len(all_traces) - len(deduplicated)
        all_traces = deduplicated

        all_traces.sort(key=lambda t: t.get("timestamp", 0))
        self.tool_executions = self._match_tool_executions()

        return all_traces

    @staticmethod
    def _belongs_to_session(session_id: str, parent_session: str) -> bool:
        return session_id == parent_session or session_id.startswith(
            (parent_session + "_subagent_", parent_session + "_fork_agent_")
        )

    def _load_single_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """加载单个日志文件"""
        with open(file_path, encoding="utf-8", errors="replace") as f:
            if file_path.suffix == ".json":
                return self._parse_json_file(f)
            else:
                return self._parse_log_file(f)

    def _parse_json_file(self, f) -> List[Dict[str, Any]]:
        traces: List[Dict[str, Any]] = []

        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            message = entry.get("message", "")
            timestamp = self._parse_json_timestamp(entry)
            process_id = str(entry.get("process_id", entry.get("process", "")))
            self._parse_telemetry_line(message, timestamp, process_id)
            if TRACE_MARKER not in message:
                continue

            match = JSON_LINE_PATTERN.match(message)
            if match:
                trace = self._extract_trace_fields(match, timestamp, group_offset=0)
                traces.append(trace)

        return traces

    def _parse_log_file(self, f) -> List[Dict[str, Any]]:
        traces: List[Dict[str, Any]] = []

        for line in f:
            line = line.strip()
            timestamp = self._parse_log_timestamp(line)
            process_id = self._parse_log_process_id(line)
            self._parse_telemetry_line(line, timestamp, process_id)
            if TRACE_MARKER not in line:
                continue

            match = LOG_LINE_PATTERN.match(line)
            if match:
                trace = self._extract_trace_fields(match, timestamp, group_offset=1)
                traces.append(trace)

        return traces

    @staticmethod
    def _parse_log_timestamp(line: str) -> float:
        match = _LINE_TIMESTAMP_PATTERN.match(line)
        if not match:
            return 0.0
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S.%f").timestamp()
        except ValueError:
            return 0.0

    @staticmethod
    def _parse_log_process_id(line: str) -> str:
        match = _LINE_TIMESTAMP_PATTERN.match(line)
        return match.group(2) if match else ""

    def _parse_telemetry_line(self, line: str, timestamp: float, process_id: str = "") -> None:
        """收集 TelemetryRail 生命周期；完成行没有 call id，稍后统一匹配。"""
        if not timestamp or "[TelemetryRail]" not in line:
            return
        start = _TOOL_START_PATTERN.search(line)
        if start:
            self._tool_starts.append(
                (timestamp, start.group(1).strip(), start.group(2).strip(), process_id)
            )
            return
        end = _TOOL_END_PATTERN.search(line)
        if end:
            duration = float(end.group(2))
            if end.group(3) == "ms":
                duration /= 1000.0
            self._tool_ends.append((timestamp, end.group(1).strip(), duration, process_id))

    def _match_tool_executions(self) -> List[ToolExecution]:
        """按工具名及 `结束时间-记录耗时` 匹配缺少 call id 的完成事件。"""
        unmatched = set(range(len(self._tool_starts)))
        starts_by_key: Dict[Tuple[str, str], List[int]] = {}
        for index, (_, tool_name, _, process_id) in enumerate(self._tool_starts):
            starts_by_key.setdefault((process_id, tool_name), []).append(index)
        executions: List[ToolExecution] = []
        matched_ends = 0
        for end_time, tool_name, duration, process_id in sorted(self._tool_ends):
            expected_start = end_time - duration
            candidates = [
                i
                for i in starts_by_key.get((process_id, tool_name), [])
                if i in unmatched and self._tool_starts[i][0] <= end_time
            ]
            if not candidates:
                continue
            best = min(candidates, key=lambda i: abs(self._tool_starts[i][0] - expected_start))
            if abs(self._tool_starts[best][0] - expected_start) > 2.0:
                # 完成事件缺少 call id；距离过大时宁可标为未测量，也不错误归因。
                continue
            start_time, _, tool_call_id, _ = self._tool_starts[best]
            unmatched.remove(best)
            matched_ends += 1
            executions.append(
                ToolExecution(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    start_time=start_time,
                    end_time=end_time,
                    duration_seconds=duration,
                    process_id=process_id,
                )
            )
        self.diagnostics["unmatched_tool_starts"] = len(unmatched)
        self.diagnostics["unmatched_tool_ends"] = len(self._tool_ends) - matched_ends
        return sorted(executions, key=lambda execution: execution.start_time)

    @staticmethod
    def _parse_json_timestamp(entry: Dict[str, Any]) -> float:
        """从 JSON 日志条目中解析时间戳"""
        timestamp_str = entry.get("timestamp", "")
        if timestamp_str:
            try:
                return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f").timestamp()
            except ValueError:
                pass
        return 0.0

    @staticmethod
    def _parse_body_part(body_part_str: Optional[str]) -> Optional[Tuple[int, int]]:
        """解析 body_part 字符串为 (current, total) 元组"""
        if not body_part_str:
            return None
        parts = body_part_str.split("/")
        return (int(parts[0]), int(parts[1]))

    @staticmethod
    def _extract_trace_fields(match, timestamp: float, group_offset: int) -> Dict[str, Any]:
        """从正则匹配中提取 trace 字段。

        group_offset: JSON 格式从 group(1) 开始（offset=0），
                      LOG 格式从 group(2) 开始（offset=1，因为 group(1) 是时间戳）。
        """
        o = group_offset
        event = match.group(1 + o)
        event_id = match.group(2 + o) or ""
        session_id = match.group(3 + o)
        request_id = match.group(4 + o)
        iteration = int(match.group(5 + o))
        model_name = match.group(6 + o)
        body_part_str = match.group(7 + o)
        reasoning_seq_str = match.group(8 + o)
        body_str = match.group(9 + o)

        return {
            "timestamp": timestamp,
            "event": event,
            "event_id": event_id,
            "session_id": session_id,
            "request_id": request_id,
            "iteration": iteration,
            "model_name": model_name,
            "body_part": LogLoader._parse_body_part(body_part_str),
            "reasoning_seq": int(reasoning_seq_str) if reasoning_seq_str else None,
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
