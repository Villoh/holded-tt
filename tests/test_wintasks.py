"""Windows Task Scheduler backend, driven through a fake `schtasks`. Runs on every OS."""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from holded_tt import timers, units, wintasks as w
from holded_tt.errors import HoldedCliError, InputError

EXE = r"C:\Users\me\AppData\Local\Programs\holded-tt\holded-tt.exe"
CET = timezone(timedelta(hours=1))
NS = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"


class Schtasks:
    """Records commands, keeps the XML each /Create was given, and answers queries."""

    def __init__(self, listing="", plan_xml=None, fail_create=False):
        self.calls: list[list[str]] = []
        self.created: dict[str, str] = {}
        self.listing, self.plan_xml, self.fail_create = listing, plan_xml, fail_create

    def __call__(self, command, **_kw):
        self.calls.append(command)
        args = command[1:]
        ok = SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[0] == "/Create":
            if self.fail_create:
                return SimpleNamespace(returncode=1, stdout="", stderr="ERROR: Access is denied.")
            raw = open(args[args.index("/XML") + 1], "rb").read()  # still on disk during the call
            assert raw[:2] in (b"\xff\xfe", b"\xfe\xff")  # UTF-16 with a BOM
            self.created[args[args.index("/TN") + 1]] = raw.decode("utf-16")
            return ok
        if args[:2] == ["/Query", "/FO"]:
            return SimpleNamespace(returncode=0, stdout=self.listing, stderr="")
        if args[0] == "/Query" and "/XML" in args:
            if self.plan_xml is None:
                return SimpleNamespace(returncode=1, stdout="", stderr="ERROR: not found")
            return SimpleNamespace(returncode=0, stdout=self.plan_xml, stderr="")
        return ok

    def verbs(self, verb):
        return [c for c in self.calls if c[1] == verb]


def parse(xml: str) -> ET.Element:
    return ET.fromstring(xml.split("?>", 1)[1])


def node(root: ET.Element, path: str) -> ET.Element:
    """`root.find` that fails with the missing path instead of returning None."""
    found = root.find("/".join(f"{NS}{part}" for part in path.split("/")))
    assert found is not None, f"missing <{path}>"
    return found


def text(root: ET.Element, path: str) -> str:
    return node(root, path).text or ""


def listing(*stamps) -> str:
    return "".join(f'"\\holded-tt\\holded-tt-next-{s}","N/A","Ready"\n' for s in stamps) + '"\\Other\\thing","N/A","Ready"\n'


# ---------------------------------------------------------------------------
# the XML
# ---------------------------------------------------------------------------


def test_plan_task_runs_on_weekdays_at_the_chosen_time_and_at_logon() -> None:
    root = parse(w.plan_xml(EXE, "08:00", datetime(2026, 11, 3)))

    cal = node(root, "Triggers/CalendarTrigger")
    assert text(cal, "StartBoundary") == "2026-11-03T08:00:00"
    days = [d.tag.replace(NS, "") for d in node(cal, "ScheduleByWeek/DaysOfWeek")]
    assert days == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]  # no weekends
    assert root.find(f"{NS}Triggers/{NS}LogonTrigger") is not None  # the login hook


def test_logon_trigger_is_limited_to_this_user(monkeypatch) -> None:
    monkeypatch.setenv("USERDOMAIN", "PC")
    monkeypatch.setenv("USERNAME", "mikel")

    root = parse(w.plan_xml(EXE, "08:00"))

    assert text(root, "Triggers/LogonTrigger/UserId") == "PC\\mikel"


def test_tasks_run_the_scheduled_tick_as_this_user_without_a_stored_password() -> None:
    for xml in (w.plan_xml(EXE, "08:00"), w.next_xml(datetime(2026, 11, 3, 14, 12, 38, tzinfo=CET), EXE)):
        root = parse(xml)
        exec_ = node(root, "Actions/Exec")
        assert text(exec_, "Command") == EXE
        assert text(exec_, "Arguments") == "clock tick --schedule"
        principal = node(root, "Principals/Principal")
        assert text(principal, "LogonType") == "InteractiveToken"
        assert text(principal, "RunLevel") == "LeastPrivilege"  # never elevated


