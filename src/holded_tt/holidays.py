"""Holiday cache: fetch from Holded, persist locally, invalidate on year change."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from holded_tt.holded_client import HoldedClient


try:
    _PARIS_TZ = ZoneInfo("Europe/Paris")
except ZoneInfoNotFoundError:
    _PARIS_TZ = timezone.utc


def _current_year_paris() -> int:
    return datetime.now(_PARIS_TZ).year


def _load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _save_cache(path: Path, year: int, holidays: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "year": year,
        "holidays": holidays,
        "fetched_at": (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        ),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_cached_holidays(path: Path, year: int) -> dict[date, str] | None:
    """Return cached holiday dates→names for year, or None if cache is stale or absent."""
    cache = _load_cache(path)
    if cache.get("year") != year:
        return None
    result: dict[date, str] = {}
    for entry in cache.get("holidays", []):
        try:
            if isinstance(entry, str):
                result[date.fromisoformat(entry)] = ""
            elif isinstance(entry, dict):
                d = date.fromisoformat(str(entry["date"])[:10])
                result[d] = entry.get("name", "")
        except (ValueError, KeyError):
            pass
    return result


def extract_workplace_holidays(year_summary: dict, year: int) -> dict[date, str]:
    """Extract accepted workplace holidays from a Holded timeoff-year-summary payload."""
    time_offs = year_summary.get("workplaceTimeOffs", [])
    holidays: dict[date, str] = {}
    for entry in time_offs:
        if (
            entry.get("assignationType") == "workplace"
            and entry.get("status") == "accepted"
        ):
            holiday_date: date | None = None
            for key in ("date", "startDate", "start"):
                raw = entry.get(key)
                if raw:
                    try:
                        d = date.fromisoformat(str(raw)[:10])
                        if d.year == year:
                            holiday_date = d
                    except ValueError:
                        pass
                    break
            if holiday_date is not None:
                name = ""
                for name_key in ("name", "description", "typeName"):
                    val = entry.get(name_key)
                    if val:
                        name = str(val)
                        break
                holidays[holiday_date] = name
    return holidays


def fetch_holidays(
    client: HoldedClient,
    cache_path: Path,
    year: int,
    workplace_id: str,
) -> dict[date, str]:
    """Return holidays for year, using cache when valid and fetching from API otherwise."""
    cached = get_cached_holidays(cache_path, year)
    if cached is not None:
        return cached

    summary = client.get_year_summary(year, workplace_id)
    holidays = extract_workplace_holidays(summary, year)
    _save_cache(
        cache_path,
        year,
        [{"date": d.isoformat(), "name": name} for d, name in sorted(holidays.items())],
    )
    return holidays
