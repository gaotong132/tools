"""Shared test fixtures for the LLM trace analyzer.

Most tests use tiny synthetic inputs from :mod:`tests.trace_factory`.  The
captured production log is deliberately loaded only by the contract tests.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

from llm_trace_analyzer.analyzer import ChainAnalyzer
from llm_trace_analyzer.loader import LogLoader
from llm_trace_analyzer.models import AnalysisResult, LLMRequest, LLMResponse, SystemMetrics
from llm_trace_analyzer.parser import TraceParser

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_LOG = FIXTURES_DIR / "llm_trace_b2fbb87bbeeb.log"
SAMPLE_SESSION_ID = "officeclaw_b2fbb87bbeebde489553cb50"
SAMPLE_SHORT_ID = "b2fbb87bbeeb"


@dataclass(frozen=True)
class ParsedFixture:
    loader: LogLoader
    parser: TraceParser
    traces: List[dict]
    requests: Dict[str, List[LLMRequest]]
    responses: Dict[str, List[LLMResponse]]
    metrics: Dict[Tuple[str, int], List[SystemMetrics]]
    result: AnalysisResult


@pytest.fixture(scope="session")
def captured_session() -> ParsedFixture:
    """Parse the captured log once for slow, end-to-end contract tests."""
    loader = LogLoader(str(SAMPLE_LOG), load_rollover=False)
    traces = loader.load()
    parser = TraceParser(traces)
    requests, responses, metrics = parser.parse()
    result = ChainAnalyzer(
        requests,
        responses,
        metrics,
        tool_executions=loader.tool_executions,
    ).analyze()
    return ParsedFixture(loader, parser, traces, requests, responses, metrics, result)