def test_tasks_do_not_rely_on_restart_on_failure() -> None:
    """Measured on a real windows-latest runner: a task whose program exits 2 is NOT restarted
    by RestartOnFailure. The app re-arms its own retry instead (see autoclock.retry_later)."""
    for xml in (w.plan_xml(EXE, "08:00"), w.next_xml(datetime(2026, 11, 3, 14, 12, 38, tzinfo=CET), EXE)):
        root = parse(xml)
        assert root.find(f"{NS}Settings/{NS}RestartOnFailure") is None
        assert text(root, "Settings/StartWhenAvailable") == "true"  # a missed start still runs
    assert w.RETRIES_NATIVELY is False and units.RETRIES_NATIVELY is True


def test_one_shot_task_fires_at_the_exact_second_with_its_offset() -> None:
    root = parse(w.next_xml(datetime(2026, 11, 3, 14, 12, 38, tzinfo=CET), EXE))

    trigger = node(root, "Triggers/TimeTrigger")
    assert text(trigger, "StartBoundary") == "2026-11-03T14:12:38+01:00"
    assert text(trigger, "EndBoundary") == "2026-11-03T15:12:38+01:00"
    assert root.find(f"{NS}Settings/{NS}DeleteExpiredTaskAfter") is not None  # cleans itself up


def test_the_plan_task_never_expires() -> None:
    root = parse(w.plan_xml(EXE, "08:00"))

    assert root.find(f"{NS}Settings/{NS}DeleteExpiredTaskAfter") is None
    assert root.find(f"{NS}Triggers/{NS}CalendarTrigger/{NS}EndBoundary") is None


def test_an_executable_path_with_xml_characters_is_escaped() -> None:
    root = parse(w.plan_xml(r"C:\Tom & Jerry\<x>\holded-tt.exe", "08:00"))

    assert text(root, "Actions/Exec/Command") == r"C:\Tom & Jerry\<x>\holded-tt.exe"


@pytest.mark.parametrize("bad", ["25:00", "8:00", "08:60", "", "0800"])
def test_a_bad_plan_time_is_a_usage_error(bad) -> None:
    with pytest.raises(InputError):
        w.plan_xml(EXE, bad)


def test_task_name_carries_the_utc_time() -> None:
    assert w.next_task_name(datetime(2026, 11, 3, 14, 12, 38, tzinfo=CET)) == "\\holded-tt\\holded-tt-next-20261103T131238"


# ---------------------------------------------------------------------------
# arm_at / disarm / armed_events
# ---------------------------------------------------------------------------


def test_arm_at_registers_the_task_with_force_and_removes_the_temp_file() -> None:
    run = Schtasks()
    when = datetime(2026, 11, 3, 14, 12, 38, tzinfo=CET)

    w.arm_at(when, EXE, run)

    create = run.verbs("/Create")[0]
    assert create[:4] == ["schtasks", "/Create", "/TN", "\\holded-tt\\holded-tt-next-20261103T131238"]
    assert "/F" in create  # the same event twice replaces, never fires twice
    xml_path = create[create.index("/XML") + 1]
    import os
    assert not os.path.exists(xml_path)
    assert "2026-11-03T14:12:38+01:00" in run.created["\\holded-tt\\holded-tt-next-20261103T131238"]


def test_arm_at_failure_is_reported_with_schtasks_output() -> None:
    with pytest.raises(HoldedCliError, match="Could not schedule") as info:
        w.arm_at(datetime(2026, 11, 3, 14, 0, tzinfo=CET), EXE, Schtasks(fail_create=True))

    assert "Access is denied" in info.value.hint and info.value.exit_code == 2  # retried


