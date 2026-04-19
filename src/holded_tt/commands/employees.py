from __future__ import annotations

import typer
from rich import box as rich_box
from rich.table import Table

from holded_tt.console import get_output_console
from holded_tt.holded_client import HoldedClient
from holded_tt.state import AppState


def _string_value(value: object, default: str = "-") -> str:
    if value in (None, ""):
        return default
    return str(value)


def _get_nested_str(data: object, *keys: str) -> str:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return "-"
        current = current.get(key)
    return _string_value(current)


def _team_names(employee: dict[str, object]) -> str:
    teams = employee.get("teams")
    if not isinstance(teams, list) or not teams:
        return "-"

    names = [team.get("name") for team in teams if isinstance(team, dict)]
    rendered = [str(name) for name in names if name not in (None, "")]
    return ", ".join(rendered) if rendered else "-"


def employees_command(ctx: typer.Context) -> None:
    """List organization employees from Holded Teamzone."""

    state: AppState = ctx.obj

    with HoldedClient(state.session_store) as client:
        employees = client.get_organization_employees()

    console = get_output_console()

    if not employees:
        console.print("[dim]No organization employees found.[/dim]")
        return

    table = Table(
        show_header=True,
        header_style="bold",
        box=rich_box.SIMPLE_HEAD,
        padding=(0, 1),
    )
    table.add_column("ID", style="dim", overflow="fold")
    table.add_column("Name", overflow="fold")
    table.add_column("Email", overflow="fold")
    table.add_column("Job Title", overflow="fold")
    table.add_column("Workplace", overflow="fold")
    table.add_column("Teams", overflow="fold")

    for employee in employees:
        table.add_row(
            _string_value(employee.get("id"), "?"),
            _string_value(employee.get("fullName") or employee.get("name"), "Unnamed"),
            _get_nested_str(employee, "contactInfo", "email"),
            _get_nested_str(employee, "contract", "jobTitle"),
            _get_nested_str(employee, "workplace", "name"),
            _team_names(employee),
        )

    console.print(table)
