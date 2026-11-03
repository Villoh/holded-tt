"""Day-schedule helpers shared by `track` (bulk) and `clock tick` (real time)."""

from __future__ import annotations

import random
from datetime import date

from holded_tt.config import WEEKDAYS, AppConfig


def hhmm_to_minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def fmt_minutes(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def day_schedule(
    config: AppConfig,
    day: date,
    start: str | None = None,
    end: str | None = None,
    pauses: list[str] | None = None,
) -> tuple[str, str, tuple[str, ...]]:
    """Resolve start/end/pauses for ``day``: explicit args > weekday override > defaults."""
    override = config.days.get(WEEKDAYS[day.weekday()], {})
    chosen = pauses if pauses is not None else override.get("pause", config.pause)
    return (
        str(start or override.get("start") or config.start),
        str(end or override.get("end") or config.end),
        tuple(chosen),
    )


def jitter_schedule(
    start: str, end: str, pauses: tuple[str, ...], max_minutes: int, max_extra: int
) -> tuple[str, str, tuple[str, ...]]:
    """Randomise a day: start +-``max_minutes``, plus 0..``max_extra`` extra minutes worked.

    The day keeps its configured length and gains a single random ``extra`` (never
    negative), so net hours land between the configured ones and those plus
    ``max_extra``. Pauses shift +-``max_minutes`` as a block, kept inside the day,
    with their length unchanged.
    """
    s, e = hhmm_to_minutes(start), hhmm_to_minutes(end)
    last = 23 * 60 + 59
    length = e - s + random.randint(0, max(0, min(max_extra, last - (e - s))))  # must fit before 23:59
    new_start = max(min(s + random.randint(-max_minutes, max_minutes), last - length), 0)
    new_end = new_start + length
    windows = [tuple(map(hhmm_to_minutes, p.split("-"))) for p in pauses]
    lo = max(-max_minutes, new_start - min((a for a, _ in windows), default=new_start))
    hi = min(max_minutes, new_end - max((b for _, b in windows), default=new_end))
    shift = random.randint(lo, hi) if lo <= hi else 0
    return (
        fmt_minutes(new_start),
        fmt_minutes(new_end),
        tuple(f"{fmt_minutes(a + shift)}-{fmt_minutes(b + shift)}" for a, b in windows),
    )
