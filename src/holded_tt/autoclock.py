"""Unattended real-time clocking, driven by ``holded-tt clock tick``.

A timer runs ``tick`` every few minutes. It keeps one plan per day (jittered
times, see schedule.py) in a JSON file and advances it against the *real*
tracker state in Holded. That makes it safe to run often, to miss runs and to
resume after a reboot: every step checks what Holded says before acting.
"""

from __future__ import annotations

import contextlib
import json
import os
import random
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from holded_tt.config import AppConfig
from holded_tt.errors import HoldedCliError
from holded_tt.exit_codes import EXIT_NO_RETRY
from holded_tt.units import RETRY_PROPERTIES
from holded_tt.schedule import (
    day_schedule,
    fmt_minutes,
    hhmm_to_minutes,
    jitter_schedule,
)
from holded_tt.timeoff import extract_employee_absences, extract_workplace_holidays

_NEVER = 10**6
SKIPPED_BY_YOU = "skipped by you"


@dataclass
class Plan:
    date: str
    status: str = "active"  # active | skipped | missed
    reason: str = ""
    in_at: int = 0  # minutes since local midnight
    out_at: int = 0
    duration: int = 0  # planned gross minutes (out - in); keeps net hours when in is late
    pauses: list[list[int]] = field(default_factory=list)
    done: list[str] = field(default_factory=list)  # "in", "p0", "r0", ..., "out"


@dataclass
class Tracker:
    state: str  # none | running | paused
    start: int = 0  # local minutes, only meaningful when state != "none"


def _covers(absence: dict[str, Any], day: date) -> bool:
    try:
        start = date.fromisoformat(str(absence["start"])[:10])
        end = absence.get("end")
        last = date.fromisoformat(str(end)[:10]) if end else start
    except (KeyError, ValueError):
        return False
    return start <= day <= last


def build_plan(
    config: AppConfig,
    day: date,
    fetch_summary: Callable[[int], dict],
    skips: frozenset[date] = frozenset(),
) -> Plan:
    """Plan ``day``: skip days you ruled out, weekends, holidays and accepted time off."""
    iso = day.isoformat()
    if day in skips:  # checked first: no reason to ask Holded about a day you are not working
        return Plan(iso, "skipped", SKIPPED_BY_YOU)
    if day.weekday() >= 5:
        return Plan(iso, "skipped", "weekend")
    summary = fetch_summary(day.year)
    holidays = extract_workplace_holidays(summary, day.year)
    if day in holidays:
        return Plan(iso, "skipped", f"holiday {holidays[day]}".strip())
    for absence in extract_employee_absences(summary):
        if absence.get("status") == "accepted" and _covers(absence, day):
            return Plan(iso, "skipped", "time off")

    sched = day_schedule(config, day)
    if config.jitter:
        sched = jitter_schedule(*sched, config.jitter)
    start, end, pauses = sched
    in_at, out_at = hhmm_to_minutes(start), hhmm_to_minutes(end)
    return Plan(
        iso,
        in_at=in_at,
        out_at=out_at,
        duration=out_at - in_at,
        pauses=[[hhmm_to_minutes(t) for t in p.split("-")] for p in pauses],
    )


def _next_due(plan: Plan) -> int:
    """Earliest planned time of a pending event, or _NEVER."""
    if plan.status != "active" or "out" in plan.done:
        return _NEVER
    times = [] if "in" in plan.done else [plan.in_at]
    for i, (a, b) in enumerate(plan.pauses):
        times += [a] if f"p{i}" not in plan.done else []
        times += [b] if f"r{i}" not in plan.done else []
    return min(times + [plan.out_at])


def next_event(plan: Plan) -> int | None:
    """Minute of the next pending event, or None when the plan has nothing left."""
    due = _next_due(plan)
    return None if due == _NEVER else due


def executable() -> str:
    """Path the scheduled timers should run: how we were started, else PATH."""
    argv0 = os.path.abspath(sys.argv[0])
    if os.path.basename(argv0) == "holded-tt":
        return argv0
    found = shutil.which("holded-tt")
    if found is None:
        raise HoldedCliError(
            message="Cannot find the holded-tt executable to schedule.",
            hint="Put holded-tt on PATH, or start it by its full path.",
            exit_code=EXIT_NO_RETRY,
        )
    return found


