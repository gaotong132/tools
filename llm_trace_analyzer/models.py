"""数据模型定义模块"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple


class CallStatus(str, Enum):
    """请求/响应配对的完整性状态。"""

    COMPLETE = "complete"
    REQUEST_ONLY = "request_only"
    RESPONSE_ONLY = "response_only"
    INVALID = "invalid"


@dataclass
class ToolExecution:
    """TelemetryRail 记录的一次真实工具执行。"""

    tool_call_id: str
    tool_name: str
    start_time: float
    end_time: float
    duration_seconds: float
    process_id: str = ""


@dataclass
class SystemMetrics:
    """系统资源指标"""

    phase: str = ""  # periodic (周期性采样)
    cpu_percent: float = 0.0
    memory_rss_mb: float = 0.0
    memory_vms_mb: float = 0.0
    read_bytes: int = 0
    write_bytes: int = 0
    timestamp: float = 0.0  # 采样时间戳


@dataclass
class IterationTiming:
    """单个迭代的时间统计"""

    iteration_num: int
    session_id: str
    request_timestamp: float = 0.0
    response_timestamp: float = 0.0
    llm_call_duration: float = 0.0  # 模型调用时间（秒）
    tool_processing_duration: float = 0.0  # TelemetryRail 工具执行时间之和（秒）
    is_last_iteration: bool = False
    event_id: str = ""
    call_kind: str = "agent"
    tool_executions: List[ToolExecution] = field(default_factory=list)
    status: CallStatus = CallStatus.COMPLETE
    # 系统资源指标
    system_metrics: List[SystemMetrics] = field(default_factory=list)


@dataclass
class LLMRequest:
    session_id: str
    iteration: int
    model_name: str
    timestamp: float
    body: Dict[str, Any]
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tools: List[Dict[str, Any]] = field(default_factory=list)
    source: str = "parent"
    source_label: str = ""
    is_internal: bool = False  # 是否为框架内部请求（如 command_intent）
    event_id: str = ""
    call_kind: str = "agent"


@dataclass
class LLMResponse:
    session_id: str
    iteration: int
    model_name: str
    timestamp: float
    content: str = ""
    reasoning_content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    source: str = "parent"
    source_label: str = ""
    event_id: str = ""
    call_kind: str = "agent"
    # Token 统计
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_tokens: int = 0
    input_cost: float = 0.0
    output_cost: float = 0.0
    total_cost: float = 0.0


@dataclass
class SubagentInfo:
    task_id: str
    session_id: str
    start_time: float = 0.0
    end_time: float = 0.0
    depth: int = 0  # 嵌套深度：0=直接子Agent, 1=子Agent的子Agent...
    parent_session_id: str = ""  # 直接调用者 session_id
    chain_path: List[str] = field(default_factory=list)  # 嵌套路径：["Parent", "Sub1", "Sub2"]


@dataclass
class LLMChain:
    session_id: str
    model_name: str
    requests: List[LLMRequest] = field(default_factory=list)
    responses: List[LLMResponse] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    total_iterations: int = 0
    subagents: List[SubagentInfo] = field(default_factory=list)
    is_subagent: bool = False
    # 时间统计
    iteration_timings: List[IterationTiming] = field(default_factory=list)
    total_llm_duration_seconds: float = 0.0
    total_tool_duration_seconds: float = 0.0


@dataclass
class Statistics:
    total_sessions: int = 0
    total_requests: int = 0
    total_responses: int = 0
    total_iterations: int = 0
    completed_calls: int = 0
    incomplete_calls: int = 0
    invalid_calls: int = 0
    sessions_by_model: Dict[str, int] = field(default_factory=dict)
    # 时间统计
    total_duration_seconds: float = 0.0  # 所有 session 总耗时
    total_llm_time_seconds: float = 0.0  # 模型调用总时间
    total_tool_time_seconds: float = 0.0  # 工具调用+思考总时间
    avg_llm_time_seconds: float = 0.0  # 平均每次模型调用耗时
    avg_tool_time_seconds: float = 0.0  # 平均每次工具调用+思考耗时
    # Token 统计
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cache_tokens: int = 0
    total_input_cost: float = 0.0
    total_output_cost: float = 0.0
    total_cost: float = 0.0
    # 工具调用统计
    tool_call_counts: Dict[str, int] = field(default_factory=dict)  # tool_name -> count
    total_tool_calls: int = 0
    # 工具失败统计
    tool_failure_counts: Dict[str, int] = field(default_factory=dict)  # tool_name -> fail count
    failed_tool_calls: int = 0
    # 每个 session 的统计（用于对比表）
    session_stats: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AnalysisResult:
    sessions: Dict[str, LLMChain] = field(default_factory=dict)
    statistics: Statistics = field(default_factory=Statistics)
    sorted_sessions: List[LLMChain] = field(default_factory=list)
    diagnostics: Dict[str, int] = field(default_factory=dict)


def _pair_key(item: Any) -> Tuple[str, Any]:
    """优先使用并发安全的 event_id；兼容没有 event_id 的旧日志。"""
    return (item.session_id, item.event_id or item.iteration)


def pair_requests_responses(
    requests: List[LLMRequest],
    responses: List[LLMResponse],
) -> List[Dict[str, Any]]:
    """按 event_id（旧日志回退 iteration）配对请求和响应。

    返回: [{"request": LLMRequest|None, "response": LLMResponse|None, "timestamp": float}, ...]
    """
    paired: Dict[Tuple[str, Any], Dict[str, Any]] = {}

    for req in requests:
        key = _pair_key(req)
        if key not in paired:
            paired[key] = {"request": None, "response": None, "timestamp": 0}
        paired[key]["request"] = req
        paired[key]["timestamp"] = req.timestamp

    for resp in responses:
        key = _pair_key(resp)
        if key not in paired:
            paired[key] = {"request": None, "response": None, "timestamp": 0}
        paired[key]["response"] = resp
        if paired[key]["timestamp"] == 0:
            paired[key]["timestamp"] = resp.timestamp

    return sorted(paired.values(), key=lambda x: x["timestamp"])


def build_global_num_map(sorted_items: List[Dict[str, Any]]) -> Dict[Tuple[str, Any], int]:
    """为排序后的配对项分配全局编号 (1-based)。"""
    result: Dict[Tuple[str, Any], int] = {}
    for i, item in enumerate(sorted_items):
        req = item["request"]
        resp = item["response"]
        key = _pair_key(req or resp)
        result[key] = i + 1
    return result
