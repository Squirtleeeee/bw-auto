"""终端输出美化 (rich 封装)"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def print_header(text: str) -> None:
    console.print(Panel(text, style="bold cyan"))


def print_success(text: str) -> None:
    console.print(f"  [green]✓[/green] {text}")


def print_error(text: str) -> None:
    console.print(f"  [red]✗[/red] {text}")


def print_info(text: str) -> None:
    console.print(f"  [yellow]→[/yellow] {text}")


def print_countdown(remaining_secs: float) -> None:
    """倒计时显示"""
    mins, secs = divmod(int(remaining_secs), 60)
    hours, mins = divmod(mins, 60)
    if hours:
        ts = f"{hours:02d}:{mins:02d}:{secs:02d}"
    else:
        ts = f"{mins:02d}:{secs:02d}"
    console.print(f"  ⏳ 距离开售: [bold yellow]{ts}[/bold yellow]", end="\r")
