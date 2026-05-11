"""CLI tests for timeoff command group."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any


def _fake_state() -> SimpleNamespace:
    from holded_tt.config import AppConfig
    return SimpleNamespace(
        config=AppConfig(),
        session_store=object(),
    )


def _patch_cli(monkeypatch, fake_state):
    cli_module = importlib.import_module("holded_tt.cli")
    monkeypatch.setattr(cli_module, "create_app_state", lambda: fake_state)
    return cli_module


def _patch_client(monkeypatch, fake_client):
    timeoff_module = importlib.import_module("holded_tt.commands.timeoff")
    monkeypatch.setattr(timeoff_module, "HoldedClient", lambda *_: fake_client)


_SUMMARY = {
    "totalDays": 33,
    "usedDays": 10,
    "availableDays": 23,
    "hasUnlimitedDays": False,
    "daysAvailableBreakdown": {"total": 33, "policy": 24, "accrued": 9, "extra": 0},
    "daysUsedBreakdown": {"total": 10, "policy": 1, "accrued": 9, "extra": 0},
    "accruedDaysExpiration": "march",
    "employeeTimeOffs": [
        {
            "id": "abc123",
            "start": "2026-06-15",
            "end": None,
            "numDays": 1,
            "status": "pending",
            "timeoffType": {"name": "Vacaciones"},
        }
    ],
    "workplaceTimeOffs": [
        {
            "assignationType": "workplace",
            "status": "accepted",
            "start": "2026-08-15",
            "name": "Asuncion de la Virgen",
        }
    ],
    "timeOffDetails": [
        {"id": "type-vac", "name": "Vacaciones", "discountsDays": True, "needsApproval": True},
    ],
}


class _FakeClient:
    def __init__(self, summary: dict = _SUMMARY, request_id: str = "new-id-001"):
        self._summary = summary
        self._request_id = request_id
        self.cancelled: list[str] = []
        self.details_requested: list[list[str]] = []

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *_: Any) -> None:
        pass

    def get_timeoff_summary(self, year: int) -> dict:
        return self._summary

    def request_timeoff(self, start, timeoff_type_id, day_period, description="", end=None) -> str:
        return self._request_id

    def cancel_timeoff(self, timeoff_id: str) -> None:
        self.cancelled.append(timeoff_id)

    def get_timeoff_details(self, timeoff_ids: list[str]) -> list[dict]:
        self.details_requested.append(timeoff_ids)
        return [{"id": tid, "status": "pending", "start": "2026-06-15", "end": None, "numDays": 1, "timeoffType": {"name": "Vacaciones"}} for tid in timeoff_ids]


def test_timeoff_show_renders_all_three_blocks(runner, monkeypatch) -> None:
    """TIO-01: No flags — shows summary, absences and workplace holidays."""
    state = _fake_state()
    _patch_client(monkeypatch, _FakeClient())
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["timeoff", "show"])

    assert result.exit_code == 0, result.stdout
    assert "23" in result.stdout
    assert "abc123" in result.stdout
    assert "Asuncion" in result.stdout


def test_timeoff_show_holidays_only(runner, monkeypatch) -> None:
    """TIO-02: --holidays — only workplace holidays block is shown."""
    state = _fake_state()
    _patch_client(monkeypatch, _FakeClient())
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["timeoff", "show", "--holidays"])

    assert result.exit_code == 0, result.stdout
    assert "Asuncion" in result.stdout
    assert "abc123" not in result.stdout


def test_timeoff_show_mine_only(runner, monkeypatch) -> None:
    """TIO-03: --mine — only personal absences block is shown."""
    state = _fake_state()
    _patch_client(monkeypatch, _FakeClient())
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["timeoff", "show", "--mine"])

    assert result.exit_code == 0, result.stdout
    assert "abc123" in result.stdout
    assert "Asuncion" not in result.stdout


def test_timeoff_show_holidays_and_mine_exits_with_error(runner, monkeypatch) -> None:
    """TIO-04: --holidays and --mine together — exits with error."""
    state = _fake_state()
    _patch_client(monkeypatch, _FakeClient())
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["timeoff", "show", "--holidays", "--mine"])

    assert result.exit_code != 0


def test_timeoff_request_single_day(runner, monkeypatch) -> None:
    """TIO-05: --date — posts single-day request, prints created ID."""
    state = _fake_state()
    fake = _FakeClient()
    _patch_client(monkeypatch, fake)
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["timeoff", "request", "--date", "2026-06-15"])

    assert result.exit_code == 0, result.stdout
    assert "new-id-001" in result.stdout


def test_timeoff_request_date_range(runner, monkeypatch) -> None:
    """TIO-06: --from/--to — posts range request with end field, prints ID."""
    state = _fake_state()
    fake = _FakeClient()
    _patch_client(monkeypatch, fake)
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["timeoff", "request", "--from", "2026-06-15", "--to", "2026-06-20"])

    assert result.exit_code == 0, result.stdout
    assert "new-id-001" in result.stdout


def test_timeoff_request_without_date_exits_error(runner, monkeypatch) -> None:
    """TIO-07: no --date or --from/--to — exits with error."""
    state = _fake_state()
    _patch_client(monkeypatch, _FakeClient())
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["timeoff", "request"])

    assert result.exit_code != 0


def test_timeoff_cancel(runner, monkeypatch) -> None:
    """TIO-08: cancel --id — posts cancel, prints confirmation."""
    state = _fake_state()
    fake = _FakeClient()
    _patch_client(monkeypatch, fake)
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["timeoff", "cancel", "--id", "abc123"])

    assert result.exit_code == 0, result.stdout
    assert fake.cancelled == ["abc123"]


def test_timeoff_details(runner, monkeypatch) -> None:
    """TIO-09: details --id — fetches and renders details."""
    state = _fake_state()
    fake = _FakeClient()
    _patch_client(monkeypatch, fake)
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["timeoff", "details", "--id", "abc123"])

    assert result.exit_code == 0, result.stdout
    assert fake.details_requested == [["abc123"]]
