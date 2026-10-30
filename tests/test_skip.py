"""Tests for `clock skip`: the skip list, cancelling today's plan, and the CLI."""

from __future__ import annotations

import importlib
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from holded_tt import autoclock, units
from holded_tt.autoclock import (
    SKIPPED_BY_YOU,
    Plan,
    build_plan,
    load_plan,
    load_skips,
    run_tick,
    save_plan,
    save_skips,
    skip_plan,
    unskip_plan,
)
from holded_tt.config import AppConfig
from holded_tt.errors import HoldedCliError

UTC = timezone.utc
TODAY = date(2026, 4, 7)  # a Tuesday
TOMORROW = TODAY + timedelta(days=1)
H = 60


def cfg(**kw) -> AppConfig:
    return AppConfig(
        start="08:30", end="17:30", timezone="UTC", pause=["14:00-14:30"], jitter=0, max_late=90,
        days={}, **kw,
    )


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)


class Holded:
    """Counts API calls and records what was clocked."""

    def __init__(self) -> None:
        self.api = 0
        self.actions: list[str] = []
        self.tracker: dict | None = None

    def get_timeoff_summary(self, _year):
        self.api += 1
        return {}

    def get_current_tracker(self):
        self.api += 1
        return self.tracker

    def clock_in(self):
        self.actions.append("in")
        self.tracker = {"id": "t", "start": at(TODAY, 8, 30).isoformat(), "running": True, "paused": False}
        return "t"

    def clock_out(self, _id):
        self.actions.append("out")
        self.tracker = None

    def pause_tracker(self, _id):
        self.actions.append("pause")

    def resume_tracker(self, _id):
        self.actions.append("resume")


# ---------------------------------------------------------------------------
# skip list
# ---------------------------------------------------------------------------


def test_skips_round_trip_and_keep_only_today_onwards(tmp_path) -> None:
    path = tmp_path / "skips.json"
    old = TODAY - timedelta(days=3)

    save_skips(path, [old, TODAY, TOMORROW], TODAY)

    assert load_skips(path) == frozenset({TODAY, TOMORROW})  # the past is pruned, so the file never grows


def test_skips_missing_or_corrupt_file_means_none(tmp_path) -> None:
    path = tmp_path / "skips.json"
    assert load_skips(path) == frozenset()
    path.write_text("{not json")
    assert load_skips(path) == frozenset()
    path.write_text('{"days": "2026-04-07"}')  # wrong shape
    assert load_skips(path) == frozenset()
    path.write_text("[1, 2]")
    assert load_skips(path) == frozenset()


def test_skips_one_bad_entry_does_not_drop_the_good_ones(tmp_path) -> None:
    path = tmp_path / "skips.json"
    path.write_text(json.dumps({"days": ["2026-04-07", "garbage", None, 5, "2026-04-09"]}))

    assert load_skips(path) == frozenset({date(2026, 4, 7), date(2026, 4, 9)})


# ---------------------------------------------------------------------------
# build_plan / run_tick honour the list
# ---------------------------------------------------------------------------


def test_a_skipped_day_is_not_planned_and_does_not_ask_holded() -> None:
    def boom(_year):
        raise AssertionError("must not call Holded for a day you skipped")

    plan = build_plan(cfg(), TODAY, boom, frozenset({TODAY}))

    assert (plan.status, plan.reason) == ("skipped", SKIPPED_BY_YOU)


def test_other_days_are_unaffected_by_the_list() -> None:
    plan = build_plan(cfg(), TODAY, lambda _y: {}, frozenset({TOMORROW}))

    assert plan.status == "active" and plan.in_at == 8 * H + 30


def test_skipping_another_day_does_not_stop_todays_plan(tmp_path) -> None:
    """A trip next week must not cancel today, and yesterday's plan must not leak into today."""
    holded = Holded()
    plan_file = tmp_path / "plan.json"
    save_plan(plan_file, Plan((TODAY - timedelta(days=1)).isoformat(), "skipped", SKIPPED_BY_YOU))

    out = run_tick(cfg(), plan_file, holded, at(TODAY, 6, 0), skips=frozenset({TOMORROW}))

    assert "plan 08:30 -> 17:30" in out[0]
    assert load_plan(plan_file).status == "active"  # type: ignore[union-attr]
    run_tick(cfg(), plan_file, holded, at(TODAY, 8, 30), skips=frozenset({TOMORROW}))
    assert holded.actions == ["in"]


