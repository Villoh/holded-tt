from __future__ import annotations

import re
from datetime import date
from typing import Optional

import typer
from rich import box as rich_box
from rich.table import Table
from rich.text import Text

from holded_cli.console import get_output_console
from holded_cli.dates import date_range, filter_holidays, filter_weekends, parse_date
from holded_cli.errors import InputError
from holded_cli.holded_client import HoldedClient
from holded_cli.holidays import fetch_holidays, get_cached_holidays
from holded_cli.state import AppState


TRACK_HELP = """Register working days in a date range on Holded.

Weekends and workplace holidays are excluded by default.

Example:
  holded track --from 2026-04-01 --to 2026-04-30
  holded track --today
  holded track --from 2026-04-01 --to 2026-04-30 --dry-run
"""

_PAUSE_RE = re.compile(r"^\d{2}:\d{2}-\d{2}:\d{2}$")
_BULK_CONFIRM_THRESHOLD = 10


def _validate_pause(value: str) -> str:
    if not _PAUSE_RE.match(value):
        raise typer.BadParameter(
            f"Expected HH:MM-HH:MM format, got: {value!r}"
        )
    start_str, end_str = value.split("-")
    if start_str >= end_str:
        raise typer.BadParameter(f"Pause start must be before end: {value!r}")
    return value


def _hhmm_to_minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _build_pauses(pauses: list[str]) -> list[dict]:
    return [
        {"type": "pause", "start": p.split("-")[0], "end": p.split("-")[1]}
        for p in pauses
    ]


def _build_preview_table(
    days: list[date], start: str, end: str, pauses: list[str]
) -> Table:
    table = Table(
        show_header=True,
        header_style="bold",
        box=rich_box.SIMPLE_HEAD,
        padding=(0, 2),
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Date", min_width=12)
    table.add_column("Day", min_width=11, style="dim")
    table.add_column("Start", min_width=6)
    table.add_column("End", min_width=6)
    table.add_column("Pauses", min_width=12, style="dim")
    pauses_str = ", ".join(pauses) if pauses else "—"
    for i, d in enumerate(days, 1):
        table.add_row(
            str(i),
            d.isoformat(),
            d.strftime("%A"),
            start,
            end,
            pauses_str,
        )
    return table


def _resolve_holidays(
    state: AppState,
    from_year: int,
    to_year: int,
    workplace_id: str,
    dry_run: bool,
) -> frozenset[date]:
    """Return the combined holiday set for the relevant years.

    Uses cache when available. For a dry-run, falls back to an empty set
    rather than failing if authentication is unavailable.
    """
    all_holidays: set[date] = set()

    for year in range(from_year, to_year + 1):
        cached = get_cached_holidays(state.holidays_file, year)
        if cached is not None:
            all_holidays.update(cached)
        else:
            if dry_run:
                # Best-effort: skip holiday filtering rather than hard-fail
                pass
            else:
                with HoldedClient(state.session_store) as client:
                    fetched = fetch_holidays(
                        client, state.holidays_file, year, workplace_id
                    )
                all_holidays.update(fetched)

    return frozenset(all_holidays)


def track_command(
    ctx: typer.Context,
    from_date: Optional[str] = typer.Option(
        None, "--from", help="Start date in YYYY-MM-DD format."
    ),
    to_date: Optional[str] = typer.Option(
        None, "--to", help="End date in YYYY-MM-DD format."
    ),
    today: bool = typer.Option(False, "--today", help="Register today only."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview days without submitting."
    ),
    include_weekends: bool = typer.Option(
        False, "--include-weekends", help="Include Saturday and Sunday."
    ),
    include_holidays: bool = typer.Option(
        False, "--include-holidays", help="Include workplace holidays."
    ),
    workplace: Optional[str] = typer.Option(
        None, "--workplace", help="Override the default workplace ID."
    ),
    start: Optional[str] = typer.Option(
        None, "--start", help="Work start time (HH:MM). Overrides config default."
    ),
    end: Optional[str] = typer.Option(
        None, "--end", help="Work end time (HH:MM). Overrides config default."
    ),
    pause: Optional[list[str]] = typer.Option(
        None, "--pause", help="Pause window (HH:MM-HH:MM). Repeatable."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation for large submissions."
    ),
) -> None:
    """Register working days in Holded for a date range.

    Example:
      holded track --from 2026-04-01 --to 2026-04-30
    """
    state: AppState = ctx.obj

    # --- Resolve date range ---
    if today:
        resolved_from = resolved_to = date.today()
    elif from_date and to_date:
        resolved_from = parse_date(from_date)
        resolved_to = parse_date(to_date)
    elif from_date or to_date:
        raise InputError(
            message="Both --from and --to are required when not using --today.",
            hint="Provide both: holded track --from YYYY-MM-DD --to YYYY-MM-DD",
        )
    else:
        raise InputError(
            message="No date range specified.",
            hint="Use --from/--to or --today.",
        )

    if resolved_from > resolved_to:
        raise InputError(
            message=f"Start date {resolved_from} is after end date {resolved_to}.",
            hint="The --from date must be on or before --to.",
        )

    # --- Resolve effective options from config defaults ---
    config = state.config
    effective_workplace = workplace or config.workplace_id
    effective_start = start or config.start
    effective_end = end or config.end

    # --- Validate pauses ---
    validated_pauses: list[str] = [_validate_pause(p) for p in (pause or [])]

    # --- Build working-day list ---
    days = date_range(resolved_from, resolved_to)

    if not include_weekends:
        days = filter_weekends(days)

    if not include_holidays:
        holidays = _resolve_holidays(
            state,
            resolved_from.year,
            resolved_to.year,
            effective_workplace,
            dry_run=dry_run,
        )
        days = filter_holidays(days, holidays)

    console = get_output_console()

    if not days:
        console.print("No working days found in the specified range.")
        raise typer.Exit(0)

    # --- Show preview table ---
    table = _build_preview_table(days, effective_start, effective_end, validated_pauses)
    console.print(table)

    if dry_run:
        console.print(
            f"[dim]Dry run — would register {len(days)} day(s). "
            f"Remove --dry-run to submit.[/dim]"
        )
        raise typer.Exit(0)

    # --- Confirmation prompt for large submissions ---
    if len(days) > _BULK_CONFIRM_THRESHOLD and not yes:
        confirmed = typer.confirm(
            f"About to register {len(days)} day(s) from {resolved_from} to {resolved_to}. Proceed?",
            default=False,
        )
        if not confirmed:
            raise typer.Abort()

    # --- Submit ---
    payload = {
        "workplaceId": effective_workplace,
        "timezone": config.timezone,
        "days": [d.isoformat() for d in days],
        "start": effective_start,
        "end": effective_end,
        "pauses": _build_pauses(validated_pauses),
    }

    with HoldedClient(state.session_store) as client:
        console.print("[dim]Validating…[/dim]")
        client.check_bulk_timetracking(payload)

        console.print("[dim]Submitting…[/dim]")
        client.submit_bulk_timetracking(payload)

    date_range_str = (
        f"{resolved_from.strftime('%d %b')} → {resolved_to.strftime('%d %b %Y')}"
    )
    result = Text()
    result.append("✓  ", style="green bold")
    result.append(f"{len(days)} day(s) registered", style="bold")
    result.append(f"  ·  {date_range_str}", style="dim")
    console.print(result)
