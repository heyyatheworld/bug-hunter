import ollama
import os
import subprocess

PROJECT_NAME = "BugHunter"
DEV_MODEL = "llama3"
QA_MODEL = "qwen2.5-coder:7b"
LOG_FILE = "bughunter_log.txt"
RESULT_FILE = "solution.py"

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

        execution_result = run_generated_code(RESULT_FILE)
        
        print(f"🔍 [{i}] {QA_MODEL.upper()} searching for issues...")
        qa_response = ollama.chat(model=QA_MODEL, messages=[
            {'role': 'system', 'content': "You are a strict QA engineer. You received code and its execution result. Find errors. If everything works perfectly and the code is clean, write 'PASS'."},
            {'role': 'user', 'content': f"CODE:\n{current_code}\n\nEXECUTION RESULT:\n{execution_result}"}
        ])
        
        feedback = qa_response['message']['content']
        save_to_log(f"ITERATION {i}\nCODE:\n{current_code}\nRESULT:\n{execution_result}\nQA FEEDBACK:\n{feedback}")

        if "PASS" in feedback.upper() and i > 0:
            print("🎯 No errors found. Target achieved!")
            break
        else:
            print(f"⚠️ Issue found, sending for revision.")

    print(f"\n🏆 Hunt completed! Final code in {RESULT_FILE}, logs in {LOG_FILE}")

if __name__ == "__main__":
    task_to_solve = "Write a working prototype of a tic-tac-toe game using the Tkinter library. Be sure to add a win check. Three in a row or three diagonally."
    start_hunt(task_to_solve)