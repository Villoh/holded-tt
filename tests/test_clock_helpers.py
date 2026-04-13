"""Tests for clock command helpers and CLI surface (CLK-01 through CLK-08)."""

from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Pure-function tests: _elapsed
# ---------------------------------------------------------------------------


class _FakeDatetime(datetime):
    """Datetime subclass that returns a fixed 'now'."""

    _fixed_now: datetime

    @classmethod
    def now(cls, tz=None) -> datetime:  # type: ignore[override]
        return cls._fixed_now


def _patch_clock_datetime(monkeypatch: pytest.MonkeyPatch, fixed_now: datetime) -> None:
    clock_module = importlib.import_module("holded_tt_cli.commands.clock")
    _FakeDatetime._fixed_now = fixed_now
    monkeypatch.setattr(clock_module, "datetime", _FakeDatetime)


def test_elapsed_seconds_only(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_now = datetime(2026, 4, 13, 10, 0, 45, tzinfo=timezone.utc)
    _patch_clock_datetime(monkeypatch, fixed_now)
    clock_module = importlib.import_module("holded_tt_cli.commands.clock")

    result = clock_module._elapsed("2026-04-13T10:00:00+00:00")

    assert result == "45s"


def test_elapsed_minutes_and_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_now = datetime(2026, 4, 13, 10, 3, 20, tzinfo=timezone.utc)
    _patch_clock_datetime(monkeypatch, fixed_now)
    clock_module = importlib.import_module("holded_tt_cli.commands.clock")

    result = clock_module._elapsed("2026-04-13T10:00:00+00:00")

    assert result == "3m 20s"


def test_elapsed_hours_and_minutes(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_now = datetime(2026, 4, 13, 11, 30, 0, tzinfo=timezone.utc)
    _patch_clock_datetime(monkeypatch, fixed_now)
    clock_module = importlib.import_module("holded_tt_cli.commands.clock")

    # 1h 30m elapsed — seconds are not shown when hours > 0
    result = clock_module._elapsed("2026-04-13T10:00:00+00:00")

    assert result == "1h 30m"


def test_elapsed_naive_start_treated_as_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_now = datetime(2026, 4, 13, 10, 0, 10, tzinfo=timezone.utc)
    _patch_clock_datetime(monkeypatch, fixed_now)
    clock_module = importlib.import_module("holded_tt_cli.commands.clock")

    # Holded sometimes returns naive timestamps — should be treated as UTC
    result = clock_module._elapsed("2026-04-13T10:00:00")

    assert result == "10s"


# ---------------------------------------------------------------------------
# Pure-function tests: _local_hhmm
# ---------------------------------------------------------------------------


def test_local_hhmm_converts_to_paris_time() -> None:
    clock_module = importlib.import_module("holded_tt_cli.commands.clock")

    # UTC 08:30 in summer Paris time (UTC+2) = 10:30
    result = clock_module._local_hhmm("2026-04-13T08:30:00+00:00", "Europe/Paris")

    assert result == "10:30"


def test_local_hhmm_converts_to_utc() -> None:
    clock_module = importlib.import_module("holded_tt_cli.commands.clock")

    result = clock_module._local_hhmm("2026-04-13T17:00:00+00:00", "UTC")

    assert result == "17:00"


def test_print_status_shows_running_paused_total(runner, monkeypatch) -> None:
    Client = type(
        "FakeClient",
        (),
        {
            "__enter__": lambda self: self,
            "__exit__": lambda self, *_: None,
            "get_current_tracker": lambda self: {
                **{
                    "id": "t1",
                    "start": "2026-04-13T08:00:00+00:00",
                    "running": True,
                    "paused": False,
                },
                "pausedTime": 600,
            },
        },
    )
    cli_module = importlib.import_module("holded_tt_cli.cli")
    clock_module = importlib.import_module("holded_tt_cli.commands.clock")
    monkeypatch.setattr(
        cli_module,
        "create_app_state",
        lambda: type(
            "State",
            (),
            {
                "session_store": object(),
                "config": type("Config", (), {"timezone": "UTC"})(),
            },
        )(),
    )
    monkeypatch.setattr(clock_module, "HoldedClient", lambda *_: Client())

    result = runner.invoke(cli_module.app, ["clock", "status"])

    assert result.exit_code == 0
    assert "paused 10m" in result.stdout


def test_print_status_shows_idle_tracker_state(runner, monkeypatch) -> None:
    Client = type(
        "FakeClient",
        (),
        {
            "__enter__": lambda self: self,
            "__exit__": lambda self, *_: None,
            "get_current_tracker": lambda self: {
                "id": "t1",
                "start": "2026-04-13T08:00:00+00:00",
                "running": False,
                "paused": False,
                "pausedTime": 0,
            },
        },
    )
    cli_module = importlib.import_module("holded_tt_cli.cli")
    clock_module = importlib.import_module("holded_tt_cli.commands.clock")
    monkeypatch.setattr(
        cli_module,
        "create_app_state",
        lambda: type(
            "State",
            (),
            {
                "session_store": object(),
                "config": type("Config", (), {"timezone": "UTC"})(),
            },
        )(),
    )
    monkeypatch.setattr(clock_module, "HoldedClient", lambda *_: Client())

    result = runner.invoke(cli_module.app, ["clock", "status"])

    assert result.exit_code == 0
    assert "No active tracker" in result.stdout


# ---------------------------------------------------------------------------
# CLI surface tests
# ---------------------------------------------------------------------------


def test_clock_help_lists_subcommands(runner) -> None:
    cli_module = importlib.import_module("holded_tt_cli.cli")

    result = runner.invoke(cli_module.app, ["clock", "--help"])

    assert result.exit_code == 0
    assert "in" in result.stdout
    assert "out" in result.stdout
    assert "pause" in result.stdout
    assert "resume" in result.stdout
    assert "status" in result.stdout


def test_clock_without_session_raises_auth_error(
    tmp_path: Path, runner, monkeypatch
) -> None:
    """clock sub-commands are not wrapped with _with_cli_error_handling, so
    MissingAuthenticationError propagates as an unhandled exception (exit 1,
    captured in result.exception)."""
    paths_module = importlib.import_module("holded_tt_cli.paths")
    session_module = importlib.import_module("holded_tt_cli.session")
    state_module = importlib.import_module("holded_tt_cli.state")
    config_module = importlib.import_module("holded_tt_cli.config")
    auth_module = importlib.import_module("holded_tt_cli.auth")

    config_dir = tmp_path / "holded-tt-cli"
    session_file = config_dir / "session.json"

    monkeypatch.setattr(paths_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(paths_module, "CONFIG_FILE", config_dir / "config.toml")
    monkeypatch.setattr(paths_module, "SESSION_FILE", session_file)
    monkeypatch.setattr(paths_module, "HOLIDAYS_FILE", config_dir / "holidays.json")
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_dir / "config.toml")
    monkeypatch.setattr(session_module, "SESSION_FILE", session_file)
    monkeypatch.setattr(state_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(state_module, "CONFIG_FILE", config_dir / "config.toml")
    monkeypatch.setattr(state_module, "SESSION_FILE", session_file)
    monkeypatch.setattr(state_module, "HOLIDAYS_FILE", config_dir / "holidays.json")

    cli_module = importlib.import_module("holded_tt_cli.cli")

    # `clock in` calls HoldedClient which requires a session
    result = runner.invoke(cli_module.app, ["clock", "in"])

    assert result.exit_code != 0
    assert isinstance(result.exception, auth_module.MissingAuthenticationError)
