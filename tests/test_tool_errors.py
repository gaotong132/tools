"""Failure detector registry contracts."""

import pytest

from llm_trace_analyzer.tool_errors import detect_tool_failure


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("read_file operation execution error, reason: denied", (True, "framework_error")),
        ("[ERROR]: fetch failed (timeout)", (True, "fetch_error")),
        ("command completed successfully", (False, None)),
        ("", (False, None)),
    ],
)
def test_detect_tool_failure(content, expected):
    assert detect_tool_failure(content) == expected
