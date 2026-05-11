"""Timeoff command group: show, request, cancel, details."""

from __future__ import annotations

from datetime import date
from typing import Optional

import typer
from rich import box as rich_box
from rich.table import Table
from rich.text import Text

from holded_tt.console import get_output_console, render_error
from holded_tt.dates import parse_date
from holded_tt.errors import HoldedCliError, InputError
from holded_tt.holded_client import HoldedClient
from holded_tt.state import AppState
from holded_tt.timeoff import (
    _current_year_paris,
    build_request_start,
    extract_employee_absences,
    extract_workplace_holidays,
    parse_days_summary,
    resolve_vacation_type_id,
)


TIMEOFF_HELP = """Manage time-off requests and view absences.

Examples:
  holded-tt timeoff show
  holded-tt timeoff show --mine
  holded-tt timeoff show --holidays
  holded-tt timeoff show --year 2025
  holded-tt timeoff request --date 2026-06-15
  holded-tt timeoff request --from 2026-06-15 --to 2026-06-20
  holded-tt timeoff cancel --id <id>
  holded-tt timeoff details --id <id>
"""

app = typer.Typer(help=TIMEOFF_HELP)


def _run_with_cli_error_handling(command, *args, **kwargs):  # type: ignore[no-untyped-def]
    try:
        return command(*args, **kwargs)
    except HoldedCliError as error:
        render_error(error)
        raise typer.Exit(code=error.exit_code) from None


def _render_summary(days: dict) -> None:
    console = get_output_console()
    line = Text()
    line.append(f"{days['available']} días disponibles", style="bold")
    line.append(f"  ·  {days['total']} total  ·  {days['used']} usados", style="dim")
    if days.get("accrued_expiration"):
        line.append(f"  ·  acumulados caducan en {days['accrued_expiration']}", style="dim")
    console.print(line)

    bd_avail = days.get("breakdown_available", {})
    bd_used = days.get("breakdown_used", {})
    if bd_avail:
        console.print(
            f"  [dim]disponibles: {bd_avail.get('policy', 0)} política"
            f" + {bd_avail.get('accrued', 0)} acumulados"
            f" + {bd_avail.get('extra', 0)} extra[/dim]"
        )
    if bd_used:
        console.print(
            f"  [dim]usados: {bd_used.get('policy', 0)} política"
            f" + {bd_used.get('accrued', 0)} acumulados"
            f" + {bd_used.get('extra', 0)} extra[/dim]"
        )
    console.print()


