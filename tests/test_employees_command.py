"""Tests for organization command with mocked HoldedClient."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


def _fake_state() -> SimpleNamespace:
    return SimpleNamespace(session_store=object())


def _patch(monkeypatch, fake_state, employees: list[dict]):
    cli_module = importlib.import_module("holded_tt.cli")
    employees_module = importlib.import_module("holded_tt.commands.employees")

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get_organization_employees(self):
            return employees

    monkeypatch.setattr(cli_module, "create_app_state", lambda: fake_state)
    monkeypatch.setattr(employees_module, "HoldedClient", lambda *_: FakeClient())
    return cli_module


@pytest.mark.parametrize("value", [None, ""])
def test_string_value_returns_default_for_empty_values(value) -> None:
    employees_module = importlib.import_module("holded_tt.commands.employees")

    assert employees_module._string_value(value, "fallback") == "fallback"


def test_get_nested_str_returns_placeholder_when_intermediate_value_is_not_dict() -> (
    None
):
    employees_module = importlib.import_module("holded_tt.commands.employees")

    assert (
        employees_module._get_nested_str(
            {"contract": "Engineer"}, "contract", "jobTitle"
        )
        == "-"
    )


def test_organization_lists_directory_fields(runner, monkeypatch) -> None:
    employees = [
        {
            "id": "emp-1",
            "fullName": "Mikel Example",
            "contactInfo": {"email": "mikel@example.com"},
            "contract": {"jobTitle": "Engineer"},
            "workplace": {"name": "Barcelona"},
            "teams": [{"name": "Platform"}, {"name": "CLI"}],
        },
        {
            "id": "emp-2",
            "name": "Alex",
            "contactInfo": {"email": "alex@example.com"},
            "contract": {"jobTitle": "Designer"},
            "workplace": {"name": "Remote"},
            "teams": [],
        },
    ]
    cli = _patch(monkeypatch, _fake_state(), employees)

    result = runner.invoke(cli.app, ["organization"])

    assert result.exit_code == 0
    assert "emp-1" in result.stdout
    assert "Mikel Example" in result.stdout
    assert "mikel@example" in result.stdout
    assert ".com" in result.stdout
    assert "Engineer" in result.stdout
    assert "Barcelona" in result.stdout
    assert "Platform" in result.stdout
    assert "CLI" in result.stdout
    assert "emp-2" in result.stdout
    assert "Alex" in result.stdout


def test_organization_shows_empty_message_when_none(runner, monkeypatch) -> None:
    cli = _patch(monkeypatch, _fake_state(), employees=[])

    result = runner.invoke(cli.app, ["organization"])

    assert result.exit_code == 0
    assert "No organization employees found" in result.stdout
