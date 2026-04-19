"""Tests for workplaces command with mocked HoldedClient (WP-01 through WP-02)."""

from __future__ import annotations

import importlib
from types import SimpleNamespace


def _fake_state() -> SimpleNamespace:
    return SimpleNamespace(session_store=object())


def _patch(monkeypatch, fake_state, workplaces: list[dict]):
    cli_module = importlib.import_module("holded_tt.cli")
    workplaces_module = importlib.import_module("holded_tt.commands.workplaces")

    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def get_workplaces(self): return workplaces

    monkeypatch.setattr(cli_module, "create_app_state", lambda: fake_state)
    monkeypatch.setattr(workplaces_module, "HoldedClient", lambda *_: FakeClient())
    return cli_module


def test_workplaces_lists_id_and_name(runner, monkeypatch) -> None:
    workplaces = [
        {"id": "wp-1", "name": "Oficina Madrid"},
        {"id": "wp-2", "name": "Remoto"},
    ]
    cli = _patch(monkeypatch, _fake_state(), workplaces)

    result = runner.invoke(cli.app, ["workplaces"])

    assert result.exit_code == 0
    assert "wp-1" in result.stdout
    assert "Oficina Madrid" in result.stdout
    assert "wp-2" in result.stdout
    assert "Remoto" in result.stdout


def test_workplaces_shows_empty_message_when_none(runner, monkeypatch) -> None:
    cli = _patch(monkeypatch, _fake_state(), workplaces=[])

    result = runner.invoke(cli.app, ["workplaces"])

    assert result.exit_code == 0
    assert "No workplaces found" in result.stdout
