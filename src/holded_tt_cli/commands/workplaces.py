from __future__ import annotations

import typer
from rich import box as rich_box
from rich.table import Table

from holded_tt_cli.console import get_output_console
from holded_tt_cli.holded_client import HoldedClient
from holded_tt_cli.state import AppState


def workplaces_command(ctx: typer.Context) -> None:
    """List available Holded workplace IDs and names."""

    state: AppState = ctx.obj

    with HoldedClient(state.session_store) as client:
        workplaces = client.get_workplaces()

    console = get_output_console()

    if not workplaces:
        console.print("[dim]No workplaces found.[/dim]")
        return

    table = Table(
        show_header=True,
        header_style="bold",
        box=rich_box.SIMPLE_HEAD,
        padding=(0, 2),
    )
    table.add_column("ID", style="dim")
    table.add_column("Name")

    for wp in workplaces:
        wp_id = wp.get("id") or wp.get("_id") or "?"
        wp_name = wp.get("name") or wp.get("title") or "Unnamed"
        table.add_row(wp_id, wp_name)

    console.print(table)
