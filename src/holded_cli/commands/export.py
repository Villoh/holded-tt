from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import typer
from rich.text import Text

from holded_cli.console import get_output_console
from holded_cli.dates import parse_date
from holded_cli.errors import InputError
from holded_cli.holded_client import HoldedClient
from holded_cli.state import AppState


EXPORT_HELP = """Export time-tracking records for a date range.

Examples:
  holded export --from 2026-04-01 --to 2026-04-30
  holded export --from 2026-04-01 --to 2026-04-30 --format xlsx
  holded export --from 2026-04-01 --to 2026-04-30 --out ~/Desktop/april.pdf
"""

_MIDNIGHT = "00:00:00"
_END_OF_DAY = "23:59:59"


def _seconds_to_hhmm(seconds: int) -> str:
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    h, m = divmod(seconds // 60, 60)
    return f"{sign}{h:02d}:{m:02d}"


def _utc_to_local_hhmm(utc_iso: str, tz_name: str) -> str:
    dt = datetime.fromisoformat(utc_iso)
    return dt.astimezone(ZoneInfo(tz_name)).strftime("%H:%M")


def _format_pauses(pauses: list[dict], tz_name: str) -> str:
    parts = []
    for p in pauses:
        start = _utc_to_local_hhmm(p["start"], tz_name)
        end = _utc_to_local_hhmm(p["end"], tz_name)
        parts.append(f"{start}-{end}")
    return ", ".join(parts) if parts else "—"


def _build_xlsx(data: list[dict], tz_name: str, from_str: str, to_str: str) -> bytes:
    import io
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Time Tracking"

    # --- Title ---
    ws.merge_cells("A1:H1")
    title_cell = ws["A1"]
    title_cell.value = f"Time Tracking  ·  {from_str} → {to_str}"
    title_cell.font = Font(bold=True, size=13)
    title_cell.alignment = Alignment(horizontal="left")
    ws.row_dimensions[1].height = 22

    ws.append([])  # blank row

    # --- Headers ---
    headers = ["Date", "Day", "Start", "End", "Pauses", "Worked", "Expected", "Overtime"]
    ws.append(headers)
    header_row = ws.max_row
    header_fill = PatternFill("solid", fgColor="1F3864")
    for col, _ in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # --- Data rows ---
    weekend_fill = PatternFill("solid", fgColor="F2F2F2")

    for entry in data:
        d = entry["date"]
        dt = datetime.fromisoformat(d)
        day_name = dt.strftime("%A")
        is_weekend = dt.weekday() >= 5

        trackers = entry.get("trackers", [])
        stats = entry.get("stats", {})

        if trackers:
            tracker = trackers[0]
            start = _utc_to_local_hhmm(tracker["start"], tz_name)
            end = _utc_to_local_hhmm(tracker["end"], tz_name)
            pauses = _format_pauses(tracker.get("pauses", []), tz_name)
            worked = _seconds_to_hhmm(stats.get("timeWorked", 0))
            expected = _seconds_to_hhmm(stats.get("expectedTime", 0))
            overtime_secs = stats.get("overtime", 0)
            overtime = ("+" if overtime_secs > 0 else "") + _seconds_to_hhmm(overtime_secs)
        else:
            start = end = pauses = worked = expected = overtime = "—"

        row = [d, day_name, start, end, pauses, worked, expected, overtime]
        ws.append(row)

        if is_weekend or not trackers:
            row_idx = ws.max_row
            for col in range(1, len(headers) + 1):
                ws.cell(row=row_idx, column=col).fill = weekend_fill

    # --- Column widths ---
    col_widths = [13, 12, 7, 7, 18, 9, 10, 10]
    for i, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_command(
    ctx: typer.Context,
    from_date: str = typer.Option(..., "--from", help="Start date in YYYY-MM-DD format."),
    to_date: str = typer.Option(..., "--to", help="End date in YYYY-MM-DD format."),
    fmt: str = typer.Option("pdf", "--format", help="Output format: pdf or xlsx."),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Output file path. Defaults to current directory."
    ),
) -> None:
    """Export time-tracking records as PDF or Excel for a date range.

    Example:
      holded export --from 2026-04-01 --to 2026-04-30
      holded export --from 2026-04-01 --to 2026-04-30 --format xlsx
    """
    state: AppState = ctx.obj

    if fmt not in ("pdf", "xlsx"):
        raise InputError(
            message=f"Unknown format: {fmt!r}",
            hint="Use --format pdf or --format xlsx.",
        )

    resolved_from = parse_date(from_date)
    resolved_to = parse_date(to_date)

    if resolved_from > resolved_to:
        raise InputError(
            message=f"Start date {resolved_from} is after end date {resolved_to}.",
            hint="The --from date must be on or before --to.",
        )

    if out is None:
        filename = f"holded-{resolved_from}_{resolved_to}.{fmt}"
        out = Path.cwd() / filename

    console = get_output_console()

    with HoldedClient(state.session_store) as client:
        if fmt == "pdf":
            console.print("[dim]Fetching PDF…[/dim]")
            content = client.get_timetracking_pdf(
                resolved_from, resolved_to, state.config.timezone
            )
        else:
            console.print("[dim]Fetching data…[/dim]")
            data = client.get_timetracking_data(
                resolved_from, resolved_to, state.config.timezone
            )
            content = _build_xlsx(
                data, state.config.timezone, str(resolved_from), str(resolved_to)
            )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(content)

    result = Text()
    result.append("✓  ", style="green bold")
    result.append(str(out), style="bold")
    result.append(f"  ·  {len(content) / 1024:.1f} KB", style="dim")
    console.print(result)
