from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from holded_tt_cli.auth import describe_saved_session
from holded_tt_cli.console import get_output_console
from holded_tt_cli.state import AppState


REQUIRED_COOKIE_NAMES = frozenset(
    {"hat", "PHPSESSID", "accountid", "TwoFactorAuth_remember_device"}
)

_STATUS_STYLE = {
    "likely valid": ("green", "●"),
    "unknown":      ("yellow", "●"),
    "missing":      ("red", "○"),
}


def session_command(ctx: typer.Context) -> None:
    """Show the saved Holded session status and timestamp."""

    state: AppState = ctx.obj
    session_store = state.session_store

    session_data = session_store.load()
    cookies = session_data.get("cookies") or {}
    status = describe_saved_session(session_store)
    saved_at = session_store.saved_at() or "—"

    color, dot = _STATUS_STYLE.get(status, ("dim", "○"))

    if isinstance(cookies, dict) and cookies:
        present = sum(1 for name in REQUIRED_COOKIE_NAMES if name in cookies)
        total = len(REQUIRED_COOKIE_NAMES)
        cookies_text = Text(f"{present} / {total}", style="green" if present == total else "yellow")
    else:
        cookies_text = Text("none", style="red")

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim", min_width=10)
    grid.add_column()

    status_cell = Text()
    status_cell.append(f"{dot}  ", style=color)
    status_cell.append(status, style=f"{color} bold" if status == "likely valid" else color)

    grid.add_row("status", status_cell)
    grid.add_row("saved", Text(saved_at, style="dim"))
    grid.add_row("cookies", cookies_text)

    get_output_console().print(Panel(grid, title="[bold]Session[/bold]", title_align="left", padding=(1, 2)))
