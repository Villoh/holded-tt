from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import typer
from rich.text import Text

from holded_tt_cli.console import get_output_console
from holded_tt_cli.errors import InputError
from holded_tt_cli.holded_client import HoldedApiError, HoldedClient
from holded_tt_cli.state import AppState


CLOCK_HELP = "Real-time clock-in, clock-out, pause, and resume."

app = typer.Typer(help=CLOCK_HELP, invoke_without_command=True)


def _get_state(ctx: typer.Context) -> AppState:
    return ctx.find_root().obj  # type: ignore[return-value]


def _elapsed(start_iso: str) -> str:
    """Return a human-readable elapsed time from a UTC ISO timestamp to now."""
    start = datetime.fromisoformat(start_iso)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - start
    total = int(delta.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _local_hhmm(utc_iso: str, tz_name: str) -> str:
    from zoneinfo import ZoneInfo

    dt = datetime.fromisoformat(utc_iso)
    return dt.astimezone(ZoneInfo(tz_name)).strftime("%H:%M")


def _require_active(client: HoldedClient) -> dict[str, Any]:
    tracker = client.get_current_tracker()
    if tracker is None:
        raise InputError(
            message="No active tracker.",
            hint="Run `holded-tt clock in` to start one.",
        )
    return tracker


def _print_status(tracker: dict[str, Any], tz_name: str) -> None:
    console = get_output_console()
    start_local = _local_hhmm(tracker["start"], tz_name)
    elapsed = _elapsed(tracker["start"])
    paused_secs = tracker.get("pausedTime") or 0
    paused_str = f"{paused_secs // 60}m" if paused_secs else "—"

    if tracker.get("paused"):
        paused_since = tracker.get("pausedSince") or ""
        since_str = _local_hhmm(paused_since, tz_name) if paused_since else "?"
        line = Text()
        line.append("⏸  Paused", style="yellow bold")
        line.append(f"  since {since_str}", style="dim")
        line.append(f"  ·  started {start_local}", style="dim")
        line.append(f"  ·  paused {paused_str}", style="dim")
    elif tracker.get("running"):
        line = Text()
        line.append("●  Running", style="green bold")
        line.append(f"  since {start_local}", style="dim")
        line.append(f"  ·  elapsed {elapsed}", style="dim")
        if paused_secs:
            line.append(f"  ·  paused {paused_str}", style="dim")
    else:
        line = Text()
        line.append("○  No active tracker", style="dim")

    console.print(line)


@app.callback()
def _clock_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        state = _get_state(ctx)
        with HoldedClient(state.session_store) as client:
            tracker = client.get_current_tracker()
        if tracker:
            _print_status(tracker, state.config.timezone)
        else:
            get_output_console().print("[dim]No active tracker.[/dim]")


@app.command("in")
def in_command(ctx: typer.Context) -> None:
    """Start a new tracker (clock in)."""
    state = _get_state(ctx)
    console = get_output_console()

    with HoldedClient(state.session_store) as client:
        # Guard: don't start a second tracker
        existing = client.get_current_tracker()
        if existing:
            raise InputError(
                message="A tracker is already running.",
                hint="Run `holded-tt clock out` to stop it first.",
            )
        client.clock_in()
        tracker = client.get_current_tracker()

    start_local = (
        _local_hhmm(tracker["start"], state.config.timezone) if tracker else "?"
    )
    line = Text()
    line.append("✓  Clocked in", style="green bold")
    line.append(f"  at {start_local}", style="dim")
    console.print(line)


@app.command("out")
def out_command(ctx: typer.Context) -> None:
    """Stop the active tracker (clock out)."""
    state = _get_state(ctx)
    console = get_output_console()

    with HoldedClient(state.session_store) as client:
        tracker = _require_active(client)
        tracker_id = tracker["id"]
        start_local = _local_hhmm(tracker["start"], state.config.timezone)
        client.clock_out(tracker_id)

    elapsed = _elapsed(tracker["start"])
    line = Text()
    line.append("✓  Clocked out", style="green bold")
    line.append(f"  started {start_local}", style="dim")
    line.append(f"  ·  elapsed {elapsed}", style="dim")
    console.print(line)


@app.command("pause")
def pause_command(ctx: typer.Context) -> None:
    """Pause the active tracker."""
    state = _get_state(ctx)
    console = get_output_console()

    with HoldedClient(state.session_store) as client:
        tracker = _require_active(client)
        if tracker.get("paused"):
            raise InputError(
                message="Tracker is already paused.",
                hint="Run `holded-tt clock resume` to continue.",
            )
        client.pause_tracker(tracker["id"])

    line = Text()
    line.append("✓  Paused", style="yellow bold")
    console.print(line)


@app.command("resume")
def resume_command(ctx: typer.Context) -> None:
    """Resume a paused tracker."""
    state = _get_state(ctx)
    console = get_output_console()

    with HoldedClient(state.session_store) as client:
        tracker = _require_active(client)
        if not tracker.get("paused"):
            raise InputError(
                message="Tracker is not paused.",
                hint="Run `holded-tt clock pause` to pause it first.",
            )
        result = client.resume_tracker(tracker["id"])

    pause_start = (
        (tracker.get("currentPause") or {}).get("start") or result.get("end") or ""
    )
    duration_str = f"  ·  paused {_elapsed(pause_start)}" if pause_start else ""
    line = Text()
    line.append("✓  Resumed", style="green bold")
    line.append(f"{duration_str}", style="dim")
    console.print(line)


@app.command("status")
def status_command(ctx: typer.Context) -> None:
    """Show the current tracker state."""
    state = _get_state(ctx)

    with HoldedClient(state.session_store) as client:
        tracker = client.get_current_tracker()

    if tracker:
        _print_status(tracker, state.config.timezone)
    else:
        get_output_console().print("[dim]No active tracker.[/dim]")
