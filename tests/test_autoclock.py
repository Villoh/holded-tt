"""Tests for unattended clocking (`clock tick`): planning, stepping and full-day runs."""

from __future__ import annotations

import importlib
import random
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from holded_tt.autoclock import Plan, Tracker, build_plan, load_plan, run_tick, step
from holded_tt.config import AppConfig
from holded_tt.errors import HoldedCliError

UTC = timezone.utc
TUE = date(2026, 4, 7)
FRI = date(2026, 4, 10)
SAT = date(2026, 4, 4)
H = 60  # minutes per hour


def hm(text: str) -> int:
    h, m = text.split(":")
    return int(h) * H + int(m)


def cfg(**kw) -> AppConfig:
    base = dict(
        start="08:30",
        end="17:30",
        timezone="UTC",
        pause=["14:00-14:30"],
        jitter=0,
        max_late=90,
        days={"fri": {"end": "15:00", "pause": []}},
    )
    return AppConfig(**{**base, **kw})


def at(day: date, minute: int) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(minutes=minute)


class FakeHolded:
    """Just enough of HoldedClient to track real state and worked minutes."""

    def __init__(self, day: date = TUE, summary: dict | None = None) -> None:
        self.day = day
        self.minute = 0
        self.summary = summary or {}
        self.tracker: dict | None = None
        self.calls: list[tuple[str, str]] = []
        self.api = 0
        self.worked = 0
        self._since = 0

    def _now(self) -> datetime:
        return at(self.day, self.minute)

    def _log(self, action: str) -> None:
        self.calls.append((f"{self.minute // H:02d}:{self.minute % H:02d}", action))

    def start_running(self, minute: int, day: date | None = None) -> None:
        """A tracker started by hand (optionally on another day)."""
        self.tracker = {
            "id": "t1",
            "start": at(day or self.day, minute).isoformat(),
            "running": True,
            "paused": False,
        }
        self._since = minute

    def get_timeoff_summary(self, year: int) -> dict:
        self.api += 1
        return self.summary

    def get_current_tracker(self) -> dict | None:
        self.api += 1
        return self.tracker

    def clock_in(self) -> str:
        self.start_running(self.minute)
        self._log("in")
        return "t1"

    def pause_tracker(self, _id: str) -> dict:
        assert self.tracker and self.tracker["running"]
        self.worked += self.minute - self._since
        self.tracker.update(running=False, paused=True)
        self._log("pause")
        return {}

    def resume_tracker(self, _id: str) -> dict:
        assert self.tracker and self.tracker["paused"]
        self._since = self.minute
        self.tracker.update(running=True, paused=False)
        self._log("resume")
        return {}

    def clock_out(self, _id: str) -> None:
        assert self.tracker and self.tracker["running"]
        self.worked += self.minute - self._since
        self.tracker = None
        self._log("out")


def simulate(client: FakeHolded, config: AppConfig, plan_file, first: int, last: int = 20 * H):
    """Run a tick every 5 minutes like a timer would. Errors are collected, not raised."""
    lines: list[str] = []
    errors: list[HoldedCliError] = []
    for minute in range(first, last + 1, 5):
        client.minute = minute
        try:
            lines += run_tick(config, plan_file, client, client._now())
        except HoldedCliError as error:
            errors.append(error)
    return lines, errors


# ---------------------------------------------------------------------------
# build_plan
# ---------------------------------------------------------------------------


def test_plan_without_jitter_matches_config() -> None:
    plan = build_plan(cfg(), TUE, lambda _y: {})

    assert (plan.status, plan.in_at, plan.out_at, plan.duration) == ("active", hm("08:30"), hm("17:30"), 9 * H)
    assert plan.pauses == [[hm("14:00"), hm("14:30")]]


def test_plan_uses_weekday_override() -> None:
    plan = build_plan(cfg(), FRI, lambda _y: {})

    assert (plan.in_at, plan.out_at, plan.pauses) == (hm("08:30"), hm("15:00"), [])


def test_weekend_is_skipped_without_calling_holded() -> None:
    def boom(_year: int) -> dict:
        raise AssertionError("must not fetch for a weekend")

    plan = build_plan(cfg(), SAT, boom)

    assert (plan.status, plan.reason) == ("skipped", "weekend")


def test_workplace_holiday_is_skipped() -> None:
    summary = {"workplaceTimeOffs": [
        {"assignationType": "workplace", "status": "accepted", "start": "2026-04-07", "name": "Fiesta"}
    ]}

    plan = build_plan(cfg(), TUE, lambda _y: summary)

    assert plan.status == "skipped" and "Fiesta" in plan.reason


