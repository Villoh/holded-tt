"""Tests for holiday cache extraction and persistence."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


def test_extract_workplace_holidays_filters_by_type_and_status() -> None:
    from holded_cli.holidays import extract_workplace_holidays

    summary = {
        "workplaceTimeOffs": [
            {"assignationType": "workplace", "status": "accepted", "date": "2026-01-01"},
            {"assignationType": "workplace", "status": "pending", "date": "2026-01-06"},
            {"assignationType": "personal", "status": "accepted", "date": "2026-01-12"},
            {"assignationType": "workplace", "status": "accepted", "date": "2026-04-17"},
        ]
    }

    holidays = extract_workplace_holidays(summary, 2026)

    assert date(2026, 1, 1) in holidays
    assert date(2026, 4, 17) in holidays
    assert date(2026, 1, 6) not in holidays
    assert date(2026, 1, 12) not in holidays


def test_extract_workplace_holidays_ignores_other_years() -> None:
    from holded_cli.holidays import extract_workplace_holidays

    summary = {
        "workplaceTimeOffs": [
            {"assignationType": "workplace", "status": "accepted", "date": "2025-12-25"},
            {"assignationType": "workplace", "status": "accepted", "date": "2026-01-01"},
        ]
    }

    holidays = extract_workplace_holidays(summary, 2026)

    assert date(2025, 12, 25) not in holidays
    assert date(2026, 1, 1) in holidays


def test_get_cached_holidays_returns_none_for_wrong_year(tmp_path: Path) -> None:
    from holded_cli.holidays import get_cached_holidays

    cache_file = tmp_path / "holidays.json"
    cache_file.write_text(
        json.dumps({"year": 2025, "holidays": ["2025-01-01"]}),
        encoding="utf-8",
    )

    result = get_cached_holidays(cache_file, 2026)

    assert result is None


def test_get_cached_holidays_returns_dates_for_matching_year(tmp_path: Path) -> None:
    from holded_cli.holidays import get_cached_holidays

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
    from holded_cli.holidays import get_cached_holidays

    result = get_cached_holidays(tmp_path / "holidays.json", 2026)

    assert result is None
