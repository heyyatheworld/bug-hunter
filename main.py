"""
BugHunter — CLI for LLM-based code generation with linter and QA feedback.
All entrypoint logic runs under if __name__ == "__main__".
"""

import argparse
import os
import shutil
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
    result_panel,
    show_banner,
    status_spinner,
    step_result,
    success,
    warning,
)

PROJECT_NAME = "BugHunter"
LOG_FILE = "bughunter_log.txt"
RESULT_FILE = "solution.py"
DEFAULT_TASK = "Write a function that returns the sum of a list of numbers. Use a docstring and PEP 8."
CONFIG_FILENAME = "config.yml"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# BugHunter
# ---------------------------------------------------------------------------

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
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(text + "\n" + "=" * 50 + "\n")

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
        content_orig = None
        if test_append:
            with open(filename, "r", encoding="utf-8") as f:
                content_orig = f.read()
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content_orig + "\n" + test_append.strip() + "\n")
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
        except Exception as e:
            return f"EXECUTION FAILED: {str(e)}"
        finally:
            if content_orig is not None:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content_orig)

    def _apply_black(self, code: str) -> str:
        try:
            return black.format_str(code, mode=black.FileMode(line_length=self.line_length))
        except black.NothingChanged:
            return code

    def _strip_markdown(self, code: str) -> str:
        s = code.strip()
        if s.startswith("```"):
            lines = s.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            s = "\n".join(lines)
        return s.replace("```python", "").replace("```", "").strip()

    def _save_solution(self, code: str) -> None:
        """Save code to RESULT_FILE: strip Markdown then write (code must already be Black-formatted)."""
        clean = self._strip_markdown(code)
        with open(RESULT_FILE, "w", encoding="utf-8") as f:
            f.write(clean)

    def hunt(self, task: str, test_call: str | None = None) -> None:
        if os.path.exists(LOG_FILE):
            os.remove(LOG_FILE)
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
                with status_spinner("[bold green]DEV model generating code..."):
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
                with status_spinner("[bold green]QA model analyzing..."):
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
                    warning("Linter issues — sending for revision.")
                else:
                    warning("QA found issues — sending for revision.")
            else:
                warning(f"Reached {self.max_iters} iterations without full pass.")

        final_summary(RESULT_FILE, LOG_FILE, achieved)
        if os.path.isfile(RESULT_FILE):
            with open(RESULT_FILE, "r", encoding="utf-8") as f:
                final_result_panel(f.read(), title=f"Final result — {RESULT_FILE}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

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
    return parser


if __name__ == "__main__":
    show_banner(PROJECT_NAME)
    config = load_config()
    parser = _build_parser()
    args = parser.parse_args()
    task = (args.task or "").strip() or DEFAULT_TASK
    max_iters = getattr(args, "iters", None)
    model = getattr(args, "model", None)

    hunter = BugHunter(config, dev_model_override=model, max_iters_override=max_iters)
    preview = task[:60] + "..." if len(task) > 60 else task
    info(f"Starting \"{preview}\" | model={hunter.dev_model} | max_iters={hunter.max_iters}")
    hunter.hunt(task)
