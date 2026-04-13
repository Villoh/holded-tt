from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from holded_tt_cli.config import save_config
from holded_tt_cli.console import get_output_console
from holded_tt_cli.errors import InputError
from holded_tt_cli.state import AppState


CONFIG_HELP = "Inspect or update local Holded TT CL defaults."

app = typer.Typer(help=CONFIG_HELP)

ALLOWED_CONFIG_KEYS = {
    "defaults.workplace_id": "workplace_id",
    "defaults.start": "start",
    "defaults.end": "end",
    "defaults.timezone": "timezone",
}


def _get_state(ctx: typer.Context) -> AppState:
    state = ctx.find_root().obj
    if not isinstance(state, AppState):
        raise RuntimeError("AppState is not available on the root Typer context.")
    return state


def _resolve_config_attr(key: str) -> str:
    if key not in ALLOWED_CONFIG_KEYS:
        allowed_keys = ", ".join(ALLOWED_CONFIG_KEYS)
        raise InputError(
            message=f"Unsupported config key: {key}",
            hint=f"Choose one of: {allowed_keys}",
        )
    return ALLOWED_CONFIG_KEYS[key]


@app.command("show")
def show_command(ctx: typer.Context) -> None:
    """Show local config defaults and resolved storage paths."""

    state = _get_state(ctx)

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim", min_width=20)
    grid.add_column()

    grid.add_row("workplace_id", state.config.workplace_id or "[dim]—[/dim]")
    grid.add_row("start", state.config.start)
    grid.add_row("end", state.config.end)
    grid.add_row("timezone", state.config.timezone)
    grid.add_row("", "")
    grid.add_row("[dim]config[/dim]", Text(str(state.config_file), style="dim"))
    grid.add_row("[dim]session[/dim]", Text(str(state.session_file), style="dim"))
    grid.add_row("[dim]holidays[/dim]", Text(str(state.holidays_file), style="dim"))

    get_output_console().print(
        Panel(
            grid, title="[bold]Configuration[/bold]", title_align="left", padding=(1, 2)
        )
    )


@app.command("set")
def set_command(
    ctx: typer.Context,
    key: str = typer.Argument(
        ...,
        help=(
            "Config key to update. Valid keys:\n\n"
            "  defaults.workplace_id   Default workplace for track\n\n"
            "  defaults.start          Work start time (HH:MM)\n\n"
            "  defaults.end            Work end time (HH:MM)\n\n"
            "  defaults.timezone       Timezone (e.g. Europe/Madrid)"
        ),
    ),
    value: str = typer.Argument(..., help="New value to persist."),
) -> None:
    """Update one supported local config default.

    Example:

      holded-tt config set defaults.workplace_id <workplace_id>

      holded-tt config set defaults.start 09:00

      holded-tt config set defaults.timezone Europe/Madrid
    """

    state = _get_state(ctx)
    config_attr = _resolve_config_attr(key)

    setattr(state.config, config_attr, value)
    save_config(state.config)

    line = Text()
    line.append("✓  ", style="green bold")
    line.append(key, style="dim")
    line.append(" → ", style="dim")
    line.append(value, style="bold")
    get_output_console().print(line)
