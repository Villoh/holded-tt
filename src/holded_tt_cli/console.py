"""Shared console helpers for stdout and stderr output."""

from __future__ import annotations

from typing import TextIO

from rich.console import Console

from holded_tt_cli.errors import HoldedCliError


def get_output_console(file: TextIO | None = None) -> Console:
    """Return the standard output console with sane non-TTY defaults."""

    return Console(file=file, soft_wrap=True, legacy_windows=False)


def get_error_console(file: TextIO | None = None) -> Console:
    """Return the standard error console with sane non-TTY defaults."""

    return Console(file=file, stderr=file is None, soft_wrap=True, legacy_windows=False)


def render_error(error: HoldedCliError, console: Console | None = None) -> None:
    """Render a user-facing CLI error without exposing internals."""

    error_console = console or get_error_console()
    error_console.print(f"Error: {error.message}", markup=False)
    error_console.print(f"Hint: {error.hint}", markup=False)
