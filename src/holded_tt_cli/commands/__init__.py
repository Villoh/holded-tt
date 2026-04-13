from __future__ import annotations

from holded_tt_cli.commands.clock import app as clock_app
from holded_tt_cli.commands.config import app as config_app
from holded_tt_cli.commands.employee import employee_command
from holded_tt_cli.commands.employees import employees_command
from holded_tt_cli.commands.export import export_command
from holded_tt_cli.commands.login import login_command
from holded_tt_cli.commands.session import session_command
from holded_tt_cli.commands.track import app as track_app
from holded_tt_cli.commands.track import track_command, track_update_command
from holded_tt_cli.commands.workplaces import workplaces_command

__all__ = [
    "clock_app",
    "config_app",
    "employee_command",
    "employees_command",
    "export_command",
    "login_command",
    "session_command",
    "track_app",
    "track_command",
    "track_update_command",
    "workplaces_command",
]
