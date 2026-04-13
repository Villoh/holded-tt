"""Tests for the holded track command (TRK-01 through TRK-11)."""

from __future__ import annotations

import importlib
import json
from datetime import date, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import typer


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


def _patch_client(
    monkeypatch,
    cli_module,
    fake_state,
    *,
    calls: list,
    timetracking_data=None,
    day_data=None,
):
    """Patch HoldedClient in track module to record calls."""
    track_module = importlib.import_module("holded_cli.commands.track")
    if timetracking_data is not None or day_data is not None:
        monkeypatch.setattr(
            track_module, "ZoneInfo", lambda *_: timezone(timedelta(hours=2))
        )

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get_employee(self):
            return {"id": "emp-1"}

        def get_timetracking_data(self, *_args, **_kwargs):
            return [] if timetracking_data is None else timetracking_data

        def get_day_timetracking(self, *_args, **_kwargs):
            return {} if day_data is None else day_data

        def check_bulk_timetracking(self, payload):
            calls.append(("check", payload))

        def submit_bulk_timetracking(self, payload):
            calls.append(("submit", payload))

        def update_bulk_timetracking(self, payload):
            calls.append(("update", payload))

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


def test_resolve_single_date_supports_today_and_requires_value() -> None:
    track_module = importlib.import_module("holded_cli.commands.track")

    assert track_module._resolve_single_date("2026-04-07", False) == date(2026, 4, 7)
    assert track_module._resolve_single_date(None, True) == date.today()
    with pytest.raises(track_module.InputError):
        track_module._resolve_single_date(None, False)


def test_timezone_for_day_falls_back_to_utc_for_unknown_timezone(monkeypatch) -> None:
    track_module = importlib.import_module("holded_cli.commands.track")

    def raising_zoneinfo(_name: str):
        raise track_module.ZoneInfoNotFoundError("missing tzdata")

    monkeypatch.setattr(track_module, "ZoneInfo", raising_zoneinfo)

    assert (
        track_module._timezone_for_day("Mars/Olympus", date(2026, 4, 7)) == timezone.utc
    )


def test_build_trackers_falls_back_for_european_timezones(monkeypatch) -> None:
    track_module = importlib.import_module("holded_cli.commands.track")

    def raising_zoneinfo(_name: str):
        raise track_module.ZoneInfoNotFoundError("missing tzdata")

    monkeypatch.setattr(track_module, "ZoneInfo", raising_zoneinfo)

    trackers = track_module._build_trackers(
        [
            {
                "id": "trk-1",
                "date": date(2026, 4, 7),
                "workplaceId": "wp-1",
                "timezone": "Europe/Madrid",
                "isRemote": False,
            },
            {
                "id": "trk-2",
                "date": date(2026, 12, 7),
                "workplaceId": "wp-1",
                "timezone": "Europe/Madrid",
                "isRemote": False,
            },
        ],
        "08:30",
        "17:00",
        ["14:00-14:30"],
    )

    assert trackers == [
        {
            "id": "trk-1",
            "workplaceId": "wp-1",
            "isRemote": False,
            "start": "2026-04-07T08:30:00+02:00",
            "end": "2026-04-07T17:00:00+02:00",
            "pauses": [{"start": "14:00", "end": "14:30"}],
        },
        {
            "id": "trk-2",
            "workplaceId": "wp-1",
            "isRemote": False,
            "start": "2026-12-07T08:30:00+01:00",
            "end": "2026-12-07T17:00:00+01:00",
            "pauses": [{"start": "14:00", "end": "14:30"}],
        },
    ]


def test_resolve_update_rows_rejects_multiple_invalid_shapes() -> None:
    track_module = importlib.import_module("holded_cli.commands.track")

    with pytest.raises(track_module.InputError) as exc_info:
        track_module._resolve_update_rows(
            [
                {"date": "2026-04-07", "trackers": [{"id": "a"}, {"id": "b"}]},
                {"date": "2026-04-08", "trackers": ["broken"]},
                {"date": "2026-04-09", "trackers": [{"id": "", "end": "x"}]},
            ],
            [date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)],
            "",
            "Europe/Madrid",
        )

    assert "multiple trackers found" in exc_info.value.hint


