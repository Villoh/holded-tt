from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import typer
from rich.console import Group
from rich.panel import Panel
from rich.table import Table

from holded_tt_cli.console import get_output_console
from holded_tt_cli.holded_client import HoldedClient
from holded_tt_cli.state import AppState


def _render_value(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (dict, list)):
        if not value:
            return "-"
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return "-"
    if value == "":
        return "-"
    return str(value)


def _pick_first(*values: object) -> str | None:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return None


def _personal_field_value(payload: dict[str, object], key: str) -> Any:
    field = payload.get(key)
    if isinstance(field, dict) and "value" in field:
        return field.get("value")
    return field


def _resolve_timezone_name(state: AppState, tracker: dict[str, object]) -> str:
    tracker_timezone = tracker.get("timezone")
    if isinstance(tracker_timezone, str) and tracker_timezone:
        return tracker_timezone
    return state.config.timezone


def _get_zoneinfo(tz_name: str) -> timezone | ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return timezone.utc


def _format_timestamp(value: object, *, tz_name: str = "UTC") -> str:
    if not value:
        return "-"
    if isinstance(value, (int, float)):
        zone = _get_zoneinfo(tz_name)
        timestamp = float(value)
        if abs(timestamp) >= 100_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=zone).date().isoformat()
    if isinstance(value, str):
        try:
            zone = _get_zoneinfo(tz_name)
            return (
                datetime.fromisoformat(value.replace("Z", "+00:00"))
                .astimezone(zone)
                .strftime("%Y-%m-%d %H:%M:%S %z")
            )
        except ValueError:
            return value
    return str(value)


def _add_rows(grid: Table, rows: list[tuple[str, object]]) -> bool:
    added = False
    for label, value in rows:
        rendered = _render_value(value)
        if rendered == "-":
            continue
        grid.add_row(label, rendered)
        added = True
    return added


def _build_section(title: str, rows: list[tuple[str, object]]) -> Panel | None:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim", min_width=16)
    grid.add_column()
    if not _add_rows(grid, rows):
        return None
    return Panel(
        grid, title=f"[bold]{title}[/bold]", title_align="left", padding=(1, 2)
    )


def employee_command(ctx: typer.Context) -> None:
    """Show the current Holded employee profile."""

    state: AppState = ctx.obj

    with HoldedClient(state.session_store) as client:
        employee = client.get_employee()
        personal_info = client.get_personal_info()

    console = get_output_console()

    if not employee and not personal_info:
        console.print("[dim]No employee data found.[/dim]")
        return

    full_name = _pick_first(
        employee.get("fullName"),
        " ".join(
            part
            for part in [employee.get("name"), employee.get("surname")]
            if isinstance(part, str) and part
        ),
        " ".join(
            part
            for part in [
                _personal_field_value(personal_info, "name"),
                _personal_field_value(personal_info, "lastName"),
            ]
            if isinstance(part, str) and part
        ),
    )
    tracker = (
        employee.get("tracker") if isinstance(employee.get("tracker"), dict) else {}
    )
    contract = (
        employee.get("contract") if isinstance(employee.get("contract"), dict) else {}
    )
    display_timezone = _resolve_timezone_name(state, tracker)

    summary_section = _build_section(
        "You",
        [
            ("name", full_name),
            (
                "email",
                _pick_first(
                    employee.get("email"),
                    _personal_field_value(personal_info, "email"),
                    _personal_field_value(personal_info, "email2"),
                ),
            ),
            (
                "role",
                _pick_first(contract.get("jobTitle"), employee.get("jobTitle")),
            ),
            ("mobile", _personal_field_value(personal_info, "mobile")),
            ("nationality", _personal_field_value(personal_info, "nationality")),
            ("supervisor", employee.get("isSupervisor")),
        ],
    )

    tracker_section = _build_section(
        "Tracker",
        [
            ("status", tracker.get("status")),
            ("running", tracker.get("running")),
            (
                "started at",
                _format_timestamp(
                    tracker.get("startDateWithTimeZone") or tracker.get("start"),
                    tz_name=display_timezone,
                ),
            ),
            ("effective time", tracker.get("effectiveWorkedTime")),
            ("paused time", tracker.get("pausedTime")),
            ("timezone", tracker.get("timezone")),
            ("log method", tracker.get("logMethod")),
        ],
    )

    employment_section = _build_section(
        "Employment",
        [
            ("employee id", employee.get("id")),
            ("tracker id", tracker.get("id")),
            ("account id", tracker.get("accountId")),
            ("employee name", tracker.get("employeeName")),
            ("can manage trackers", employee.get("canManageTrackers")),
            ("bonus count", employee.get("bonusCount")),
        ],
    )

    personal_section = _build_section(
        "Personal info",
        [
            (
                "birth date",
                _format_timestamp(
                    _personal_field_value(personal_info, "dateOfBirth"),
                    tz_name=display_timezone,
                ),
            ),
            ("gender", _personal_field_value(personal_info, "gender")),
            ("phone", _personal_field_value(personal_info, "phone")),
            ("street", _personal_field_value(personal_info, "street")),
            ("city", _personal_field_value(personal_info, "city")),
            ("postal code", _personal_field_value(personal_info, "postalCode")),
            ("province", _personal_field_value(personal_info, "province")),
            ("country", _personal_field_value(personal_info, "country")),
        ],
    )

    private_section = _build_section(
        "Private records",
        [
            ("iban", _personal_field_value(personal_info, "iban")),
            (
                "identity document",
                _personal_field_value(personal_info, "identityDocument"),
            ),
            (
                "document type",
                _personal_field_value(personal_info, "identityDocumentType"),
            ),
            ("social security", _personal_field_value(personal_info, "socialSecurity")),
            (
                "emergency contacts",
                _personal_field_value(personal_info, "emergencyContacts"),
            ),
        ],
    )

    panels = [
        panel
        for panel in [
            summary_section,
            tracker_section,
            employment_section,
            personal_section,
            private_section,
        ]
        if panel is not None
    ]

    console.print(Group(*panels))
