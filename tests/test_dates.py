"""Tests for date range generation and filtering."""

from __future__ import annotations

from datetime import date

import pytest


def test_date_range_returns_all_days() -> None:
    from holded_tt_cli.dates import date_range

    days = date_range(date(2026, 4, 1), date(2026, 4, 5))

    assert days == [
        date(2026, 4, 1),
        date(2026, 4, 2),
        date(2026, 4, 3),
        date(2026, 4, 4),
        date(2026, 4, 5),
    ]


def test_date_range_returns_single_day() -> None:
    from holded_tt_cli.dates import date_range

    assert date_range(date(2026, 4, 1), date(2026, 4, 1)) == [date(2026, 4, 1)]


def test_date_range_returns_empty_for_inverted_range() -> None:
    from holded_tt_cli.dates import date_range

    assert date_range(date(2026, 4, 5), date(2026, 4, 1)) == []


def test_filter_weekends_removes_saturday_and_sunday() -> None:
    from holded_tt_cli.dates import date_range, filter_weekends

    # 2026-04-06 is Monday, ..., 2026-04-12 is Sunday
    days = date_range(date(2026, 4, 6), date(2026, 4, 12))
    working = filter_weekends(days)

    assert len(working) == 5
    assert all(d.weekday() < 5 for d in working)


def test_filter_holidays_removes_matching_dates() -> None:
    from holded_tt_cli.dates import filter_holidays

    days = [date(2026, 4, 1), date(2026, 4, 2), date(2026, 4, 3)]
    holidays = frozenset([date(2026, 4, 2)])

    filtered = filter_holidays(days, holidays)

    assert filtered == [date(2026, 4, 1), date(2026, 4, 3)]


def test_parse_date_returns_correct_date() -> None:
    from holded_tt_cli.dates import parse_date

    assert parse_date("2026-04-01") == date(2026, 4, 1)


def test_parse_date_raises_input_error_on_bad_format() -> None:
    from holded_tt_cli.dates import parse_date
    from holded_tt_cli.errors import InputError

    with pytest.raises(InputError) as exc_info:
        parse_date("01/04/2026")

    assert "YYYY-MM-DD" in exc_info.value.hint
