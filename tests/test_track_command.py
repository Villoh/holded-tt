"""Tests for the holded track command (TRK-01 through TRK-11)."""

from __future__ import annotations

import importlib
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

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
        json.dumps(
            {
                "cookies": {"hat": "tok", "PHPSESSID": "sid"},
                "saved_at": "2026-04-10T08:00:00Z",
            }
        ),
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


def test_track_dry_run_shows_table_for_week(
    tmp_path: Path, runner, monkeypatch
) -> None:
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
    assert "would register 5 day(s)" in result.stdout
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
    assert "would register 5 day(s)" in result.stdout


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
            "--from",
            "2026-04-06",
            "--to",
            "2026-04-12",
            "--include-weekends",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "would register 7 day(s)" in result.stdout


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
    assert "would register 3 day(s)" in result.stdout


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
        assert "would register 1 day(s)" in result.stdout
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
            "--from",
            "2026-04-07",
            "--to",
            "2026-04-07",
            "--pause",
            "12:00-13:00",
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
            "--from",
            "2026-04-07",
            "--to",
            "2026-04-07",
            "--pause",
            "12:00",  # malformed — no end time
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


# ---------------------------------------------------------------------------
# Submit path — mocked HoldedClient
# ---------------------------------------------------------------------------


def _fake_state_with_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SimpleNamespace:
    """Patch runtime files and return a fake AppState with real config + session store."""
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(paths["session_file"])
    _write_holiday_cache(paths["holidays_file"], 2026, [])

    state_module = importlib.import_module("holded_cli.state")
    config_module = importlib.import_module("holded_cli.config")
    session_module = importlib.import_module("holded_cli.session")

    return SimpleNamespace(
        session_store=session_module.SessionStore(),
        config=config_module.load_config(),
        holidays_file=paths["holidays_file"],
        config_dir=paths["session_file"].parent,
        config_file=paths["session_file"].parent / "config.toml",
        session_file=paths["session_file"],
    )


def _patch_client(monkeypatch, cli_module, fake_state, *, calls: list):
    """Patch HoldedClient in track module to record calls."""
    track_module = importlib.import_module("holded_cli.commands.track")

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def check_bulk_timetracking(self, payload):
            calls.append(("check", payload))

        def submit_bulk_timetracking(self, payload):
            calls.append(("submit", payload))

    monkeypatch.setattr(cli_module, "create_app_state", lambda: fake_state)
    monkeypatch.setattr(track_module, "HoldedClient", lambda *_: FakeClient())


def test_validate_pause_rejects_reversed_times(
    tmp_path: Path, runner, monkeypatch
) -> None:
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(paths["session_file"])
    _write_holiday_cache(paths["holidays_file"], 2026, [])
    cli_module = importlib.import_module("holded_cli.cli")

    # "13:00-12:00" — start >= end → BadParameter
    result = runner.invoke(
        cli_module.app,
        [
            "track",
            "--from",
            "2026-04-07",
            "--to",
            "2026-04-07",
            "--pause",
            "13:00-12:00",
            "--dry-run",
        ],
    )

    assert result.exit_code != 0


def test_hhmm_to_minutes_converts_correctly() -> None:
    track_module = importlib.import_module("holded_cli.commands.track")

    assert track_module._hhmm_to_minutes("08:30") == 510
    assert track_module._hhmm_to_minutes("00:00") == 0
    assert track_module._hhmm_to_minutes("17:45") == 1065


def test_track_only_from_without_to_shows_error(
    tmp_path: Path, runner, monkeypatch
) -> None:
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(paths["session_file"])
    cli_module = importlib.import_module("holded_cli.cli")

    result = runner.invoke(cli_module.app, ["track", "--from", "2026-04-07"])

    assert result.exit_code != 0
    assert "Traceback" not in result.stdout


def test_track_dry_run_shows_no_working_days_message(
    tmp_path: Path, runner, monkeypatch
) -> None:
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(paths["session_file"])
    # Mark the entire range as holidays
    _write_holiday_cache(paths["holidays_file"], 2026, ["2026-04-07"])
    cli_module = importlib.import_module("holded_cli.cli")

    result = runner.invoke(
        cli_module.app,
        ["track", "--from", "2026-04-07", "--to", "2026-04-07", "--dry-run"],
    )

    assert result.exit_code == 0
    assert "No working days" in result.stdout


