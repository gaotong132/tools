# Python Tools

Collection of modular Python utility packages. Each tool is a self-contained package.

## Setup

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows
pip install -e .[dev]
```

## Commands

```bash
# Run tools
ha                              # Analyze Agent session history
ha <json_file> -o report.html   # Analyze specific file
lt                              # Analyze LLM request traces (auto-finds app.log)
lt <log_file> -o report.html    # Analyze specific log
lt --session <id>               # Filter by session

# Dev
black . && ruff check . && mypy .
pytest
```

## Architecture

- **Packages:** One tool per directory (`agent_history_analyzer/`, `llm_trace_analyzer/`)
- **Entry points:** Defined in `pyproject.toml` `[project.scripts]`
- **No tests yet** - pytest configured but `tests/` doesn't exist

## Agent History Analyzer (`ha`)

Default session search: `~/.office-claw/.jiuwenclaw/agent/sessions/` (recursive search for `history.json`)

## LLM Trace Analyzer (`lt`)

Default log search: `~/.office-claw/.jiuwenclaw/.logs/app.log`

Parses `[LLM_IO_TRACE]` logs:
- Merges fragmented request bodies (body_part 1/N → N/N)
- Links requests (messages+tools) with responses (content+tool_calls)
- Supports `--session` filter

## Gotchas

- **Activate venv first** - dev tools won't work without it
- **Windows paths:** Use backslashes in PowerShell/CMD
- **Wait for user confirmation before git push** - always ask user to confirm before pushing commits