from __future__ import annotations

import inspect
import sys
from functools import wraps

import typer

# Ensure Unicode characters (e.g. ✓) render correctly on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from holded_cli import __version__
from holded_cli.commands import (
    clock_app,
    employee_command,
    employees_command,
    export_command,
    login_command,
    session_command,
    track_app,
    workplaces_command,
)
from holded_cli.commands.clock import CLOCK_HELP
from holded_cli.commands.config import CONFIG_HELP, set_command, show_command
from holded_cli.console import render_error
from holded_cli.errors import HoldedCliError
from holded_cli.state import create_app_state


app = typer.Typer(
    name="holded",
    help="Holded time-tracking CLI.",
    invoke_without_command=True,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
)
config_app = typer.Typer(help=CONFIG_HELP, invoke_without_command=True)


def _with_cli_error_handling(command):
    @wraps(command)
    def wrapped(*args, **kwargs):  # type: ignore[no-untyped-def]
        try:
            return command(*args, **kwargs)
        except HoldedCliError as error:
            render_error(error)
            raise typer.Exit(code=error.exit_code) from None

    wrapped.__signature__ = inspect.signature(command)
    return wrapped


def _version_callback(value: bool) -> None:
    if not value:
        return

    typer.echo(__version__)
    raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the installed holded version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Holded time-tracking CLI."""

    del version
    ctx.obj = create_app_state()


app.command(
    "login", help="Authenticate with Holded and save the local session cookies."
)(_with_cli_error_handling(login_command))
app.command(
    "session",
    help="Show saved session status and timestamp.",
)(_with_cli_error_handling(session_command))
app.command(
    "workplaces",
    help="List available Holded workplace IDs and names.",
)(_with_cli_error_handling(workplaces_command))
app.command(
    "employee",
    help="Show the current Holded employee profile and personal info.",
)(_with_cli_error_handling(employee_command))
app.command(
    "organization",
    help="List organization employees from Holded Teamzone.",
)(_with_cli_error_handling(employees_command))
app.command(
    "export",
    help=(
        "Export time-tracking records as PDF or Excel.\n\n"
        "Example:\n"
        "  holded export --from 2026-04-01 --to 2026-04-30\n"
        "  holded export --from 2026-04-01 --to 2026-04-30 --format xlsx"
    ),
)(_with_cli_error_handling(export_command))
config_app.command("show")(_with_cli_error_handling(show_command))
config_app.command("set")(_with_cli_error_handling(set_command))


@config_app.callback()
def _config_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _with_cli_error_handling(show_command)(ctx)


app.add_typer(clock_app, name="clock")
app.add_typer(config_app, name="config")
app.add_typer(track_app, name="track")