@pytest.mark.parametrize(
    "absence, skipped",
    [
        ({"status": "accepted", "start": "2026-04-06", "end": "2026-04-08"}, True),  # range
        ({"status": "accepted", "start": "2026-04-07", "end": None}, True),  # single day
        ({"status": "pending", "start": "2026-04-06", "end": "2026-04-08"}, False),
        ({"status": "accepted", "start": "2026-04-08", "end": "2026-04-09"}, False),
        ({"status": "accepted", "start": "garbage", "end": None}, False),
    ],
)
def test_personal_time_off_only_skips_accepted_days_it_covers(absence, skipped) -> None:
    plan = build_plan(cfg(), TUE, lambda _y: {"employeeTimeOffs": [absence]})

    assert (plan.status == "skipped") is skipped


def test_jitter_plan_keeps_net_hours() -> None:
    for seed in range(200):
        random.seed(seed)
        plan = build_plan(cfg(jitter=20), TUE, lambda _y: {})
        paused = sum(b - a for a, b in plan.pauses)
        assert plan.duration - paused >= 8 * H + 30
        assert plan.out_at - plan.in_at == plan.duration


# ---------------------------------------------------------------------------
# step (pure state machine)
# ---------------------------------------------------------------------------


def plan_for(**kw) -> Plan:
    base = dict(date="2026-04-07", in_at=hm("08:30"), out_at=hm("17:30"), duration=9 * H, pauses=[[hm("14:00"), hm("14:30")]])
    return Plan(**{**base, **kw})


def test_step_waits_until_planned_time() -> None:
    plan = plan_for()

    assert step(plan, hm("08:29"), Tracker("none"), 90) == []
    assert plan.done == []


def test_step_late_in_pushes_out_to_keep_duration() -> None:
    plan = plan_for()

    assert step(plan, hm("08:50"), Tracker("none"), 90) == ["in"]
    assert plan.out_at == hm("17:50")


def test_step_in_at_the_limit_is_allowed_but_one_minute_more_is_missed() -> None:
    assert step(plan_for(), hm("10:00"), Tracker("none"), 90) == ["in"]

    plan = plan_for()
    assert step(plan, hm("10:01"), Tracker("none"), 90) == []
    assert plan.status == "missed" and "10:01" in plan.reason
    assert step(plan, hm("12:00"), Tracker("none"), 90) == []  # stays dead


def test_step_adopts_a_tracker_started_by_hand() -> None:
    plan = plan_for()

    assert step(plan, hm("09:15"), Tracker("running", hm("09:12")), 90) == []
    assert "in" in plan.done
    assert plan.out_at == hm("09:12") + 9 * H  # keeps the planned duration from the real start


def test_step_manual_early_in_never_shortens_the_day() -> None:
    plan = plan_for()

    step(plan, hm("08:30"), Tracker("running", hm("07:50")), 90)

    assert plan.out_at == hm("17:30")


def test_step_pause_and_resume_in_order() -> None:
    plan = plan_for(done=["in"])

    assert step(plan, hm("14:00"), Tracker("running", hm("08:30")), 90) == ["pause"]
    assert step(plan, hm("14:10"), Tracker("paused", hm("08:30")), 90) == []
    assert step(plan, hm("14:30"), Tracker("paused", hm("08:30")), 90) == ["resume"]


def test_step_late_resume_pushes_out_by_the_extra_pause() -> None:
    plan = plan_for(done=["in", "p0"])

    assert step(plan, hm("14:45"), Tracker("paused", hm("08:30")), 90) == ["resume"]
    assert plan.out_at == hm("17:45")


def test_step_skips_a_pause_that_is_already_over() -> None:
    """Laptop was off over lunch: don't pause now just because the plan says so."""
    plan = plan_for(done=["in"])

    assert step(plan, hm("14:40"), Tracker("running", hm("08:30")), 90) == []
    assert {"p0", "r0"} <= set(plan.done)
    assert plan.out_at == hm("17:30")


def test_step_respects_a_manual_clock_out() -> None:
    plan = plan_for(done=["in"])

    assert step(plan, hm("14:10"), Tracker("none"), 90) == []
    assert step(plan, hm("17:35"), Tracker("none"), 90) == []
    assert "out" in plan.done


def test_step_resumes_before_clocking_out_if_left_paused() -> None:
    plan = plan_for(done=["in", "p0", "r0"])

    assert step(plan, hm("17:35"), Tracker("paused", hm("08:30")), 90) == ["resume", "out"]