def test_tick_on_a_skipped_day_clocks_nothing_and_stays_quiet(tmp_path) -> None:
    holded = Holded()
    plan_file = tmp_path / "plan.json"
    out = []

    for hour, minute in [(6, 0), (8, 30), (14, 0), (17, 30)]:
        out += run_tick(cfg(), plan_file, holded, at(TODAY, hour, minute), skips=frozenset({TODAY}))

    assert holded.actions == [] and holded.api == 0
    assert out == [f"{TODAY}: skipped ({SKIPPED_BY_YOU})"]  # said once, not at every tick


def test_a_plan_made_before_the_skip_is_cancelled_by_the_next_tick(tmp_path) -> None:
    """Belt and braces: even if the armed timer was not stopped, the tick obeys the list."""
    holded = Holded()
    plan_file = tmp_path / "plan.json"
    run_tick(cfg(), plan_file, holded, at(TODAY, 6, 0))  # planned, active
    assert load_plan(plan_file).status == "active"  # type: ignore[union-attr]

    out = run_tick(cfg(), plan_file, holded, at(TODAY, 8, 30), skips=frozenset({TODAY}))

    assert holded.actions == [] and "skipped" in out[0]
    assert load_plan(plan_file).reason == SKIPPED_BY_YOU  # type: ignore[union-attr]


def test_skip_does_not_touch_a_day_that_already_finished(tmp_path) -> None:
    plan_file = tmp_path / "plan.json"
    save_plan(plan_file, Plan(TODAY.isoformat(), in_at=510, out_at=1050, duration=540, done=["in", "out"]))

    run_tick(cfg(), plan_file, Holded(), at(TODAY, 18, 0), skips=frozenset({TODAY}))

    assert load_plan(plan_file).done == ["in", "out"]  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# skip_plan / unskip_plan
# ---------------------------------------------------------------------------


def test_skip_plan_cancels_the_rest_of_todays_plan(tmp_path) -> None:
    plan_file = tmp_path / "plan.json"
    save_plan(plan_file, Plan(TODAY.isoformat(), in_at=510, out_at=1050, duration=540))

    assert skip_plan(plan_file, TODAY) is True

    plan = load_plan(plan_file)
    assert plan is not None and (plan.status, plan.reason) == ("skipped", SKIPPED_BY_YOU)
    assert autoclock.next_event(plan) is None  # nothing left to arm


def test_skip_plan_without_a_plan_for_today_does_nothing(tmp_path) -> None:
    plan_file = tmp_path / "plan.json"

    assert skip_plan(plan_file, TODAY) is False  # no file
    save_plan(plan_file, Plan(TOMORROW.isoformat(), in_at=510, out_at=1050, duration=540))
    assert skip_plan(plan_file, TODAY) is False  # a plan for another day is left alone
    assert load_plan(plan_file).status == "active"  # type: ignore[union-attr]


def test_unskip_plan_only_drops_a_plan_that_we_skipped(tmp_path) -> None:
    plan_file = tmp_path / "plan.json"
    save_plan(plan_file, Plan(TODAY.isoformat(), "skipped", "weekend"))
    assert unskip_plan(plan_file, TODAY) is False and plan_file.exists()  # a holiday stays a holiday

    save_plan(plan_file, Plan(TODAY.isoformat(), "skipped", SKIPPED_BY_YOU))
    assert unskip_plan(plan_file, TODAY) is True and not plan_file.exists()


def test_undo_then_tick_plans_the_day_afresh(tmp_path) -> None:
    holded = Holded()
    plan_file = tmp_path / "plan.json"
    run_tick(cfg(), plan_file, holded, at(TODAY, 6, 0), skips=frozenset({TODAY}))
    assert load_plan(plan_file).status == "skipped"  # type: ignore[union-attr]

    unskip_plan(plan_file, TODAY)
    out = run_tick(cfg(), plan_file, holded, at(TODAY, 6, 5))

    assert "plan 08:30 -> 17:30" in out[0]
    assert load_plan(plan_file).status == "active"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.fixture()
def cli(monkeypatch, tmp_path):
    cli_module = importlib.import_module("holded_tt.cli")
    clock = importlib.import_module("holded_tt.commands.clock")
    state = SimpleNamespace(config=cfg(), config_dir=tmp_path, session_store=object())
    monkeypatch.setattr(cli_module, "create_app_state", lambda: state)
    monkeypatch.setattr(clock, "_local_today", lambda _state: TODAY)
    disarmed = []
    monkeypatch.setattr(clock.units, "disarm", lambda *_a, **_k: disarmed.append(True))
    cli_module.disarmed = disarmed  # type: ignore[attr-defined]
    return cli_module


