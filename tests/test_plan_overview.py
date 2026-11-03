"""Tests for `clock plan`: the read-only overview and the systemd lookups behind it."""

from __future__ import annotations

import importlib
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from holded_tt import units
from holded_tt.autoclock import Plan, plan_overview, save_plan, save_skips

TODAY = date(2026, 11, 3)  # a Tuesday
CET = timezone(timedelta(hours=1))
H = 60


def plan(**kw) -> Plan:
    base = dict(date="2026-11-03", in_at=493, out_at=1053, duration=550, pauses=[[852, 882]])
    return Plan(**{**base, **kw})


def armed_at(hour: int, minute: int, second: int) -> datetime:
    """An armed timer, as systemd reports it: UTC."""
    return datetime(2026, 11, 3, hour - 1, minute, second, tzinfo=timezone.utc)


def overview(p, armed=(), skips=frozenset(), next_run=None, today=TODAY):
    return plan_overview(p, today, skips, list(armed) if armed is not None else None, CET, next_run)


def text(lines) -> str:
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# plan_overview
# ---------------------------------------------------------------------------


def test_active_plan_lists_every_event_with_its_state() -> None:
    out = overview(plan(done=["in"]), [armed_at(14, 12, 38)])

    assert out[0].endswith("2026-11-03  active")
    assert "in     08:13  done" in out[1]
    assert "pause  14:12  next  armed for 14:12:38" in out[2]
    assert "resume 14:42  pending" in out[3]
    assert "out    17:33  pending" in out[4]


def test_the_planned_net_is_the_length_minus_the_pauses() -> None:
    out = overview(plan(done=["in"]), [armed_at(14, 12, 38)])

    assert any(line.startswith("net planned: 8h40") for line in out)  # 550 gross - 30 pause = 520


def test_the_real_clock_in_is_shown_when_it_differs_from_the_plan() -> None:
    # clocked in at 08:23 (503) instead of 08:13: out = 503 + 550 = 1053
    out = overview(plan(done=["in"]), [armed_at(14, 12, 38)])

    assert "done  (actual 08:23)" in text(out)
    assert "(08:23 -> 17:33)" in text(out)


def test_the_real_clock_in_is_not_guessed_after_a_resume() -> None:
    """A late resume pushes out_at back, so out_at - duration no longer gives the clock-in."""
    out = overview(plan(done=["in", "p0", "r0"], out_at=1060), [armed_at(17, 33, 0)])

    assert "actual" not in text(out)
    assert "(08:13 -> 17:40)" in text(out)


def test_only_the_first_pending_event_is_next_and_carries_the_armed_time() -> None:
    out = overview(plan(done=["in", "p0"]), [armed_at(14, 42, 7)])

    assert "resume 14:42  next  armed for 14:42:07" in text(out)
    assert text(out).count("next") == 1 and "out    17:33  pending" in text(out)


def test_a_plan_with_nothing_left_has_no_next_and_no_warning() -> None:
    out = overview(plan(done=["in", "p0", "r0", "out"]), [])

    assert "next " not in text(out).replace("next planning", "") and "warning" not in text(out)


def test_warns_when_a_pending_event_has_nothing_armed() -> None:
    out = overview(plan(done=["in"]), [])

    assert "warning: nothing is armed" in text(out) and "clock tick --schedule" in text(out)


def test_no_warning_when_systemd_cannot_be_asked() -> None:
    """None means unknown (no systemctl): do not claim the chain is broken."""
    out = overview(plan(done=["in"]), None)

    assert "warning" not in text(out) and "armed for" not in text(out)


def test_an_armed_timer_for_another_day_does_not_count_as_armed_today() -> None:
    tomorrow = datetime(2026, 11, 4, 7, 12, 0, tzinfo=timezone.utc)

    assert "warning: nothing is armed" in text(overview(plan(done=["in"]), [tomorrow]))


def test_armed_times_are_shown_in_the_configured_zone_not_utc() -> None:
    out = overview(plan(done=["in"]), [datetime(2026, 11, 3, 13, 12, 38, tzinfo=timezone.utc)])

    assert "armed for 14:12:38" in text(out)  # 13:12:38 UTC is 14:12:38 in CET


@pytest.mark.parametrize("status, reason", [("skipped", "holiday Todos los Santos"), ("skipped", "weekend"),
                                            ("missed", "clock-in was planned for 08:13 but it is 11:00")])
def test_inactive_plans_show_why_and_no_events(status, reason) -> None:
    out = overview(Plan("2026-11-03", status, reason))

    assert out[0].endswith(f"{status}: {reason}") and len(out) == 1


def test_no_plan_for_today_says_so_and_mentions_a_stale_one() -> None:
    assert "no plan yet" in overview(None)[0]

    stale = overview(Plan("2026-11-02", "skipped", "holiday"))
    assert "no plan yet" in stale[0] and "last plan: 2026-11-02" in text(stale)


def test_next_planning_and_future_skips_are_listed_and_past_skips_are_not() -> None:
    skips = frozenset({date(2026, 11, 2), date(2026, 11, 5), date(2026, 11, 6)})

    out = overview(plan(done=["in"]), [armed_at(14, 12, 38)], skips, "Wed 2026-11-04 08:00:00 CET")

    assert "next planning: Wed 2026-11-04 08:00:00 CET" in out
    assert "skipped days: 2026-11-05, 2026-11-06" in out


