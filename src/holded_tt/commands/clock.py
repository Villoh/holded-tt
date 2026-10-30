from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

import typer
from rich.text import Text

from holded_tt.autoclock import (
    arm_next,
    executable,
    load_plan,
    load_skips,
    next_event,
    run_tick,
    save_skips,
    skip_plan,
    unskip_plan,
)
from holded_tt.dates import date_range
from holded_tt.schedule import fmt_minutes
from holded_tt import units
from holded_tt.commands.track import _resolve_date_range, _timezone_for_day
from holded_tt.console import get_output_console, render_error
from holded_tt.errors import HoldedCliError, InputError
from holded_tt.holded_client import HoldedClient
from holded_tt.state import AppState


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


@app.command("tick")
def tick_command(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would happen without clocking or saving."
    ),
    schedule: bool = typer.Option(
        False,
        "--schedule",
        help="Then arm a one-shot systemd timer for the next event (Linux), so nothing runs in between.",
    ),
) -> None:
    """Advance today's automatic clocking plan once.

    Plans the day (with jitter) on the first run, then clocks in, pauses,
    resumes and clocks out as each time comes due. Weekends, holidays and
    accepted time off are skipped. Run it from a periodic timer, or with
    --schedule from a daily timer and let each run arm the next event.
    """
    state = _get_state(ctx)
    plan_file = state.config_dir / "plan.json"
    now = datetime.now(_timezone_for_day(state.config.timezone, date.today()))
    try:
        with HoldedClient(state.session_store) as client:
            lines = run_tick(
                state.config,
                plan_file,
                client,
                now,
                dry_run,
                load_skips(state.config_dir / "skips.json"),
            )
        plan = load_plan(plan_file) if schedule else None
        if plan is not None and dry_run:
            nxt = next_event(plan)
            if nxt is not None:
                lines.append(f"would arm next event at {fmt_minutes(nxt)}")
        elif plan is not None:
            when = arm_next(plan, now, executable())
            if when is not None:
                lines.append(f"next event armed for {when:%H:%M:%S}")
    except HoldedCliError as error:
        render_error(error)
        raise typer.Exit(code=error.exit_code) from None
    for line in lines:
        typer.echo(f"{now:%Y-%m-%d %H:%M}  {line}")


def _local_today(state: AppState) -> date:
    return datetime.now(_timezone_for_day(state.config.timezone, date.today())).date()


@app.command("skip")
def skip_command(
    ctx: typer.Context,
    target_date: Optional[str] = typer.Option(
        None, "--date", help="Single day to skip (YYYY-MM-DD)."
    ),
    from_date: Optional[str] = typer.Option(
        None, "--from", help="First day to skip (YYYY-MM-DD)."
    ),
    to_date: Optional[str] = typer.Option(
        None, "--to", help="Last day to skip (YYYY-MM-DD)."
    ),
    undo: bool = typer.Option(
        False, "--undo", help="Stop skipping these days."
    ),
) -> None:
    """Do not clock the given days: a sick day, a trip, anything not in Holded.

    With no dates it skips today. Skipping today also cancels what is left of
    today's plan and stops the timer armed for it.

    Example:
      holded-tt clock skip
      holded-tt clock skip --from 2026-11-02 --to 2026-11-06
      holded-tt clock skip --date 2026-11-03 --undo
    """
    state = _get_state(ctx)
    plan_file = state.config_dir / "plan.json"
    skips_file = state.config_dir / "skips.json"
    today = _local_today(state)
    lines: list[str] = []
    try:
        if target_date is not None and (from_date or to_date):
            raise InputError(
                message="--date cannot be combined with --from or --to.",
                hint="Use --date YYYY-MM-DD alone, or --from/--to for a range.",
            )
        if target_date is not None:
            from_date = to_date = target_date
        if from_date or to_date:
            first, last = _resolve_date_range(from_date, to_date, False)
        else:
            first = last = today
        requested = date_range(first, last)
        days = [d for d in requested if d >= today]
        if not days:
            raise InputError(
                message="Those days are already in the past.",
                hint="Only today and future days can be skipped.",
            )
        if len(days) < len(requested):
            lines.append(f"ignored {len(requested) - len(days)} day(s) in the past")

        skips = set(load_skips(skips_file))
        skips = skips - set(days) if undo else skips | set(days)
        save_skips(skips_file, skips, today)
        verb = "no longer skipping" if undo else "skipping"
        span = days[0].isoformat() if len(days) == 1 else f"{days[0]} to {days[-1]}"
        lines.append(f"{verb} {len(days)} day(s): {span}")

        if today in days:
            if undo:
                unskip_plan(plan_file, today)
                # Skipping today disarmed the timer, so the chain is broken whether or not a
                # plan had been made: someone has to plan the rest of today.
                lines.append(
                    "run `holded-tt clock tick --schedule` to plan the rest of today, "
                    "or leave it for tomorrow's timer"
                )
            else:
                before = load_plan(plan_file)
                skip_plan(plan_file, today)
                units.disarm()
                if (
                    before is not None
                    and before.date == today.isoformat()
                    and "in" in before.done
                    and "out" not in before.done
                ):
                    lines.append(
                        "warning: you are clocked in and nothing will clock you out now; "
                        "run `holded-tt clock out` when you are done"
                    )
    except HoldedCliError as error:
        render_error(error)
        raise typer.Exit(code=error.exit_code) from None
    upcoming = sorted(d.isoformat() for d in skips)
    if upcoming:
        shown = ", ".join(upcoming[:10]) + (" ..." if len(upcoming) > 10 else "")
        lines.append(f"skipped days: {shown}")
    for line in lines:
        typer.echo(line)


@app.command("install")
def install_command(
    plan_at: str = typer.Option(
        "06:00",
        "--plan-at",
        help="Time (HH:MM, Mon-Fri) the day is planned. Must be before your earliest clock-in.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print the unit files and commands without writing or running anything."
    ),
) -> None:
    """Install the systemd user units that run `clock tick --schedule` for you (Linux).

    Writes a daily timer, the service it runs (also at login) and a failure alert to
    ~/.config/systemd/user, then enables them. Existing units not generated by
    holded-tt are never overwritten. Starting the service runs a real tick, so
    install does not start it.
    """
    try:
        exe = executable()
        lines = units.install(exe, plan_at, dry_run)
    except HoldedCliError as error:
        render_error(error)
        raise typer.Exit(code=error.exit_code) from None
    for line in lines:
        typer.echo(line)
    if exe.startswith("/nix/store/"):
        typer.echo(
            "warning: that executable path changes on every rebuild and is garbage-collected; "
            "run install again from a stable path (e.g. /etc/profiles/per-user/<user>/bin/holded-tt).",
            err=True,
        )


@app.command("uninstall")
def uninstall_command() -> None:
    """Remove the units written by `clock install` and stop any armed timer."""
    try:
        lines = units.uninstall()
    except HoldedCliError as error:
        render_error(error)
        raise typer.Exit(code=error.exit_code) from None
    for line in lines:
        typer.echo(line)


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
