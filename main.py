"""BugHunter: CLI for LLM-based code generation with linter and QA feedback."""

import argparse
import os
import re
import shutil
import socket
import subprocess
import sys

import black
import ollama
import yaml

from ui_utils import (
    dev_qa_line,
    error,
    final_result_panel,
    final_summary,
    info,
    iteration_header,
    iteration_progress,
    log_background,
    panel_ai_assistant,
    parse_linter_to_bug_rows,
    result_panel,
    show_banner,
    start_background_logger,
    status_llm_thinking,
    step_result,
    stop_background_logger,
    success,
    table_bugs,
    warning,
)

PROJECT_NAME = "BugHunter"
LOG_FILE = "bughunter_log.txt"
RESULT_FILE = "solution.py"
DEFAULT_TASK = "Write a function that counts Fibonacci numbers up to the tenth number. Use a docstring and PEP 8."
CONFIG_FILENAME = "config.yml"


def load_config(path: str | None = None) -> dict:
    """Load YAML config. path defaults to config.yml next to script or in cwd. Raises if missing."""
    if path is None:
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, CONFIG_FILENAME)
    if not os.path.isfile(path):
        error(f"Config file not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data:
        error("Config file is empty.")
        sys.exit(1)
    return data


class BugHunter:
    """Orchestrates code generation, formatting, linting, and QA feedback loop."""

    def __init__(self, config: dict, dev_model_override: str | None = None, max_iters_override: int | None = None):
        self.config = config
        models = config.get("models") or {}
        settings = config.get("settings") or {}
        self.dev_model = dev_model_override or models.get("dev") or "qwen2.5-coder:7b"
        self.qa_model = models.get("qa") or "qwen2.5-coder:7b"
        self.max_iters = max_iters_override if max_iters_override is not None else settings.get("max_iterations", 5)
        self.line_length = settings.get("line_length", 88)
        prompts = config.get("prompts") or {}
        dev_tpl = prompts.get("developer") or "You are a senior Python developer. Write clean code."
        qa_tpl = prompts.get("qa") or "Analyze the code for logic and PEP 8."
        self.prompt_developer = dev_tpl.format(line_length=self.line_length)
        self.prompt_qa = qa_tpl

    def _log(self, text: str) -> None:
        log_background(text)

    def _run_linter(self, filename: str) -> str:
        if not shutil.which("flake8"):
            return "LINTER: flake8 not installed, skipped."
        try:
            result = subprocess.run(
                ["flake8", filename, f"--max-line-length={self.line_length}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return "LINTER: OK"
            return f"LINTER:\n{result.stdout or result.stderr}".strip()
        except Exception as e:
            return f"LINTER ERROR: {e}"

    def _run_generated_code(self, filename: str, test_append: str | None = None) -> str:
        """Run generated code in a Docker sandbox; optionally fall back to local Python."""

        def _run_local() -> str:
            try:
                result = subprocess.run(
                    ["python", filename],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return f"SUCCESS. Output:\n{result.stdout}"
                return f"RUNTIME ERROR:\n{result.stderr}"
            except subprocess.TimeoutExpired:
                self._log("ERROR: Local execution timed out after 5 seconds")
                return "EXECUTION TIMEOUT (local)"
            except Exception as exc:  # noqa: BLE001
                return f"EXECUTION FAILED (local): {exc}"

        # Always append an environment check, optionally followed by a test call.
        content_orig: str | None = None
        with open(filename, "r", encoding="utf-8") as f:
            content_orig = f.read()

        env_check_snippet = (
            "import os, socket\n"
            "print(f'--- ENVIRONMENT CHECK: Is Docker? {os.path.exists(\"/.dockerenv\")} | "
            "{socket.gethostname()} ---')"
        )

        with open(filename, "w", encoding="utf-8") as f:
            f.write(content_orig.rstrip() + "\n" + env_check_snippet + "\n")
            if test_append:
                f.write(test_append.strip() + "\n")

        abs_path = os.path.abspath(filename)
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--memory=128m",
            "--cpus=0.5",
            "-v",
            f"{abs_path}:/app/solution.py:ro",
            "python:3.11-slim",
            "python",
            "/app/solution.py",
        ]

        try:
            if shutil.which("docker") is None:
                warning("Docker is not available on PATH, falling back to local execution.")
                return _run_local()

            self._log(f"DEBUG: Running Docker command: {' '.join(docker_cmd)}")

            try:
                result = subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
            except subprocess.TimeoutExpired:
                self._log("ERROR: Container execution timed out after 15 seconds")
                return "EXECUTION TIMEOUT (Docker sandbox)"

            self._log(f"DOCKER STDOUT: {result.stdout}")
            self._log(f"DOCKER STDERR: {result.stderr}")

            if result.returncode == 0:
                return f"SUCCESS. Output:\n{result.stdout}"

            stderr = result.stderr or ""
            if "Cannot connect to the Docker daemon" in stderr or "docker: command not found" in stderr:
                warning("Docker daemon is not running or unreachable, falling back to local execution.")
                return _run_local()

            return f"RUNTIME ERROR:\n{stderr or result.stdout}"
        except Exception as exc:  # noqa: BLE001
            warning(f"Docker execution failed ({exc}), falling back to local execution.")
            return _run_local()
        finally:
            if content_orig is not None:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content_orig)

    def _apply_black(self, code: str) -> str:
        try:
            return black.format_str(code, mode=black.FileMode(line_length=self.line_length))
        except (black.NothingChanged, black.parsing.InvalidInput):
            return code

    def _strip_markdown(self, code: str) -> str:
        """Extract Python code from markdown fences produced by the LLM."""
        # 1) Try to extract the first ```python ... ``` block (case-insensitive)
        match = re.search(r"```python\s*(.*?)```", code, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # 2) Fallback: extract the first generic ``` ... ``` block (any language or none)
        match = re.search(r"```\s*(.*?)```", code, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 3) No fenced blocks at all: return cleaned original text
        return code.strip()

    def _save_solution(self, code: str) -> None:
        """Save code to RESULT_FILE: strip Markdown and ensure trailing newline."""
        clean = self._strip_markdown(code)
        if not clean.endswith("\n"):
            clean = clean + "\n"
        with open(RESULT_FILE, "w", encoding="utf-8") as f:
            f.write(clean)

    def hunt(self, task: str, test_call: str | None = None) -> None:
        success(f"{PROJECT_NAME} is on the hunt...")
        self._log(f"TARGET TASK: {task}")

        current_code = ""
        feedback = ""
        linter_result = ""
        execution_result = ""
        linter_ok = True
        achieved = False

        with iteration_progress(self.max_iters, "Iterations") as (progress, task_id):
            for i in range(self.max_iters):
                if i > 0:
                    iteration_header(
                        i,
                        linter_result[:80] + "..." if len(linter_result) > 80 else linter_result,
                        execution_result[:80] + "..." if len(execution_result) > 80 else execution_result,
                        feedback[:120] + "..." if len(feedback) > 120 else feedback,
                    )

                dev_system = self.prompt_developer
                if i > 0:
                    dev_system += "\n\nFix the code below. Output ONLY Python code (no explanations)."
                if i > 0 and not linter_ok:
                    dev_system += f"\n\nPEP8 errors to fix:\n{linter_result}\n"

                dev_user = (
                    task
                    if i == 0
                    else (
                        f"QA feedback:\n{feedback}\n\n"
                        f"Linter:\n{linter_result}\n\nRuntime:\n{execution_result}\n\n"
                        f"Code to fix:\n{current_code}"
                    )
                )

                dev_qa_line(i, self.dev_model, "generating")
                with status_llm_thinking("LLM generating code..."):
                    response = ollama.chat(
                        model=self.dev_model,
                        messages=[
                            {"role": "system", "content": dev_system},
                            {"role": "user", "content": dev_user},
                        ],
                        options={"temperature": 0},
                    )

                code_before = current_code
                raw = response["message"]["content"]
                current_code = self._apply_black(self._strip_markdown(raw))
                self._save_solution(current_code)
                panel_ai_assistant(current_code[:2000] + ("..." if len(current_code) > 2000 else ""), role="DEV", as_code=True)

                linter_result = self._run_linter(RESULT_FILE)
                linter_ok = linter_result.strip() == "LINTER: OK" or "not installed, skipped" in linter_result

                if i > 0 and current_code == code_before and not linter_ok:
                    error("Agent Stuck in Loop: code unchanged and linter still fails. Stopping.")
                    result_panel(linter_result, title="Linter output")
                    self._log(f"Agent Stuck in Loop\nLINTER:\n{linter_result}")
                    break
                if i > 0 and current_code == code_before:
                    qa_pass_prev = "PASS" in feedback.upper()
                    if qa_pass_prev:
                        warning("Agent Stuck in Loop: code unchanged (QA had passed). Stopping.")
                        self._log("Agent Stuck in Loop (same code, QA had passed)")
                        break

                execution_result = self._run_generated_code(RESULT_FILE, test_append=test_call)
                runtime_ok = execution_result.startswith("SUCCESS")
                step_result(len(current_code.strip().splitlines()), linter_ok, runtime_ok)

                feedback_data = f"TASK:\n{task}\n\nCODE:\n{current_code}\n\nLINTER:\n{linter_result}\n\nRUNTIME:\n{execution_result}"
                dev_qa_line(i, self.qa_model, "analyzing")
                with status_llm_thinking("LLM analyzing code..."):
                    qa_response = ollama.chat(
                        model=self.qa_model,
                        messages=[
                            {"role": "system", "content": self.prompt_qa},
                            {"role": "user", "content": feedback_data},
                        ],
                        options={"temperature": 0},
                    )
                feedback = qa_response["message"]["content"]
                qa_pass = "PASS" in feedback.upper()
                panel_ai_assistant(feedback[:1500] + ("..." if len(feedback) > 1500 else ""), role="QA", as_code=False)
                bug_rows = parse_linter_to_bug_rows(linter_result)
                bug_rows.append((
                    "QA Verdict",
                    "-",
                    "PASS" if qa_pass else "ISSUES",
                    feedback[:120] + ("..." if len(feedback) > 120 else ""),
                ))
                table_bugs(bug_rows)
                if qa_pass:
                    success("QA: PASS")
                else:
                    warning("QA: issues")

                self._log(f"ITERATION {i}\nCODE:\n{current_code}\nLINTER:\n{linter_result}\nRUNTIME:\n{execution_result}\nQA:\n{feedback}")

                progress.update(task_id, advance=1)

                if qa_pass and linter_ok and i > 0:
                    achieved = True
                    success("Target achieved!")
                    break
                if not linter_ok:
                    warning("Linter issues - sending for revision.")
                else:
                    warning("QA found issues - sending for revision.")
            else:
                warning(f"Reached {self.max_iters} iterations without full pass.")

        final_summary(RESULT_FILE, LOG_FILE, achieved)
        if os.path.isfile(RESULT_FILE):
            with open(RESULT_FILE, "r", encoding="utf-8") as f:
                final_result_panel(f.read(), title=f"Final result: {RESULT_FILE}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="BugHunter",
        description="Generate and refine Python code from a task (config: config.yml).",
        epilog="Examples:\n  python main.py \"sum of list\"\n  python main.py \"factorial\" -i 10 --model llama3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("task", type=str, nargs="?", default=DEFAULT_TASK, help="Task description.")
    parser.add_argument("-i", "--iters", type=int, default=None, metavar="N", help="Override max iterations from config.")
    parser.add_argument("--model", type=str, default=None, metavar="NAME", help="Override DEV model from config.")
    parser.add_argument(
        "-t",
        "--test",
        type=str,
        default=None,
        metavar="PYCODE",
        help="Python code to append at the end of the script for testing (e.g., \"print(my_func(10))\").",
    )
    return parser


if __name__ == "__main__":
    show_banner(PROJECT_NAME)
    start_background_logger(LOG_FILE, clear=True)
    try:
        config = load_config()
        parser = _build_parser()
        args = parser.parse_args()
        task = (args.task or "").strip() or DEFAULT_TASK
        max_iters = getattr(args, "iters", None)
        model = getattr(args, "model", None)
        test_call = getattr(args, "test", None)

        hunter = BugHunter(config, dev_model_override=model, max_iters_override=max_iters)
        preview = task[:60] + "..." if len(task) > 60 else task
        info(f"Starting \"{preview}\" | model={hunter.dev_model} | max_iters={hunter.max_iters}")
        hunter.hunt(task, test_call=test_call)
    finally:
        stop_background_logger()
