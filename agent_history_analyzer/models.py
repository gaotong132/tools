"""数据类定义模块"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CompressionData:
    """上下文压缩数据"""

    timestamp: float
    before: int
    after: int
    rate: float


@dataclass
class ToolCallData:
    """工具调用数据"""

    name: str
    arguments: str
    tool_call_id: str
    timestamp: float
    start_time: float
    duration: float = 0.0


@dataclass
class ToolResultData:
    """工具结果数据"""

    tool_name: str
    tool_call_id: str
    result: Any
    timestamp: float


@dataclass
class FlowItem:
    """执行流程项"""

    type: str
    timestamp: float
    content: Optional[str] = None
    start_timestamp: Optional[float] = None
    end_timestamp: Optional[float] = None
    duration: float = 0.0
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    arguments: Optional[str] = None
    result: Optional[Any] = None
    before: Optional[int] = None
    after: Optional[int] = None
    rate: Optional[float] = None


@dataclass
class RequestData:
    """请求数据"""

    request_id: str
    start_time: float
    end_time: float
    events: List[Dict[str, Any]]
    user_input: str = ""
    assistant_response: str = ""
    execution_flow: List[FlowItem] = field(default_factory=list)
    tool_calls: List[ToolCallData] = field(default_factory=list)
    tool_results: List[ToolResultData] = field(default_factory=list)
    compressions: List[CompressionData] = field(default_factory=list)
    duration: float = 0.0


@dataclass
class Statistics:
    """统计数据"""

    total_requests: int = 0
    user_messages: int = 0
    assistant_messages: int = 0
    tool_calls: int = 0
    context_compressed: int = 0
    total_time: float = 0.0
    avg_request_time: float = 0.0


@dataclass
class TopDurationStep:
    """耗时排行步骤"""

    request_id: str
    type: str
    duration: float
    summary: str
    user_input: str
    flow_item_index: int = 0


@dataclass(init=False)
class AnalysisResult:
    """分析结果"""

    total_events: int
    requests: Dict[str, RequestData]
    statistics: Statistics
    tool_usage: Dict[str, Dict[str, Any]]
    compression_events: List[Dict[str, Any]]
    timeline: List[RequestData]
    top_duration_steps: List[TopDurationStep]

    def __init__(self):
        self.total_events = 0
        self.requests = {}
        self.statistics = Statistics()
        self.tool_usage = defaultdict(lambda: {"count": 0, "total_time": 0.0})
        self.compression_events = []
        self.timeline = []
        self.top_duration_steps = []