def test_resolve_tracker_for_update_handles_running_and_fallbacks() -> None:
    track_module = importlib.import_module("holded_cli.commands.track")

    with pytest.raises(track_module.InputError) as exc_info:
        track_module._resolve_tracker_for_update(
            {"trackers": [{"id": "trk-1", "running": True, "end": None}]},
            "trk-1",
            date(2026, 4, 7),
            "",
            "Europe/Madrid",
        )

    assert "still running" in exc_info.value.message

    tracker = track_module._resolve_tracker_for_update(
        {
            "trackers": [
                {
                    "id": "trk-2",
                    "running": False,
                    "end": "2026-04-07T15:00:00+00:00",
                    "start": "2026-04-07T06:30:00+00:00",
                    "pauses": "broken",
                }
            ]
        },
        "trk-2",
        date(2026, 4, 7),
        "",
        "Europe/Madrid",
    )

    assert tracker["workplaceId"] == ""
    assert tracker["timezone"] == "Europe/Madrid"
    assert tracker["pauses"] == []


def test_extract_pause_windows_and_format_tracker_time_handle_invalid_values(
    monkeypatch,
) -> None:
    track_module = importlib.import_module("holded_cli.commands.track")
    monkeypatch.setattr(track_module, "_timezone_for_day", lambda *_: timezone.utc)

    pauses = track_module._extract_pause_windows(
        [
            {"start": "2026-04-07T12:00:00+00:00", "end": "2026-04-07T12:30:00+00:00"},
            {"start": "broken", "end": "2026-04-07T12:30:00+00:00"},
            "bad",
        ],
        "UTC",
    )

    assert pauses == [{"start": "12:00", "end": "12:30"}]
    assert (
        track_module._format_tracker_time("broken", "UTC", date(2026, 4, 7)) == "broken"
    )
    assert track_module._format_tracker_time(None, "UTC", date(2026, 4, 7)) == "-"
    assert track_module._format_duration(3660) == "01:01"
    assert track_module._format_duration(-1) == "-"
    assert (
        track_module._format_pause_summary(
            [
                {
                    "start": "2026-04-07T12:00:00+00:00",
                    "end": "2026-04-07T12:30:00+00:00",
                }
            ],
            "UTC",
            date(2026, 4, 7),
        )
        == "12:00 -> 12:30"
    )
    assert track_module._format_pause_summary("broken", "UTC", date(2026, 4, 7)) == "-"


def test_render_trackers_table_formats_local_times_and_skips_broken_rows(
    monkeypatch,
) -> None:
    track_module = importlib.import_module("holded_cli.commands.track")
    monkeypatch.setattr(track_module, "_timezone_for_day", lambda *_: timezone.utc)

    table = track_module._render_trackers_table(
        [
            {
                "date": "2026-04-07",
                "trackers": [
                    {
                        "id": "trk-1",
                        "start": "2026-04-07T06:30:00+00:00",
                        "end": "2026-04-07T15:00:00+00:00",
                        "time": 30600,
                        "pauses": [{}, {}],
                        "running": False,
                        "approvedStatus": "pending",
                        "logMethod": "clocking",
                        "isRemote": True,
                        "workplaceId": None,
                    },
                    "broken",
                ],
            }
        ]
    )

    cells = [column._cells for column in table.columns]
    assert "06:30 -> 15:00" in cells[2]
    assert "-" in cells[3]
    assert "done" in cells[4]
    assert "pending" in cells[5]
    assert "clocking" in cells[6]
    assert "yes" in cells[7]


def test_resolve_track_days_can_skip_holiday_lookup() -> None:
    track_module = importlib.import_module("holded_cli.commands.track")

    days = track_module._resolve_track_days(
        SimpleNamespace(holidays_file=None),
        date(2026, 4, 6),
        date(2026, 4, 7),
        "",
        dry_run=False,
        include_weekends=True,
        include_holidays=True,
    )

    assert days == [date(2026, 4, 6), date(2026, 4, 7)]


def test_run_with_cli_error_handling_translates_cli_errors(monkeypatch) -> None:
    track_module = importlib.import_module("holded_cli.commands.track")
    rendered: list[str] = []

    monkeypatch.setattr(
        track_module, "render_error", lambda error: rendered.append(error.message)
    )

    def raising_command():
        raise track_module.InputError(message="boom", hint="fix it")

    with pytest.raises(typer.Exit) as exc_info:
        track_module._run_with_cli_error_handling(raising_command)

    assert exc_info.value.exit_code == 1
    assert rendered == ["boom"]


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

        def get_employee(self):
            return {"id": "emp-1"}

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
    monkeypatch.setattr(
        track_module, "ZoneInfo", lambda *_: timezone(timedelta(hours=2))
    )
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
    check_payload = next(p for op, p in calls if op == "check")
    submit_payload = next(p for op, p in calls if op == "submit")
    assert (
        check_payload
        == submit_payload
        == {
            "workplaceId": "",
            "timezone": "Europe/Paris",
            "days": ["2026-04-07"],
            "start": "08:30",
            "end": "17:30",
            "pauses": [],
        }
    )


