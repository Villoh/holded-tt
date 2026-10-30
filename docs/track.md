# `holded-tt track`
Registers working days on Holded for a date range. Weekends and workplace holidays are skipped automatically.

```bash
# Register a full month
holded-tt track --from 2026-04-01 --to 2026-04-30

# Register today only
holded-tt track --today

# Preview without submitting
holded-tt track --from 2026-04-01 --to 2026-04-30 --dry-run

# Override defaults for a single run
holded-tt track --from 2026-04-01 --to 2026-04-30 \
             --start 08:30 --end 17:00 \
             --pause 13:00-14:00 \
             --workplace <id>

# Include weekends or holidays
holded-tt track --from 2026-04-01 --to 2026-04-30 \
             --include-weekends \
             --include-holidays

# Skip confirmation for large submissions
holded-tt track --from 2026-01-01 --to 2026-12-31 --yes

# Randomise start, end and pause by up to 20 minutes per day
holded-tt track --from 2026-04-01 --to 2026-04-30 --jitter 20
```

Notes:

- Use either `--today` or both `--from YYYY-MM-DD` and `--to YYYY-MM-DD`.
- `holded-tt track --today` uses your configured defaults (`workplace_id`, `start`, `end`, `timezone`, `pause`) and still skips weekends and holidays unless you opt in with `--include-weekends` or `--include-holidays`.
- `--pause` is repeatable and must use `HH:MM-HH:MM` format.
- Submissions larger than 10 resulting days require confirmation unless you pass `--yes`.
- `--jitter N` (or `defaults.jitter`) randomises each day's start, end and pause by up to `N` minutes so entries are not identical every day. Start and end move in either direction, but net worked hours never drop below the configured schedule: a later start forces an equally later end. Pauses keep their length and stay inside the day. The override flag wins over the config value, and `--jitter 0` turns it off. Because every day gets its own schedule, `track` sends one batch per day when jitter is on.
- `--dry-run` does not fetch holidays from Holded. Preview mode skips live holiday filtering to avoid requiring a session just to inspect the date range.

Subcommands:

```bash
# Inspect tracked entries and tracker IDs for a single day
holded-tt track show --date 2026-04-10

# Inspect a date range
holded-tt track show --from 2026-04-07 --to 2026-04-10

# Update a date range, one existing tracker per day
holded-tt track update --from 2026-04-07 --to 2026-04-10 --end 17:00

# Include weekends or holidays when updating a range
holded-tt track update --from 2026-04-07 --to 2026-04-10 \
                    --include-weekends --include-holidays \
                    --end 17:00

# Update a single existing tracker by its tracker ID
holded-tt track update --date 2026-04-10 --tracker-id <tracker_id> --end 17:00

# Replace the pause windows explicitly
holded-tt track update --date 2026-04-10 --tracker-id <tracker_id> \
                    --start 08:30 --end 17:00 \
                    --pause 14:00-14:30
```

Notes for `track show` and `track update`:

- `track show --date` uses Holded's single-day timetracking endpoint. `track show --from/--to` uses the range endpoint.
- `track show` is intended to help you discover the `tracker.id` values returned by Holded and inspect the current `Time`, `Worked`, `Pauses`, `Status`, `Approved`, `Method`, and `Remote` fields.
- `track update` updates either a single tracker (`--date` + `--tracker-id`) or a date range (`--from/--to` or `--today`).
- Single-tracker updates require both `--tracker-id` and either `--date` or `--today`.
- Range updates filter weekends and workplace holidays by default, just like `holded-tt track`. Use `--include-weekends` and `--include-holidays` to opt in. These flags only affect range updates.
- Range updates are strict: each target day must have exactly one existing tracker. Days with zero trackers, multiple trackers, or running trackers raise an error.
- Range updates are processed one tracker at a time, not atomically. If a later day fails, earlier days in the same command may already have been updated.
- If `--start` or `--end` is omitted during `track update`, the CLI keeps the existing value from Holded.
- If `--pause` is omitted during `track update`, the CLI keeps the existing pauses. If you pass `--pause`, it replaces the current pauses with the provided list.
- Existing pauses are displayed in `track show` and update previews as `HH:MM -> HH:MM`.
