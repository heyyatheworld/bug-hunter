"""
Rich-based UI utilities for BugHunter: console output, status spinners,
progress bars, tables/panels, and syntax-highlighted code.
Logging to file runs in a background thread.
"""

import queue
import threading
from contextlib import contextmanager

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.syntax import Syntax
from rich.table import Table
from rich.theme import Theme
from rich.box import DOUBLE

# Theme: SUCCESS green, INFO blue, WARNING yellow, ERROR red + underline
_custom_theme = Theme(
    {
        "success": "bold green",
        "info": "bold blue",
        "warning": "bold yellow",
        "error": "bold red underline",
    }
)

console = Console(theme=_custom_theme)

# Background log writer
_log_queue: queue.Queue[str | None] = queue.Queue()
_log_thread: threading.Thread | None = None
_log_filepath: str = ""


def _log_worker() -> None:
    global _log_filepath
    with open(_log_filepath, "a", encoding="utf-8") as f:
        while True:
            item = _log_queue.get()
            if item is None:
                break
            f.write(item + "\n" + "=" * 50 + "\n")
            f.flush()


def start_background_logger(filepath: str, clear: bool = True) -> None:
    """Start background thread that writes enqueued messages to filepath."""
    global _log_thread, _log_filepath
    _log_filepath = filepath
    if clear and filepath:
        try:
            open(filepath, "w").close()
        except OSError:
            pass
    _log_thread = threading.Thread(target=_log_worker, daemon=True)
    _log_thread.start()


def log_background(text: str) -> None:
    """Enqueue a message for background write to log file (non-blocking)."""
    _log_queue.put(text)


def stop_background_logger() -> None:
    """Signal logger to stop and wait for queue to drain."""
    _log_queue.put(None)
    if _log_thread is not None:
        _log_thread.join()


def show_banner(title: str = "BugHunter") -> None:
    """Print a banner panel with the given title."""
    banner = Panel(
        f"[bold cyan]{title}[/]",
        box=DOUBLE,
        border_style="cyan",
        padding=(0, 2),
    )
    console.print(banner)


def success(msg: str) -> None:
    console.print(f"[success]{msg}[/success]")


def info(msg: str) -> None:
    console.print(f"[info]{msg}[/info]")


def warning(msg: str) -> None:
    console.print(f"[warning]{msg}[/warning]")


def error(msg: str) -> None:
    console.print(f"[error]{msg}[/error]")


def status_spinner(msg: str = "Processing..."):
    """Context manager for long-running task with spinner."""
    return console.status(f"[bold green]{msg}[/bold green]", spinner="dots")


def status_llm_thinking(msg: str = "LLM analyzing code..."):
    """Context manager for LLM request/response: purple 'thinking' spinner."""
    return console.status(f"[bold purple]{msg}[/bold purple]", spinner="dots")


def panel_ai_assistant(content: str, role: str = "AI Assistant", as_code: bool = False) -> None:
    """Show LLM response in a panel titled [AI Assistant]. Use as_code=True for code (Syntax)."""
    title = f"[AI Assistant] {role}"
    if as_code:
        syn = Syntax(content, "python", line_numbers=True, theme="monokai")
        console.print(Panel(syn, title=title, border_style="magenta", padding=(0, 1)))
    else:
        console.print(Panel(content, title=title, border_style="magenta", padding=(1, 2)))


@contextmanager
def iteration_progress(total: int, description: str = "Iterations"):
    """Context manager: yields (progress, task_id). Call progress.update(task_id, advance=1) each step."""
    columns = [
        TextColumn("[bold blue]{task.description}"),
        SpinnerColumn(),
        BarColumn(bar_width=24),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ]
    with Progress(*columns, console=console) as progress:
        task_id = progress.add_task(description, total=total)
        yield progress, task_id


def result_table(rows: list[tuple[str, str]], title: str = "Result") -> None:
    """Print a two-column table (e.g. Key | Value)."""
    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("Item", style="dim")
    table.add_column("Value")
    for a, b in rows:
        table.add_row(a, b)
    console.print(table)