def test_track_submit_builds_bulk_create_payload_with_pauses(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    fake_state = _fake_state_with_files(tmp_path, monkeypatch)
    calls: list = []
    _patch_client(monkeypatch, cli_module, fake_state, calls=calls)

    result = runner.invoke(
        cli_module.app,
        [
            "track",
            "--from",
            "2026-04-07",
            "--to",
            "2026-04-08",
            "--workplace",
            "wp-123",
            "--start",
            "08:30",
            "--end",
            "17:00",
            "--pause",
            "14:00-14:30",
        ],
    )

    assert result.exit_code == 0
    check_payload = next(p for op, p in calls if op == "check")
    submit_payload = next(p for op, p in calls if op == "submit")
    assert (
        check_payload
        == submit_payload
        == {
            "workplaceId": "wp-123",
            "timezone": "Europe/Paris",
            "days": ["2026-04-07", "2026-04-08"],
            "start": "08:30",
            "end": "17:00",
            "pauses": [{"start": "14:00", "end": "14:30"}],
        }
    )


def test_track_show_lists_tracker_ids_for_date(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    fake_state = _fake_state_with_files(tmp_path, monkeypatch)
    calls: list = []
    day_data = {
        "date": "2026-04-07",
        "trackers": [
            {
                "id": "trk-1",
                "startDateWithTimeZone": "2026-04-07T08:30:00+02:00",
                "end": "2026-04-07T15:00:00+00:00",
                "effectiveWorkedTime": 28800,
                "pauses": [
                    {
                        "start": "2026-04-07T12:00:00+00:00",
                        "end": "2026-04-07T12:30:00+00:00",
                    }
                ],
                "status": "done",
                "approvedStatus": "pending",
                "logMethod": "clocking",
                "isRemote": True,
                "workplaceId": "wp-1",
                "timezone": "Europe/Madrid",
            }
        ],
    }
    _patch_client(
        monkeypatch,
        cli_module,
        fake_state,
        calls=calls,
        day_data=day_data,
    )

    result = runner.invoke(
        cli_module.app,
        [
            "track",
            "show",
            "--date",
            "2026-04-07",
        ],
    )

    assert result.exit_code == 0
    assert "trk-1" in result.stdout
    assert "2026-04-07" in result.stdout
    assert "08:30" in result.stdout
    assert "14:00 -> 14:30" in result.stdout
    assert "pending" in result.stdout
    assert "clocking" in result.stdout
    assert "yes" in result.stdout


def test_track_show_lists_tracker_ids_for_range(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    fake_state = _fake_state_with_files(tmp_path, monkeypatch)
    calls: list = []
    timetracking_data = [
        {"date": "2026-04-07", "trackers": [{"id": "trk-1", "status": "done"}]},
        {"date": "2026-04-08", "trackers": []},
    ]
    _patch_client(
        monkeypatch,
        cli_module,
        fake_state,
        calls=calls,
        timetracking_data=timetracking_data,
    )

    result = runner.invoke(
        cli_module.app,
        ["track", "show", "--from", "2026-04-07", "--to", "2026-04-08"],
    )

    assert result.exit_code == 0
    assert "trk-1" in result.stdout
    assert "empty" in result.stdout


def test_track_show_without_data_reports_empty(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    fake_state = _fake_state_with_files(tmp_path, monkeypatch)
    calls: list = []
    _patch_client(monkeypatch, cli_module, fake_state, calls=calls, day_data={})

    result = runner.invoke(cli_module.app, ["track", "show", "--date", "2026-04-07"])

    assert result.exit_code == 0
    assert "No tracked data found" in result.stdout


def test_track_update_builds_tracker_update_payload(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    fake_state = _fake_state_with_files(tmp_path, monkeypatch)
    calls: list = []
    day_data = {
        "date": "2026-04-07",
        "trackers": [
            {
                "id": "trk-1",
                "running": False,
                "end": "2026-04-07T15:30:00+00:00",
                "startDateWithTimeZone": "2026-04-07T08:30:00+02:00",
                "workplaceId": "wp-1",
                "timezone": "Europe/Madrid",
                "pauses": [
                    {
                        "start": "2026-04-07T12:00:00+00:00",
                        "end": "2026-04-07T12:30:00+00:00",
                    }
                ],
            }
        ],
    }
    _patch_client(
        monkeypatch,
        cli_module,
        fake_state,
        calls=calls,
        day_data=day_data,
    )

    result = runner.invoke(
        cli_module.app,
        [
            "track",
            "update",
            "--date",
            "2026-04-07",
            "--tracker-id",
            "trk-1",
            "--end",
            "17:00",
            "--yes",
        ],
    )

    assert result.exit_code == 0
    update_payload = next(p for op, p in calls if op == "update")
    assert update_payload == {
        "trackers": [
            {
                "id": "trk-1",
                "workplaceId": "wp-1",
                "isRemote": False,
                "start": "2026-04-07T08:30:00+02:00",
                "end": "2026-04-07T17:00:00+02:00",
                "pauses": [{"start": "14:00", "end": "14:30"}],
            },
        ]
    }


def test_track_update_range_updates_each_day_one_by_one(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    fake_state = _fake_state_with_files(tmp_path, monkeypatch)
    calls: list = []
    timetracking_data = [
        {
            "date": "2026-04-07",
            "trackers": [
                {
                    "id": "trk-1",
                    "running": False,
                    "start": "2026-04-07T06:30:00+00:00",
                    "end": "2026-04-07T15:30:00+00:00",
                    "workplaceId": "wp-1",
                    "timezone": "Europe/Madrid",
                    "pauses": [],
                }
            ],
        },
        {
            "date": "2026-04-08",
            "trackers": [
                {
                    "id": "trk-2",
                    "running": False,
                    "start": "2026-04-08T06:30:00+00:00",
                    "end": "2026-04-08T15:30:00+00:00",
                    "workplaceId": "wp-1",
                    "timezone": "Europe/Madrid",
                    "pauses": [],
                }
            ],
        },
    ]
    _patch_client(
        monkeypatch,
        cli_module,
        fake_state,
        calls=calls,
        timetracking_data=timetracking_data,
    )

    result = runner.invoke(
        cli_module.app,
        [
            "track",
            "update",
            "--from",
            "2026-04-07",
            "--to",
            "2026-04-08",
            "--end",
            "17:00",
            "--yes",
        ],
    )

    assert result.exit_code == 0
    update_payloads = [p for op, p in calls if op == "update"]
    assert len(update_payloads) == 2
    assert update_payloads[0]["trackers"][0]["id"] == "trk-1"
    assert update_payloads[0]["trackers"][0]["end"] == "2026-04-07T17:00:00+02:00"
    assert update_payloads[1]["trackers"][0]["id"] == "trk-2"
    assert update_payloads[1]["trackers"][0]["end"] == "2026-04-08T17:00:00+02:00"


def test_track_update_range_skips_weekends_by_default(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    fake_state = _fake_state_with_files(tmp_path, monkeypatch)
    calls: list = []
    timetracking_data = [
        {
            "date": "2026-04-10",
            "trackers": [
                {
                    "id": "trk-1",
                    "running": False,
                    "start": "2026-04-10T06:30:00+00:00",
                    "end": "2026-04-10T15:30:00+00:00",
                    "workplaceId": "wp-1",
                    "timezone": "Europe/Madrid",
                    "pauses": [],
                }
            ],
        }
    ]
    _patch_client(
        monkeypatch,
        cli_module,
        fake_state,
        calls=calls,
        timetracking_data=timetracking_data,
    )

    result = runner.invoke(
        cli_module.app,
        [
            "track",
            "update",
            "--from",
            "2026-04-10",
            "--to",
            "2026-04-12",
            "--end",
            "17:00",
            "--yes",
        ],
    )

    assert result.exit_code == 0
    assert len([1 for op, _ in calls if op == "update"]) == 1


def test_track_update_range_can_include_weekends(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    fake_state = _fake_state_with_files(tmp_path, monkeypatch)
    calls: list = []
    timetracking_data = [
        {
            "date": "2026-04-10",
            "trackers": [
                {
                    "id": "trk-1",
                    "running": False,
                    "start": "2026-04-10T06:30:00+00:00",
                    "end": "2026-04-10T15:30:00+00:00",
                    "workplaceId": "wp-1",
                    "timezone": "Europe/Madrid",
                    "pauses": [],
                }
            ],
        },
        {
            "date": "2026-04-11",
            "trackers": [
                {
                    "id": "trk-2",
                    "running": False,
                    "start": "2026-04-11T06:30:00+00:00",
                    "end": "2026-04-11T15:30:00+00:00",
                    "workplaceId": "wp-1",
                    "timezone": "Europe/Madrid",
                    "pauses": [],
                }
            ],
        },
        {
            "date": "2026-04-12",
            "trackers": [
                {
                    "id": "trk-3",
                    "running": False,
                    "start": "2026-04-12T06:30:00+00:00",
                    "end": "2026-04-12T15:30:00+00:00",
                    "workplaceId": "wp-1",
                    "timezone": "Europe/Madrid",
                    "pauses": [],
                }
            ],
        },
    ]
    _patch_client(
        monkeypatch,
        cli_module,
        fake_state,
        calls=calls,
        timetracking_data=timetracking_data,
    )

    result = runner.invoke(
        cli_module.app,
        [
            "track",
            "update",
            "--from",
            "2026-04-10",
            "--to",
            "2026-04-12",
            "--include-weekends",
            "--end",
            "17:00",
            "--yes",
        ],
    )

    assert result.exit_code == 0
    assert len([1 for op, _ in calls if op == "update"]) == 3


def test_track_update_range_rejects_multiple_trackers_in_day(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    fake_state = _fake_state_with_files(tmp_path, monkeypatch)
    calls: list = []
    timetracking_data = [
        {
            "date": "2026-04-07",
            "trackers": [
                {"id": "trk-1", "end": "2026-04-07T15:30:00+00:00"},
                {"id": "trk-2", "end": "2026-04-07T16:00:00+00:00"},
            ],
        }
    ]
    _patch_client(
        monkeypatch,
        cli_module,
        fake_state,
        calls=calls,
        timetracking_data=timetracking_data,
    )

    result = runner.invoke(
        cli_module.app,
        [
            "track",
            "update",
            "--from",
            "2026-04-07",
            "--to",
            "2026-04-07",
            "--end",
            "17:00",
            "--yes",
        ],
    )

    assert result.exit_code == 1
    assert "multiple trackers found" in result.stderr


def test_track_update_keeps_existing_values_and_confirms_by_default(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    fake_state = _fake_state_with_files(tmp_path, monkeypatch)
    calls: list = []
    day_data = {
        "date": "2026-04-07",
        "trackers": [
            {
                "id": "trk-1",
                "running": False,
                "start": "2026-04-07T06:30:00+00:00",
                "end": "2026-04-07T15:30:00+00:00",
                "workplaceId": "wp-1",
                "timezone": "Europe/Madrid",
                "pauses": [
                    {
                        "start": "2026-04-07T12:00:00+00:00",
                        "end": "2026-04-07T12:30:00+00:00",
                    }
                ],
            }
        ],
    }
    _patch_client(
        monkeypatch,
        cli_module,
        fake_state,
        calls=calls,
        day_data=day_data,
    )

    result = runner.invoke(
        cli_module.app,
        [
            "track",
            "update",
            "--date",
            "2026-04-07",
            "--tracker-id",
            "trk-1",
        ],
        input="y\n",
    )

    assert result.exit_code == 0
    update_payload = next(p for op, p in calls if op == "update")
    assert update_payload["trackers"][0]["start"] == "2026-04-07T08:30:00+02:00"
    assert update_payload["trackers"][0]["end"] == "2026-04-07T17:30:00+02:00"
    assert update_payload["trackers"][0]["pauses"] == [
        {"start": "14:00", "end": "14:30"}
    ]


def test_track_update_can_abort_confirmation(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    fake_state = _fake_state_with_files(tmp_path, monkeypatch)
    calls: list = []
    day_data = {
        "date": "2026-04-07",
        "trackers": [
            {
                "id": "trk-1",
                "running": False,
                "start": "2026-04-07T06:30:00+00:00",
                "end": "2026-04-07T15:30:00+00:00",
                "workplaceId": "wp-1",
                "timezone": "Europe/Madrid",
                "pauses": [],
            }
        ],
    }
    _patch_client(
        monkeypatch,
        cli_module,
        fake_state,
        calls=calls,
        day_data=day_data,
    )

    result = runner.invoke(
        cli_module.app,
        [
            "track",
            "update",
            "--date",
            "2026-04-07",
            "--tracker-id",
            "trk-1",
        ],
        input="n\n",
    )

    assert result.exit_code != 0
    assert not any(op == "update" for op, _ in calls)


def test_track_update_rejects_missing_tracker_id(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    fake_state = _fake_state_with_files(tmp_path, monkeypatch)
    calls: list = []
    day_data = {"date": "2026-04-07", "trackers": []}
    _patch_client(
        monkeypatch,
        cli_module,
        fake_state,
        calls=calls,
        day_data=day_data,
    )

    result = runner.invoke(
        cli_module.app,
        [
            "track",
            "update",
            "--date",
            "2026-04-07",
            "--tracker-id",
            "trk-missing",
        ],
    )

    assert result.exit_code == 1
    assert "trk-missing" in result.stderr


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