def test_it_does_not_modify_the_plan() -> None:
    p = plan(done=["in"])
    before = (p.status, list(p.done), p.out_at)

    overview(p, [])

    assert (p.status, list(p.done), p.out_at) == before


# ---------------------------------------------------------------------------
# units.armed_events / units.next_planning
# ---------------------------------------------------------------------------


class Run:
    def __init__(self, stdout="", returncode=0):
        self.calls = []
        self.result = SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)

    def __call__(self, command, **_kw):
        self.calls.append(command)
        return self.result


@pytest.fixture()
def has_systemctl(monkeypatch):
    real = units.shutil.which
    monkeypatch.setattr(units.shutil, "which", lambda n: "/usr/bin/systemctl" if n == "systemctl" else real(n))


def test_armed_events_reads_the_time_from_the_unit_names_sorted(has_systemctl) -> None:
    listing = (
        "holded-tt-next-20261103T171000.timer loaded active waiting [systemd-run] x\n"
        "holded-tt-next-20261103T131238.timer loaded active waiting [systemd-run] x\n"
    )
    run = Run(listing)

    got = units.armed_events(run)

    assert got == [datetime(2026, 11, 3, 13, 12, 38, tzinfo=timezone.utc),
                   datetime(2026, 11, 3, 17, 10, 0, tzinfo=timezone.utc)]
    assert "--user" in run.calls[0] and "holded-tt-next-*.timer" in run.calls[0]


def test_armed_events_is_an_empty_list_when_nothing_is_armed(has_systemctl) -> None:
    assert units.armed_events(Run("")) == []


def test_armed_events_ignores_lines_that_are_not_our_timers(has_systemctl) -> None:
    assert units.armed_events(Run("other.timer loaded active waiting x\nholded-tt-next-garbage.timer\n")) == []


def test_armed_events_is_unknown_not_empty_when_systemd_cannot_answer(monkeypatch, has_systemctl) -> None:
    assert units.armed_events(Run("", returncode=1)) is None

    monkeypatch.setattr(units.shutil, "which", lambda _n: None)
    assert units.armed_events(Run()) is None


def test_next_planning_returns_what_systemd_prints(has_systemctl) -> None:
    assert units.next_planning(Run("Wed 2026-11-04 08:00:00 CET\n")) == "Wed 2026-11-04 08:00:00 CET"


def test_next_planning_is_none_when_not_installed_or_unknown(monkeypatch, has_systemctl) -> None:
    assert units.next_planning(Run("\n")) is None  # unit not loaded: empty value
    assert units.next_planning(Run("x", returncode=1)) is None
    monkeypatch.setattr(units.shutil, "which", lambda _n: None)
    assert units.next_planning(Run()) is None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.fixture()
def cli(monkeypatch, tmp_path):
    cli_module = importlib.import_module("holded_tt.cli")
    clock = importlib.import_module("holded_tt.commands.clock")
    from holded_tt.config import AppConfig

    state = SimpleNamespace(config=AppConfig(timezone="UTC"), config_dir=tmp_path, session_store=object())
    monkeypatch.setattr(cli_module, "create_app_state", lambda: state)
    monkeypatch.setattr(clock, "_local_today", lambda _s: TODAY)
    monkeypatch.setattr(clock.timers, "armed_events", lambda *_a, **_k: [armed_at(14, 12, 38)])
    monkeypatch.setattr(clock.timers, "next_planning", lambda *_a, **_k: "Wed 2026-11-04 08:00:00 CET")
    return cli_module


def test_plan_command_prints_the_overview_from_the_files(runner, cli, tmp_path) -> None:
    save_plan(tmp_path / "plan.json", plan(done=["in"]))
    save_skips(tmp_path / "skips.json", [date(2026, 11, 5)], TODAY)

    result = runner.invoke(cli.app, ["clock", "plan"])

    assert result.exit_code == 0, result.output
    for expected in ("2026-11-03  active", "pause  14:12  next", "net planned: 8h40",
                     "next planning: Wed 2026-11-04", "skipped days: 2026-11-05"):
        assert expected in result.stdout


def test_plan_command_without_any_file_says_there_is_no_plan(runner, cli) -> None:
    result = runner.invoke(cli.app, ["clock", "plan"])

    assert result.exit_code == 0 and "no plan yet" in result.stdout


def test_plan_command_is_read_only(runner, cli, tmp_path, monkeypatch) -> None:
    clock = importlib.import_module("holded_tt.commands.clock")
    save_plan(tmp_path / "plan.json", plan(done=["in"]))
    before = (tmp_path / "plan.json").read_text()
    monkeypatch.setattr(clock, "HoldedClient", lambda *_: pytest.fail("must not call Holded"))
    monkeypatch.setattr(clock.timers, "disarm", lambda *_a, **_k: pytest.fail("must not stop timers"))

    result = runner.invoke(cli.app, ["clock", "plan"])

    assert result.exit_code == 0
    assert (tmp_path / "plan.json").read_text() == before and not (tmp_path / "skips.json").exists()