def _render_absences_table(absences: list[dict]) -> None:
    console = get_output_console()
    if not absences:
        console.print("[dim]No hay ausencias personales.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=rich_box.SIMPLE_HEAD)
    table.add_column("ID", min_width=24, overflow="fold")
    table.add_column("Inicio", min_width=12)
    table.add_column("Fin", min_width=12)
    table.add_column("Días", min_width=5)
    table.add_column("Tipo", min_width=14)
    table.add_column("Estado", min_width=10)

    for entry in absences:
        timeoff_type = entry.get("timeoffType") or {}
        type_name = timeoff_type.get("name") or "—" if isinstance(timeoff_type, dict) else "—"
        status = str(entry.get("status") or "—")
        end_val = str(entry.get("end") or "—")
        table.add_row(
            str(entry.get("id") or "—"),
            str(entry.get("start") or "—"),
            end_val,
            str(entry.get("numDays") or "—"),
            type_name,
            status,
        )
    console.print(table)


def _render_holidays_table(holidays: dict[date, str]) -> None:
    console = get_output_console()
    if not holidays:
        console.print("[dim]No hay festivos para este año.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=rich_box.SIMPLE_HEAD, padding=(0, 2))
    table.add_column("#", style="dim", width=4)
    table.add_column("Fecha", min_width=12)
    table.add_column("Día", min_width=11, style="dim")
    table.add_column("Nombre", min_width=20)

    for i, d in enumerate(sorted(holidays.keys()), 1):
        table.add_row(str(i), d.isoformat(), d.strftime("%A"), holidays[d])
    console.print(table)


@app.command("show")
def show_command(
    ctx: typer.Context,
    holidays_only: bool = typer.Option(False, "--holidays", help="Show only workplace holidays."),
    mine_only: bool = typer.Option(False, "--mine", help="Show only personal absences."),
    year: Optional[int] = typer.Option(None, "--year", help="Year to query (default: current year)."),
) -> None:
    """Show timeoff summary, personal absences, and workplace holidays."""
    _run_with_cli_error_handling(
        _show_command_impl, ctx, holidays_only=holidays_only, mine_only=mine_only, year=year
    )


def _show_command_impl(
    ctx: typer.Context,
    holidays_only: bool,
    mine_only: bool,
    year: Optional[int],
) -> None:
    if holidays_only and mine_only:
        raise InputError(
            message="--holidays and --mine cannot be used together.",
            hint="Use one filter at a time, or omit both to see everything.",
        )

    state: AppState = ctx.obj
    target_year = year if year is not None else _current_year_paris()
    console = get_output_console()

    with HoldedClient(state.session_store) as client:
        summary = client.get_timeoff_summary(target_year)

    if holidays_only:
        holidays = extract_workplace_holidays(summary, target_year)
        _render_holidays_table(holidays)
        console.print(f"[dim]{len(holidays)} festivo(s)  ·  {target_year}[/dim]")
        return

    if mine_only:
        absences = extract_employee_absences(summary)
        console.print(f"[bold]Mis ausencias[/bold]  [dim]{target_year}[/dim]")
        _render_absences_table(absences)
        return

    # All blocks
    days = parse_days_summary(summary)
    _render_summary(days)

    console.print("[bold]Mis ausencias[/bold]")
    absences = extract_employee_absences(summary)
    _render_absences_table(absences)
    console.print()

    console.print("[bold]Festivos del workplace[/bold]")
    today = date.today()
    holidays = extract_workplace_holidays(summary, target_year)
    future_holidays = {d: name for d, name in holidays.items() if d >= today}
    _render_holidays_table(future_holidays if future_holidays else holidays)


@app.command("request")
def request_command(
    ctx: typer.Context,
    target_date: Optional[str] = typer.Option(None, "--date", help="Single date (YYYY-MM-DD)."),
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date (YYYY-MM-DD)."),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date (YYYY-MM-DD)."),
    period: str = typer.Option("full_day", "--period", help="Day period: full_day, morning, afternoon."),
    description: str = typer.Option("", "--description", help="Optional description."),
) -> None:
    """Request vacation days."""
    _run_with_cli_error_handling(
        _request_command_impl, ctx,
        target_date=target_date, from_date=from_date, to_date=to_date,
        period=period, description=description,
    )


def _request_command_impl(
    ctx: typer.Context,
    target_date: Optional[str],
    from_date: Optional[str],
    to_date: Optional[str],
    period: str,
    description: str,
) -> None:
    valid_periods = {"full_day", "morning", "afternoon"}
    if period not in valid_periods:
        raise InputError(
            message=f"Invalid period: {period!r}.",
            hint=f"Choose one of: {', '.join(sorted(valid_periods))}",
        )

    if target_date and (from_date or to_date):
        raise InputError(
            message="--date cannot be combined with --from or --to.",
            hint="Use --date for a single day, or --from/--to for a range.",
        )

    if target_date:
        resolved_start = parse_date(target_date)
        resolved_end: date | None = None
    elif from_date and to_date:
        resolved_start = parse_date(from_date)
        resolved_end = parse_date(to_date)
        if resolved_start > resolved_end:
            raise InputError(
                message=f"Start date {resolved_start} is after end date {resolved_end}.",
                hint="--from must be on or before --to.",
            )
    else:
        raise InputError(
            message="No date specified.",
            hint="Use --date YYYY-MM-DD or --from YYYY-MM-DD --to YYYY-MM-DD.",
        )

    state: AppState = ctx.obj
    console = get_output_console()

    with HoldedClient(state.session_store) as client:
        summary = client.get_timeoff_summary(resolved_start.year)
        type_id = resolve_vacation_type_id(summary)
        start_str = build_request_start(resolved_start, state.config.timezone)
        end_str = build_request_start(resolved_end, state.config.timezone) if resolved_end else None
        created_id = client.request_timeoff(
            start=start_str,
            timeoff_type_id=type_id,
            day_period=period,
            description=description,
            end=end_str,
        )

    result = Text()
    result.append("✓  ", style="green bold")
    result.append("Solicitud creada", style="bold")
    result.append(f"  ·  {created_id}", style="dim")
    console.print(result)


@app.command("cancel")
def cancel_command(
    ctx: typer.Context,
    timeoff_id: str = typer.Option(..., "--id", help="Timeoff request ID to cancel."),
) -> None:
    """Cancel a pending timeoff request."""
    _run_with_cli_error_handling(_cancel_command_impl, ctx, timeoff_id=timeoff_id)


def _cancel_command_impl(ctx: typer.Context, timeoff_id: str) -> None:
    state: AppState = ctx.obj
    console = get_output_console()

    with HoldedClient(state.session_store) as client:
        client.cancel_timeoff(timeoff_id)

    result = Text()
    result.append("✓  ", style="green bold")
    result.append("Solicitud cancelada", style="bold")
    result.append(f"  ·  {timeoff_id}", style="dim")
    console.print(result)


@app.command("details")
def details_command(
    ctx: typer.Context,
    timeoff_ids: list[str] = typer.Option(..., "--id", help="Timeoff request ID (repeatable)."),
) -> None:
    """Fetch full details for one or more timeoff requests."""
    _run_with_cli_error_handling(_details_command_impl, ctx, timeoff_ids=timeoff_ids)


def _details_command_impl(ctx: typer.Context, timeoff_ids: list[str]) -> None:
    state: AppState = ctx.obj
    console = get_output_console()

    with HoldedClient(state.session_store) as client:
        details = client.get_timeoff_details(timeoff_ids)

    if not details:
        console.print("[dim]No se encontraron detalles.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=rich_box.SIMPLE_HEAD)
    table.add_column("ID", min_width=24, overflow="fold")
    table.add_column("Inicio", min_width=12)
    table.add_column("Fin", min_width=12)
    table.add_column("Días", min_width=5)
    table.add_column("Tipo", min_width=14)
    table.add_column("Estado", min_width=10)

    for entry in details:
        if not isinstance(entry, dict):
            continue
        timeoff_type = entry.get("timeoffType") or {}
        type_name = timeoff_type.get("name") or "—" if isinstance(timeoff_type, dict) else "—"
        table.add_row(
            str(entry.get("id") or "—"),
            str(entry.get("start") or "—"),
            str(entry.get("end") or "—"),
            str(entry.get("numDays") or "—"),
            type_name,
            str(entry.get("status") or "—"),
        )
    console.print(table)
