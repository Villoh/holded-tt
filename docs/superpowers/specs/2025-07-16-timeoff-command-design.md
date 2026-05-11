# Design: `holded-tt timeoff` command group

**Date:** 2025-07-16  
**Status:** Approved

## Summary

Replace the existing `holded-tt holidays` command with a new `holded-tt timeoff` command group that covers all time-off related functionality: viewing absences, viewing workplace holidays, and requesting vacation days. The cache layer is removed entirely in favour of always fetching fresh data from the API.

## Interface

### `holded-tt timeoff show`

Fetches `GET /internal/team/v2/timeoff-year-summary?year=YYYY` and displays the result.

```
holded-tt timeoff show                  # all: summary + personal absences + workplace holidays
holded-tt timeoff show --holidays       # workplace holidays only
holded-tt timeoff show --mine           # personal absences only
holded-tt timeoff show --year 2025      # specific year (default: current year)
```

**Output without filters — three blocks:**

1. **Summary** — available days, total, used, breakdown (policy/accrued), accrued expiry month
2. **My absences** (`employeeTimeOffs`) — table: start → end, days, type name, status (pending/accepted)
3. **Workplace holidays** (`workplaceTimeOffs`) — table: date, weekday, name (future dates only by default)

**`--holidays` filter:** renders only block 3 (all workplace holidays for the year, not just future ones).  
**`--mine` filter:** renders only block 2.  
**`--holidays` and `--mine` are mutually exclusive.**

### `holded-tt timeoff request`

Posts `POST /internal/team/v2/employee-request` as multipart/form-data.

```
holded-tt timeoff request --date 2026-06-15
holded-tt timeoff request --from 2026-06-15 --to 2026-06-20
holded-tt timeoff request --date 2026-06-15 --period morning
```

- `--date` single day shorthand; cannot be combined with `--from`/`--to`
- `--from` / `--to` for a date range (both required together)
- `--period` optional: `full_day` (default) | `morning` | `afternoon`
- The `timeoffTypeId` for vacations is resolved from `timeOffDetails` in the summary response: the first entry where `discountsDays=true` and `needsApproval=true`.
- On success: prints the created request ID.
- On error: raises `HoldedApiError` with a descriptive hint.

### `holded-tt timeoff cancel`

Cancels a pending timeoff request.

```
holded-tt timeoff cancel --id 6a020a7e17d2ca7fe0017ddb
```

- `--id` required — the timeoff request ID (visible in `timeoff show --mine`)
- Posts `POST /internal/team/v2/timeoff-cancel` with JSON body `{"timeoffId": "<id>"}`
- On success: prints confirmation.

### `holded-tt timeoff details`

Fetches full details of one or more timeoff requests.

```
holded-tt timeoff details --id 6a020a7e17d2ca7fe0017ddb
```

- `--id` required (repeatable for multiple IDs)
- Posts `POST /internal/team/v2/timeoff-details` with JSON body `{"timeoffIds": ["<id>", ...]}`
- Displays the full timeoff detail(s) in a table.

## Architecture

### New files

| File | Purpose |
|------|---------|
| `src/holded_tt/timeoff.py` | Business logic: payload parsing, holiday extraction, absence formatting |
| `src/holded_tt/commands/timeoff.py` | Typer app with `show` and `request` subcommands |
| `tests/test_timeoff.py` | Unit tests for payload parsing logic |
| `tests/test_timeoff_command.py` | CLI tests for `timeoff show` and `timeoff request` |

### Deleted files

| File | Reason |
|------|--------|
| `src/holded_tt/holidays.py` | Replaced by `timeoff.py` |
| `src/holded_tt/commands/holidays.py` | Replaced by `commands/timeoff.py` |
| `tests/test_holidays.py` | Replaced by `test_timeoff.py` |
| `tests/test_holidays_command.py` | Replaced by `test_timeoff_command.py` |

### Modified files

**`src/holded_tt/holded_client.py`**
- Add `get_timeoff_summary(year: int) -> dict` — `GET /internal/team/v2/timeoff-year-summary`
- Add `request_timeoff(start: str, timeoff_type_id: str, day_period: str, description: str, end: str | None) -> str` — `POST /internal/team/v2/employee-request` as multipart/form-data, returns created ID
- Add `cancel_timeoff(timeoff_id: str) -> None` — `POST /internal/team/v2/timeoff-cancel`
- Add `get_timeoff_details(timeoff_ids: list[str]) -> list[dict]` — `POST /internal/team/v2/timeoff-details`
- Remove `get_year_summary()`

