"""
Rich-based UI utilities for BugHunter: console output, status spinners,
progress bars, tables/panels, and syntax-highlighted code.
"""

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


def status_spinner(msg: str = "Обработка..."):
    """Context manager for long-running task with spinner. Use: with status_spinner('...') as s: ..."""
    return console.status(f"[bold green]{msg}[/bold green]", spinner="dots")


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


def code_snippet(code: str, language: str = "python", line_numbers: bool = True) -> None:
    """Print syntax-highlighted code (compact, max height ~20 lines)."""
    syn = Syntax(code, language, line_numbers=line_numbers, theme="monokai")
    console.print(syn)


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
    """Print the generated code in a panel with syntax highlighting."""
    syn = Syntax(code, "python", line_numbers=True, theme="monokai")
    console.print(Panel(syn, title=title, border_style="cyan", padding=(0, 1)))