def skips(tmp_path) -> frozenset[date]:
    return load_skips(tmp_path / "skips.json")


def test_skip_with_no_dates_skips_today(runner, cli, tmp_path) -> None:
    result = runner.invoke(cli.app, ["clock", "skip"])

    assert result.exit_code == 0, result.output
    assert skips(tmp_path) == frozenset({TODAY})
    assert "skipping 1 day(s): 2026-04-07" in result.stdout


def test_skip_today_cancels_the_plan_and_stops_the_armed_timer(runner, cli, tmp_path) -> None:
    save_plan(tmp_path / "plan.json", Plan(TODAY.isoformat(), in_at=510, out_at=1050, duration=540))

    runner.invoke(cli.app, ["clock", "skip"])

    assert load_plan(tmp_path / "plan.json").reason == SKIPPED_BY_YOU  # type: ignore[union-attr]
    assert cli.disarmed == [True]


def test_skip_a_future_day_does_not_touch_todays_plan_or_timer(runner, cli, tmp_path) -> None:
    save_plan(tmp_path / "plan.json", Plan(TODAY.isoformat(), in_at=510, out_at=1050, duration=540))

    result = runner.invoke(cli.app, ["clock", "skip", "--date", "2026-04-09"])

    assert result.exit_code == 0
    assert skips(tmp_path) == frozenset({date(2026, 4, 9)})
    assert load_plan(tmp_path / "plan.json").status == "active"  # type: ignore[union-attr]
    assert cli.disarmed == []


def test_skip_a_range(runner, cli, tmp_path) -> None:
    result = runner.invoke(cli.app, ["clock", "skip", "--from", "2026-04-08", "--to", "2026-04-10"])

    assert result.exit_code == 0 and "skipping 3 day(s): 2026-04-08 to 2026-04-10" in result.stdout
    assert skips(tmp_path) == {date(2026, 4, d) for d in (8, 9, 10)}


def test_skips_accumulate_and_undo_removes_only_what_was_asked(runner, cli, tmp_path) -> None:
    runner.invoke(cli.app, ["clock", "skip", "--date", "2026-04-08"])
    runner.invoke(cli.app, ["clock", "skip", "--from", "2026-04-10", "--to", "2026-04-11"])
    assert len(skips(tmp_path)) == 3

    result = runner.invoke(cli.app, ["clock", "skip", "--date", "2026-04-10", "--undo"])

    assert result.exit_code == 0 and "no longer skipping 1 day(s)" in result.stdout
    assert skips(tmp_path) == {date(2026, 4, 8), date(2026, 4, 11)}


def test_undo_today_forgets_a_plan_we_skipped_and_says_how_to_replan(runner, cli, tmp_path) -> None:
    save_plan(tmp_path / "plan.json", Plan(TODAY.isoformat(), in_at=510, out_at=1050, duration=540))
    runner.invoke(cli.app, ["clock", "skip"])
    assert load_plan(tmp_path / "plan.json").reason == SKIPPED_BY_YOU  # type: ignore[union-attr]

    result = runner.invoke(cli.app, ["clock", "skip", "--undo"])

    assert result.exit_code == 0 and "clock tick --schedule" in result.stdout
    assert not (tmp_path / "plan.json").exists() and skips(tmp_path) == frozenset()


def test_undo_today_says_how_to_replan_even_if_no_plan_had_been_made(runner, cli, tmp_path) -> None:
    """Skipping disarmed the timer either way, so the chain is broken until someone replans."""
    runner.invoke(cli.app, ["clock", "skip"])
    assert not (tmp_path / "plan.json").exists()  # skip before any tick: nothing to cancel

    result = runner.invoke(cli.app, ["clock", "skip", "--undo"])

    assert result.exit_code == 0 and "clock tick --schedule" in result.stdout


def test_undo_a_future_day_does_not_mention_replanning(runner, cli, tmp_path) -> None:
    runner.invoke(cli.app, ["clock", "skip", "--date", "2026-04-09"])

    result = runner.invoke(cli.app, ["clock", "skip", "--date", "2026-04-09", "--undo"])

    assert "clock tick" not in result.stdout


