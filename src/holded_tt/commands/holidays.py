from __future__ import annotations

from datetime import date
from typing import Optional

import typer
from rich import box as rich_box
from rich.table import Table
from rich.text import Text

from holded_tt.console import get_output_console
from holded_tt.holded_client import HoldedClient
from holded_tt.holidays import (
    _current_year_paris,
    _save_cache,
    extract_workplace_holidays,
    get_cached_holidays,
)
from holded_tt.state import AppState


def holidays_command(
    ctx: typer.Context,
    year: Optional[int] = typer.Option(
        None, "--year", help="Year to fetch holidays for (default: current year)."
    ),
    refresh: bool = typer.Option(
        False, "--refresh", help="Bypass cache and fetch from Holded API."
    ),
) -> None:
    """Show workplace holidays for a given year, using local cache when available."""
    state: AppState = ctx.obj
    console = get_output_console()

    target_year = year if year is not None else _current_year_paris()

    holidays: frozenset[date] | None = None
    source = "cached"

    if not refresh:
        holidays = get_cached_holidays(state.holidays_file, target_year)

    if holidays is None:
        with HoldedClient(state.session_store) as client:
            summary = client.get_year_summary(target_year)
        holidays = extract_workplace_holidays(summary, target_year)
        _save_cache(
            state.holidays_file,
            target_year,
            sorted(d.isoformat() for d in holidays),
        )
        source = "refreshed" if refresh else "fetched"

    if not holidays:
        console.print(f"[dim]No holidays found for {target_year}.[/dim]")
        raise typer.Exit(0)

    sorted_holidays = sorted(holidays)

    table = Table(
        show_header=True,
        header_style="bold",
        box=rich_box.SIMPLE_HEAD,
        padding=(0, 2),
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Date", min_width=12)
    table.add_column("Day", min_width=11, style="dim")

    for i, d in enumerate(sorted_holidays, 1):
        table.add_row(str(i), d.isoformat(), d.strftime("%A"))

    console.print(table)

    summary_line = Text()
    summary_line.append(
        f"{len(sorted_holidays)} holiday(s)  ·  {target_year}  ·  {source}",
        style="dim",
    )
    console.print(summary_line)
