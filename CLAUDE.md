# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup (uv recommended)
uv venv && uv pip install -e .[dev]

# Run tools
ha                              # Analyze Agent session history (auto-finds latest)
ha <json_file> -o report.html   # Analyze specific file
lt                              # Analyze LLM request traces (auto-finds app.log)
lt <log_file> -o report_dir     # Analyze specific log
lt --session <id>               # Filter by session ID

# Dev
black . && ruff check . && mypy .
pytest
```

## Architecture

Two modular Python tools, each a self-contained package with consistent structure:

```
agent_history_analyzer/  (CLI: ha)
├── loader.py      # JSON file loading, auto-find latest history.json
├── analyzer.py    # EventAnalyzer - processes events, builds timeline
├── models.py      # RequestData, AnalysisResult, Statistics, FlowItem
├── reporter.py    # HTMLReporter - generates visualization
├── templates.py   # HTML/CSS templates for report
├── constants.py   # EventType, FlowItemType enums
└── main.py        # CLI entry point

llm_trace_analyzer/  (CLI: lt)
├── loader.py      # LogLoader - parses LLM_IO_TRACE logs, auto-find app.log
├── parser.py      # TraceParser - merges fragmented request bodies
├── analyzer.py    # ChainAnalyzer - links requests/responses, identifies subagents
├── models.py      # LLMRequest, LLMResponse, LLMChain, AnalysisResult
├── reporter.py    # HTMLReporter - generates multi-session reports
├── templates.py   # HTML/CSS templates
├── constants.py   # TraceEventType enum
└── main.py        # CLI entry point
```

Key patterns:
- Entry points defined in `pyproject.toml` `[project.scripts]`
- Each package exports main class via `__init__.py`
- Reports use embedded HTML templates (no external template engine)

## Default Search Paths

- **ha**: `~/.office-claw/.jiuwenclaw/agent/sessions/` (recursive search for `history.json`)
- **lt**: `~/.office-claw/.jiuwenclaw/.logs/app.log`

## Data Flow

**agent_history_analyzer**: JSON → EventAnalyzer.analyze() → AnalysisResult → HTMLReporter.generate()

Events processed (EventType enum):
- `context.compressed` → compression metrics
- `chat.delta` → reasoning chunks (LLM_REASONING source)
- `chat.final` → assistant response (ANSWER source)
- `chat.tool_call` / `chat.tool_result` → tool invocations

**llm_trace_analyzer**: Log → LogLoader → TraceParser → ChainAnalyzer → AnalysisResult → HTMLReporter

Parses `[LLM_IO_TRACE]` entries with:
- Request body fragments (`body_part 1/N → N/N`) merged by TraceParser
- Request-response pairing by iteration number
- Subagent session identification (`subagent_<task_id>`)
- Parent-child session linking via spawn_subagent timestamps

## Gotchas

- **No tests yet** - pytest configured but `tests/` doesn't exist
- **Windows paths** - use backslashes in PowerShell/CMD
- **OfficeClaw dependency** - requires `LOG_LEVEL=debug` for LLM_IO_TRACE logging