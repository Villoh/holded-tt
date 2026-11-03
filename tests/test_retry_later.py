"""Retries for schedulers that do not retry a failed run themselves (Windows Task Scheduler)."""

from __future__ import annotations

import importlib
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from holded_tt import timers
from holded_tt.autoclock import clear_failures, note_failure, retry_later
from holded_tt.errors import HoldedCliError
from holded_tt.exit_codes import EXIT_NO_RETRY
from holded_tt.units import RETRY_ATTEMPTS, RETRY_SECONDS

NOW = datetime(2026, 11, 3, 17, 30, tzinfo=timezone.utc)


@pytest.fixture()
def armed(monkeypatch):
    calls = []
    monkeypatch.setattr(timers, "arm_at", lambda when, exe, run=None: calls.append((when, exe)))
    return calls


def test_failures_are_counted_per_day_and_restart_on_a_new_day(tmp_path) -> None:
    path = tmp_path / "failures.json"

    assert [note_failure(path, date(2026, 11, 3)) for _ in range(3)] == [1, 2, 3]
    assert note_failure(path, date(2026, 11, 4)) == 1  # yesterday's failures do not count


def test_a_corrupt_failures_file_counts_from_one(tmp_path) -> None:
    path = tmp_path / "failures.json"
    path.write_text("{nope")

    assert note_failure(path, date(2026, 11, 3)) == 1


def test_clear_failures_forgets_them_and_tolerates_no_file(tmp_path) -> None:
    path = tmp_path / "failures.json"
    note_failure(path, date(2026, 11, 3))

    clear_failures(path)
    clear_failures(path)

    assert not path.exists()


def test_retry_arms_a_task_two_minutes_ahead(tmp_path, armed) -> None:
    told = retry_later(tmp_path / "f.json", NOW, "holded-tt.exe")

    assert armed == [(NOW + timedelta(seconds=RETRY_SECONDS), "holded-tt.exe")]
    assert f"retrying in 2 min (attempt 1 of {RETRY_ATTEMPTS})" in told


def test_retry_gives_up_after_the_same_number_of_attempts_as_systemd(tmp_path, armed) -> None:
    path = tmp_path / "f.json"
    for _ in range(RETRY_ATTEMPTS):
        retry_later(path, NOW, "x")
    armed.clear()

    told = retry_later(path, NOW, "x")

    assert armed == [] and "giving up" in told


def test_retry_reports_when_it_cannot_arm(tmp_path, monkeypatch) -> None:
    def boom(*_a, **_k):
        raise HoldedCliError(message="Access is denied", hint="x")

    monkeypatch.setattr(timers, "arm_at", boom)

    assert "could not arm a retry: Access is denied" in retry_later(tmp_path / "f.json", NOW, "x")


# --- CLI: `tick --schedule` re-arms a retry only where the scheduler will not retry ---------


@pytest.fixture()
def cli(monkeypatch, tmp_path):
    cli_module = importlib.import_module("holded_tt.cli")
    clock = importlib.import_module("holded_tt.commands.clock")
    from holded_tt.config import AppConfig

    state = SimpleNamespace(config=AppConfig(timezone="UTC"), config_dir=tmp_path, session_store=object())
    monkeypatch.setattr(cli_module, "create_app_state", lambda: state)
    monkeypatch.setattr(clock, "executable", lambda: "holded-tt.exe")

    class Client:
        def __enter__(self): return self
        def __exit__(self, *_): pass

    monkeypatch.setattr(clock, "HoldedClient", lambda *_: Client())
    return SimpleNamespace(app=cli_module.app, clock=clock, dir=tmp_path)


def fail_with(code):
    def run(*_a, **_k):
        raise HoldedCliError(message="boom", hint="h", exit_code=code)
    return run


def test_a_failed_scheduled_run_arms_a_retry_where_the_scheduler_does_not(runner, cli, monkeypatch, armed) -> None:
    monkeypatch.setattr(cli.clock.timers, "retries_natively", lambda: False)
    monkeypatch.setattr(cli.clock, "run_tick", fail_with(2))

    result = runner.invoke(cli.app, ["clock", "tick", "--schedule"])

    assert result.exit_code == 2 and len(armed) == 1
    assert "retrying in 2 min" in result.output
    assert json.loads((cli.dir / "failures.json").read_text())["attempts"] == 1


def test_no_retry_is_armed_where_the_scheduler_retries_itself(runner, cli, monkeypatch, armed) -> None:
    monkeypatch.setattr(cli.clock.timers, "retries_natively", lambda: True)
    monkeypatch.setattr(cli.clock, "run_tick", fail_with(2))

    result = runner.invoke(cli.app, ["clock", "tick", "--schedule"])

    assert result.exit_code == 2 and armed == [] and not (cli.dir / "failures.json").exists()


def test_a_failure_that_retrying_cannot_fix_is_not_retried(runner, cli, monkeypatch, armed) -> None:
    monkeypatch.setattr(cli.clock.timers, "retries_natively", lambda: False)
    monkeypatch.setattr(cli.clock, "run_tick", fail_with(EXIT_NO_RETRY))

    result = runner.invoke(cli.app, ["clock", "tick", "--schedule"])

    assert result.exit_code == EXIT_NO_RETRY and armed == []


def test_a_plain_tick_without_schedule_never_arms_a_retry(runner, cli, monkeypatch, armed) -> None:
    monkeypatch.setattr(cli.clock.timers, "retries_natively", lambda: False)
    monkeypatch.setattr(cli.clock, "run_tick", fail_with(2))

    runner.invoke(cli.app, ["clock", "tick"])

    assert armed == []


def test_a_successful_scheduled_run_clears_earlier_failures(runner, cli, monkeypatch, armed) -> None:
    note_failure(cli.dir / "failures.json", date.today())
    monkeypatch.setattr(cli.clock, "run_tick", lambda *_a, **_k: [])

    result = runner.invoke(cli.app, ["clock", "tick", "--schedule"])

    assert result.exit_code == 0 and not (cli.dir / "failures.json").exists()
