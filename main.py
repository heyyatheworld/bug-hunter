import argparse
import sys

import black
import ollama
import os
import shutil
import subprocess

PROJECT_NAME = "BugHunter"
DEV_MODEL = "qwen2.5-coder:7b"
QA_MODEL = "qwen2.5-coder:7b"
LOG_FILE = "bughunter_log.txt"
RESULT_FILE = "solution.py"
MAX_ITERATIONS = 10
MAX_LINE_LENGTH = 88
DEFAULT_TASK = "Write a function that returns the sum of a list of numbers. Use a docstring and PEP 8."

def run_linter(filename):
    """Run flake8 on the file. Returns linter errors or 'LINTER: OK'. Handles missing flake8."""
    if not shutil.which("flake8"):
        return "LINTER: flake8 not installed, skipped."
    try:
        result = subprocess.run(
            ["flake8", filename, f"--max-line-length={MAX_LINE_LENGTH}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return "LINTER: OK"
        return f"LINTER:\n{result.stdout or result.stderr}".strip()
    except Exception as e:
        return f"LINTER ERROR: {e}"

def run_generated_code(filename, test_append=None):
    """Runs the file. If test_append is set, appends it to the file, runs, then restores original content."""
    content_orig = None
    if test_append:
        with open(filename, "r", encoding="utf-8") as f:
            content_orig = f.read()
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content_orig + "\n" + test_append.strip() + "\n")
    try:
        result = subprocess.run(['python', filename], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            out = f"SUCCESS. Output:\n{result.stdout}"
        else:
            out = f"RUNTIME ERROR:\n{result.stderr}"
        return out
    except Exception as e:
        return f"EXECUTION FAILED: {str(e)}"
    finally:
        if content_orig is not None:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content_orig)

def save_to_log(text):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n" + "="*50 + "\n")

def apply_black_formatting(code: str) -> str:
    """Format code with black (line_length=88). Returns formatted string; handles NothingChanged."""
    try:
        return black.format_str(code, mode=black.FileMode(line_length=MAX_LINE_LENGTH))
    except black.NothingChanged:
        return code

def format_code(filename):
    """Format file with black (PEP 8, strict line length). No-op if NothingChanged."""
    with open(filename, "r", encoding="utf-8") as f:
        code = f.read()
    try:
        formatted = black.format_str(code, mode=black.FileMode(line_length=MAX_LINE_LENGTH))
        with open(filename, "w", encoding="utf-8") as f:
            f.write(formatted)
    except black.NothingChanged:
        pass

def _strip_markdown(code: str) -> str:
    """Remove Markdown code fence artifacts (e.g. ```python, ```) from model output."""
    s = code.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines)
    return s.replace("```python", "").replace("```", "").strip()

def save_final_code(code):
    """Save code to RESULT_FILE after removing Markdown artifacts. Expects already formatted code."""
    clean_code = _strip_markdown(code)
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        f.write(clean_code)

