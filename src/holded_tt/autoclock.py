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
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from holded_tt.config import AppConfig
from holded_tt.errors import HoldedCliError
from holded_tt.exit_codes import EXIT_NO_RETRY
from holded_tt.units import RETRY_ATTEMPTS, RETRY_SECONDS
from holded_tt import timers
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
        sched = jitter_schedule(*sched, config.jitter, config.max_extra)
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


NIX_STORE = "/nix/store/"
NIX_WRAPPED = ".holded-tt-wrapped"


def _stable_alias(target: str) -> str | None:
    """A PATH entry named holded-tt, outside the Nix store, that is the same program."""
    real = os.path.realpath(target)
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(directory, "holded-tt")
        if (
            directory
            and not candidate.startswith(NIX_STORE)
            and os.path.isfile(candidate)
            and os.path.realpath(candidate) == real  # same file, so it runs just as well
        ):
            return candidate
    return None


def executable() -> str:
    """Path the scheduled timers should run: how we were started, else PATH.

    Under Nix the program runs through a wrapper: Python sees `.holded-tt-wrapped` as
    its script and the wrapper puts its own /nix/store/.../bin first on PATH, so both
    point into the store, which changes on every rebuild and is garbage-collected.
    The rest of PATH is untouched, so look there for the same program under a stable
    name (e.g. /etc/profiles/per-user/<user>/bin/holded-tt).
    """
    argv0 = os.path.abspath(sys.argv[0])
    if os.path.basename(argv0) == NIX_WRAPPED:
        argv0 = os.path.join(os.path.dirname(argv0), "holded-tt")
    if os.path.basename(argv0) in ("holded-tt", "holded-tt.exe"):
        if argv0.startswith(NIX_STORE):
            return _stable_alias(argv0) or argv0
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
    """Arm a one-shot timer (systemd or Windows Task Scheduler) for the next planned event.

    Nothing stays running in between. The seconds are random but fixed per event, so
    arming the same event twice (a retry) reuses one unit instead of firing twice.
    """
    minute = next_event(plan)
    if minute is None:
        return None
    second = random.Random(f"{plan.date}-{minute}").randrange(60)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    when = max(midnight + timedelta(minutes=minute, seconds=second), now + timedelta(seconds=5))
    timers.arm_at(when, exe, run=run)
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
        plan.out_at = real + plan.duration  # same length from the real start, so net hours hold

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


def plan_overview(
    plan: Plan | None,
    today: date,
    skips: frozenset[date],
    armed: list[datetime] | None,
    tz: Any,
    next_plan_run: str | None = None,
) -> list[str]:
    """Human-readable view of today's plan. Read-only; ``armed`` None means "unknown"."""
    out: list[str] = []
    if plan is None or plan.date != today.isoformat():
        out.append(f"{today:%A %Y-%m-%d}  no plan yet")
        out.append(
            "  it is made by the daily timer or the first run today"
            + (f" (last plan: {plan.date})" if plan else "")
        )
    elif plan.status != "active":
        out.append(f"{today:%A %Y-%m-%d}  {plan.status}: {plan.reason}")
    else:
        out.append(f"{today:%A %Y-%m-%d}  active")
        pending_at = _next_due(plan)
        todays_armed = [a.astimezone(tz) for a in armed or [] if a.astimezone(tz).date() == today]
        # out_at = real clock-in + duration until a late resume pushes it back, after which
        # the real clock-in can no longer be recovered from the plan.
        resumed = any(k.startswith("r") for k in plan.done)
        real_in = plan.out_at - plan.duration if "in" in plan.done and not resumed else None
        events = [("in", "in", plan.in_at)]
        for i, (a, b) in enumerate(plan.pauses):
            events += [(f"p{i}", "pause", a), (f"r{i}", "resume", b)]
        events.append(("out", "out", plan.out_at))
        shown_next = False
        for key, label, minute in events:
            if key in plan.done:
                note = "done"
                if key == "in" and real_in is not None and real_in != minute:
                    note += f"  (actual {fmt_minutes(real_in)})"
            elif minute == pending_at and not shown_next:
                shown_next = True
                note = "next"
                if todays_armed:
                    note += f"  armed for {todays_armed[0]:%H:%M:%S}"
            else:
                note = "pending"
            out.append(f"  {label:<7}{fmt_minutes(minute)}  {note}")
        paused = sum(b - a for a, b in plan.pauses)
        net = plan.duration - paused
        out.append(f"net planned: {net // 60}h{net % 60:02d}  ({fmt_minutes(real_in if real_in is not None else plan.in_at)} -> {fmt_minutes(plan.out_at)})")
        if shown_next and armed is not None and not todays_armed:
            out.append(
                "warning: nothing is armed for the next event, so it will not happen "
                "until the next planning run. Run `holded-tt clock tick --schedule` to re-arm."
            )
    if next_plan_run:
        out.append(f"next planning: {next_plan_run}")
    upcoming = sorted(d.isoformat() for d in skips if d >= today)
    if upcoming:
        out.append("skipped days: " + ", ".join(upcoming[:10]) + (" ..." if len(upcoming) > 10 else ""))
    return out


def note_failure(path: Path, today: date) -> int:
    """Count a failed scheduled run for today and return how many there have been."""
    attempts = 0
    try:
        data = json.loads(path.read_text())
        if data["date"] == today.isoformat():
            attempts = int(data["attempts"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    attempts += 1
    path.write_text(json.dumps({"date": today.isoformat(), "attempts": attempts}))
    return attempts


def clear_failures(path: Path) -> None:
    path.unlink(missing_ok=True)


def retry_later(path: Path, now: datetime, exe: str) -> str:
    """After a failed scheduled run, arm a retry in RETRY_SECONDS. Returns what to tell the user.

    For schedulers that do not retry by themselves. Gives up after RETRY_ATTEMPTS failures in
    a day, like the systemd start limit; the next planning run starts afresh.
    """
    attempts = note_failure(path, now.date())
    if attempts > RETRY_ATTEMPTS:
        return f"giving up after {RETRY_ATTEMPTS} failed attempts today"
    try:
        timers.arm_at(now + timedelta(seconds=RETRY_SECONDS), exe)
    except HoldedCliError as error:
        return f"could not arm a retry: {error.message}"
    return f"retrying in {RETRY_SECONDS // 60} min (attempt {attempts} of {RETRY_ATTEMPTS})"
