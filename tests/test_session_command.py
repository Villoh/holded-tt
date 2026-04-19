"""Tests for the holded session command (AUTH-03, AUTH-04)."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def _write_session(session_file: Path, cookies: dict, saved_at: str | None) -> None:
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(
        json.dumps({"cookies": cookies, "saved_at": saved_at}),
        encoding="utf-8",
    )


def _patch_runtime_files(base_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect all runtime file paths to a temp directory. Returns the session file path."""
    paths_module = importlib.import_module("holded_tt.paths")
    session_module = importlib.import_module("holded_tt.session")
    state_module = importlib.import_module("holded_tt.state")
    config_module = importlib.import_module("holded_tt.config")

    config_dir = base_dir / "holded-tt-cli"
    config_file = config_dir / "config.toml"
    session_file = config_dir / "session.json"
    holidays_file = config_dir / "holidays.json"

    monkeypatch.setattr(paths_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(paths_module, "CONFIG_FILE", config_file)
    monkeypatch.setattr(paths_module, "SESSION_FILE", session_file)
    monkeypatch.setattr(paths_module, "HOLIDAYS_FILE", holidays_file)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
    monkeypatch.setattr(session_module, "SESSION_FILE", session_file)
    monkeypatch.setattr(state_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(state_module, "CONFIG_FILE", config_file)
    monkeypatch.setattr(state_module, "SESSION_FILE", session_file)
    monkeypatch.setattr(state_module, "HOLIDAYS_FILE", holidays_file)

    return session_file


def test_session_reports_missing_when_no_session_file(
    tmp_path: Path, runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_runtime_files(tmp_path, monkeypatch)
    session_command_module = importlib.import_module("holded_tt.commands.session")
    monkeypatch.setattr(session_command_module, "validate_saved_session", lambda _: "missing")
    cli_module = importlib.import_module("holded_tt.cli")

    result = runner.invoke(cli_module.app, ["session"])

    assert result.exit_code == 0
    assert "missing" in result.stdout
    assert "live" in result.stdout
    assert "Traceback" not in result.stdout


def test_session_reports_active_for_live_valid_session(
    tmp_path: Path, runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_file = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(
        session_file,
        cookies={"hat": "token", "PHPSESSID": "abc"},
        saved_at="2026-04-10T12:00:00Z",
    )
    session_command_module = importlib.import_module("holded_tt.commands.session")
    monkeypatch.setattr(session_command_module, "validate_saved_session", lambda _: "active")
    cli_module = importlib.import_module("holded_tt.cli")

    result = runner.invoke(cli_module.app, ["session", "--live"])

    assert result.exit_code == 0
    assert "active" in result.stdout
    assert "live" in result.stdout
    assert "2026-04-10" in result.stdout


def test_session_reports_likely_valid_in_offline_mode(
    tmp_path: Path, runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_file = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(
        session_file,
        cookies={"hat": "token", "PHPSESSID": "abc"},
        saved_at="2026-04-10T12:00:00Z",
    )
    session_command_module = importlib.import_module("holded_tt.commands.session")
    monkeypatch.setattr(session_command_module, "describe_saved_session", lambda _: "likely valid")
    cli_module = importlib.import_module("holded_tt.cli")

    result = runner.invoke(cli_module.app, ["session", "--offline"])

    assert result.exit_code == 0
    assert "likely valid" in result.stdout
    assert "offline" in result.stdout
    assert "2026-04-10" in result.stdout


def test_session_shows_cookie_count(
    tmp_path: Path, runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_file = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(
        session_file,
        cookies={"hat": "tok", "PHPSESSID": "sid", "accountid": "aid"},
        saved_at="2026-04-10T08:00:00Z",
    )
    session_command_module = importlib.import_module("holded_tt.commands.session")
    monkeypatch.setattr(session_command_module, "validate_saved_session", lambda _: "active")
    cli_module = importlib.import_module("holded_tt.cli")

    result = runner.invoke(cli_module.app, ["session"])

    assert result.exit_code == 0
    assert "3" in result.stdout
    assert "4" in result.stdout
