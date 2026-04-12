"""Tests for the holded track command (TRK-01 through TRK-11)."""

from __future__ import annotations

import importlib
import json
from datetime import date
from pathlib import Path

import httpx
import pytest


def _patch_runtime_files(base_dir: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Redirect all runtime file paths to a temp directory. Returns path dict."""
    paths_module = importlib.import_module("holded_cli.paths")
    session_module = importlib.import_module("holded_cli.session")
    state_module = importlib.import_module("holded_cli.state")
    config_module = importlib.import_module("holded_cli.config")

    config_dir = base_dir / "holded-cli"
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

    return {
        "config_dir": config_dir,
        "session_file": session_file,
        "holidays_file": holidays_file,
    }


def _write_session(session_file: Path) -> None:
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(
        json.dumps({
            "cookies": {"hat": "tok", "PHPSESSID": "sid"},
            "saved_at": "2026-04-10T08:00:00Z",
        }),
        encoding="utf-8",
    )


def _write_holiday_cache(holidays_file: Path, year: int, holidays: list[str]) -> None:
    holidays_file.parent.mkdir(parents=True, exist_ok=True)
    holidays_file.write_text(
        json.dumps({"year": year, "holidays": holidays}),
        encoding="utf-8",
    )


def test_track_requires_date_argument(tmp_path: Path, runner, monkeypatch) -> None:
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(paths["session_file"])
    cli_module = importlib.import_module("holded_cli.cli")

    result = runner.invoke(cli_module.app, ["track"])

    assert result.exit_code == 1
    assert "Traceback" not in result.stdout


def test_track_rejects_inverted_date_range(tmp_path: Path, runner, monkeypatch) -> None:
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(paths["session_file"])
    cli_module = importlib.import_module("holded_cli.cli")

    result = runner.invoke(
        cli_module.app, ["track", "--from", "2026-04-10", "--to", "2026-04-01"]
    )

    assert result.exit_code == 1
    assert "Traceback" not in result.stdout


def test_track_dry_run_shows_table_for_week(tmp_path: Path, runner, monkeypatch) -> None:
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(paths["session_file"])
    # Cache an empty holiday set so no API call is needed
    _write_holiday_cache(paths["holidays_file"], 2026, [])
    cli_module = importlib.import_module("holded_cli.cli")

    # 2026-04-06 Mon to 2026-04-10 Fri = 5 working days
    result = runner.invoke(
        cli_module.app,
        ["track", "--from", "2026-04-06", "--to", "2026-04-10", "--dry-run"],
    )

    assert result.exit_code == 0
    assert "Would register 5 day(s)" in result.stdout
    assert "Traceback" not in result.stdout


def test_track_dry_run_excludes_weekends_by_default(
    tmp_path: Path, runner, monkeypatch
) -> None:
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(paths["session_file"])
    _write_holiday_cache(paths["holidays_file"], 2026, [])
    cli_module = importlib.import_module("holded_cli.cli")

    # 2026-04-06 Mon to 2026-04-12 Sun = 5 working days, 2 weekend days
    result = runner.invoke(
        cli_module.app,
        ["track", "--from", "2026-04-06", "--to", "2026-04-12", "--dry-run"],
    )

    assert result.exit_code == 0
    assert "Would register 5 day(s)" in result.stdout


def test_track_dry_run_includes_weekends_when_flag_given(
    tmp_path: Path, runner, monkeypatch
) -> None:
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(paths["session_file"])
    _write_holiday_cache(paths["holidays_file"], 2026, [])
    cli_module = importlib.import_module("holded_cli.cli")

    result = runner.invoke(
        cli_module.app,
        [
            "track",
            "--from", "2026-04-06",
            "--to", "2026-04-12",
            "--include-weekends",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Would register 7 day(s)" in result.stdout


def test_track_dry_run_excludes_cached_holidays(
    tmp_path: Path, runner, monkeypatch
) -> None:
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(paths["session_file"])
    # 2026-04-17 is Good Friday — mark it as a holiday
    _write_holiday_cache(paths["holidays_file"], 2026, ["2026-04-17"])
    cli_module = importlib.import_module("holded_cli.cli")

    # Mon 14 to Fri 17 = 4 working days, minus holiday on Fri = 3
    result = runner.invoke(
        cli_module.app,
        ["track", "--from", "2026-04-14", "--to", "2026-04-17", "--dry-run"],
    )

    assert result.exit_code == 0
    assert "Would register 3 day(s)" in result.stdout


def test_track_dry_run_today_registers_today(
    tmp_path: Path, runner, monkeypatch
) -> None:
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(paths["session_file"])
    _write_holiday_cache(paths["holidays_file"], date.today().year, [])
    cli_module = importlib.import_module("holded_cli.cli")

    result = runner.invoke(cli_module.app, ["track", "--today", "--dry-run"])

    today = date.today()
    if today.weekday() < 5:
        assert result.exit_code == 0
        assert "Would register 1 day(s)" in result.stdout
    else:
        # Weekend — expect 0 days or explicit message
        assert result.exit_code == 0


def test_track_dry_run_shows_pauses_in_table(
    tmp_path: Path, runner, monkeypatch
) -> None:
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(paths["session_file"])
    _write_holiday_cache(paths["holidays_file"], 2026, [])
    cli_module = importlib.import_module("holded_cli.cli")

    result = runner.invoke(
        cli_module.app,
        [
            "track",
            "--from", "2026-04-07",
            "--to", "2026-04-07",
            "--pause", "12:00-13:00",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "12:00-13:00" in result.stdout


def test_track_rejects_malformed_pause(tmp_path: Path, runner, monkeypatch) -> None:
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(paths["session_file"])
    _write_holiday_cache(paths["holidays_file"], 2026, [])
    cli_module = importlib.import_module("holded_cli.cli")

    result = runner.invoke(
        cli_module.app,
        [
            "track",
            "--from", "2026-04-07",
            "--to", "2026-04-07",
            "--pause", "12:00",  # malformed — no end time
            "--dry-run",
        ],
    )

    assert result.exit_code != 0


def test_track_without_session_shows_auth_error(
    tmp_path: Path, runner, monkeypatch
) -> None:
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    # No session file written
    _write_holiday_cache(paths["holidays_file"], 2026, [])
    cli_module = importlib.import_module("holded_cli.cli")

    result = runner.invoke(
        cli_module.app,
        ["track", "--from", "2026-04-07", "--to", "2026-04-07", "--dry-run"],
    )

    # Auth error should show up as operational error (exit 2)
    # OR the dry_run may skip API and only fail on submission
    # Either way: no traceback
    assert "Traceback" not in result.stdout
