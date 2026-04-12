"""Reusable textual renderers for CLI status output."""

from __future__ import annotations

from collections.abc import Iterable


def render_key_values(title: str, rows: Iterable[tuple[str, str]]) -> str:
    """Return a readable key/value block for terminal output."""

    lines = [title]
    for label, value in rows:
        lines.append(f"  {label}: {value}")
    return "\n".join(lines)


def render_stub_status(command_name: str, summary: str, next_step: str) -> str:
    """Return a readable placeholder block for not-yet-wired commands."""

    return "\n".join(
        [
            f"Command: {command_name}",
            f"Status: {summary}",
            f"Next step: {next_step}",
        ]
    )