def result_panel(content: str, title: str = "Output") -> None:
    """Print content in a bordered panel."""
    console.print(Panel(content, title=title, border_style="green"))


CODE_THEME = "monokai"


def code_snippet(code: str, language: str = "python", line_numbers: bool = True) -> None:
    """Print syntax-highlighted code (theme: monokai)."""
    syn = Syntax(code, language, line_numbers=line_numbers, theme=CODE_THEME)
    console.print(syn)


def table_bugs(rows: list[tuple[str, str, str, str]], title: str = "Found issues / QA analysis") -> None:
    """Table: Error type, Line, Severity (AI Score), Recommendation."""
    if not rows:
        return
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Error type", style="cyan")
    table.add_column("Line", justify="right")
    table.add_column("Severity (AI Score)", style="yellow")
    table.add_column("Recommendation", style="dim")
    for r in rows:
        table.add_row(*r)
    console.print(table)


def parse_linter_to_bug_rows(linter_output: str) -> list[tuple[str, str, str, str]]:
    """Convert flake8-style output to table rows (type, line, severity, recommendation)."""
    rows = []
    if not linter_output or "LINTER: OK" in linter_output or "skipped" in linter_output:
        return rows
    for line in linter_output.replace("LINTER:\n", "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(":", 3)
        err_type = ""
        line_no = ""
        severity = "medium"
        if len(parts) >= 4:
            line_no = parts[1].strip()
            rest = parts[3].strip()
            if rest.startswith("E"):
                err_type = rest.split()[0] if rest else "E***"
            if "E5" in err_type or "line too long" in rest:
                severity = "high"
            rows.append((err_type or "style", line_no, severity, rest[:80] + ("..." if len(rest) > 80 else "")))
        else:
            rows.append(("-", "-", "-", line[:80]))
    return rows


def iteration_header(iteration: int, linter_preview: str, runtime_preview: str, qa_preview: str) -> None:
    """Compact header for a fix-round iteration."""
    console.print()
    console.print(Panel(
        f"[bold]Iteration {iteration} (fix round)[/bold]\n"
        f"Linter: [dim]{linter_preview}[/dim]\n"
        f"Runtime: [dim]{runtime_preview}[/dim]\n"
        f"QA: [dim]{qa_preview}[/dim]",
        border_style="blue",
        padding=(0, 1),
    ))


def dev_qa_line(iteration: int, model: str, kind: str) -> None:
    """Single line: [i] MODEL generating/analyzing..."""
    icon = "🛠" if kind == "dev" else "🔍"
    console.print(f"{icon} [{iteration}] [bold]{model}[/bold] {kind}...")


def step_result(lines: int, linter_ok: bool, runtime_ok: bool) -> None:
    """Single line: DEV: N lines | Linter: OK/ISSUES | Runtime: OK/ERROR"""
    l = "OK" if linter_ok else "ISSUES"
    r = "OK" if runtime_ok else "ERROR"
    console.print(f"  [dim]DEV: {lines} lines | Linter: {l} | Runtime: {r}[/dim]")


def final_summary(result_file: str, log_file: str, achieved: bool) -> None:
    """Final panel: success or max iters, output files."""
    if achieved:
        title = "Target achieved"
        border = "green"
    else:
        title = "Max iterations reached"
        border = "yellow"
    console.print(Panel(
        f"Output: [bold]{result_file}[/bold]\nLogs: [bold]{log_file}[/bold]",
        title=title,
        border_style=border,
    ))


def final_result_panel(code: str, title: str = "Final result (solution.py)") -> None:
    """Print the generated code in a panel with syntax highlighting (monokai)."""
    syn = Syntax(code, "python", line_numbers=True, theme=CODE_THEME)
    console.print(Panel(syn, title=title, border_style="cyan", padding=(0, 1)))
