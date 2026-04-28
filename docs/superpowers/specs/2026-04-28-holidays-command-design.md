# holidays command design

**Date:** 2026-04-28  
**Status:** approved

## Summary

Add `holded-tt holidays` as a top-level CLI command that shows workplace holidays for a given year, using the existing JSON cache and fetching from the Holded API when needed.

## Motivation

`track` calls `fetch_holidays` silently. Users have no way to inspect or manually refresh the holidays cache without running a full `track --dry-run`.

## Interface

```
holded-tt holidays [--year YYYY] [--refresh]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--year` | current year (Europe/Paris) | Year to fetch holidays for |
| `--refresh` | false | Bypass cache, always fetch from API |

### Examples

```
holded-tt holidays
holded-tt holidays --year 2025
holded-tt holidays --refresh
holded-tt holidays --year 2025 --refresh
```

## Behaviour

**Without `--refresh`:**
1. Call `get_cached_holidays(state.holidays_file, year)`
2. If cache hit → display table, status line says `cached`
3. If cache miss/stale → call API → save cache → display table, status line says `fetched`

**With `--refresh`:**
1. Skip cache check entirely
2. Call `client.get_year_summary(year)` + `extract_workplace_holidays`
3. Save updated cache via `_save_cache`
4. Display table, status line says `refreshed`

**No holidays found:** print `No holidays found for {year}.` and exit 0.

## Output

Rich table (same style as `workplaces`):

```
  #   Date         Day
  1   2026-01-01   Thursday
  2   2026-04-17   Friday
  ...

  12 holiday(s) · 2026 · cached
```

Status tokens: `cached` | `fetched` | `refreshed`

## Implementation

### New file
`src/holded_tt/commands/holidays.py` — single `holidays_command` function.

### Files touched
| File | Change |
|------|--------|
| `src/holded_tt/commands/holidays.py` | new — command implementation |
| `src/holded_tt/commands/__init__.py` | export `holidays_command` |
| `src/holded_tt/cli.py` | register `holded-tt holidays` |

### Reuse
- `get_cached_holidays` — cache read (existing, `holidays.py`)
- `extract_workplace_holidays` — payload parsing (existing, `holidays.py`)
- `_save_cache` — cache write (existing, `holidays.py`, currently private)
- `_current_year_paris` — default year (existing, `holidays.py`, currently private)
- `HoldedClient.get_year_summary` — API call (existing, `holded_client.py`)
- `_with_cli_error_handling` — error wrapper (existing, `cli.py`)
- `AppState` — session + config + file paths (existing, `state.py`)

### Private helper exposure
`_save_cache` and `_current_year_paris` are private. Two options:
- Make them public (rename, remove underscore) — preferred, they are reusable
- Inline equivalent logic in the new command — avoid duplication

Preferred: make both public in `holidays.py`.

## Error handling

- Auth error → `HoldedCliError` via `require_saved_session` (existing flow)
- API error → `HoldedApiError` (existing flow)
- Both surfaced via `_with_cli_error_handling` in `cli.py`

## Testing

Unit tests in `tests/test_holidays_command.py`:
- Cache hit → no API call, table rendered, `cached` status
- Cache miss → API called, cache saved, `fetched` status
- `--refresh` → API always called regardless of existing cache, `refreshed` status
- `--year` → correct year passed through
- No holidays → correct empty message, exit 0
