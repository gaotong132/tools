"""LLM Trace Analyzer 包"""

from typing import TYPE_CHECKING, Any

from .analyzer import ChainAnalyzer
from .loader import LogLoader, find_latest_log
from .models import AnalysisResult, LLMChain, LLMRequest, LLMResponse
from .parser import TraceParser
from .reporter import HTMLReporter

if TYPE_CHECKING:
    from .main import LLMTraceAnalyzer

__version__ = "0.2.0"
__all__ = [
    "LLMTraceAnalyzer",
    "LogLoader",
    "TraceParser",
    "ChainAnalyzer",
    "HTMLReporter",
    "AnalysisResult",
    "LLMChain",
    "LLMRequest",
    "LLMResponse",
    "find_latest_log",
]


def __getattr__(name: str) -> Any:
    """延迟加载 CLI，避免 `python -m llm_trace_analyzer.main` 的重复导入警告。"""
    if name == "LLMTraceAnalyzer":
        from .main import LLMTraceAnalyzer

        return LLMTraceAnalyzer
    raise AttributeError(name)