def start_hunt(task, test_call=None, max_iters=5, model_name=None):
    dev_model = model_name if model_name is not None else DEV_MODEL
    if os.path.exists(LOG_FILE): os.remove(LOG_FILE)
    print(f"🕵️‍♂️ {PROJECT_NAME} is on the hunt...")
    save_to_log(f"TARGET TASK: {task}")

    current_code = ""
    feedback = ""
    linter_result = ""
    execution_result = ""
    linter_ok = True

    QA_SYSTEM = (
        "You are a strict QA engineer. You receive TASK, CODE, linter result, and runtime result. "
        "You MUST do the following in order:\n"
        "1) Extract and list each requirement from TASK (one per line).\n"
        "2) For each requirement, analyze CODE and the run results, then write CHECK or X next to it.\n"
        "3) If at least one requirement has X, you are FORBIDDEN to write PASS; list what is wrong.\n"
        "4) Only if every requirement has CHECK and there are no linter/runtime errors may you write PASS."
    )

    DEV_SYSTEM_RULES = (
        "GOLDEN RULES OF FORMATTING (mandatory):\n"
        "• Short Docstrings: Split docstrings into multiple lines; no line over 80 characters.\n"
        "• Variable Extraction: Never put complex computations inside f-strings. Extract to variables first (e.g. orig_slice = original_numbers[:5]), then use only variable names in f-strings.\n"
        "• Multiline Returns: For long return strings use parentheses: return ( f\"Part one: {a}\" f\"Part two: {b}\" ). One logical part per line.\n"
        "• Neighbors: For neighbor logic use only: for i in range(1, len(arr) - 1):. No enumerate-with-slices.\n"
        "• PEP 8: Two blank lines before each def; no trailing spaces; one blank line at end of file."
    )

    for i in range(max_iters):
        if i > 0:
            prev_lines = len(current_code.strip().splitlines())
            print(f"\n--- Iteration {i} (fix round) ---")
            print(f"  Passing to DEV: previous code ({prev_lines} lines), QA feedback, linter & runtime from last run.")
            print(f"  Linter (last): {linter_result[:80]}..." if len(linter_result) > 80 else f"  Linter (last): {linter_result}")
            print(f"  Runtime (last): {execution_result[:80]}..." if len(execution_result) > 80 else f"  Runtime (last): {execution_result}")
            print(f"  QA said: {feedback[:120]}..." if len(feedback) > 120 else f"  QA said: {feedback}")

        role_desc = "You are a Senior Developer." if i == 0 else "Fix bugs found by QA. You MUST fix the code below; do not repeat the same mistakes."
        dev_system_content = f"{role_desc}\n\n{DEV_SYSTEM_RULES}\n\nWrite ONLY Python code. No text except code comments."
        if i > 0 and not linter_ok:
            pep8_block = (
                "ВНИМАНИЕ: Убедись, что перед определением функции def ровно ДВЕ пустые строки, "
                "а в самом конце файла — одна пустая строка. Не оставляй пробелов в конце строк.\n\n"
                f"Твой код не прошел проверку PEP8. Исправь следующие ошибки:\n{linter_result}\n\n"
            )
        else:
            pep8_block = ""

        print(f"\n🛠 [{i}] {dev_model.upper()} generating solution...")
        
        dev_user_content = (
            task if i == 0
            else (
                pep8_block
                + "The following code from the PREVIOUS iteration had the errors below. "
                "Output ONLY the corrected Python code (no explanations).\n\n"
                "--- ERRORS FROM PREVIOUS RUN ---\n"
                f"QA feedback:\n{feedback}\n\n"
                f"Linter result:\n{linter_result}\n\n"
                f"Runtime result:\n{execution_result}\n\n"
                "--- CODE TO FIX (from previous iteration) ---\n"
                f"{current_code}"
            )
        )
        response = ollama.chat(
            model=dev_model,
            messages=[
                {'role': 'system', 'content': dev_system_content},
                {'role': 'user', 'content': dev_user_content}
            ],
            options={'temperature': 0}
        )
        
        code_before_iteration = current_code
        raw_code = response['message']['content']
        current_code = apply_black_formatting(_strip_markdown(raw_code))
        save_final_code(current_code)

        linter_result = run_linter(RESULT_FILE)
        linter_ok = linter_result.strip() == "LINTER: OK" or "not installed, skipped" in linter_result

        if i > 0 and current_code == code_before_iteration and not linter_ok:
            print(f"\n⚠️ STUCK_IN_LOOP: Code unchanged and linter still reports errors. Stopping.")
            print(f"Linter output:\n{linter_result}")
            save_to_log(f"STUCK_IN_LOOP\nLINTER:\n{linter_result}")
            break

        execution_result = run_generated_code(RESULT_FILE, test_append=test_call)
        runtime_ok = execution_result.startswith("SUCCESS")
        new_lines = len(current_code.strip().splitlines())
        print(f"  DEV produced {new_lines} lines. Linter: {'OK' if linter_ok else 'ISSUES'} | Runtime: {'OK' if runtime_ok else 'ERROR'}")

        feedback_data = f"TASK:\n{task}\n\nCODE:\n{current_code}\n\nLINTER RESULT:\n{linter_result}\n\nRUNTIME RESULT:\n{execution_result}"
        print(f"🔍 [{i}] {QA_MODEL.upper()} searching for issues...")
        qa_response = ollama.chat(
            model=QA_MODEL,
            messages=[
                {'role': 'system', 'content': QA_SYSTEM},
                {'role': 'user', 'content': feedback_data}
            ],
            options={'temperature': 0}
        )
        
        feedback = qa_response['message']['content']
        qa_pass = "PASS" in feedback.upper()
        print(f"  QA verdict: {'PASS' if qa_pass else 'issues'}")
        print(f"  QA response (excerpt): {feedback[:200]}..." if len(feedback) > 200 else f"  QA response: {feedback}")
        save_to_log(f"ITERATION {i}\nCODE:\n{current_code}\nLINTER:\n{linter_result}\nRUNTIME:\n{execution_result}\nQA FEEDBACK:\n{feedback}")

        if qa_pass and not linter_ok and i > 0:
            msg = "QA одобрил, но Линтер против. Продолжаем полировку"
            save_to_log(msg)
            print(f"⚠️ {msg}")

        if qa_pass and linter_ok and i > 0:
            print("\n🎯 No errors or warnings. Target achieved!")
            break
        else:
            if not linter_ok:
                print(f"⚠️ Linter issues (or errors), sending for revision.")
            else:
                print(f"⚠️ Issue found, sending for revision.")
    else:
        print(f"\n⚠️ Reached {max_iters} attempts without full pass. Task may be too complex for current setup.")

    print(f"\n🏆 Hunt completed! Final code in {RESULT_FILE}, logs in {LOG_FILE}")

def _build_parser():
    parser = argparse.ArgumentParser(
        prog="BugHunter",
        description="Generate and refine Python code from a task description using LLM (DEV + QA) and linter.",
        epilog=(
            "Examples:\n"
            "  python main.py \"Write a function that returns the sum of a list\"\n"
            "  python main.py \"Implement factorial(n)\" -i 10 --model llama3\n"
            "  python main.py \"Parse CSV and return dict\" --iters 3"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "task",
        type=str,
        nargs="?",
        default=DEFAULT_TASK,
        help="Task description for code generation (default: sum-of-list example).",
    )
    parser.add_argument(
        "-i", "--iters",
        type=int,
        default=5,
        metavar="N",
        help="Maximum number of iterations (default: 5).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        metavar="NAME",
        help="Ollama model name for the developer (default: qwen2.5-coder:7b).",
    )
    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()
    task = (args.task or "").strip() or DEFAULT_TASK
    task_preview = task[:60] + "..." if len(task) > 60 else task
    print(f"BugHunter: Starting task \"{task_preview}\" with model {args.model or DEV_MODEL} (Max iters: {args.iters})")
    start_hunt(task, max_iters=args.iters, model_name=args.model)