**`src/holded_tt/commands/track.py`**
- Replace `fetch_holidays()` / `get_cached_holidays()` calls with a direct call to `client.get_timeoff_summary(year)` + `extract_workplace_holidays()` from the new `timeoff.py` module

**`src/holded_tt/commands/__init__.py`**
- Export `timeoff_app`, remove `holidays_command`

**`src/holded_tt/cli.py`**
- Register `timeoff_app` under `"timeoff"`, remove `holidays` command registration

**`src/holded_tt/state.py`** and **`src/holded_tt/paths.py`**
- Remove `holidays_file` field and `HOLIDAYS_FILE` constant

## API details

### GET /internal/team/v2/timeoff-year-summary

Query param: `year` (integer as string).  
Response fields used:
- `totalDays`, `usedDays`, `availableDays`, `hasUnlimitedDays`
- `daysAvailableBreakdown` — `policy`, `accrued`, `extra`
- `daysUsedBreakdown` — same shape
- `accruedDaysExpiration` — month name string (e.g. `"march"`)
- `employeeTimeOffs[]` — personal absences
- `workplaceTimeOffs[]` — workplace holidays
- `timeOffDetails[]` — used to resolve `timeoffTypeId` for vacation requests

### POST /internal/team/v2/employee-request

Sent as `multipart/form-data` with fields:
- `start` — ISO-8601 datetime with timezone offset (e.g. `2026-06-15T00:00:00+02:00`)
- `end` — ISO-8601 datetime with timezone offset; omitted for single-day requests
- `dayPeriod` — `full_day` | `morning` | `afternoon`
- `description` — empty string by default
- `timeoffTypeId` — ID of the vacation type resolved from `timeOffDetails`

Response: JSON object with `id` field (string).

### POST /internal/team/v2/timeoff-cancel

JSON body: `{"timeoffId": "<id>"}`  
Response: success on 2xx.

### POST /internal/team/v2/timeoff-details

JSON body: `{"timeoffIds": ["<id>", ...]}`  
Response: array of timeoff detail objects.

## Business logic in `timeoff.py`

- `extract_workplace_holidays(summary, year) -> dict[date, str]` — keep same signature as current `holidays.py` (used by `track.py`)
- `extract_employee_absences(summary) -> list[dict]` — parse `employeeTimeOffs`
- `resolve_vacation_type_id(summary) -> str` — find first `timeOffDetails` entry where `discountsDays=True` and `needsApproval=True`
- `build_timeoff_request_start(d: date, timezone: str) -> str` — format date as ISO-8601 with correct UTC offset

## Cache removal

`holidays_file` is removed from `AppState` and `paths.py`. The `track.py` holiday resolution path calls `client.get_timeoff_summary(year)` directly inside a `HoldedClient` context. No local file is written or read.

The `config show` command currently displays the `holidays` file path — this row is removed.

## Error handling

- Mutually exclusive flags `--holidays` and `--mine`: raise `InputError` if both are provided.
- Missing `timeoffTypeId` (no vacation type found in summary): raise `HoldedApiError` with a clear hint.
- API errors follow the existing `HoldedApiError` pattern used throughout the client.

## Testing strategy

**`test_timeoff.py` (unit):**
- `extract_workplace_holidays` — filters by `assignationType=workplace` and `status=accepted`
- `extract_employee_absences` — returns all entries from `employeeTimeOffs`
- `resolve_vacation_type_id` — returns correct ID, raises on empty list

**`test_timeoff_command.py` (CLI):**
- `timeoff show` no flags — renders all three blocks
- `timeoff show --holidays` — renders only workplace holidays block
- `timeoff show --mine` — renders only absences block
- `timeoff show --holidays --mine` — exits with error
- `timeoff request --date 2026-06-15` — posts correct payload (single day, no `end`), prints ID
- `timeoff request --from 2026-06-15 --to 2026-06-20` — posts correct payload with `end` field, prints ID
- `timeoff request` without `--date` or `--from`/`--to` — exits with error
- `timeoff cancel --id <id>` — posts cancel payload, prints confirmation
- `timeoff details --id <id>` — posts details payload, renders result
