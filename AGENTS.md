# Python Tools - Agent Instructions

## Project Overview
Collection of standalone Python utility scripts. Each tool in `tools/` is independent and self-contained.

## Environment Setup
```powershell
# Activate venv (Windows)
.\venv\Scripts\Activate.ps1

# Alternative activation
.\venv\Scripts\activate.bat
```

**Note:** Virtual environment created with `py -m venv venv`. Use `py -3` or `py` launcher on Windows if `python` command not available.

## Running Tools

### Agent History Analyzer
```powershell
# Basic usage
py -3 tools\analyze_agent_history.py <json_file_path>

# With verbose output
py -3 tools\analyze_agent_history.py <json_file_path> --verbose

# Custom output file
py -3 tools\analyze_agent_history.py <json_file_path> --output my_report.html
```

**Input:** JSON file containing Agent session history (array of events with `event_type`, `timestamp`, `role`, etc.)

**Output:** HTML report with execution flow timeline, tool call statistics, and collapsible details.

## Development Workflow

```powershell
# Install dev dependencies (after activating venv)
pip install -e .[dev]

# Format code
black tools/

# Lint
ruff check tools/

# Type check
mypy tools/

# Run tests (when tests exist)
pytest
```

## Project Structure
```
tools/
├── tools/                          # All utility scripts
│   └── analyze_agent_history.py   # Agent session analyzer
├── venv/                          # Virtual environment (git-ignored)
├── pyproject.toml                 # Project config, LSP, tool settings
├── requirements.txt               # Dependencies
├── LSP_SETUP.md                   # Detailed LSP configuration guide
└── README.md                      # Project documentation
```

## Key Implementation Details

### Agent History Analyzer (`tools/analyze_agent_history.py`)
- **Architecture:** Single-file script with no external dependencies beyond Python stdlib
- **Event Processing:** 
  - Groups events by `request_id` 
  - Maintains `execution_flow` list to preserve chronological order of reasoning + tool calls + compression events + assistant responses
  - Merges consecutive `chat.delta` events into single reasoning segments
  - Calculates duration for each reasoning segment, tool call, and assistant response
  - Tracks all context compression events in execution flow
  - Computes cumulative time across all operations
- **Output:** Generates standalone HTML with inline CSS/JS (no external assets needed)
- **Layout:** Two-column display with left-aligned timing and right-aligned content
- **Statistics:** Tracks tool call counts, durations, and compression events
- **Visual Features:** 
  - Compact header with summary statistics
  - Execution flow timeline with per-item duration and cumulative time
  - Duration badges with prominent styling (blue background, white text)
  - Total duration displayed in request header
  - All compression events shown in chronological order
  - Code blocks formatted with syntax highlighting for `execute_python_code`
  - Collapsible tool call results and parameters
- **Parameter Formatting:** Special handling for `execute_python_code` to display code blocks with monospace font and background

### Tool Configuration
All tool configs in `pyproject.toml`:
- **Pyright/PyLSP:** LSP servers configured for type checking and IDE support
- **Black:** Line length 100
- **Ruff:** Linting with E, W, F, I, C, B, UP rules
- **MyPy:** Basic type checking with `ignore_missing_imports = true`

## Common Gotchas

1. **Windows Paths:** Use backslashes or raw strings for Windows paths in PowerShell/CMD
2. **Python Launcher:** Use `py -3` or `py` if `python` command not in PATH
3. **Virtual Environment:** Always activate venv before running `pip install` or development tools
4. **LSP Detection:** LSP reads `pyproject.toml` automatically. Select interpreter: `./venv/Scripts/python.exe`
5. **No External Dependencies:** Keep tools dependency-free when possible (stdlib only)

## LSP Configuration

For detailed LSP setup instructions for VS Code, Neovim, PyCharm, and other editors, see **[LSP_SETUP.md](LSP_SETUP.md)**.

Quick VS Code setup:
1. Install Python and Pylance extensions
2. Select interpreter: `Ctrl+Shift+P` → "Python: Select Interpreter" → `./venv/Scripts/python.exe`
3. LSP automatically reads configuration from `pyproject.toml`

## Adding New Tools

1. Create new script in `tools/` directory
2. Follow existing pattern: single-file, minimal dependencies, argparse CLI
3. Update README.md with usage instructions
4. No need to update pyproject.toml unless adding new dependencies

## Testing & Verification

Currently no automated tests. Manual testing workflow:
1. Run tool with `--verbose` flag
2. Check generated output
3. Verify with `ruff check` and `mypy` for code quality