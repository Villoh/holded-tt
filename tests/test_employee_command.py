"""Tests for employee command output."""

from __future__ import annotations

import importlib.util
from datetime import timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import typer


EMPLOYEE_COMMAND_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "holded_cli"
    / "commands"
    / "employee.py"
)


def _load_employee_module():
    spec = importlib.util.spec_from_file_location(
        "test_holded_cli_commands_employee", EMPLOYEE_COMMAND_PATH
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_state() -> SimpleNamespace:
    return SimpleNamespace(
        session_store=object(),
        config=SimpleNamespace(timezone="Europe/Madrid"),
    )


def _patch(monkeypatch, fake_state, employee: dict, personal_info: dict):
    employee_module = _load_employee_module()

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get_employee(self):
            return employee

        def get_personal_info(self):
            return personal_info

    monkeypatch.setattr(employee_module, "HoldedClient", lambda *_: FakeClient())
    monkeypatch.setattr(
        employee_module, "_get_zoneinfo", lambda *_: timezone(timedelta(hours=1))
    )

    app = typer.Typer()
    app.command("employee")(employee_module.employee_command)
    app.command("me")(employee_module.employee_command)
    app.command("whoami")(employee_module.employee_command)
    return app, fake_state


def test_employee_helper_functions_cover_sparse_and_fallback_values() -> None:
    employee_module = _load_employee_module()

    assert employee_module._render_value(True) == "yes"
    assert employee_module._render_value(False) == "no"
    assert employee_module._render_value({}) == "-"
    assert employee_module._render_value(["b", "a"]) == '["b", "a"]'
    assert employee_module._render_value("") == "-"
    assert employee_module._pick_first(None, "", 42) == "42"
    assert employee_module._pick_first(None, "") is None
    assert (
        employee_module._personal_field_value({"email": {"value": "a@b.c"}}, "email")
        == "a@b.c"
    )
    assert employee_module._personal_field_value({"email": "a@b.c"}, "email") == "a@b.c"
    assert (
        employee_module._resolve_timezone_name(
            _fake_state(),
            {"timezone": "Europe/Paris"},
        )
        == "Europe/Paris"
    )
    assert employee_module._resolve_timezone_name(_fake_state(), {}) == "Europe/Madrid"


def test_employee_timestamp_helpers_cover_invalid_timezone_and_values() -> None:
    employee_module = _load_employee_module()

    zone = employee_module._get_zoneinfo("Definitely/Not-A-Timezone")

    assert zone == timezone.utc
    assert employee_module._format_timestamp(None) == "-"
    assert employee_module._format_timestamp("not-a-date") == "not-a-date"
    assert employee_module._format_timestamp(object()).startswith("<object object at")
    assert (
        employee_module._format_timestamp("2026-04-13T09:22:39Z", tz_name="UTC")
        == "2026-04-13 09:22:39 +0000"
    )


def test_employee_section_helpers_skip_empty_rows() -> None:
    employee_module = _load_employee_module()

    section = employee_module._build_section(
        "Filled",
        [("name", "Alice"), ("unused", None)],
    )

    assert section is not None
    assert (
        employee_module._build_section("Empty", [("unused", None), ("blank", "")])
        is None
    )


def test_employee_combines_employee_and_personal_info(runner, monkeypatch) -> None:
    app, state = _patch(
        monkeypatch,
        _fake_state(),
        employee={
            "id": "emp-1",
            "fullName": "Alice Example",
            "isSupervisor": False,
            "contract": {"jobTitle": "Backend Developer"},
            "tracker": {
                "status": "running",
                "running": True,
                "startDateWithTimeZone": "2026-04-13T09:22:39+02:00",
                "timezone": "Europe/Madrid",
            },
        },
        personal_info={
            "email": {"value": "alice@example.com", "isVisible": True},
            "mobile": {"value": "+34 600 123 456", "isVisible": True},
            "country": {"value": "ES", "isVisible": False},
            "dateOfBirth": {"value": 827362800000, "isVisible": False},
        },
    )

    result = runner.invoke(app, ["employee"], obj=state)

    assert result.exit_code == 0
    assert "You" in result.stdout
    assert "Tracker" in result.stdout
    assert "Employment" in result.stdout
    assert "Personal info" in result.stdout
    assert "Private records" not in result.stdout
    assert "Raw employee payload" not in result.stdout
    assert "Raw personal payload" not in result.stdout
    assert "emp-1" in result.stdout
    assert "Alice Example" in result.stdout
    assert "Backend Developer" in result.stdout
    assert "running" in result.stdout
    assert "alice@example.com" in result.stdout
    assert "+34 600 123 456" in result.stdout
    assert "ES" in result.stdout
    assert "1996-03-21" in result.stdout


def test_employee_birth_date_uses_configured_timezone(runner, monkeypatch) -> None:
    app, state = _patch(
        monkeypatch,
        _fake_state(),
        employee={},
        personal_info={"dateOfBirth": {"value": 827362800000, "isVisible": False}},
    )

    result = runner.invoke(app, ["employee"], obj=state)

    assert result.exit_code == 0
    assert "1996-03-21" in result.stdout
    assert "1996-03-20" not in result.stdout


def test_employee_birth_date_accepts_seconds_timestamps(runner, monkeypatch) -> None:
    app, state = _patch(
        monkeypatch,
        _fake_state(),
        employee={},
        personal_info={"dateOfBirth": {"value": 827362800, "isVisible": False}},
    )

    result = runner.invoke(app, ["employee"], obj=state)

    assert result.exit_code == 0
    assert "1996-03-21" in result.stdout
    assert "1996-03-20" not in result.stdout


def test_employee_birth_date_accepts_millisecond_timestamps(
    runner, monkeypatch
) -> None:
    app, state = _patch(
        monkeypatch,
        _fake_state(),
        employee={},
        personal_info={"dateOfBirth": {"value": 827362800000, "isVisible": False}},
    )

    result = runner.invoke(app, ["employee"], obj=state)

    assert result.exit_code == 0
    assert "1996-03-21" in result.stdout
    assert "1996-03-20" not in result.stdout


def test_employee_aliases_resolve_to_same_combined_view(runner, monkeypatch) -> None:
    app, state = _patch(
        monkeypatch,
        _fake_state(),
        employee={"name": "Alice"},
        personal_info={"email": {"value": "alice@example.com"}},
    )

    for command_name in ("me", "whoami"):
        result = runner.invoke(app, [command_name], obj=state)

        assert result.exit_code == 0
        assert "You" in result.stdout
        assert "Alice" in result.stdout
        assert "alice@example.com" in result.stdout


def test_employee_shows_empty_message_when_both_payloads_are_missing(
    runner, monkeypatch
) -> None:
    app, state = _patch(monkeypatch, _fake_state(), employee={}, personal_info={})

    result = runner.invoke(app, ["employee"], obj=state)

    assert result.exit_code == 0
    assert "No employee data found" in result.stdout


def test_employee_uses_fallback_name_and_shows_private_section(
    runner, monkeypatch
) -> None:
    app, state = _patch(
        monkeypatch,
        _fake_state(),
        employee={
            "name": "Alice",
            "surname": "Example",
            "tracker": {
                "start": "2026-04-13T09:22:39Z",
                "running": False,
            },
        },
        personal_info={
            "iban": {"value": "ES7620770024003102575766"},
            "identityDocument": {"value": "12345678A"},
        },
    )

    result = runner.invoke(app, ["employee"], obj=state)

    assert result.exit_code == 0
    assert "Alice Example" in result.stdout
    assert "Private records" in result.stdout
    assert "ES7620770024003102575766" in result.stdout
    assert "2026-04-13 10:22:39 +0100" in result.stdout
    assert "no" in result.stdout
