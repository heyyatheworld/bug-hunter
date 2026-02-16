# BugHunter

A tool for automatic Python code generation and verification using two LLMs: one acts as a developer, the other as a QA engineer. The code is executed, and both the result and the code itself are passed to QA; if issues are found, the cycle repeats until "PASS" is achieved or iterations are exhausted.

## How It Works

1. **Developer (DEV)** — generates Python code based on task description (default model: `llama3`).
2. **Execution** — generated code is saved to `solution.py` and executed via `subprocess`.
3. **QA** — the second model (`qwen2.5-coder:7b`) receives the code and execution output/error, searching for bugs and weak points.
4. **Iterations** — if QA doesn't write "PASS", their feedback is sent to the developer for fixes, and the cycle repeats (default: up to 2 additional iterations).

Each iteration's logs are written to `bughunter_log.txt`.

## Requirements

- Python 3.x
- [Ollama](https://ollama.ai/) with running server and downloaded models:
  - `llama3` (DEV)
  - `qwen2.5-coder:7b` (QA)

## Installation

```bash
pip install ollama
```

Or with a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install ollama
```

Make sure Ollama is running and models are downloaded:

```bash
ollama pull llama3
ollama pull qwen2.5-coder:7b
```

## Usage

```bash
python main.py
```

By default, it solves: "Write a function that downloads an image from a URL and saves it. Add URL validation."

To solve your own task, modify the `task_to_solve` variable at the end of `main.py` or pass it to `start_hunt()`.

### Configuration

You can configure the following at the top of `main.py`:

| Variable     | Description                    | Default              |
|-------------|--------------------------------|----------------------|
| `DEV_MODEL` | Developer model                | `llama3`             |
| `QA_MODEL`  | QA model                       | `qwen2.5-coder:7b`   |
| `LOG_FILE`  | Iteration log file             | `bughunter_log.txt`  |
| `RESULT_FILE` | Final code file              | `solution.py`        |

In `start_hunt(task, iterations=2)`:
- `task` — task description for the developer;
- `iterations` — number of additional "fix based on QA feedback" iterations (0 = only initial generation and one QA check).

## Output

- **solution.py** — latest version of generated code.
- **bughunter_log.txt** — step-by-step log: code, execution result, and QA response for each iteration.