def test_arm_at_without_schtasks_is_not_retried() -> None:
    def missing(*_a, **_k):
        raise FileNotFoundError

    with pytest.raises(HoldedCliError, match="schtasks not found") as info:
        w.arm_at(datetime(2026, 11, 3, 14, 0, tzinfo=CET), EXE, missing)

    assert info.value.exit_code == 3 and "periodic" in info.value.hint


def test_arm_at_deletes_one_shot_tasks_that_fired_long_ago_and_only_those() -> None:
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%Y%m%dT%H%M%S")
    soon = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%Y%m%dT%H%M%S")
    run = Schtasks(listing(old, soon))

    w.arm_at(datetime.now(timezone.utc) + timedelta(hours=1), EXE, run)

    deleted = [c[c.index("/TN") + 1] for c in run.verbs("/Delete")]
    assert deleted == [f"\\holded-tt\\holded-tt-next-{old}"]


def test_disarm_deletes_every_one_shot_task_and_nothing_else() -> None:
    run = Schtasks(listing("20261103T131238", "20261103T164500"))

    w.disarm(run)

    deleted = [c[c.index("/TN") + 1] for c in run.verbs("/Delete")]
    assert deleted == ["\\holded-tt\\holded-tt-next-20261103T131238", "\\holded-tt\\holded-tt-next-20261103T164500"]
    assert all("/F" in c for c in run.verbs("/Delete"))


def test_disarm_is_quiet_without_a_task_scheduler() -> None:
    def missing(*_a, **_k):
        raise FileNotFoundError

    w.disarm(missing)  # does not raise


def test_armed_events_returns_only_future_tasks_sorted() -> None:
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0)
    sooner = future - timedelta(hours=1)
    past = future - timedelta(hours=5)
    stamp = lambda d: d.strftime("%Y%m%dT%H%M%S")  # noqa: E731

    got = w.armed_events(Schtasks(listing(stamp(future), stamp(past), stamp(sooner))))

    assert got == [sooner, future]  # the past task has fired: it is not "armed"


def test_armed_events_is_unknown_not_empty_when_the_scheduler_cannot_answer() -> None:
    assert w.armed_events(lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="", stderr="x")) is None

    def missing(*_a, **_k):
        raise FileNotFoundError

    assert w.armed_events(missing) is None


# ---------------------------------------------------------------------------
# install / uninstall / next_planning
# ---------------------------------------------------------------------------


def test_install_creates_only_the_plan_task_and_never_runs_it() -> None:
    run = Schtasks()

    out = w.install(EXE, "08:30", run=run)

    assert list(run.created) == [w.PLAN_TASK]
    assert "T08:30:00" in run.created[w.PLAN_TASK]
    assert not run.verbs("/Run")  # a run is a real tick: it could clock you in
    assert any("created task" in line for line in out)


def test_install_dry_run_prints_the_xml_and_touches_nothing() -> None:
    run = Schtasks()

    out = w.install(EXE, "08:00", dry_run=True, run=run)

    assert run.created == {} and not run.verbs("/Create")
    assert "<ScheduleByWeek>" in "\n".join(out)


def test_install_is_idempotent_over_our_own_task() -> None:
    ours = w.plan_xml(EXE, "08:00")

    w.install(EXE, "09:00", run=Schtasks(plan_xml=ours))  # does not raise


def test_install_refuses_to_overwrite_a_foreign_task() -> None:
    foreign = ('<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
               "<RegistrationInfo><Description>mine</Description></RegistrationInfo></Task>")
    run = Schtasks(plan_xml=foreign)

    with pytest.raises(HoldedCliError, match="not generated by holded-tt"):
        w.install(EXE, run=run)

    assert not run.verbs("/Create")