def test_past_days_are_ignored_with_a_note_and_all_past_is_an_error(runner, cli, tmp_path) -> None:
    mixed = runner.invoke(cli.app, ["clock", "skip", "--from", "2026-04-05", "--to", "2026-04-08"])
    assert mixed.exit_code == 0 and "ignored 2 day(s) in the past" in mixed.stdout
    assert skips(tmp_path) == {TODAY, TOMORROW}

    past = runner.invoke(cli.app, ["clock", "skip", "--date", "2026-04-01"])
    assert past.exit_code == 2 or past.exit_code == 1
    assert "already in the past" in past.output


def test_skip_warns_when_you_are_clocked_in_and_nothing_will_clock_you_out(runner, cli, tmp_path) -> None:
    plan = Plan(TODAY.isoformat(), in_at=510, out_at=1050, duration=540, done=["in"])
    save_plan(tmp_path / "plan.json", plan)

    result = runner.invoke(cli.app, ["clock", "skip"])

    assert result.exit_code == 0 and "clocked in" in result.stdout and "clock out" in result.stdout


def test_skip_does_not_warn_when_nothing_is_open(runner, cli, tmp_path) -> None:
    save_plan(tmp_path / "plan.json", Plan(TODAY.isoformat(), in_at=510, out_at=1050, duration=540))

    result = runner.invoke(cli.app, ["clock", "skip"])

    assert "warning" not in result.stdout


@pytest.mark.parametrize(
    "args, message",
    [
        (["--date", "2026-04-08", "--from", "2026-04-09"], "cannot be combined"),
        (["--from", "2026-04-09"], "Both --from and --to"),
        (["--date", "garbage"], "Invalid date"),
        (["--from", "2026-04-10", "--to", "2026-04-09"], "after end date"),
    ],
)
def test_skip_rejects_bad_input_without_writing_anything(runner, cli, tmp_path, args, message) -> None:
    result = runner.invoke(cli.app, ["clock", "skip", *args])

    assert result.exit_code == 1 and message in result.output
    assert not (tmp_path / "skips.json").exists()


def test_skip_lists_what_is_currently_skipped(runner, cli, tmp_path) -> None:
    result = runner.invoke(cli.app, ["clock", "skip", "--from", "2026-04-08", "--to", "2026-04-09"])

    assert "skipped days: 2026-04-08, 2026-04-09" in result.stdout


def test_tick_command_reads_the_skip_list(runner, cli, tmp_path, monkeypatch) -> None:
    clock = importlib.import_module("holded_tt.commands.clock")
    seen = {}

    class Client:
        def __enter__(self): return self
        def __exit__(self, *_): pass

    monkeypatch.setattr(clock, "HoldedClient", lambda *_: Client())
    monkeypatch.setattr(clock, "run_tick", lambda *a, **_k: seen.update(skips=a[5]) or [])
    save_skips(tmp_path / "skips.json", [TOMORROW], TODAY)

    runner.invoke(cli.app, ["clock", "tick"])

    assert seen["skips"] == frozenset({TOMORROW})


# ---------------------------------------------------------------------------
# units.disarm
# ---------------------------------------------------------------------------


@pytest.fixture()
def with_systemctl(monkeypatch):
    """Pretend systemd is there: CI hosts for macOS, Windows and Nix builds have no systemctl."""
    real = units.shutil.which
    monkeypatch.setattr(
        units.shutil, "which", lambda name: "/usr/bin/systemctl" if name == "systemctl" else real(name)
    )


def test_disarm_stops_every_armed_timer(with_systemctl) -> None:
    calls = []
    units.disarm(lambda cmd, **_k: calls.append(cmd) or SimpleNamespace(returncode=0, stderr=""))

    assert len(calls) == 1 and calls[0][-2:] == ["stop", units.ARMED_PATTERN]


def test_disarm_is_a_quiet_no_op_without_systemd(monkeypatch) -> None:
    monkeypatch.setattr(units.shutil, "which", lambda _n: None)

    units.disarm(lambda *_a, **_k: pytest.fail("must not run anything"))  # does not raise


def test_a_real_failure_to_stop_is_not_fatal(with_systemctl) -> None:
    """Nothing armed makes `systemctl stop` fail; skipping must still succeed."""
    calls = []

    def failing(cmd, **_k):
        calls.append(cmd)
        return SimpleNamespace(returncode=5, stderr="Unit not loaded")

    units.disarm(failing)  # does not raise

    assert len(calls) == 1  # it did try; the failure was swallowed, not skipped
