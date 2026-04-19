from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import typer
from rich import box as rich_box
from rich.table import Table
from rich.text import Text

from holded_tt.console import get_output_console, render_error
from holded_tt.dates import date_range, filter_holidays, filter_weekends, parse_date
from holded_tt.errors import HoldedCliError, InputError
from holded_tt.holded_client import HoldedClient
from holded_tt.holidays import fetch_holidays, get_cached_holidays
from holded_tt.state import AppState


TRACK_HELP = """Register working days in a date range on Holded.

Weekends and workplace holidays are excluded by default.

Example:
  holded-tt track --from 2026-04-01 --to 2026-04-30
  holded-tt track --today
  holded-tt track --from 2026-04-01 --to 2026-04-30 --dry-run
"""

TRACK_UPDATE_HELP = """Update existing tracked days on Holded.

The command can update a single tracker by `--tracker-id` and `--date`, or a
date range by resolving exactly one existing tracker per target day and sending
updates one by one.

Examples:
  holded-tt track update --date 2026-04-07 --tracker-id trk_123 --end 17:00
  holded-tt track update --from 2026-04-07 --to 2026-04-09 --end 17:00
"""

TRACK_SHOW_HELP = """Show tracked time entries and tracker IDs.

Examples:
  holded-tt track show --date 2026-04-10
  holded-tt track show --from 2026-04-07 --to 2026-04-10
"""

_PAUSE_RE = re.compile(r"^\d{2}:\d{2}-\d{2}:\d{2}$")
_BULK_CONFIRM_THRESHOLD = 10


app = typer.Typer(
    help=TRACK_HELP,
    invoke_without_command=True,
    no_args_is_help=False,
)


def _run_with_cli_error_handling(command, *args, **kwargs):  # type: ignore[no-untyped-def]
    try:
        return command(*args, **kwargs)
    except HoldedCliError as error:
        render_error(error)
        raise typer.Exit(code=error.exit_code) from None


def _validate_pause(value: str) -> str:
    if not _PAUSE_RE.match(value):
        raise typer.BadParameter(f"Expected HH:MM-HH:MM format, got: {value!r}")
    start_str, end_str = value.split("-")
    if start_str >= end_str:
        raise typer.BadParameter(f"Pause start must be before end: {value!r}")
    return value


def _hhmm_to_minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _build_pauses(pauses: list[str]) -> list[dict]:
    return [{"start": p.split("-")[0], "end": p.split("-")[1]} for p in pauses]


def _last_sunday(year: int, month: int) -> date:
    day = date(year, month + 1, 1) - timedelta(days=1)
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _timezone_for_day(tz_name: str, day: date):
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        if tz_name in {"Europe/Paris", "Europe/Madrid"}:
            summer_start = _last_sunday(day.year, 3)
            summer_end = _last_sunday(day.year, 10)
            offset_hours = 2 if summer_start <= day < summer_end else 1
            return timezone(timedelta(hours=offset_hours))
        return timezone.utc


def _build_trackers(
    tracker_rows: list[dict[str, object]],
    start: str,
    end: str,
    pauses: list[str],
) -> list[dict]:
    start_time = time.fromisoformat(start)
    end_time = time.fromisoformat(end)
    pause_windows = _build_pauses(pauses)
    return [
        {
            "id": row["id"],
            "workplaceId": row["workplaceId"],
            "isRemote": row["isRemote"],
            "start": datetime.combine(
                row["date"],
                start_time,
                tzinfo=_timezone_for_day(str(row["timezone"]), row["date"]),
            ).isoformat(),
            "end": datetime.combine(
                row["date"],
                end_time,
                tzinfo=_timezone_for_day(str(row["timezone"]), row["date"]),
            ).isoformat(),
            "pauses": [pause.copy() for pause in pause_windows],
        }
        for row in tracker_rows
    ]


def _resolve_single_date(target_date: Optional[str], today: bool) -> date:
    if today:
        return date.today()
    if target_date:
        return parse_date(target_date)
    raise InputError(
        message="No date specified.",
        hint="Use --date YYYY-MM-DD or --today.",
    )


