# BugHunter

**Version 1.0.0** · [CHANGELOG](CHANGELOG.md) · [License: MIT](LICENSE)

CLI for automatic **Python** generation and review using two **Ollama** models: a developer (DEV) and a QA reviewer. Code is formatted with **Black**, optionally checked with **flake8**, and executed in a **Docker** sandbox or locally. The loop continues until QA and the linter agree (with safeguards against infinite churn) or the iteration limit is reached. The interface uses **Rich** (banner, spinners, panels, bugs table, progress).

**At a glance:** presets (`--preset`) and presentation mode (`--demo`), optional **HTML** report, Ollama **preflight** and clearer **runtime errors**, **`OLLAMA_HOST`** for remote servers, **`pytest`** plus **GitHub Actions** CI.

## How it works

1. **Startup** — After **config** is loaded and DEV/QA model names are resolved (including CLI overrides), BugHunter queries Ollama for the local model list. If the server is unreachable or those models are not installed, the program exits with a short hint (use **`--skip-model-check`** to skip this, e.g. for debugging).
2. **DEV** (model from config) — generates Python code from the task description.
3. **Black** — code is formatted (`line_length` from `config.yml`) before linting.
4. **flake8** — static check (PEP 8, line length). Errors go into the bugs table and into DEV feedback.
5. **Execution** — generated code is saved to `solution.py` and run:
   - **Docker** (default): `python:3.11-slim`, read-only mount of `solution.py`, `--network none`, `--memory=128m`, `--cpus=0.5`, `--rm`. A temporary env check and optional test snippet are injected only for the run; the file is restored afterward so `solution.py` stays clean.
   - **Local fallback** — if Docker is not installed or the daemon is unreachable, code runs with the local Python (with the same temporary injection and restoration).
6. **QA** — second model receives task, code, linter and runtime output; should start the verdict with `VERDICT: PASS` or `VERDICT: ISSUES` (see `config.yml`). The app parses that line when present.
7. **Iterations** — QA and linter feedback are sent back to DEV for fixes; cycle repeats (limit set in config or via `-i`).
8. **Anti-loop** — if the model returns identical code while linter or QA still report issues, the loop stops ("Agent Stuck in Loop").
9. **Final cleanup** — when the target is achieved, `solution.py` is overwritten with only the approved code (Black-formatted, no debug or test snippets).

LLM output is normalized: the first ` ```python ... ``` ` block is extracted with a regex so extra text before/after does not end up in the file. Iteration logs are written to **bughunter_log.txt** in the background; the Rich UI is shown in the console.

**QA verdict** — if the QA response contains `VERDICT: PASS` or `VERDICT: ISSUES` (case-insensitive), that line decides success; otherwise the tool falls back to detecting `PASS` in the text (legacy).

## Execution timeouts

- **Docker sandbox**: subprocess timeout **15 seconds** (infinite loops or slow I/O in the container).
- **Local fallback** (when Docker is missing or unreachable): **5 seconds**.

These differ because container startup adds overhead; local runs are meant to fail fast.

## Requirements

