"""Tests for holiday cache extraction and persistence."""

from __future__ import annotations

import json
from datetime import date
import importlib
import sys
from pathlib import Path


def test_extract_workplace_holidays_filters_by_type_and_status() -> None:
    from holded_tt.holidays import extract_workplace_holidays

    summary = {
        "workplaceTimeOffs": [
            {
                "assignationType": "workplace",
                "status": "accepted",
                "date": "2026-01-01",
            },
            {"assignationType": "workplace", "status": "pending", "date": "2026-01-06"},
            {"assignationType": "personal", "status": "accepted", "date": "2026-01-12"},
            {
                "assignationType": "workplace",
                "status": "accepted",
                "date": "2026-04-17",
            },
        ]
    }

    holidays = extract_workplace_holidays(summary, 2026)

    assert date(2026, 1, 1) in holidays
    assert date(2026, 4, 17) in holidays
    assert date(2026, 1, 6) not in holidays
    assert date(2026, 1, 12) not in holidays


def test_extract_workplace_holidays_ignores_other_years() -> None:
    from holded_tt.holidays import extract_workplace_holidays

    summary = {
        "workplaceTimeOffs": [
            {
                "assignationType": "workplace",
                "status": "accepted",
                "date": "2025-12-25",
            },
            {
                "assignationType": "workplace",
                "status": "accepted",
                "date": "2026-01-01",
            },
        ]
    }

    holidays = extract_workplace_holidays(summary, 2026)

    assert date(2025, 12, 25) not in holidays
    assert date(2026, 1, 1) in holidays


def test_get_cached_holidays_returns_none_for_wrong_year(tmp_path: Path) -> None:
    from holded_tt.holidays import get_cached_holidays

    cache_file = tmp_path / "holidays.json"
    cache_file.write_text(
        json.dumps({"year": 2025, "holidays": ["2025-01-01"]}),
        encoding="utf-8",
    )

    result = get_cached_holidays(cache_file, 2026)

    assert result is None


def test_get_cached_holidays_returns_dates_for_matching_year(tmp_path: Path) -> None:
    from holded_tt.holidays import get_cached_holidays

    cache_file = tmp_path / "holidays.json"
    cache_file.write_text(
        json.dumps({"year": 2026, "holidays": ["2026-01-01", "2026-04-17"]}),
        encoding="utf-8",
    )

    result = get_cached_holidays(cache_file, 2026)

    assert result is not None
    assert date(2026, 1, 1) in result
    assert date(2026, 4, 17) in result


def test_get_cached_holidays_returns_none_for_missing_file(tmp_path: Path) -> None:
    from holded_tt.holidays import get_cached_holidays

    result = get_cached_holidays(tmp_path / "holidays.json", 2026)

    assert result is None


def test_get_cached_holidays_skips_malformed_date_strings(tmp_path: Path) -> None:
    from holded_tt.holidays import get_cached_holidays

    cache_file = tmp_path / "holidays.json"
    cache_file.write_text(
        json.dumps(
            {"year": 2026, "holidays": ["not-a-date", "2026-01-01", "also-bad"]}
        ),
        encoding="utf-8",
    )

    result = get_cached_holidays(cache_file, 2026)

    # Malformed entries are silently skipped; the valid one is kept
    assert result is not None
    assert date(2026, 1, 1) in result
    assert len(result) == 1


def test_load_cache_returns_empty_dict_on_corrupt_file(tmp_path: Path) -> None:
    from holded_tt.holidays import _load_cache

    corrupt = tmp_path / "bad.json"
    corrupt.write_text("{ not valid json", encoding="utf-8")

    result = _load_cache(corrupt)

    assert result == {}


def test_save_cache_writes_valid_json_with_year_and_holidays(tmp_path: Path) -> None:
    from holded_tt.holidays import _save_cache

    cache_file = tmp_path / "holidays.json"
    _save_cache(
        cache_file,
        2026,
        [{"date": "2026-01-01", "name": "Año Nuevo"}, {"date": "2026-04-17", "name": "Viernes Santo"}],
    )

    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert payload["year"] == 2026
    assert any(e["date"] == "2026-01-01" for e in payload["holidays"])
    assert any(e["date"] == "2026-04-17" for e in payload["holidays"])
    assert "fetched_at" in payload


def test_save_cache_creates_parent_directories(tmp_path: Path) -> None:
    from holded_tt.holidays import _save_cache

    nested = tmp_path / "a" / "b" / "holidays.json"
    _save_cache(nested, 2026, [])

    assert nested.exists()


def test_extract_workplace_holidays_uses_first_date_key_found() -> None:
    """Entry with multiple date keys: only the first valid key is used (break)."""
    from holded_tt.holidays import extract_workplace_holidays

    # Entry has both "date" and "startDate" — "date" is checked first
    summary = {
        "workplaceTimeOffs": [
            {
                "assignationType": "workplace",
                "status": "accepted",
                "date": "2026-05-01",
                "startDate": "2026-05-02",  # should be ignored
            }
        ]
    }

    holidays = extract_workplace_holidays(summary, 2026)

    assert date(2026, 5, 1) in holidays
    assert date(2026, 5, 2) not in holidays


def test_extract_workplace_holidays_skips_invalid_date_values() -> None:
    from holded_tt.holidays import extract_workplace_holidays

    summary = {
        "workplaceTimeOffs": [
            {
                "assignationType": "workplace",
                "status": "accepted",
                "date": "not-a-date",
            }
        ]
    }

    assert extract_workplace_holidays(summary, 2026) == {}


def test_current_year_paris_returns_plausible_year() -> None:
    from holded_tt.holidays import _current_year_paris

    year = _current_year_paris()

    assert isinstance(year, int)
    assert 2020 <= year <= 2100


def test_holidays_falls_back_to_utc_when_paris_timezone_is_unavailable(
    monkeypatch,
) -> None:
    import zoneinfo

    sys.modules.pop("holded_tt.holidays", None)
    monkeypatch.setattr(
        zoneinfo,
        "ZoneInfo",
        lambda key: (_ for _ in ()).throw(zoneinfo.ZoneInfoNotFoundError(key)),
    )

    holidays = importlib.import_module("holded_tt.holidays")

    assert holidays._PARIS_TZ == holidays.timezone.utc


def test_fetch_holidays_fetches_from_api_when_cache_absent(tmp_path: Path) -> None:
    from holded_tt.holidays import fetch_holidays

    cache_file = tmp_path / "holidays.json"

    class FakeClient:
        def get_year_summary(self, year, workplace_id):
            return {
                "workplaceTimeOffs": [
                    {
                        "assignationType": "workplace",
                        "status": "accepted",
                        "date": "2026-04-17",
                    }
                ]
            }

    result = fetch_holidays(FakeClient(), cache_file, 2026, "wp-1")

    assert date(2026, 4, 17) in result
    # Cache should have been written
    assert cache_file.exists()
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert payload["year"] == 2026


def test_fetch_holidays_returns_cache_without_api_call(tmp_path: Path) -> None:
    from holded_tt.holidays import fetch_holidays

    cache_file = tmp_path / "holidays.json"
    cache_file.write_text(
        json.dumps({"year": 2026, "holidays": ["2026-01-01"]}),
        encoding="utf-8",
    )

    api_called: list[bool] = []

    class FakeClient:
        def get_year_summary(self, year, workplace_id):
            api_called.append(True)
            return {}

    result = fetch_holidays(FakeClient(), cache_file, 2026, "")

    assert date(2026, 1, 1) in result
    assert api_called == []  # API was NOT called