def arm_next(
    plan: Plan, now: datetime, exe: str, run: Callable[..., Any] = subprocess.run
) -> datetime | None:
    """Arm a one-shot systemd timer that runs `clock tick` at the next planned event.

    Nothing stays running in between. The seconds are random but fixed per event, so
    arming the same event twice (a retry) reuses one unit instead of firing twice.
    """
    minute = next_event(plan)
    if minute is None:
        return None
    second = random.Random(f"{plan.date}-{minute}").randrange(60)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    when = max(midnight + timedelta(minutes=minute, seconds=second), now + timedelta(seconds=5))
    utc = when.astimezone(timezone.utc)
    command = [
        "systemd-run", "--user", "--quiet", "--collect",
        f"--unit=holded-tt-next-{utc:%Y%m%dT%H%M%S}",
        f"--on-calendar={utc:%Y-%m-%d %H:%M:%S} UTC",
        "--timer-property=AccuracySec=1s",
        *[f"--property={p}" for p in RETRY_PROPERTIES],
        "--", exe, "clock", "tick", "--schedule",
    ]
    try:
        done = run(command, capture_output=True, text=True)
    except FileNotFoundError:
        raise HoldedCliError(
            message="systemd-run not found: --schedule needs systemd (Linux).",
            hint="Run `holded-tt clock tick` from a periodic timer instead, without --schedule.",
            exit_code=EXIT_NO_RETRY,
        ) from None
    if done.returncode and "already" not in done.stderr:  # "already loaded" = armed before
        raise HoldedCliError(
            message="Could not schedule the next clock event.",
            hint=done.stderr.strip() or f"systemd-run exited with {done.returncode}.",
        )
    return when


def step(plan: Plan, now: int, tracker: Tracker, max_late: int) -> list[str]:
    """Advance ``plan`` in place and return the actions to run, in order.

    Every decision looks at the real tracker state, so repeating a step after a
    crash is harmless. A late clock-in pushes the clock-out so net hours hold.
    """
    if plan.status != "active" or "out" in plan.done:
        return []
    acts: list[str] = []
    state = tracker.state

    if "in" not in plan.done:
        if now < plan.in_at:
            return acts
        if state != "none":  # already clocked in (by hand or by a previous run)
            real = tracker.start
        elif now - plan.in_at > max_late:
            plan.status = "missed"
            plan.reason = (
                f"clock-in was planned for {fmt_minutes(plan.in_at)} but it is "
                f"{fmt_minutes(now)} (limit: {max_late} min late)"
            )
            return acts
        else:
            acts.append("in")
            state, real = "running", now
        plan.done.append("in")
        plan.out_at = max(plan.out_at, real + plan.duration)

    for i, (a, b) in enumerate(plan.pauses):
        p, r = f"p{i}", f"r{i}"
        if now >= a and p not in plan.done:
            if state == "running" and now < b:  # window already over: skip it
                acts.append("pause")
                state = "paused"
            plan.done.append(p)
        if now >= b and r not in plan.done:
            if state == "paused":
                acts.append("resume")
                state = "running"
                plan.out_at += now - b  # a longer pause must not cost net hours
            plan.done.append(r)

    if now >= plan.out_at:
        if state == "paused":
            acts.append("resume")
            state = "running"
        if state != "none":  # nothing to stop if it was closed by hand
            acts.append("out")
        plan.done.append("out")
    return acts


def load_skips(path: Path) -> frozenset[date]:
    """Days you asked not to be clocked. Missing or corrupt file means none."""
    try:
        raw = json.loads(path.read_text())["days"]
    except (OSError, ValueError, KeyError, TypeError):
        return frozenset()
    days: set[date] = set()
    for item in raw if isinstance(raw, list) else []:
        with contextlib.suppress(TypeError, ValueError):  # one bad entry must not drop the rest
            days.add(date.fromisoformat(item))
    return frozenset(days)


def save_skips(path: Path, days: Iterable[date], today: date) -> None:
    """Store ``days``, dropping the ones already in the past."""
    path.write_text(json.dumps({"days": sorted(d.isoformat() for d in days if d >= today)}))


