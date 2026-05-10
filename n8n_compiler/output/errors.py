"""Error display utilities - npm/bun style error reporting."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich import box


@dataclass
class CompilerError:
    """Represents a compiler error with context."""
    error_type: str
    message: str
    file_path: Optional[Path] = None
    line_number: Optional[int] = None
    column: Optional[int] = None
    context_lines: Optional[list[str]] = None
    suggestions: Optional[list[str]] = None


def extract_json_error_position(error_msg: str, content: str) -> tuple[Optional[int], Optional[int]]:
    """Extract line and column from JSON decode error."""
    # Pattern: "line X column Y"
    match = re.search(r'line (\d+) column (\d+)', error_msg)
    if match:
        return int(match.group(1)), int(match.group(2))
    
    # Pattern: "position X"
    match = re.search(r'position (\d+)', error_msg)
    if match:
        pos = int(match.group(1))
        # Convert position to line/column
        lines = content[:pos].split('\n')
        line = len(lines)
        col = len(lines[-1]) + 1 if lines else 1
        return line, col
    
    return None, None


def get_context_lines(content: str, line_number: int, context: int = 3) -> list[tuple[int, str, bool]]:
    """Get lines around the error with line numbers."""
    lines = content.split('\n')
    start = max(0, line_number - context - 1)
    end = min(len(lines), line_number + context)
    
    result = []
    for i in range(start, end):
        is_error_line = (i + 1) == line_number
        result.append((i + 1, lines[i], is_error_line))
    
    return result


def display_error(error: CompilerError, console: Optional[Console] = None) -> None:
    """Display a styled error message like npm/bun."""
    if console is None:
        console = Console()
    
    # Build error content
    lines = []
    
    # Error type and message
    lines.append(f"[bold red]✗[/bold red] [bold]{error.error_type}[/bold]")
    lines.append("")
    lines.append(f"  {error.message}")
    
    # File info
    if error.file_path:
        location = f"[cyan]{error.file_path}[/cyan]"
        if error.line_number:
            location += f":[yellow]{error.line_number}[/yellow]"
            if error.column:
                location += f":[yellow]{error.column}[/yellow]"
        lines.append("")
        lines.append(f"  File: {location}")
    
    # Context lines
    if error.context_lines:
        lines.append("")
        for line_num, content, is_error in error.context_lines:
            prefix = "[red]→[/red]" if is_error else " "
            num_style = "[red]" if is_error else "[dim]"
            lines.append(f"  {prefix} {num_style}{line_num:>4}[/] │ {content}")
            
            # Show column indicator on error line
            if is_error and error.column:
                pointer = " " * (error.column + 8) + "[red]^[/red]"
                lines.append(pointer)
    
    # Suggestions
    if error.suggestions:
        lines.append("")
        lines.append("  [bold]Suggestions:[/bold]")
        for suggestion in error.suggestions:
            lines.append(f"    • {suggestion}")
    
    # Create panel
    panel = Panel(
        "\n".join(lines),
        title="[bold red]Compilation Error[/bold red]",
        border_style="red",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    
    console.print(panel)


def create_json_error(file_path: Path, error: json.JSONDecodeError) -> CompilerError:
    """Create a CompilerError from a JSON decode error."""
    content = file_path.read_text()
    line, col = extract_json_error_position(str(error), content)
    
    context = None
    if line:
        context = [
            (num, text, is_err)
            for num, text, is_err in get_context_lines(content, line)
        ]
    
    return CompilerError(
        error_type="Invalid JSON",
        message=str(error.msg),
        file_path=file_path,
        line_number=line,
        column=col,
        context_lines=context,
        suggestions=[
            "Check for missing commas between properties",
            "Ensure all brackets and braces are properly closed",
            "Verify string values are properly quoted",
        ],
    )


def create_missing_file_error(file_path: Path, expected_by: str) -> CompilerError:
    """Create error for missing file."""
    return CompilerError(
        error_type="Missing File",
        message=f"Required file not found",
        file_path=file_path,
        suggestions=[
            f"Expected by: {expected_by}",
            "Run 'n8nc sync' to regenerate missing files",
            "Check if the file was accidentally deleted",
        ],
    )


def create_node_mismatch_error(
    file_path: Path,
    expected_id: str,
    actual_id: str,
) -> CompilerError:
    """Create error for node ID mismatch."""
    return CompilerError(
        error_type="Node ID Mismatch",
        message=f"Expected node ID '{expected_id}' but found '{actual_id}'",
        file_path=file_path,
        suggestions=[
            "The node ID in the file doesn't match the manifest",
            "This can happen if you copied a node file without updating the ID",
            f"Update the 'id' field to: {expected_id}",
        ],
    )


def create_connection_error(
    manifest_path: Path,
    source_node: str,
    target_node: str,
) -> CompilerError:
    """Create error for invalid connection."""
    return CompilerError(
        error_type="Invalid Connection",
        message=f"Connection target '{target_node}' not found",
        file_path=manifest_path,
        suggestions=[
            f"Source node: {source_node}",
            "The target node may have been deleted",
            "Update the manifest to remove this connection",
        ],
    )
