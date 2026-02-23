import ollama
import os
import shutil
import subprocess

PROJECT_NAME = "BugHunter"
DEV_MODEL = "llama3"
QA_MODEL = "qwen2.5-coder:7b"
LOG_FILE = "bughunter_log.txt"
RESULT_FILE = "solution.py"

def run_linter(filename):
    """Run flake8 on the file. Returns linter errors or 'LINTER: OK'. Handles missing flake8."""
    if not shutil.which("flake8"):
        return "LINTER: flake8 not installed, skipped."
    try:
        result = subprocess.run(
            ["flake8", filename, "--max-line-length=88"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return "LINTER: OK"
        return f"LINTER:\n{result.stdout or result.stderr}".strip()
    except Exception as e:
        return f"LINTER ERROR: {e}"

def run_generated_code(filename):
    """Attempts to run the code and returns the result or error."""
    try:
        result = subprocess.run(['python', filename], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return f"SUCCESS. Output:\n{result.stdout}"
        else:
            return f"RUNTIME ERROR:\n{result.stderr}"
    except Exception as e:
        return f"EXECUTION FAILED: {str(e)}"

def save_to_log(text):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n" + "="*50 + "\n")

def save_final_code(code):
    clean_code = code.replace("```python", "").replace("```", "").strip()
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        f.write(clean_code)

def start_hunt(task, iterations=2):
    if os.path.exists(LOG_FILE): os.remove(LOG_FILE)
    print(f"🕵️‍♂️ {PROJECT_NAME} is on the hunt...")
    save_to_log(f"TARGET TASK: {task}")

    current_code = ""

    for i in range(iterations + 1):
        role_desc = "You are a Senior Developer." if i == 0 else "Fix bugs found by QA."
        print(f"🛠 [{i}] {DEV_MODEL.upper()} generating solution...")
        
        response = ollama.chat(model=DEV_MODEL, messages=[
            {'role': 'system', 'content': f"{role_desc} Write ONLY Python code. No text except code comments."},
            {'role': 'user', 'content': task if i == 0 else f"Fix this:\n{feedback}\nCode:\n{current_code}"}
        ])
        
        current_code = response['message']['content']
        save_final_code(current_code)

        linter_result = run_linter(RESULT_FILE)
        execution_result = run_generated_code(RESULT_FILE)
        feedback_data = f"LINTER RESULT:\n{linter_result}\n\nRUNTIME RESULT:\n{execution_result}"

        print(f"🔍 [{i}] {QA_MODEL.upper()} searching for issues...")
        qa_response = ollama.chat(model=QA_MODEL, messages=[
            {'role': 'system', 'content': "You are a strict QA engineer. You receive code plus: 1) static check (linter) result (PEP8/style), 2) runtime result. Find any errors—style or execution. Only write 'PASS' if the code is clean and runs correctly."},
            {'role': 'user', 'content': f"CODE:\n{current_code}\n\n{feedback_data}"}
        ])
        
        feedback = qa_response['message']['content']
        save_to_log(f"ITERATION {i}\nCODE:\n{current_code}\nLINTER:\n{linter_result}\nRUNTIME:\n{execution_result}\nQA FEEDBACK:\n{feedback}")

        if "PASS" in feedback.upper() and i > 0:
            print("🎯 No errors found. Target achieved!")
            break
        else:
            print(f"⚠️ Issue found, sending for revision.")

    print(f"\n🏆 Hunt completed! Final code in {RESULT_FILE}, logs in {LOG_FILE}")

if __name__ == "__main__":
    task_to_solve = "Write a function analyze_text(text) that returns a dictionary containing the total word count, the most frequent word, and a frequency map of all words ≥ 3 characters, ignoring case and punctuation."
    start_hunt(task_to_solve)