def _resolve_date_range(
    from_date: Optional[str], to_date: Optional[str], today: bool
) -> tuple[date, date]:
    if today:
        resolved_from = resolved_to = date.today()
    elif from_date and to_date:
        resolved_from = parse_date(from_date)
        resolved_to = parse_date(to_date)
    elif from_date or to_date:
        raise InputError(
            message="Both --from and --to are required when not using --today.",
            hint="Provide both: holded-tt track --from YYYY-MM-DD --to YYYY-MM-DD",
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
    return resolved_from, resolved_to


def _resolve_track_days(
    state: AppState,
    resolved_from: date,
    resolved_to: date,
    workplace_id: str,
    *,
    dry_run: bool,
    include_weekends: bool,
    include_holidays: bool,
) -> list[date]:
    days = date_range(resolved_from, resolved_to)

    if not include_weekends:
        days = filter_weekends(days)

    if not include_holidays:
        holidays = _resolve_holidays(
            state,
            resolved_from.year,
            resolved_to.year,
            workplace_id,
            dry_run=dry_run,
        )
        days = filter_holidays(days, holidays)

    return days


def _resolve_update_rows(
    data: list[dict[str, object]],
    target_days: list[date],
    workplace_id: str,
    timezone_name: str,
) -> list[dict[str, object]]:
    entries = {
        entry.get("date"): entry
        for entry in data
        if isinstance(entry, dict) and isinstance(entry.get("date"), str)
    }
    tracker_rows: list[dict[str, object]] = []
    errors: list[str] = []

    for day in target_days:
        entry = entries.get(day.isoformat())
        trackers = entry.get("trackers", []) if isinstance(entry, dict) else []
        trackers = trackers if isinstance(trackers, list) else []
        if len(trackers) == 0:
            errors.append(f"{day.isoformat()}: no existing tracker")
            continue
        if len(trackers) > 1:
            errors.append(f"{day.isoformat()}: multiple trackers found")
            continue

        tracker = trackers[0]
        if not isinstance(tracker, dict):
            errors.append(f"{day.isoformat()}: unreadable tracker payload")
            continue

        tracker_id = tracker.get("id") if isinstance(tracker.get("id"), str) else ""
        if not tracker_id:
            errors.append(f"{day.isoformat()}: tracker id missing")
            continue
        if tracker.get("running") or not tracker.get("end"):
            errors.append(f"{day.isoformat()}: tracker is still running")
            continue

        resolved_workplace = workplace_id
        if not resolved_workplace:
            raw_workplace = tracker.get("workplaceId")
            resolved_workplace = raw_workplace if isinstance(raw_workplace, str) else ""

        raw_timezone = tracker.get("timezone")
        tracker_rows.append(
            {
                "id": tracker_id,
                "date": day,
                "workplaceId": resolved_workplace,
                "timezone": raw_timezone
                if isinstance(raw_timezone, str) and raw_timezone
                else timezone_name,
                "isRemote": tracker.get("isRemote")
                if isinstance(tracker.get("isRemote"), bool)
                else False,
                "start": tracker.get("startDateWithTimeZone") or tracker.get("start"),
                "end": tracker.get("end"),
                "pauses": tracker.get("pauses")
                if isinstance(tracker.get("pauses"), list)
                else [],
            }
        )

    if errors:
        raise InputError(
            message="Could not resolve a single existing tracker for every target day.",
            hint="; ".join(errors[:3]),
        )

    return tracker_rows


def _resolve_tracker_for_update(
    day_data: dict[str, object],
    tracker_id: str,
    target_day: date,
    workplace_id: str,
    timezone_name: str,
) -> dict[str, object]:
    trackers = day_data.get("trackers", []) if isinstance(day_data, dict) else []
    trackers = trackers if isinstance(trackers, list) else []

    for tracker in trackers:
        if not isinstance(tracker, dict):
            continue
        current_id = tracker.get("id")
        if current_id != tracker_id:
            continue
        if tracker.get("running") or not tracker.get("end"):
            raise InputError(
                message="The selected tracker is still running.",
                hint="Clock it out in Holded before updating it.",
            )
        raw_workplace = tracker.get("workplaceId")
        raw_timezone = tracker.get("timezone")
        return {
            "id": tracker_id,
            "date": target_day,
            "workplaceId": workplace_id
            or (raw_workplace if isinstance(raw_workplace, str) else ""),
            "timezone": raw_timezone
            if isinstance(raw_timezone, str) and raw_timezone
            else timezone_name,
            "isRemote": tracker.get("isRemote")
            if isinstance(tracker.get("isRemote"), bool)
            else False,
            "start": tracker.get("startDateWithTimeZone") or tracker.get("start"),
            "end": tracker.get("end"),
            "pauses": tracker.get("pauses")
            if isinstance(tracker.get("pauses"), list)
            else [],
        }

    raise InputError(
        message=f"Tracker {tracker_id} was not found on {target_day.isoformat()}.",
        hint="Use `holded-tt track show --date ...` to inspect the available tracker IDs.",
    )


def _extract_pause_windows(pauses: list[object], tz_name: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    zone = _timezone_for_day(tz_name, date.today())
    for pause in pauses:
        if not isinstance(pause, dict):
            continue
        start_raw = pause.get("start")
        end_raw = pause.get("end")
        if not isinstance(start_raw, str) or not isinstance(end_raw, str):
            continue
        try:
            start_dt = datetime.fromisoformat(
                start_raw.replace("Z", "+00:00")
            ).astimezone(zone)
            end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00")).astimezone(
                zone
            )
        except ValueError:
            continue
        result.append(
            {
                "start": start_dt.strftime("%H:%M"),
                "end": end_dt.strftime("%H:%M"),
            }
        )
    return result


def _format_tracker_time(value: object, tz_name: str, day: date) -> str:
    if not isinstance(value, str) or not value:
        return "-"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    return dt.astimezone(_timezone_for_day(tz_name, day)).strftime("%H:%M")


def _format_duration(value: object) -> str:
    if not isinstance(value, int) or value < 0:
        return "-"
    hours, remainder = divmod(value, 3600)
    minutes = remainder // 60
    return f"{hours:02d}:{minutes:02d}"


def _format_pause_summary(pauses: object, tz_name: str, day: date) -> str:
    if not isinstance(pauses, list):
        return "-"
    windows = _extract_pause_windows(pauses, tz_name)
    if not windows:
        return "-"
    return ", ".join(f"{item['start']} -> {item['end']}" for item in windows)


def _render_trackers_table(entries: list[dict[str, object]]) -> Table:
    table = Table(show_header=True, header_style="bold", box=rich_box.SIMPLE_HEAD)
    table.add_column("Date", min_width=12)
    table.add_column("Tracker ID", min_width=16, overflow="fold")
    table.add_column("Time", min_width=13)
    table.add_column("Worked", min_width=7)
    table.add_column("Pauses", min_width=16)
    table.add_column("Status", min_width=10)
    table.add_column("Approved", min_width=10)
    table.add_column("Method", min_width=8)
    table.add_column("Remote", min_width=7)
    for entry in entries:
        day = entry.get("date", "-")
        day_obj = (
            date.fromisoformat(str(day))
            if isinstance(day, str) and len(day) >= 10
            else date.today()
        )
        trackers = (
            entry.get("trackers", []) if isinstance(entry.get("trackers"), list) else []
        )
        if not trackers:
            table.add_row(str(day), "-", "-", "-", "-", "empty", "-", "-", "-")
            continue
        for tracker in trackers:
            if not isinstance(tracker, dict):
                continue
            tz_name = (
                tracker.get("timezone")
                if isinstance(tracker.get("timezone"), str)
                else "UTC"
            )
            pauses = (
                tracker.get("pauses", [])
                if isinstance(tracker.get("pauses"), list)
                else []
            )
            worked_time = (
                tracker.get("effectiveWorkedTime")
                if isinstance(tracker.get("effectiveWorkedTime"), int)
                else tracker.get("time")
            )
            table.add_row(
                str(day),
                str(tracker.get("id") or "-"),
                (
                    _format_tracker_time(
                        tracker.get("startDateWithTimeZone") or tracker.get("start"),
                        tz_name,
                        day_obj,
                    )
                    + " -> "
                    + _format_tracker_time(tracker.get("end"), tz_name, day_obj)
                ),
                _format_duration(worked_time),
                _format_pause_summary(pauses, tz_name, day_obj),
                str(
                    tracker.get("status")
                    or ("running" if tracker.get("running") else "done")
                ),
                str(tracker.get("approvedStatus") or "-"),
                str(tracker.get("logMethod") or "-"),
                "yes" if tracker.get("isRemote") is True else "no",
            )
    return table


def _build_preview_table(days: list[date]) -> Table:
    table = Table(
        show_header=True,
        header_style="bold",
        box=rich_box.SIMPLE_HEAD,
        padding=(0, 2),
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Date", min_width=12)
    table.add_column("Day", min_width=11, style="dim")
    for i, d in enumerate(days, 1):
        table.add_row(str(i), d.isoformat(), d.strftime("%A"))
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
      holded-tt track --from 2026-04-01 --to 2026-04-30
    """
    state: AppState = ctx.obj

    resolved_from, resolved_to = _resolve_date_range(from_date, to_date, today)

    # --- Resolve effective options from config defaults ---
    config = state.config
    effective_workplace = workplace or config.workplace_id
    effective_start = start or config.start
    effective_end = end or config.end
    configured_pauses = config.pause if isinstance(config.pause, list) else []

    # --- Validate pauses ---
    raw_pauses = pause if pause is not None else configured_pauses
    validated_pauses: list[str] = [_validate_pause(p) for p in raw_pauses]

    days = _resolve_track_days(
        state,
        resolved_from,
        resolved_to,
        effective_workplace,
        dry_run=dry_run,
        include_weekends=include_weekends,
        include_holidays=include_holidays,
    )

    console = get_output_console()

    if not days:
        console.print("No working days found in the specified range.")
        raise typer.Exit(0)

    # --- Show context line + preview table ---
    pauses_str = "  ·  pause " + ", ".join(validated_pauses) if validated_pauses else ""
    context_parts = [f"{effective_start} → {effective_end}{pauses_str}"]
    if effective_workplace:
        context_parts.append(f"workplace {effective_workplace}")
    console.print()
    console.print("[dim]" + "  ·  ".join(context_parts) + "[/dim]")
    console.print(_build_preview_table(days))

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


def track_show_command(
    ctx: typer.Context,
    target_date: Optional[str] = typer.Option(
        None, "--date", help="Target date in YYYY-MM-DD format."
    ),
    from_date: Optional[str] = typer.Option(
        None, "--from", help="Start date in YYYY-MM-DD format."
    ),
    to_date: Optional[str] = typer.Option(
        None, "--to", help="End date in YYYY-MM-DD format."
    ),
    today: bool = typer.Option(False, "--today", help="Show today only."),
) -> None:
    """Show tracked days and tracker IDs."""
    state: AppState = ctx.obj
    config = state.config
    console = get_output_console()

    with HoldedClient(state.session_store) as client:
        if target_date or today:
            resolved_date = _resolve_single_date(target_date, today)
            day_data = client.get_day_timetracking(resolved_date, config.timezone)
            entries = [day_data] if day_data else []
        else:
            resolved_from, resolved_to = _resolve_date_range(from_date, to_date, False)
            entries = client.get_timetracking_data(
                resolved_from,
                resolved_to,
                config.timezone,
                exclude_rejected=False,
            )

    if not entries:
        console.print("[dim]No tracked data found.[/dim]")
        raise typer.Exit(0)

    console.print(_render_trackers_table(entries))


def track_update_command(
    ctx: typer.Context,
    target_date: Optional[str] = typer.Option(
        None, "--date", help="Target date in YYYY-MM-DD format."
    ),
    from_date: Optional[str] = typer.Option(
        None, "--from", help="Start date in YYYY-MM-DD format."
    ),
    to_date: Optional[str] = typer.Option(
        None, "--to", help="End date in YYYY-MM-DD format."
    ),
    today: bool = typer.Option(False, "--today", help="Update today only."),
    tracker_id: Optional[str] = typer.Option(
        None, "--tracker-id", help="Tracker ID to update."
    ),
    include_weekends: bool = typer.Option(
        False, "--include-weekends", help="Include Saturday and Sunday."
    ),
    include_holidays: bool = typer.Option(
        False, "--include-holidays", help="Include workplace holidays."
    ),
    workplace: Optional[str] = typer.Option(
        None, "--workplace", help="Override the workplace ID for the updated tracker."
    ),
    start: Optional[str] = typer.Option(
        None, "--start", help="New start time (HH:MM)."
    ),
    end: Optional[str] = typer.Option(None, "--end", help="New end time (HH:MM)."),
    pause: Optional[list[str]] = typer.Option(
        None,
        "--pause",
        help="Pause window (HH:MM-HH:MM). Repeatable. Overrides existing pauses.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Update one or more existing trackers in Holded."""
    state: AppState = ctx.obj
    config = state.config
    console = get_output_console()

    def build_payload_for_row(row: dict[str, object]) -> dict[str, object]:
        row_date = row["date"]
        timezone_name = str(row["timezone"])
        current_start = row.get("start")
        current_end = row.get("end")
        if not isinstance(current_start, str) or not isinstance(current_end, str):
            raise InputError(
                message="The selected tracker is missing start/end data.",
                hint="Inspect it with `holded-tt track show --date ...` and try again.",
            )

        current_start_local = (
            datetime.fromisoformat(current_start.replace("Z", "+00:00"))
            .astimezone(_timezone_for_day(timezone_name, row_date))
            .strftime("%H:%M")
        )
        current_end_local = (
            datetime.fromisoformat(current_end.replace("Z", "+00:00"))
            .astimezone(_timezone_for_day(timezone_name, row_date))
            .strftime("%H:%M")
        )
        effective_start = start or current_start_local
        effective_end = end or current_end_local
        effective_pauses = (
            [_validate_pause(p) for p in (pause or [])]
            if pause is not None
            else [
                f"{item['start']}-{item['end']}"
                for item in _extract_pause_windows(row.get("pauses", []), timezone_name)
            ]
        )
        return {
            "trackers": _build_trackers(
                [row], effective_start, effective_end, effective_pauses
            ),
            "effective_start": effective_start,
            "effective_end": effective_end,
            "effective_pauses": effective_pauses,
        }

    with HoldedClient(state.session_store) as client:
        if tracker_id:
            resolved_date = _resolve_single_date(target_date, today)
            day_data = client.get_day_timetracking(resolved_date, config.timezone)
            tracker_rows = [
                _resolve_tracker_for_update(
                    day_data,
                    tracker_id,
                    resolved_date,
                    workplace or config.workplace_id,
                    config.timezone,
                )
            ]
        else:
            resolved_from, resolved_to = _resolve_date_range(from_date, to_date, today)
            target_days = _resolve_track_days(
                state,
                resolved_from,
                resolved_to,
                workplace or config.workplace_id,
                dry_run=False,
                include_weekends=include_weekends,
                include_holidays=include_holidays,
            )
            if not target_days:
                console.print("No tracked days found in the specified range.")
                raise typer.Exit(0)
            timetracking_data = client.get_timetracking_data(
                resolved_from,
                resolved_to,
                config.timezone,
                exclude_rejected=False,
            )
            tracker_rows = _resolve_update_rows(
                timetracking_data,
                target_days,
                workplace or config.workplace_id,
                config.timezone,
            )

        preview_payloads = [build_payload_for_row(row) for row in tracker_rows]

        console.print()
        for row, preview in zip(tracker_rows, preview_payloads):
            console.print(
                f"[dim]{row['id']}  ·  {preview['effective_start']} → {preview['effective_end']}"
                + (
                    f"  ·  pause {', '.join(preview['effective_pauses'])}"
                    if preview["effective_pauses"]
                    else ""
                )
                + f"  ·  {row['date']}[/dim]"
            )

        if not yes:
            if tracker_id:
                confirm_text = f"Update tracker {tracker_rows[0]['id']} on {tracker_rows[0]['date']}?"
            else:
                confirm_text = (
                    f"Update {len(tracker_rows)} tracker(s) from {tracker_rows[0]['date']} "
                    f"to {tracker_rows[-1]['date']}?"
                )
            confirmed = typer.confirm(confirm_text, default=False)
            if not confirmed:
                raise typer.Abort()

        console.print("[dim]Submitting…[/dim]")
        for preview in preview_payloads:
            client.update_bulk_timetracking({"trackers": preview["trackers"]})

    result = Text()
    result.append("✓  ", style="green bold")
    if tracker_id:
        result.append(f"tracker {tracker_rows[0]['id']} updated", style="bold")
        result.append(f"  ·  {tracker_rows[0]['date']}", style="dim")
    else:
        result.append(f"{len(tracker_rows)} tracker(s) updated", style="bold")
        result.append(
            f"  ·  {tracker_rows[0]['date']} → {tracker_rows[-1]['date']}", style="dim"
        )
    console.print(result)


@app.callback(invoke_without_command=True)
def track_app_callback(
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
    if ctx.invoked_subcommand is None:
        _run_with_cli_error_handling(
            track_command,
            ctx,
            from_date=from_date,
            to_date=to_date,
            today=today,
            dry_run=dry_run,
            include_weekends=include_weekends,
            include_holidays=include_holidays,
            workplace=workplace,
            start=start,
            end=end,
            pause=pause,
            yes=yes,
        )


@app.command("update", help=TRACK_UPDATE_HELP)
def track_update_entrypoint(
    ctx: typer.Context,
    target_date: Optional[str] = typer.Option(
        None, "--date", help="Target date in YYYY-MM-DD format."
    ),
    from_date: Optional[str] = typer.Option(
        None, "--from", help="Start date in YYYY-MM-DD format."
    ),
    to_date: Optional[str] = typer.Option(
        None, "--to", help="End date in YYYY-MM-DD format."
    ),
    today: bool = typer.Option(False, "--today", help="Update today only."),
    tracker_id: Optional[str] = typer.Option(
        None, "--tracker-id", help="Tracker ID to update."
    ),
    include_weekends: bool = typer.Option(
        False, "--include-weekends", help="Include Saturday and Sunday."
    ),
    include_holidays: bool = typer.Option(
        False, "--include-holidays", help="Include workplace holidays."
    ),
    workplace: Optional[str] = typer.Option(
        None, "--workplace", help="Override the workplace ID for the updated tracker."
    ),
    start: Optional[str] = typer.Option(
        None, "--start", help="New start time (HH:MM)."
    ),
    end: Optional[str] = typer.Option(None, "--end", help="New end time (HH:MM)."),
    pause: Optional[list[str]] = typer.Option(
        None,
        "--pause",
        help="Pause window (HH:MM-HH:MM). Repeatable. Overrides existing pauses.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    _run_with_cli_error_handling(
        track_update_command,
        ctx,
        target_date=target_date,
        from_date=from_date,
        to_date=to_date,
        today=today,
        tracker_id=tracker_id,
        include_weekends=include_weekends,
        include_holidays=include_holidays,
        workplace=workplace,
        start=start,
        end=end,
        pause=pause,
        yes=yes,
    )


@app.command("show", help=TRACK_SHOW_HELP)
def track_show_entrypoint(
    ctx: typer.Context,
    target_date: Optional[str] = typer.Option(
        None, "--date", help="Target date in YYYY-MM-DD format."
    ),
    from_date: Optional[str] = typer.Option(
        None, "--from", help="Start date in YYYY-MM-DD format."
    ),
    to_date: Optional[str] = typer.Option(
        None, "--to", help="End date in YYYY-MM-DD format."
    ),
    today: bool = typer.Option(False, "--today", help="Show today only."),
) -> None:
    _run_with_cli_error_handling(
        track_show_command,
        ctx,
        target_date=target_date,
        from_date=from_date,
        to_date=to_date,
        today=today,
    )
