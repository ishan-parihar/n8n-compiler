"""Output module for terminal display and errors."""

from n8n_compiler.output.terminal import Console, console
from n8n_compiler.output.errors import CompilerError, display_error

__all__ = [
    "Console",
    "console",
    "CompilerError",
    "display_error",
]