def test_step_is_idempotent_once_events_are_done() -> None:
    plan = plan_for()
    step(plan, hm("08:30"), Tracker("none"), 90)

    assert step(plan, hm("08:30"), Tracker("running", hm("08:30")), 90) == []


# ---------------------------------------------------------------------------
# run_tick: whole days against a fake Holded
# ---------------------------------------------------------------------------


def test_full_day_on_time(tmp_path) -> None:
    client = FakeHolded()

    simulate(client, cfg(), tmp_path / "plan.json", hm("06:00"))

    assert client.calls == [
        ("08:30", "in"), ("14:00", "pause"), ("14:30", "resume"), ("17:30", "out"),
    ]
    assert client.worked == 8 * H + 30
    assert client.tracker is None


def test_late_boot_keeps_net_hours(tmp_path) -> None:
    """Machine switched on at 08:50: clock-in then, clock-out 20 minutes later."""
    client = FakeHolded()

    _, errors = simulate(client, cfg(), tmp_path / "plan.json", hm("08:50"))

    assert not errors
    assert client.calls[0] == ("08:50", "in")
    assert client.calls[-1] == ("17:50", "out")
    assert client.worked == 8 * H + 30


def test_too_late_misses_the_day_and_alerts_once(tmp_path) -> None:
    client = FakeHolded()

    _, errors = simulate(client, cfg(), tmp_path / "plan.json", hm("10:05"))

    assert client.calls == []
    assert len(errors) == 1 and "Missed" in errors[0].message
    assert errors[0].exit_code == 2  # makes the systemd unit fail


def test_exactly_at_the_limit_still_clocks_in(tmp_path) -> None:
    client = FakeHolded()

    _, errors = simulate(client, cfg(), tmp_path / "plan.json", hm("10:00"))

    assert not errors and client.calls[0] == ("10:00", "in")
    assert client.worked == 8 * H + 30


def test_friday_intensive_day(tmp_path) -> None:
    client = FakeHolded(FRI)

    simulate(client, cfg(), tmp_path / "plan.json", hm("06:00"))

    assert client.calls == [("08:30", "in"), ("15:00", "out")]
    assert client.worked == 6 * H + 30


def test_weekend_and_holiday_do_nothing_and_stay_quiet(tmp_path) -> None:
    client = FakeHolded(SAT)

    lines, errors = simulate(client, cfg(), tmp_path / "plan.json", hm("06:00"))

    assert client.calls == [] and not errors
    assert len(lines) == 1 and "skipped (weekend)" in lines[0]
    assert client.api == 0


def test_time_off_does_nothing(tmp_path) -> None:
    summary = {"employeeTimeOffs": [{"status": "accepted", "start": "2026-04-06", "end": "2026-04-08"}]}
    client = FakeHolded(summary=summary)

    lines, _ = simulate(client, cfg(), tmp_path / "plan.json", hm("06:00"))

    assert client.calls == [] and "time off" in lines[0]


def test_nothing_due_makes_no_api_calls(tmp_path) -> None:
    client = FakeHolded()
    plan_file = tmp_path / "plan.json"

    simulate(client, cfg(), plan_file, hm("06:00"), hm("06:00"))
    fetched = client.api
    simulate(client, cfg(), plan_file, hm("06:05"), hm("08:25"))

    assert fetched == 1  # only the one timeoff lookup that builds the plan
    assert client.api == 1


def test_manual_clock_in_is_adopted_not_duplicated(tmp_path) -> None:
    client = FakeHolded()
    client.start_running(hm("09:12"))

    _, errors = simulate(client, cfg(), tmp_path / "plan.json", hm("09:15"))

    assert not errors
    assert ("09:15", "in") not in client.calls and all(a != "in" for _, a in client.calls)
    assert client.calls[-1] == ("18:15", "out")  # 9h from the real start, on a 5-min tick
    assert client.worked >= 8 * H + 30


def test_stale_open_tracker_from_yesterday_blocks_and_alerts(tmp_path) -> None:
    client = FakeHolded()
    client.start_running(hm("09:00"), day=TUE - timedelta(days=1))

    _, errors = simulate(client, cfg(), tmp_path / "plan.json", hm("08:30"), hm("08:40"))

    assert client.calls == []
    assert errors and "still open" in errors[0].message


