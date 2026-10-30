from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from holded_tt.config import WEEKDAYS, save_config
from holded_tt.commands.track import _validate_pause
from holded_tt.console import get_output_console
from holded_tt.errors import InputError
from holded_tt.state import AppState


CONFIG_HELP = "Inspect or update local Holded TT CL defaults."

app = typer.Typer(help=CONFIG_HELP)

ALLOWED_CONFIG_KEYS = {
    "defaults.workplace_id": "workplace_id",
    "defaults.start": "start",
    "defaults.end": "end",
    "defaults.timezone": "timezone",
    "defaults.pause": "pause",
    "defaults.jitter": "jitter",
    "defaults.max_late": "max_late",
}
INT_KEYS = {"defaults.jitter", "defaults.max_late"}
DAY_FIELDS = ("start", "end", "pause")


def _get_state(ctx: typer.Context) -> AppState:
    state = ctx.find_root().obj
    if not isinstance(state, AppState):
        raise RuntimeError("AppState is not available on the root Typer context.")
    return state


def _split_day_key(key: str) -> tuple[str, str] | None:
    """Parse ``defaults.<day>.<field>`` (e.g. defaults.fri.end)."""
    parts = key.split(".")
    if len(parts) == 3 and parts[0] == "defaults":
        if parts[1] in WEEKDAYS and parts[2] in DAY_FIELDS:
            return parts[1], parts[2]
    return None


def _resolve_config_attr(key: str) -> str:
    if key not in ALLOWED_CONFIG_KEYS and _split_day_key(key) is None:
        allowed_keys = ", ".join(ALLOWED_CONFIG_KEYS)
        raise InputError(
            message=f"Unsupported config key: {key}",
            hint=(
                f"Choose one of: {allowed_keys}, "
                f"or defaults.<{'|'.join(WEEKDAYS)}>.<{'|'.join(DAY_FIELDS)}>"
            ),
        )
    return ALLOWED_CONFIG_KEYS.get(key, key)


def _parse_config_value(key: str, value: str) -> str | int | list[str]:
    if key in INT_KEYS:
        if not value.isdigit():
            raise InputError(
                message=f"{key} must be a non-negative integer, got: {value!r}",
                hint=f"Use minutes, e.g. `holded-tt config set {key} 15`.",
            )
        return int(value)
    if not key.endswith(".pause"):
        return value

    pauses = [item.strip() for item in value.split(",") if item.strip()]
    return [_validate_pause(item) for item in pauses]


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
    grid.add_row("jitter", f"{state.config.jitter} min")
    grid.add_row("max_late", f"{state.config.max_late} min")
    grid.add_row("pause", ", ".join(state.config.pause) or "[dim]—[/dim]")
    for day in WEEKDAYS:
        for field_name, field_value in state.config.days.get(day, {}).items():
            rendered = (
                ", ".join(field_value)
                if isinstance(field_value, list)
                else field_value
            )
            grid.add_row(f"{day}.{field_name}", rendered or "[dim]none[/dim]")
    grid.add_row("", "")
    grid.add_row("[dim]config[/dim]", Text(str(state.config_file), style="dim"))
    grid.add_row("[dim]session[/dim]", Text(str(state.session_file), style="dim"))

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
            "  defaults.timezone       Timezone (e.g. Europe/Madrid)\n\n"
            "  defaults.pause          Default pauses (comma-separated HH:MM-HH:MM)\n\n"
            "  defaults.jitter         Max random minutes on start/end/pause (0 = off)\n\n"
            "  defaults.max_late       `clock tick` skips a clock-in later than this (minutes)\n\n"
            "  defaults.<day>.<field>  Per-weekday override. day: mon..sun,\n"
            "                          field: start, end or pause"
        ),
    ),
    value: str = typer.Argument(..., help="New value to persist."),
) -> None:
    """Update one supported local config default.

    Example:

      holded-tt config set defaults.workplace_id <workplace_id>

      holded-tt config set defaults.start 09:00

      holded-tt config set defaults.timezone Europe/Madrid

      holded-tt config set defaults.pause 14:00-14:30,17:00-17:15

      holded-tt config set defaults.fri.end 15:00
    """

    state = _get_state(ctx)
    config_attr = _resolve_config_attr(key)
    parsed_value = _parse_config_value(key, value)

    day_key = _split_day_key(key)
    if day_key and not isinstance(parsed_value, int):
        day, field_name = day_key
        state.config.days.setdefault(day, {})[field_name] = parsed_value
    else:
        setattr(state.config, config_attr, parsed_value)
    save_config(state.config)

    rendered_value = (
        ", ".join(parsed_value) if isinstance(parsed_value, list) else str(parsed_value)
    )

    line = Text()
    line.append("✓  ", style="green bold")
    line.append(key, style="dim")
    line.append(" → ", style="dim")
    line.append(rendered_value or "—", style="bold")
    get_output_console().print(line)
