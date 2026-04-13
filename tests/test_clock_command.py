"""Tests for clock subcommands with mocked HoldedClient (CLK-10 through CLK-25)."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_RUNNING_TRACKER = {
    "id": "t1",
    "start": "2026-04-13T08:00:00+00:00",
    "running": True,
    "paused": False,
    "pausedTime": 0,
}

_PAUSED_TRACKER = {
    "id": "t1",
    "start": "2026-04-13T08:00:00+00:00",
    "running": False,
    "paused": True,
    "pausedTime": 600,
    "pausedSince": "2026-04-13T09:00:00+00:00",
    "currentPause": {"start": "2026-04-13T09:00:00+00:00"},
}


def _fake_state(timezone: str = "UTC") -> SimpleNamespace:
    return SimpleNamespace(
        session_store=object(),
        config=SimpleNamespace(timezone=timezone),
    )


def _make_client_class(**methods):
    """Return a FakeHoldedClient class whose methods are overridden by **methods."""
    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def get_current_tracker(self): return None
        def clock_in(self): pass
        def clock_out(self, _id): pass
        def pause_tracker(self, _id): return {}
        def resume_tracker(self, _id): return {}

    for name, fn in methods.items():
        setattr(FakeClient, name, fn)

    return FakeClient


def _patch(monkeypatch, fake_state, FakeClient):
    cli_module = importlib.import_module("holded_tt_cli.cli")
    clock_module = importlib.import_module("holded_tt_cli.commands.clock")
    monkeypatch.setattr(cli_module, "create_app_state", lambda: fake_state)
    monkeypatch.setattr(clock_module, "HoldedClient", lambda *_: FakeClient())
    return cli_module


# ---------------------------------------------------------------------------
# clock (no subcommand) — callback behaviour
# ---------------------------------------------------------------------------

def test_clock_callback_shows_no_active_tracker(runner, monkeypatch) -> None:
    Client = _make_client_class()
    cli = _patch(monkeypatch, _fake_state(), Client)

    result = runner.invoke(cli.app, ["clock"])

    assert result.exit_code == 0
    assert "No active tracker" in result.stdout


def test_clock_callback_shows_running_status(runner, monkeypatch) -> None:
    Client = _make_client_class(
        get_current_tracker=lambda self: _RUNNING_TRACKER,
    )
    cli = _patch(monkeypatch, _fake_state(), Client)

    result = runner.invoke(cli.app, ["clock"])

    assert result.exit_code == 0
    assert "Running" in result.stdout


def test_clock_callback_shows_paused_status(runner, monkeypatch) -> None:
    Client = _make_client_class(
        get_current_tracker=lambda self: _PAUSED_TRACKER,
    )
    cli = _patch(monkeypatch, _fake_state(), Client)

    result = runner.invoke(cli.app, ["clock"])

    assert result.exit_code == 0
    assert "Paused" in result.stdout


# ---------------------------------------------------------------------------
# clock in
# ---------------------------------------------------------------------------

def test_clock_in_success(runner, monkeypatch) -> None:
    # First call: no existing tracker; second call: returns new tracker
    responses = [None, _RUNNING_TRACKER]
    call = [0]

    def _get_tracker(self):
        r = responses[call[0]]
        call[0] += 1
        return r

    Client = _make_client_class(get_current_tracker=_get_tracker)
    cli = _patch(monkeypatch, _fake_state(), Client)

    result = runner.invoke(cli.app, ["clock", "in"])

    assert result.exit_code == 0
    assert "Clocked in" in result.stdout


def test_clock_in_fails_when_tracker_already_running(runner, monkeypatch) -> None:
    errors_module = importlib.import_module("holded_tt_cli.errors")
    Client = _make_client_class(
        get_current_tracker=lambda self: _RUNNING_TRACKER,
    )
    cli = _patch(monkeypatch, _fake_state(), Client)

    result = runner.invoke(cli.app, ["clock", "in"])

    assert result.exit_code != 0
    assert isinstance(result.exception, errors_module.InputError)
    assert "already running" in str(result.exception)


# ---------------------------------------------------------------------------
# clock out
# ---------------------------------------------------------------------------

def test_clock_out_success(runner, monkeypatch) -> None:
    Client = _make_client_class(
        get_current_tracker=lambda self: _RUNNING_TRACKER,
    )
    cli = _patch(monkeypatch, _fake_state(), Client)

    result = runner.invoke(cli.app, ["clock", "out"])

    assert result.exit_code == 0
    assert "Clocked out" in result.stdout


def test_clock_out_fails_when_no_active_tracker(runner, monkeypatch) -> None:
    errors_module = importlib.import_module("holded_tt_cli.errors")
    Client = _make_client_class()  # get_current_tracker returns None
    cli = _patch(monkeypatch, _fake_state(), Client)

    result = runner.invoke(cli.app, ["clock", "out"])

    assert result.exit_code != 0
    assert isinstance(result.exception, errors_module.InputError)
    assert "No active tracker" in str(result.exception)


# ---------------------------------------------------------------------------
# clock pause
# ---------------------------------------------------------------------------

def test_clock_pause_success(runner, monkeypatch) -> None:
    Client = _make_client_class(
        get_current_tracker=lambda self: _RUNNING_TRACKER,
    )
    cli = _patch(monkeypatch, _fake_state(), Client)

    result = runner.invoke(cli.app, ["clock", "pause"])

    assert result.exit_code == 0
    assert "Paused" in result.stdout


def test_clock_pause_fails_when_already_paused(runner, monkeypatch) -> None:
    errors_module = importlib.import_module("holded_tt_cli.errors")
    Client = _make_client_class(
        get_current_tracker=lambda self: _PAUSED_TRACKER,
    )
    cli = _patch(monkeypatch, _fake_state(), Client)

    result = runner.invoke(cli.app, ["clock", "pause"])

    assert result.exit_code != 0
    assert isinstance(result.exception, errors_module.InputError)
    assert "already paused" in str(result.exception)


# ---------------------------------------------------------------------------
# clock resume
# ---------------------------------------------------------------------------

def test_clock_resume_success(runner, monkeypatch) -> None:
    Client = _make_client_class(
        get_current_tracker=lambda self: _PAUSED_TRACKER,
        resume_tracker=lambda self, _id: {"end": "2026-04-13T09:10:00+00:00"},
    )
    cli = _patch(monkeypatch, _fake_state(), Client)

    result = runner.invoke(cli.app, ["clock", "resume"])

    assert result.exit_code == 0
    assert "Resumed" in result.stdout


def test_clock_resume_fails_when_not_paused(runner, monkeypatch) -> None:
    errors_module = importlib.import_module("holded_tt_cli.errors")
    Client = _make_client_class(
        get_current_tracker=lambda self: _RUNNING_TRACKER,
    )
    cli = _patch(monkeypatch, _fake_state(), Client)

    result = runner.invoke(cli.app, ["clock", "resume"])

    assert result.exit_code != 0
    assert isinstance(result.exception, errors_module.InputError)
    assert "not paused" in str(result.exception)


# ---------------------------------------------------------------------------
# clock status
# ---------------------------------------------------------------------------

def test_clock_status_shows_running(runner, monkeypatch) -> None:
    Client = _make_client_class(
        get_current_tracker=lambda self: _RUNNING_TRACKER,
    )
    cli = _patch(monkeypatch, _fake_state(), Client)

    result = runner.invoke(cli.app, ["clock", "status"])

    assert result.exit_code == 0
    assert "Running" in result.stdout


def test_clock_status_shows_paused(runner, monkeypatch) -> None:
    Client = _make_client_class(
        get_current_tracker=lambda self: _PAUSED_TRACKER,
    )
    cli = _patch(monkeypatch, _fake_state(), Client)

    result = runner.invoke(cli.app, ["clock", "status"])

    assert result.exit_code == 0
    assert "Paused" in result.stdout


def test_clock_status_shows_no_active_when_no_tracker(runner, monkeypatch) -> None:
    Client = _make_client_class()
    cli = _patch(monkeypatch, _fake_state(), Client)

    result = runner.invoke(cli.app, ["clock", "status"])

    assert result.exit_code == 0
    assert "No active tracker" in result.stdout
