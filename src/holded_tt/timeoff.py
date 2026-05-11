"""Timeoff business logic: payload parsing, holiday and absence extraction."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import timezone

from holded_tt.holded_client import HoldedApiError


try:
    _PARIS_TZ = ZoneInfo("Europe/Paris")
except ZoneInfoNotFoundError:
    _PARIS_TZ = timezone.utc  # type: ignore[assignment]


def _current_year_paris() -> int:
    return datetime.now(_PARIS_TZ).year


def extract_workplace_holidays(summary: dict, year: int) -> dict[date, str]:
    """Extract accepted workplace holidays from a timeoff-year-summary payload."""
    time_offs = summary.get("workplaceTimeOffs", [])
    holidays: dict[date, str] = {}
    for entry in time_offs:
        if (
            entry.get("assignationType") == "workplace"
            and entry.get("status") == "accepted"
        ):
            holiday_date: date | None = None
            for key in ("start", "date", "startDate"):
                raw = entry.get(key)
                if raw:
                    try:
                        d = date.fromisoformat(str(raw)[:10])
                        if d.year == year:
                            holiday_date = d
                    except ValueError:
                        pass
                    break
            if holiday_date is not None:
                name = ""
                for name_key in ("name", "description", "typeName"):
                    val = entry.get(name_key)
                    if val:
                        name = str(val)
                        break
                holidays[holiday_date] = name
    return holidays


def extract_employee_absences(summary: dict) -> list[dict]:
    """Return all personal timeoffs from a timeoff-year-summary payload."""
    result: list[dict] = []
    for key in ("employeeTimeOffs", "cancelledTimeOffs", "declinedTimeOffs"):
        entries = summary.get(key)
        if isinstance(entries, list):
            result.extend(entry for entry in entries if isinstance(entry, dict))
    return result


def resolve_vacation_type_id(summary: dict) -> str:
    """Return the ID of the first timeoff type that discounts days and needs approval."""
    details = summary.get("timeOffDetails", [])
    for entry in details:
        if entry.get("discountsDays") and entry.get("needsApproval"):
            type_id = entry.get("id")
            if isinstance(type_id, str) and type_id:
                return type_id
    raise HoldedApiError(
        message="No vacation type found in Holded configuration.",
        hint="Check that a timeoff type with discountsDays=true exists in your Holded account.",
    )


def parse_days_summary(summary: dict) -> dict:
    """Extract the days summary block from a timeoff-year-summary payload."""
    return {
        "total": summary.get("totalDays", 0),
        "used": summary.get("usedDays", 0),
        "available": summary.get("availableDays", 0),
        "unlimited": summary.get("hasUnlimitedDays", False),
        "accrued_expiration": summary.get("accruedDaysExpiration"),
        "breakdown_available": summary.get("daysAvailableBreakdown", {}),
        "breakdown_used": summary.get("daysUsedBreakdown", {}),
    }


def build_request_start(d: date, tz_name: str) -> str:
    """Format a date as an ISO-8601 datetime string with the correct UTC offset."""
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = _PARIS_TZ  # type: ignore[assignment]
    return datetime.combine(d, time(0, 0, 0), tzinfo=tz).isoformat()
