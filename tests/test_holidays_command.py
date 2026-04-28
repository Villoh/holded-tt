"""Tests for holidays command (HOL-01 through HOL-05)."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace


def _fake_state(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        session_store=object(),
        holidays_file=tmp_path / "holidays.json",
    )


def _patch_cli(monkeypatch, fake_state):
    cli_module = importlib.import_module("holded_tt.cli")
    monkeypatch.setattr(cli_module, "create_app_state", lambda: fake_state)
    return cli_module


def _patch_client(monkeypatch, fake_client_instance):
    holidays_module = importlib.import_module("holded_tt.commands.holidays")
    monkeypatch.setattr(
        holidays_module, "HoldedClient", lambda *_: fake_client_instance
    )


class _FakeClient:
    def __init__(self, summary: dict):
        self._summary = summary

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def get_year_summary(self, year):
        return self._summary


def test_holidays_cache_hit_shows_table_and_cached_status(
    runner, monkeypatch, tmp_path
) -> None:
    """HOL-01: Cache hit — shows holidays from cache, status line says 'cached'."""
    state = _fake_state(tmp_path)
    state.holidays_file.write_text(
        json.dumps({"year": 2026, "holidays": ["2026-01-01", "2026-04-17"]}),
        encoding="utf-8",
    )
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["holidays", "--year", "2026"])

    assert result.exit_code == 0
    assert "2026-01-01" in result.stdout
    assert "2026-04-17" in result.stdout
    assert "cached" in result.stdout


def test_holidays_cache_miss_fetches_from_api_and_shows_fetched(
    runner, monkeypatch, tmp_path
) -> None:
    """HOL-02: Cache miss — calls API, saves cache, status says 'fetched'."""
    state = _fake_state(tmp_path)
    summary = {
        "workplaceTimeOffs": [
            {
                "assignationType": "workplace",
                "status": "accepted",
                "date": "2026-04-17",
            }
        ]
    }
    _patch_client(monkeypatch, _FakeClient(summary))
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["holidays", "--year", "2026"])

    assert result.exit_code == 0
    assert "2026-04-17" in result.stdout
    assert "fetched" in result.stdout
    assert state.holidays_file.exists()


def test_holidays_refresh_bypasses_cache_and_shows_refreshed(
    runner, monkeypatch, tmp_path
) -> None:
    """HOL-03: --refresh — calls API even when valid cache exists, status says 'refreshed'."""
    state = _fake_state(tmp_path)
    state.holidays_file.write_text(
        json.dumps({"year": 2026, "holidays": ["2026-01-01"]}),
        encoding="utf-8",
    )
    api_calls: list[int] = []

    class TrackingClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get_year_summary(self, year):
            api_calls.append(1)
            return {
                "workplaceTimeOffs": [
                    {
                        "assignationType": "workplace",
                        "status": "accepted",
                        "date": "2026-04-17",
                    }
                ]
            }

    holidays_module = importlib.import_module("holded_tt.commands.holidays")
    monkeypatch.setattr(
        holidays_module, "HoldedClient", lambda *_: TrackingClient()
    )
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["holidays", "--year", "2026", "--refresh"])

    assert result.exit_code == 0
    assert api_calls == [1]
    assert "refreshed" in result.stdout


def test_holidays_year_flag_passes_correct_year_to_api(
    runner, monkeypatch, tmp_path
) -> None:
    """HOL-04: --year — the specified year is passed to the API call."""
    state = _fake_state(tmp_path)
    received_years: list[int] = []

    class TrackingClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get_year_summary(self, year):
            received_years.append(year)
            return {}

    holidays_module = importlib.import_module("holded_tt.commands.holidays")
    monkeypatch.setattr(
        holidays_module, "HoldedClient", lambda *_: TrackingClient()
    )
    cli = _patch_cli(monkeypatch, state)

    runner.invoke(cli.app, ["holidays", "--year", "2025"])

    assert received_years == [2025]


def test_holidays_empty_result_prints_no_holidays_message(
    runner, monkeypatch, tmp_path
) -> None:
    """HOL-05: No holidays — prints 'No holidays found', exits 0."""
    state = _fake_state(tmp_path)
    _patch_client(monkeypatch, _FakeClient({}))
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["holidays", "--year", "2026"])

    assert result.exit_code == 0
    assert "No holidays found" in result.stdout
