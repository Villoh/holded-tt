from __future__ import annotations

import typer
from rich.text import Text

from holded_tt.auth import HoldedAuthClient
from holded_tt.console import get_output_console


def login_command(ctx: typer.Context) -> None:
    """Authenticate with Holded and persist the resulting session cookies."""

    console = get_output_console()
    email = typer.prompt("Email")
    password = typer.prompt("Password", hide_input=True)

    with HoldedAuthClient() as auth_client:
        auth_client.bootstrap()

        login_step = auth_client.primary_login(email, password)

        if login_step.two_factor_required:
            if login_step.masked_contact:
                console.print(f"2FA code sent to [dim]{login_step.masked_contact}[/dim]")
            two_factor_code = typer.prompt("2FA code")
            auth_client.confirm_two_factor(two_factor_code, email)

        cookies = auth_client.export_cookies()

    saved_session = ctx.obj.session_store.save(cookies)
    saved_at = saved_session.get("saved_at")
    saved_at_text = saved_at if isinstance(saved_at, str) else "unknown"

    line = Text()
    line.append("✓  ", style="green bold")
    line.append("Authenticated", style="bold")
    console.print(line)
    console.print(f"   [dim]saved  {saved_at_text}[/dim]")