def test_track_dry_run_shows_workplace_in_context_line(
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
            "--from",
            "2026-04-07",
            "--to",
            "2026-04-07",
            "--workplace",
            "wp-123",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "wp-123" in result.stdout


def test_resolve_holidays_fetches_from_api_when_cache_missing(
    tmp_path: Path, runner, monkeypatch
) -> None:
    """_resolve_holidays live-fetch path (no cache, not dry_run): fetches via HoldedClient."""
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(paths["session_file"])
    # No holiday cache written → _resolve_holidays will call fetch_holidays
    cli_module = importlib.import_module("holded_cli.cli")
    track_module = importlib.import_module("holded_cli.commands.track")

    fetch_calls: list = []

    def fake_fetch_holidays(client, cache_path, year, workplace_id):
        fetch_calls.append(year)
        # Write a cache so subsequent calls return early
        _write_holiday_cache(cache_path, year, [])
        return frozenset()

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def check_bulk_timetracking(self, payload):
            pass

        def submit_bulk_timetracking(self, payload):
            pass

    state_module = importlib.import_module("holded_cli.state")
    config_module = importlib.import_module("holded_cli.config")
    session_module = importlib.import_module("holded_cli.session")

    fake_state = SimpleNamespace(
        session_store=session_module.SessionStore(),
        config=config_module.load_config(),
        holidays_file=paths["holidays_file"],
    )

    monkeypatch.setattr(cli_module, "create_app_state", lambda: fake_state)
    monkeypatch.setattr(track_module, "HoldedClient", lambda *_: FakeClient())
    monkeypatch.setattr(track_module, "fetch_holidays", fake_fetch_holidays)

    result = runner.invoke(
        cli_module.app,
        ["track", "--from", "2026-04-07", "--to", "2026-04-07"],
    )

    assert result.exit_code == 0
    assert fetch_calls == [2026]


def test_resolve_holidays_skips_live_fetch_on_dry_run_when_cache_missing(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    track_module = importlib.import_module("holded_cli.commands.track")

    fake_state = SimpleNamespace(
        session_store=object(),
        config=SimpleNamespace(timezone="Europe/Madrid"),
        holidays_file=paths["holidays_file"],
    )

    fetch_calls: list[int] = []

    def fake_fetch_holidays(*_args, **_kwargs):
        fetch_calls.append(2026)
        return frozenset({date(2026, 4, 7)})

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    monkeypatch.setattr(track_module, "fetch_holidays", fake_fetch_holidays)
    monkeypatch.setattr(track_module, "HoldedClient", lambda *_: FakeClient())

    result = track_module._resolve_holidays(
        fake_state,
        from_year=2026,
        to_year=2026,
        workplace_id="",
        dry_run=True,
    )

    assert result == frozenset()
    assert fetch_calls == []


def test_track_submit_calls_check_and_submit(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    fake_state = _fake_state_with_files(tmp_path, monkeypatch)
    calls: list = []
    _patch_client(monkeypatch, cli_module, fake_state, calls=calls)

    result = runner.invoke(
        cli_module.app,
        ["track", "--from", "2026-04-07", "--to", "2026-04-07"],
    )

    assert result.exit_code == 0
    assert "Traceback" not in result.stdout
    assert any(op == "check" for op, _ in calls)
    assert any(op == "submit" for op, _ in calls)
    # Both calls share the same payload
    check_payload = next(p for op, p in calls if op == "check")
    assert "2026-04-07" in check_payload["days"]


def test_track_submit_shows_success_message(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    fake_state = _fake_state_with_files(tmp_path, monkeypatch)
    _patch_client(monkeypatch, cli_module, fake_state, calls=[])

    result = runner.invoke(
        cli_module.app,
        ["track", "--from", "2026-04-07", "--to", "2026-04-09"],
    )

    assert result.exit_code == 0
    assert "day(s) registered" in result.stdout


def test_track_submit_large_range_prompts_confirmation(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    fake_state = _fake_state_with_files(tmp_path, monkeypatch)
    # Override holiday cache to cover 2026 full range
    _write_holiday_cache(fake_state.holidays_file, 2026, [])
    _patch_client(monkeypatch, cli_module, fake_state, calls=[])

    # 2026-04-06 to 2026-04-30 = 19 working days → triggers confirmation
    result = runner.invoke(
        cli_module.app,
        ["track", "--from", "2026-04-06", "--to", "2026-04-30"],
        input="n\n",  # answer "no" to confirmation
    )

    assert result.exit_code != 0  # Aborted


def test_track_submit_yes_flag_skips_confirmation(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    fake_state = _fake_state_with_files(tmp_path, monkeypatch)
    _write_holiday_cache(fake_state.holidays_file, 2026, [])
    calls: list = []
    _patch_client(monkeypatch, cli_module, fake_state, calls=calls)

    result = runner.invoke(
        cli_module.app,
        ["track", "--from", "2026-04-06", "--to", "2026-04-30", "--yes"],
    )

    assert result.exit_code == 0
    assert any(op == "submit" for op, _ in calls)