def test_plan_is_fixed_for_the_day_and_survives_restarts(tmp_path) -> None:
    random.seed(7)
    plan_file = tmp_path / "plan.json"
    client = FakeHolded()
    config = cfg(jitter=20)

    simulate(client, config, plan_file, hm("06:00"), hm("06:00"))
    first = plan_file.read_text()
    random.seed(99)  # a re-plan would now give different times
    simulate(client, config, plan_file, hm("06:05"), hm("06:05"))

    assert plan_file.read_text() == first
    assert client.api == 1


def test_stale_or_corrupt_plan_is_rebuilt(tmp_path) -> None:
    plan_file = tmp_path / "plan.json"
    plan_file.write_text("{not json")
    assert load_plan(plan_file) is None

    simulate(FakeHolded(), cfg(), plan_file, hm("06:00"), hm("06:00"))
    rebuilt = load_plan(plan_file)
    assert rebuilt is not None and rebuilt.date == TUE.isoformat()

    next_day = FakeHolded(date(2026, 4, 8))
    simulate(next_day, cfg(), plan_file, hm("06:00"), hm("06:00"))
    replanned = load_plan(plan_file)
    assert replanned is not None and replanned.date == "2026-04-08"


def test_dry_run_acts_on_nothing_and_saves_nothing(tmp_path) -> None:
    client = FakeHolded()
    plan_file = tmp_path / "plan.json"
    client.minute = hm("08:30")

    lines = run_tick(cfg(), plan_file, client, client._now(), dry_run=True)

    assert client.calls == [] and not plan_file.exists()
    assert any(line.startswith("would in") for line in lines)


@pytest.mark.parametrize("seed", range(150))
def test_net_hours_hold_for_any_jitter_and_boot_time(tmp_path, seed) -> None:
    """The guarantee: whatever the jitter and whenever the machine wakes (within
    the limit), a Tue-Thu day never nets less than 8h30."""
    rng = random.Random(seed)
    random.seed(seed)
    client = FakeHolded()
    first = rng.randrange(hm("06:00"), hm("09:40") + 1, 5)  # latest plan is 08:50, limit 90

    _, errors = simulate(client, cfg(jitter=20), tmp_path / "plan.json", first)

    assert not errors
    assert client.tracker is None
    assert client.worked >= 8 * H + 30


@pytest.mark.parametrize("seed", range(50))
def test_friday_net_hours_hold_with_jitter(tmp_path, seed) -> None:
    random.seed(seed)
    client = FakeHolded(FRI)

    _, errors = simulate(client, cfg(jitter=20), tmp_path / "plan.json", hm("06:00"))

    assert not errors and client.worked >= 6 * H + 30


# ---------------------------------------------------------------------------
# CLI wiring: output and exit codes (what a systemd unit sees)
# ---------------------------------------------------------------------------


def _cli(monkeypatch, tmp_path, run_tick_stub):
    cli = importlib.import_module("holded_tt.cli")
    clock = importlib.import_module("holded_tt.commands.clock")
    state = SimpleNamespace(session_store=object(), config=cfg(), config_dir=tmp_path)

    class Client:
        def __enter__(self): return self
        def __exit__(self, *_): pass

    monkeypatch.setattr(cli, "create_app_state", lambda: state)
    monkeypatch.setattr(clock, "HoldedClient", lambda *_: Client())
    monkeypatch.setattr(clock, "run_tick", run_tick_stub)
    return cli


def test_tick_command_prints_timestamped_lines(runner, monkeypatch, tmp_path) -> None:
    seen = {}

    def stub(config, plan_file, client, now, dry_run):
        seen.update(plan_file=plan_file, dry_run=dry_run)
        return ["in"]

    cli = _cli(monkeypatch, tmp_path, stub)

    result = runner.invoke(cli.app, ["clock", "tick", "--dry-run"])

    assert result.exit_code == 0
    assert result.stdout.strip().endswith("in") and result.stdout[:4].isdigit()
    assert seen == {"plan_file": tmp_path / "plan.json", "dry_run": True}


def test_tick_command_exits_2_when_the_tick_fails(runner, monkeypatch, tmp_path) -> None:
    def stub(*_a, **_k):
        raise HoldedCliError(message="Missed today's clock-in.", hint="Clock in by hand.")

    cli = _cli(monkeypatch, tmp_path, stub)

    result = runner.invoke(cli.app, ["clock", "tick"])

    assert result.exit_code == 2
    assert "Missed today's clock-in." in result.output


def test_max_late_config_validation() -> None:
    config_cmd = importlib.import_module("holded_tt.commands.config")

    assert config_cmd._parse_config_value("defaults.max_late", "45") == 45
    with pytest.raises(Exception, match="non-negative"):
        config_cmd._parse_config_value("defaults.max_late", "soon")
