"""Tests for timeoff business logic."""

from __future__ import annotations

from datetime import date


def test_extract_workplace_holidays_filters_by_assignation_and_status() -> None:
    from holded_tt.timeoff import extract_workplace_holidays

    summary = {
        "workplaceTimeOffs": [
            {"assignationType": "workplace", "status": "accepted", "start": "2026-01-01", "name": "Año Nuevo"},
            {"assignationType": "workplace", "status": "pending", "start": "2026-01-06", "name": "Reyes"},
            {"assignationType": "employee", "status": "accepted", "start": "2026-01-12", "name": ""},
            {"assignationType": "workplace", "status": "accepted", "start": "2026-04-03", "name": "Viernes Santo"},
        ]
    }

    result = extract_workplace_holidays(summary, 2026)

    assert date(2026, 1, 1) in result
    assert date(2026, 4, 3) in result
    assert date(2026, 1, 6) not in result
    assert date(2026, 1, 12) not in result


def test_extract_workplace_holidays_ignores_other_years() -> None:
    from holded_tt.timeoff import extract_workplace_holidays

    summary = {
        "workplaceTimeOffs": [
            {"assignationType": "workplace", "status": "accepted", "start": "2025-12-25", "name": "Navidad"},
            {"assignationType": "workplace", "status": "accepted", "start": "2026-01-01", "name": "Año Nuevo"},
        ]
    }

    result = extract_workplace_holidays(summary, 2026)

    assert date(2025, 12, 25) not in result
    assert date(2026, 1, 1) in result


def test_extract_workplace_holidays_skips_invalid_dates() -> None:
    from holded_tt.timeoff import extract_workplace_holidays

    summary = {
        "workplaceTimeOffs": [
            {"assignationType": "workplace", "status": "accepted", "start": "not-a-date", "name": ""},
        ]
    }

    assert extract_workplace_holidays(summary, 2026) == {}


def test_extract_employee_absences_returns_employee_timeoffs() -> None:
    from holded_tt.timeoff import extract_employee_absences

    summary = {
        "employeeTimeOffs": [
            {"id": "abc", "start": "2026-06-15", "end": None, "numDays": 1, "status": "pending",
             "timeoffType": {"name": "Vacaciones"}},
            {"id": "def", "start": "2026-02-23", "end": "2026-03-03", "numDays": 7, "status": "accepted",
             "timeoffType": {"name": "Vacaciones"}},
        ]
    }

    result = extract_employee_absences(summary)

    assert len(result) == 2
    assert result[0]["id"] == "abc"
    assert result[1]["id"] == "def"


def test_extract_employee_absences_returns_empty_list_when_missing() -> None:
    from holded_tt.timeoff import extract_employee_absences

    assert extract_employee_absences({}) == []
    assert extract_employee_absences({"employeeTimeOffs": None}) == []


def test_resolve_vacation_type_id_returns_first_discounts_and_needs_approval() -> None:
    from holded_tt.timeoff import resolve_vacation_type_id

    summary = {
        "timeOffDetails": [
            {"id": "type-sick", "name": "Enfermedad", "discountsDays": False, "needsApproval": False},
            {"id": "type-vac", "name": "Vacaciones", "discountsDays": True, "needsApproval": True},
        ]
    }

    assert resolve_vacation_type_id(summary) == "type-vac"


def test_resolve_vacation_type_id_raises_when_not_found() -> None:
    from holded_tt.timeoff import resolve_vacation_type_id
    from holded_tt.holded_client import HoldedApiError

    summary = {"timeOffDetails": [
        {"id": "type-sick", "name": "Enfermedad", "discountsDays": False, "needsApproval": False},
    ]}

    try:
        resolve_vacation_type_id(summary)
        assert False, "Expected HoldedApiError"
    except HoldedApiError as e:
        assert "vacation" in e.message.lower() or "tipo" in e.message.lower()


def test_parse_days_summary_extracts_key_fields() -> None:
    from holded_tt.timeoff import parse_days_summary

    summary = {
        "totalDays": 33,
        "usedDays": 10,
        "availableDays": 23,
        "hasUnlimitedDays": False,
        "daysAvailableBreakdown": {"total": 33, "policy": 24, "accrued": 9, "extra": 0},
        "daysUsedBreakdown": {"total": 10, "policy": 1, "accrued": 9, "extra": 0},
        "accruedDaysExpiration": "march",
    }

    result = parse_days_summary(summary)

    assert result["total"] == 33
    assert result["used"] == 10
    assert result["available"] == 23
    assert result["accrued_expiration"] == "march"
    assert result["breakdown_available"]["policy"] == 24
    assert result["breakdown_used"]["accrued"] == 9


def test_build_request_start_formats_iso8601_with_offset() -> None:
    from holded_tt.timeoff import build_request_start
    from datetime import date

    result = build_request_start(date(2026, 6, 15), "Europe/Madrid")

    # Should be an ISO-8601 datetime string with a UTC offset (not Z)
    assert result.startswith("2026-06-15T00:00:00")
    assert "+" in result or result.endswith("-00:00")


def test_holded_client_has_get_timeoff_summary() -> None:
    from holded_tt.holded_client import HoldedClient
    assert hasattr(HoldedClient, "get_timeoff_summary")

def test_holded_client_has_request_timeoff() -> None:
    from holded_tt.holded_client import HoldedClient
    assert hasattr(HoldedClient, "request_timeoff")

def test_holded_client_has_cancel_timeoff() -> None:
    from holded_tt.holded_client import HoldedClient
    assert hasattr(HoldedClient, "cancel_timeoff")

def test_holded_client_has_get_timeoff_details() -> None:
    from holded_tt.holded_client import HoldedClient
    assert hasattr(HoldedClient, "get_timeoff_details")
