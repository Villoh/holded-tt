"""The Windows backend against the REAL Task Scheduler (schtasks).

Skipped everywhere except where HOLDED_TT_WINDOWS_TASKS=1 on Windows: the CI sets it on
`windows-latest`, which is the only Windows machine this project has. Nothing here runs a
tick, so nothing is ever clocked. Every task is removed again, even if a step fails.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from holded_tt import wintasks as w

pytestmark = [
    pytest.mark.windows_tasks,
    pytest.mark.skipif(
        sys.platform != "win32" or os.environ.get("HOLDED_TT_WINDOWS_TASKS") != "1",
        reason="needs Windows and HOLDED_TT_WINDOWS_TASKS=1",
    ),
]

EXE = sys.executable  # any real file: the tasks are created, never run


@pytest.fixture()
def clean():
    def wipe():
        w.disarm()
        subprocess.run(["schtasks", "/Delete", "/TN", w.PLAN_TASK, "/F"], capture_output=True, text=True)

    wipe()
    yield
    wipe()


def exists(name: str) -> bool:
    done = subprocess.run(["schtasks", "/Query", "/TN", name], capture_output=True, text=True)
    return done.returncode == 0


def test_install_creates_a_task_the_scheduler_accepts_and_uninstall_removes_it(clean) -> None:
    lines = w.install(EXE, "08:00")

    assert exists(w.PLAN_TASK), lines
    xml = subprocess.run(["schtasks", "/Query", "/TN", w.PLAN_TASK, "/XML"], capture_output=True, text=True).stdout
    assert "clock tick --schedule" in xml and "LogonTrigger" in xml and w.MARKER in xml

    w.uninstall()

    assert not exists(w.PLAN_TASK)


def test_install_twice_replaces_instead_of_failing(clean) -> None:
    w.install(EXE, "08:00")
    w.install(EXE, "09:30")

    assert "T09:30:00" in subprocess.run(
        ["schtasks", "/Query", "/TN", w.PLAN_TASK, "/XML"], capture_output=True, text=True
    ).stdout


def test_next_planning_is_computed_from_the_real_task(clean) -> None:
    w.install(EXE, "08:00")

    got = w.next_planning()

    assert got is not None and got.endswith("08:00:00")
    assert datetime.strptime(got[4:], "%Y-%m-%d %H:%M:%S") > datetime.now()
    assert got[:3] in ("Mon", "Tue", "Wed", "Thu", "Fri")


def test_arm_at_creates_a_one_shot_task_that_shows_up_as_armed(clean) -> None:
    when = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0)

    w.arm_at(when, EXE)

    assert exists(w.next_task_name(when))
    assert when in (w.armed_events() or [])


def test_arming_the_same_event_twice_leaves_one_task(clean) -> None:
    when = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0)

    w.arm_at(when, EXE)
    w.arm_at(when, EXE)

    assert (w.armed_events() or []).count(when) == 1


def test_disarm_removes_the_one_shot_tasks_but_not_the_plan_task(clean) -> None:
    w.install(EXE, "08:00")
    w.arm_at((datetime.now(timezone.utc) + timedelta(hours=3)).replace(microsecond=0), EXE)

    w.disarm()

    assert w.armed_events() == [] and exists(w.PLAN_TASK)


def test_dry_run_creates_nothing(clean) -> None:
    w.install(EXE, "08:00", dry_run=True)

    assert not exists(w.PLAN_TASK)


# ---------------------------------------------------------------------------
# Does a task really fire, and does it really retry? These wait for the scheduler.
# ---------------------------------------------------------------------------


def _wait_for(predicate, seconds: int, step: float = 3.0) -> bool:
    import time

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


def _diagnose(name: str) -> str:
    done = subprocess.run(["schtasks", "/Query", "/TN", name, "/V", "/FO", "LIST"], capture_output=True, text=True)
    return (done.stdout or done.stderr)[-1500:]


def test_a_one_shot_task_fires_at_its_time_and_runs_the_executable(clean, tmp_path) -> None:
    marker = tmp_path / "fired.txt"
    script = tmp_path / "fire.cmd"
    script.write_text(f'@echo off\r\necho %TIME%>> "{marker}"\r\nexit /b 0\r\n')
    when = (datetime.now(timezone.utc) + timedelta(seconds=45)).replace(microsecond=0)

    w.arm_at(when, str(script))

    fired = _wait_for(marker.exists, 150)
    assert fired, "the task never ran:\n" + _diagnose(w.next_task_name(when))
    assert marker.read_text().strip()


def test_a_failing_task_is_retried_by_the_scheduler(clean, tmp_path) -> None:
    """Exit code 2 must make Task Scheduler restart the task; the second run succeeds."""
    marker = tmp_path / "runs.txt"
    script = tmp_path / "flaky.cmd"
    script.write_text(
        "@echo off\r\n"
        f'echo x>> "{marker}"\r\n'
        f'for /f %%i in (\'type "{marker}" ^| find /c /v ""\') do set n=%%i\r\n'
        "if %n% LSS 2 exit /b 2\r\n"
        "exit /b 0\r\n"
    )
    when = (datetime.now(timezone.utc) + timedelta(seconds=45)).replace(microsecond=0)

    w.arm_at(when, str(script))

    def runs() -> int:
        return len(marker.read_text().split()) if marker.exists() else 0

    assert _wait_for(lambda: runs() >= 2, 330, step=5), (
        f"ran {runs()} time(s), expected a retry after the failure:\n" + _diagnose(w.next_task_name(when))
    )
