# Python Tools - Agent Instructions

## Project Overview
Collection of modular Python utility packages. Each tool is a self-contained package with clear separation of concerns.

## Environment Setup

```bash
# Create venv
python -m venv venv

# Activate (Windows)
.\venv\Scripts\Activate.ps1

# Install
pip install -e .[dev]
```

## Running Tools

```bash
# Agent History Analyzer
agent-history-analyzer <json_file_path>
agent-history-analyzer <json_file_path> --output my_report.html --verbose

# Or as module
python -m agent_history_analyzer <json_file_path>
```

## Development Commands

```bash
black agent_history_analyzer/    # Format
ruff check agent_history_analyzer/  # Lint
mypy agent_history_analyzer/     # Type check
pytest                           # Run tests
```

## Project Structure

```
tools/
├── agent_history_analyzer/    # Package (one per tool)
│   ├── main.py                # CLI entry point
│   ├── analyzer.py            # Event processing
│   ├── reporter.py            # HTML generation
│   ├── templates.py           # HTML/CSS/JS templates
│   ├── constants.py           # Enums (EventType, FlowItemType)
│   └── models.py              # Dataclasses
├── util/                      # Shared utilities
│   └── loader.py              # JSON loader
├── venv/
└── pyproject.toml             # Config + tool settings
```

## Key Architecture Notes

**Agent History Analyzer:**
- Events grouped by `request_id`
- `execution_flow` list preserves chronological order
- Consecutive `chat.delta` events merged into reasoning segments
- Output: standalone HTML with inline CSS/JS (no external assets)

**Each module is usable independently as a library.**

## Adding New Tools

1. Create package directory in project root with `__init__.py`, `main.py`
2. Add entry point in `pyproject.toml`:
   ```toml
   [project.scripts]
   tool-name = "tool_package.main:main"
   ```

## Gotchas

- **Windows paths:** Use backslashes in PowerShell/CMD
- **Always activate venv** before pip install or dev tools
- **Module imports:** Run as `python -m package_name` if entry point not installed