def test_uninstall_removes_the_plan_task_and_the_armed_ones() -> None:
    run = Schtasks(listing("20261103T131238"), plan_xml=w.plan_xml(EXE, "08:00"))

    out = w.uninstall(run)

    deleted = [c[c.index("/TN") + 1] for c in run.verbs("/Delete")]
    assert w.PLAN_TASK in deleted and "\\holded-tt\\holded-tt-next-20261103T131238" in deleted
    assert sum("removed" in line for line in out) == 2


def test_uninstall_leaves_a_foreign_plan_task_alone() -> None:
    foreign = ('<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
               "<RegistrationInfo><Description>mine</Description></RegistrationInfo></Task>")
    run = Schtasks(plan_xml=foreign)

    out = w.uninstall(run)

    assert [c for c in run.verbs("/Delete") if w.PLAN_TASK in c] == []
    assert any("left" in line for line in out)


def test_uninstall_with_nothing_installed_is_a_quiet_success() -> None:
    assert w.uninstall(Schtasks()) == ["nothing to remove"]


@pytest.mark.parametrize(
    "now, expected",
    [
        (datetime(2026, 11, 3, 7, 0), "Tue 2026-11-03 08:00:00"),  # before the time, a weekday
        (datetime(2026, 11, 3, 9, 0), "Wed 2026-11-04 08:00:00"),  # after it: tomorrow
        (datetime(2026, 11, 6, 9, 0), "Mon 2026-11-09 08:00:00"),  # Friday after: skips the weekend
        (datetime(2026, 11, 7, 7, 0), "Mon 2026-11-09 08:00:00"),  # Saturday
    ],
)
def test_next_planning_follows_the_weekday_schedule(now, expected) -> None:
    run = Schtasks(plan_xml=w.plan_xml(EXE, "08:00", datetime(2026, 1, 5)))

    assert w.next_planning(run, now) == expected


def test_next_planning_is_none_when_not_installed() -> None:
    assert w.next_planning(Schtasks()) is None


# ---------------------------------------------------------------------------
# platform selection
# ---------------------------------------------------------------------------


@pytest.mark.real_backend
def test_the_backend_follows_the_platform(monkeypatch) -> None:
    monkeypatch.setattr("sys.platform", "win32")
    assert timers.backend() is w

    monkeypatch.setattr("sys.platform", "linux")
    assert timers.backend() is units

    monkeypatch.setattr("sys.platform", "darwin")
    assert timers.backend() is units  # no macOS backend: it gets the clear "needs systemd" error


def test_timers_forward_to_the_selected_backend(monkeypatch) -> None:
    seen = {}
    fake = SimpleNamespace(
        install=lambda exe, plan_at, dry_run: seen.update(i=(exe, plan_at, dry_run)) or ["ok"],
        uninstall=lambda: ["bye"], disarm=lambda: seen.update(d=True),
        armed_events=lambda: [], next_planning=lambda: "x",
        arm_at=lambda when, exe, run: seen.update(a=(when, exe)),
    )
    monkeypatch.setattr(timers, "backend", lambda: fake)

    assert timers.install("e", "07:00", True) == ["ok"] and seen["i"] == ("e", "07:00", True)
    assert timers.uninstall() == ["bye"] and timers.armed_events() == [] and timers.next_planning() == "x"
    timers.disarm()
    timers.arm_at(datetime(2026, 1, 1, tzinfo=CET), "e")
    assert seen["d"] is True and seen["a"][1] == "e"


def test_executable_accepts_the_windows_launcher(monkeypatch, tmp_path) -> None:
    """pip/uv put `holded-tt.exe` in Scripts; it must be taken as is, not looked up on PATH."""
    autoclock = importlib.import_module("holded_tt.autoclock")
    launcher = tmp_path / "Scripts" / "holded-tt.exe"  # a real path, so os.path agrees on any OS
    monkeypatch.setattr("sys.argv", [str(launcher), "clock", "install"])
    monkeypatch.setattr("shutil.which", lambda _n: pytest.fail("must not search PATH"))

    assert autoclock.executable() == str(launcher)