def skip_plan(plan_file: Path, today: date) -> bool:
    """Cancel what is left of today's plan. True if a plan was there to cancel."""
    plan = load_plan(plan_file)
    if plan is None or plan.date != today.isoformat():
        return False  # nothing planned yet: the skip list is enough
    plan.status, plan.reason = "skipped", SKIPPED_BY_YOU
    save_plan(plan_file, plan)
    return True


def unskip_plan(plan_file: Path, today: date) -> bool:
    """Forget today's plan if it was skipped by you, so the next tick plans it afresh."""
    plan = load_plan(plan_file)
    if plan is None or plan.date != today.isoformat() or plan.reason != SKIPPED_BY_YOU:
        return False
    plan_file.unlink(missing_ok=True)
    return True


def load_plan(path: Path) -> Plan | None:
    try:
        return Plan(**json.loads(path.read_text()))
    except (OSError, ValueError, TypeError):
        return None  # missing or corrupt: rebuilt, and step() re-syncs with Holded


def save_plan(path: Path, plan: Plan) -> None:
    path.write_text(json.dumps(asdict(plan)))


def _tracker_view(raw: dict[str, Any] | None, now: datetime) -> Tracker:
    if not raw:
        return Tracker("none")
    state = "paused" if raw.get("paused") else "running" if raw.get("running") else "none"
    if state == "none":
        return Tracker("none")
    start = datetime.fromisoformat(raw["start"]).astimezone(now.tzinfo)
    if start.date() != now.date():
        raise HoldedCliError(
            message=f"A tracker from {start.date()} is still open.",
            hint="Close it with `holded-tt clock out`; automatic clocking is paused until then.",
        )
    return Tracker(state, start.hour * 60 + start.minute)


def _run(client: Any, action: str) -> None:
    if action == "in":
        client.clock_in()
        return
    tracker = client.get_current_tracker()
    if tracker is None:
        raise HoldedCliError(
            message=f"Cannot {action}: no active tracker.",
            hint="Run `holded-tt clock status` to inspect it.",
        )
    {
        "pause": client.pause_tracker,
        "resume": client.resume_tracker,
        "out": client.clock_out,
    }[action](tracker["id"])


def run_tick(
    config: AppConfig,
    plan_file: Path,
    client: Any,
    now: datetime,
    dry_run: bool = False,
    skips: frozenset[date] = frozenset(),
) -> list[str]:
    """Advance today's plan once. Returns log lines; raises HoldedCliError on failure.

    Quiet by default: with nothing due it prints nothing and makes no API call.
    """
    out: list[str] = []
    plan = load_plan(plan_file)
    if plan is None or plan.date != now.date().isoformat():
        plan = build_plan(config, now.date(), client.get_timeoff_summary, skips)
        if not dry_run:
            save_plan(plan_file, plan)  # the day's jitter is fixed from here on
        if plan.status == "skipped":
            out.append(f"{plan.date}: skipped ({plan.reason})")
        else:
            out.append(f"{plan.date}: plan {_describe(plan)}")
    elif now.date() in skips and plan.status == "active":
        # Skipped after the plan was made, e.g. a stale timer fired: honour it anyway.
        plan.status, plan.reason = "skipped", SKIPPED_BY_YOU
        if not dry_run:
            save_plan(plan_file, plan)
        out.append(f"{plan.date}: skipped ({plan.reason})")

    now_min = now.hour * 60 + now.minute
    if _next_due(plan) > now_min:
        return out

    acts = step(plan, now_min, _tracker_view(client.get_current_tracker(), now), config.max_late)
    for act in acts:
        out.append(f"{'would ' if dry_run else ''}{act}")
        if not dry_run:
            _run(client, act)
    if dry_run:
        if plan.status == "missed":
            out.append(f"missed: {plan.reason}")
        return out

    save_plan(plan_file, plan)
    if plan.status == "missed":
        raise HoldedCliError(
            message=f"Missed today's clock-in: {plan.reason}.",
            hint="Clock in by hand with `holded-tt clock in`; the rest of today's plan is cancelled.",
            exit_code=EXIT_NO_RETRY,
        )
    return out


def _describe(plan: Plan) -> str:
    pauses = ", ".join(f"{fmt_minutes(a)}-{fmt_minutes(b)}" for a, b in plan.pauses)
    return f"{fmt_minutes(plan.in_at)} -> {fmt_minutes(plan.out_at)}" + (
        f", pause {pauses}" if pauses else ""
    )
