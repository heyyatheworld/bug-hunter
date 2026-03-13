# BugHunter

CLI tool for automatic Python code generation and verification using two LLMs: one acts as a developer (DEV), the other as a QA engineer. Code is formatted with Black, checked with flake8, and executed in an isolated **Docker** sandbox (or locally if Docker is unavailable). Results and linter output are passed to QA. The cycle repeats until "PASS" and a clean linter run, or until the iteration limit is reached. Console UI is built with **Rich** (banner, LLM status spinners, AI response panels, bugs table).

## How it works

1. **DEV** (model from config) — generates Python code from the task description.
2. **Black** — code is formatted (`line_length` from `config.yml`) before linting.
3. **flake8** — static check (PEP 8, line length). Errors go into the bugs table and into DEV feedback.
4. **Execution** — generated code is saved to `solution.py` and run:
   - **Docker** (default): `python:3.11-slim`, read-only mount of `solution.py`, `--network none`, `--memory=128m`, `--cpus=0.5`, `--rm`. A temporary env check and optional test snippet are injected only for the run; the file is restored afterward so `solution.py` stays clean.
   - **Local fallback** — if Docker is not installed or the daemon is unreachable, code runs with the local Python (with the same temporary injection and restoration).
5. **QA** — second model receives task, code, linter and runtime output; returns PASS or a list of issues.
6. **Iterations** — QA and linter feedback are sent back to DEV for fixes; cycle repeats (limit set in config or via `-i`).
7. **Anti-loop** — if the model returns identical code while linter or QA still report issues, the loop stops ("Agent Stuck in Loop").
8. **Final cleanup** — when the target is achieved, `solution.py` is overwritten with only the approved code (Black-formatted, no debug or test snippets).

LLM output is normalized: the first ` ```python ... ``` ` block is extracted with a regex so extra text before/after does not end up in the file. Iteration logs are written to **bughunter_log.txt** in the background; the Rich UI is shown in the console.

## Requirements

- Python 3.x
- [Ollama](https://ollama.ai/) with a running server and models (names in `config.yml`; default `qwen2.5-coder:7b` for DEV and QA)
- **Docker** (optional) — for sandboxed execution. If Docker is not installed or not running, execution falls back to the local Python interpreter.
- Optional: **flake8** for style checks (if missing, lint step is skipped)

## Installation

```bash
pip install -r requirements.txt
```

Dependencies: `ollama`, `black`, `PyYAML`, `rich`.

With a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Ensure Ollama is running and required models are pulled (names from `config.yml`):

```bash
ollama pull qwen2.5-coder:7b
```

Optional, for linting:

```bash
pip install flake8
```

For sandboxed runs, have Docker installed and the daemon running. If not, BugHunter will warn and use local execution.

## Configuration

Settings are in **config.yml** in the project root (next to `main.py`). Example:

```yaml
models:
  dev: "qwen2.5-coder:7b"
  qa: "qwen2.5-coder:7b"

settings:
  max_iterations: 5
  line_length: 88

prompts:
  developer: |
    You are a senior Python developer. Write clean, self-contained code.
    IMPORTANT:
    1. Never exceed {line_length} characters per line.
    ...
  qa: |
    Analyze the code for logic, PEP 8 compliance, and task completion.
    ...
```

- **models.dev / models.qa** — Ollama model names for developer and QA.
- **settings.max_iterations** — maximum number of loop iterations.
- **settings.line_length** — line length limit for Black and flake8.
- **prompts.developer / prompts.qa** — system prompts; `{line_length}` is available in the developer prompt.

If `config.yml` is missing or empty, the script exits with an error.

## Usage (CLI)

```bash
python main.py
```

Without arguments, the default task is used (e.g. Fibonacci example).

Custom task as positional argument:

```bash
python main.py "Write a function that returns the factorial of n."
```

Flags override config:

| Argument | Description |
|----------|-------------|
| `task` | Task description (optional positional). |
| `-i`, `--iters N` | Max iterations (overrides `settings.max_iterations`). |
| `--model NAME` | Ollama model for DEV (overrides `models.dev`). |
| `-t`, `--test PYCODE` | Python code to append at the end of the script for testing (e.g. `print(my_func(10))`). Injected only during execution; not saved to `solution.py`. |

Examples:

```bash
python main.py "Sum of a list of numbers"
python main.py "Factorial" -i 10 --model llama3
python main.py "Write a sum function" --test "print(sum(5, 5))"
python main.py "Parse CSV into dict" --iters 3
```

## UI (Rich)

- **Banner** — BugHunter title panel at start.
- **LLM status** — Spinner with "LLM generating code..." / "LLM analyzing code..." during model calls.
- **[AI Assistant] panels** — DEV output (code with syntax highlight) and QA output (text) in separate panels.
- **Bugs table** — After QA: error type, line, severity, recommendation (including flake8 output and QA verdict).
- **Progress** — Iteration bar with percentage and time remaining.
- **Summary** — Panel with paths to `solution.py` and log file; then panel with final code (Syntax, monokai theme).

## Output

- **solution.py** — final generated code only (no debug or test snippets). Overwritten with clean, Black-formatted code when the target is achieved. In `.gitignore`.
- **bughunter_log.txt** — step-by-step iteration log, including Docker command and raw stdout/stderr when using the sandbox. Written in the background; in `.gitignore`.

## Project structure

- **main.py** — config load, argparse, `BugHunter` class (Docker/local execution, regex extraction, final clean write), entry point under `if __name__ == "__main__"`.
- **ui_utils.py** — Rich console, status spinners, panels, tables, syntax highlight, background file logging.
- **config.yml** — models, limits, prompts (required to run).
