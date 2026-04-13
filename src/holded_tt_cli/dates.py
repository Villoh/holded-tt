"""Pure date utilities: range generation and filtering."""

from __future__ import annotations

from datetime import date, timedelta

from holded_tt_cli.errors import InputError


def date_range(from_date: date, to_date: date) -> list[date]:
    """Return all dates from from_date to to_date inclusive."""
    if from_date > to_date:
        return []
    days: list[date] = []
    current = from_date
    while current <= to_date:
        days.append(current)
        current += timedelta(days=1)
    return days


def filter_weekends(days: list[date]) -> list[date]:
    """Remove Saturday (weekday 5) and Sunday (weekday 6)."""
    return [d for d in days if d.weekday() < 5]


def filter_holidays(days: list[date], holidays: frozenset[date]) -> list[date]:
    """Remove any day present in the holidays set."""
    return [d for d in days if d not in holidays]


def parse_date(value: str) -> date:
    """Parse a YYYY-MM-DD string, raising InputError on failure."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise InputError(
            message=f"Invalid date: {value!r}",
            hint="Use YYYY-MM-DD format (e.g., 2026-04-01).",
        )
