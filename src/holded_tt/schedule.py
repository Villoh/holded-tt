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
    start: str,
    end: str,
    pauses: tuple[str, ...],
    max_minutes: int,
    max_extra: int,
    max_pause_extra: int = 0,
) -> tuple[str, str, tuple[str, ...]]:
    """Randomise a day without touching its net hours beyond a ceiling.

    * The start moves +-``max_minutes`` and the day gains 0..``max_extra`` extra minutes
      worked, so net hours land between the configured ones and those plus ``max_extra``.
    * Each pause starts +-``max_minutes`` from where it was (all pauses shift together) and
      may last 0..``max_pause_extra`` minutes longer than configured. The day grows by the
      same amount, so a longer lunch moves the end of the day and leaves the net alone.
      Without it every pause would last exactly its configured length.
    * Pauses never overlap, and everything stays inside 00:00-23:59.
    """
    s, e = hhmm_to_minutes(start), hhmm_to_minutes(end)
    last = 23 * 60 + 59
    base = e - s
    windows = [tuple(map(hhmm_to_minutes, p.split("-"))) for p in pauses]
    stretched: list[tuple[int, int]] = []
    for i, (a, b) in enumerate(windows):
        room = windows[i + 1][0] - b - 1 if i + 1 < len(windows) else last
        grow = random.randint(0, max(0, min(max_pause_extra, room)))
        stretched.append((a, b + grow))
    grown = sum(b2 - b for (_, b2), (_, b) in zip(stretched, windows))
    grown = min(grown, max(0, last - base))  # a near-24h day has no room to grow
    length = base + grown + random.randint(0, max(0, min(max_extra, last - base - grown)))
    new_start = max(min(s + random.randint(-max_minutes, max_minutes), last - length), 0)
    new_end = new_start + length
    lo = max(-max_minutes, new_start - min((a for a, _ in stretched), default=new_start))
    hi = min(max_minutes, new_end - max((b for _, b in stretched), default=new_end))
    shift = random.randint(lo, hi) if lo <= hi else 0
    return (
        fmt_minutes(new_start),
        fmt_minutes(new_end),
        tuple(f"{fmt_minutes(a + shift)}-{fmt_minutes(b + shift)}" for a, b in stretched),
    )