- Python **3.11+** (aligned with CI; requires a current stdlib and typing style used in the repo)
- [Ollama](https://ollama.ai/) with a running server and models (names in `config.yml`; default `qwen2.5-coder:7b` for DEV and QA). To use a **remote** Ollama instance, set the **`OLLAMA_HOST`** environment variable (URL including scheme, e.g. `http://192.168.1.10:11434`) before starting BugHunter; the official Python client reads it automatically.
- **Docker** (optional) — for sandboxed execution. If Docker is not installed or not running, execution falls back to the local Python interpreter.
- Optional: **flake8** on your PATH for linting generated code (also listed in **`requirements.txt`** for dev/CI).

## Installation

```bash
pip install -r requirements.txt
```

Dependencies: `ollama`, `black`, `PyYAML`, `rich`, `pytest` (for the test suite in `tests/`).

## Quick start

1. Start **Ollama** and pull the models named in **`config.yml`** (defaults expect `ollama pull qwen2.5-coder:7b` unless you pass **`--model`** / **`--qa-model`**).
2. Install: `python -m venv .venv && .venv/bin/python -m pip install -r requirements.txt`
3. Verify: `.venv/bin/python main.py --version`
4. Run: `.venv/bin/python main.py` or e.g. `.venv/bin/python main.py --preset fibo --demo`

**Docker** is optional; if it is missing or the daemon is down, execution uses the same interpreter as in step 2.

## Tests

From the project root, with dependencies installed (recommended: virtual environment and `pip install -r requirements.txt`):

```bash
python -m pytest tests/
```

If your `venv` uses a different Python than the `pip` you invoked, use the same interpreter for both install and test, for example `.venv/bin/python -m pip install -r requirements.txt` then `.venv/bin/python -m pytest tests/`.

On GitHub, **CI** (`.github/workflows/ci.yml`) runs **`pytest`** and **`flake8`** on push and pull requests to `main` / `master` for Python 3.11–3.13. Flake8 rules live in **`.flake8`** (line length 88; long lines are ignored as **E501** so the tool matches Black-focused workflows).

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

Optional: run **flake8** locally the same way as CI:

```bash
python -m flake8 main.py ui_utils.py tests/
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

If the config file is missing or empty, the script exits with an error. By default the file **`config.yml`** in the project root (next to `main.py`) is used; override with **`-c` / `--config PATH`**.

**Exit codes:** `0` — finished the hunt loop (success or max iterations). `1` — config / startup checks (missing config, empty YAML, Ollama unreachable or missing models during preflight). `2` — Ollama request failed during DEV or QA chat (e.g. connection dropped mid-run).

## Usage (CLI)

```bash
python main.py
```

Without arguments, the default task is a short one (implement `add(a, b)`). Use **`--preset`** for built-in demos: `sum` (same as default), `fibo` (Fibonacci list), `path` (nested dict path resolver). If you pass both a positional task and **`--preset`**, the preset wins and the positional task is ignored (with an info message).

**`--demo`** turns on presentation mode: Rich section rules between iterations and a short pause so output is easier to follow when presenting or recording.

Custom task as positional argument:

```bash
python main.py "Write a function that returns the factorial of n."
```

Flags override config:

| Argument | Description |
|----------|-------------|
| `--version` | Print BugHunter version and exit (no run). |
| `task` | Task description (optional positional; default is a short `add(a, b)` task). |
| `-c`, `--config PATH` | YAML config file (default: `config.yml` next to `main.py`). |
| `--preset NAME` | Built-in task: `sum`, `fibo`, or `path`. Overrides positional `task` when set. |
| `--demo` | Presentation mode: section dividers between iterations and short pauses. |
| `--skip-model-check` | Do not verify Ollama reachability or that DEV/QA models are installed locally. |
| `-i`, `--iters N` | Max iterations (overrides `settings.max_iterations`). |
| `--model NAME` | Ollama model for DEV (overrides `models.dev`). |
| `--qa-model NAME` | Ollama model for QA (overrides `models.qa`). |
| `--html-report PATH` | After the run, write a static HTML summary of each iteration (task, code, linter, runtime, QA). |
| `-t`, `--test PYCODE` | Python code to append at the end of the script for testing (e.g. `print(my_func(10))`). Injected only during execution; not saved to `solution.py`. |

Examples:

```bash
python main.py
python main.py --version
python main.py --preset fibo --demo
python main.py --preset path -i 8
python main.py --preset fibo --html-report report.html
python main.py -c ./config.yml --qa-model mistral
python main.py "Sum of a list of numbers"
python main.py "Factorial" -i 10 --model llama3
python main.py "Write a sum function" --test "print(sum(5, 5))"
python main.py "Parse CSV into dict" --iters 3
```

## UI (Rich)

- **Banner** — BugHunter title panel at start.
- **LLM status** — Spinner with "LLM generating code..." / "LLM analyzing code..." during model calls.
- **[AI Assistant] panels** — DEV output (code with syntax highlight). QA output is rendered as **Markdown** inside the panel when the model uses headings, lists, or emphasis.
- **Bugs table** — After QA: error type, line, severity, recommendation (including flake8 output and QA verdict).
- **Progress** — Iteration bar with percentage and time remaining.
- **Summary** — Panel with paths to `solution.py` and log file; then panel with final code (Syntax, monokai theme).

## Output

- **solution.py** — final generated code only (no debug or test snippets). Overwritten with clean, Black-formatted code when the target is achieved. In `.gitignore`.
- **bughunter_log.txt** — step-by-step iteration log, including Docker command and raw stdout/stderr when using the sandbox. Written in the background; in `.gitignore`.
- **Optional HTML report** — with `--html-report PATH`, a single static HTML file is written after the hunt: task plus one section per completed iteration (code, linter, runtime, QA; long fields are truncated for file size). Safe for sharing (content is HTML-escaped in `<pre>` blocks).

## Project structure

- **main.py** — config load, argparse, `BugHunter` class (Docker/local execution, regex extraction, final clean write), entry point under `if __name__ == "__main__"`.
- **ui_utils.py** — Rich console, status spinners, panels (including Markdown for QA), tables, syntax highlight, background file logging, optional HTML report writer.
- **pyproject.toml** — pytest and Black tool defaults.
- **.flake8** — flake8 defaults for local runs and CI.
- **.github/workflows/ci.yml** — GitHub Actions: pytest + flake8 on supported Python versions.
- **CHANGELOG.md** — release notes.
- **LICENSE** — MIT.
- **config.yml** — models, limits, prompts (required to run).
- **tests/** — `pytest` unit tests for verdict parsing, markdown stripping, config load, CLI parser, linter row parsing, HTML report, Ollama helpers.
