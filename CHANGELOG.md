# Changelog

All notable changes to BugHunter are documented in this file.

## [1.0.0] — 2026-05-14

First stable release for local / team use from a git clone.

### Highlights

- **Dual-LLM loop** — Developer model writes Python; QA model reviews with `VERDICT: PASS` / `VERDICT: ISSUES` (with legacy `PASS` fallback).
- **Tooling** — Black (`line_length` from config), optional flake8, markdown fence extraction for `solution.py`.
- **Execution** — Docker sandbox (`python:3.11-slim`, no network, resource limits) or local fallback using **`sys.executable`**.
- **CLI** — Positional task, `--preset` (sum / fibo / path), `--demo`, `-c/--config`, `--model`, `--qa-model`, `--html-report`, `--test`, `--skip-model-check`, `--version`.
- **Ollama** — Preflight model list check; **`ollama_chat_or_exit`** with clear errors; exit codes **1** (config/preflight) and **2** (chat failure); **`OLLAMA_HOST`** supported via the client.
- **UI** — Rich banner, spinners, DEV syntax panel, QA Markdown panel, bugs table, progress, final summary and code panel.
- **Outputs** — `solution.py` when successful; background **`bughunter_log.txt`**; optional static HTML report.
- **Quality** — Pytest suite, GitHub Actions (Python 3.11–3.13), flake8 (`.flake8`), `pyproject.toml` for pytest/Black.
