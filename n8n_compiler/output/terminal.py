"""Terminal output utilities using Rich."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from rich.console import Console as RichConsole
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box


class Console:
    """Styled terminal output for n8nc."""
    
    def __init__(self):
        self.console = RichConsole()
        self._start_time: Optional[datetime] = None
    
    def header(self, version: str = "1.0.0", watching: Optional[str] = None) -> None:
        """Display the n8nc header."""
        content = f"[bold cyan]n8nc[/bold cyan] v{version}"
        if watching:
            content += f"\n[dim]Watching:[/dim] {watching}"
        
        panel = Panel(
            content,
            box=box.ROUNDED,
            border_style="cyan",
            padding=(0, 1),
        )
        self.console.print(panel)
        self.console.print()
    
    def timestamp(self) -> str:
        """Get formatted timestamp."""
        return datetime.now().strftime("[%H:%M:%S]")
    
    def info(self, message: str) -> None:
        """Display info message."""
        self.console.print(f"[dim]{self.timestamp()}[/dim] {message}")
    
    def success(self, message: str) -> None:
        """Display success message."""
        self.console.print(f"[dim]{self.timestamp()}[/dim] [green]✓[/green] {message}")
    
    def warning(self, message: str) -> None:
        """Display warning message."""
        self.console.print(f"[dim]{self.timestamp()}[/dim] [yellow]⚠[/yellow] {message}")
    
    def error(self, message: str) -> None:
        """Display error message."""
        self.console.print(f"[dim]{self.timestamp()}[/dim] [red]✗[/red] {message}")
    
    def change_detected(self, path: str) -> None:
        """Display file change detection."""
        self.console.print(f"[dim]{self.timestamp()}[/dim] Detected change: [cyan]{path}[/cyan]")
    
    def sync_result(
        self,
        direction: str,
        source: str,
        target: str,
        nodes: int,
        connections: int,
    ) -> None:
        """Display sync result."""
        if direction == "unpack":
            self.success(f"Unpacked → {target} ({nodes} nodes, {connections} connections)")
        elif direction == "pack":
            self.success(f"Packed → {target} ({nodes} nodes, {connections} connections)")
        else:
            self.info(f"Already in sync: {source}")
    
    def hash_update(self, old_hash: str, new_hash: str) -> None:
        """Display hash update."""
        short_old = old_hash.split(":")[-1][:8] if old_hash else "none"
        short_new = new_hash.split(":")[-1][:8] if new_hash else "none"
        self.info(f"Updated manifest hash: [dim]{short_old}[/dim] → [cyan]{short_new}[/cyan]")
    
    def table(self, title: str, columns: list[str], rows: list[list[str]]) -> None:
        """Display a table."""
        table = Table(title=title, box=box.ROUNDED)
        for col in columns:
            table.add_column(col)
        for row in rows:
            table.add_row(*row)
        self.console.print(table)
    
    def workflow_summary(
        self,
        name: str,
        nodes: int,
        connections: int,
        categories: dict[str, int],
    ) -> None:
        """Display workflow summary."""
        self.console.print()
        self.console.print(f"[bold]{name}[/bold]")
        self.console.print(f"  Nodes: [cyan]{nodes}[/cyan]")
        self.console.print(f"  Connections: [cyan]{connections}[/cyan]")
        self.console.print("  Categories:")
        for cat, count in sorted(categories.items()):
            self.console.print(f"    [dim]{cat}:[/dim] {count}")
        self.console.print()


# Global console instance
console = Console()
