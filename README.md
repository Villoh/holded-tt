# Holded TT CLI

`holded-tt` is an unofficial Python CLI for automating time tracking on [Holded](https://app.holded.com).
It is a focused time-tracking tool, not a general-purpose Holded client.

> [!IMPORTANT]
> This project is not affiliated with, endorsed by, or supported by Holded.
> Holded names and marks belong to their respective owner.

## Install

### Requirements

- Python 3.11+
- A Holded account with time tracking enabled
- An interactive terminal for `holded-tt login` (email/password prompt, plus 2FA prompt when required)

```bash
# Editable install for development
pip install -e .

# Isolated tool install (recommended for end users)
pipx install .
# or
uv tool install .
```

After installation, you can check the global CLI version with:

```bash
holded-tt --version
```

## Quick start

```bash
# 1. Authenticate
holded-tt login

# 2. Check your workplace ID
holded-tt workplaces

# Optional: inspect your profile and organization directory
holded-tt employee
holded-tt organization

# 3. Save your defaults
holded-tt config set defaults.workplace_id <id>
holded-tt config set defaults.start 09:00
holded-tt config set defaults.end 18:00
holded-tt config set defaults.timezone Europe/Madrid
holded-tt config set defaults.pause 14:00-15:00

# 4. Register a date range (preview first)
holded-tt track --from 2026-01-07 --to 2026-04-07 --dry-run
holded-tt track --from 2026-01-07 --to 2026-04-07
```

## Runtime storage

The CLI stores its runtime files in a per-user config directory resolved via `platformdirs` as `holded-tt-cli`.

- Linux: `~/.config/holded-tt-cli`
- macOS: `~/Library/Application Support/holded-tt-cli`
- Windows: `C:\Users\<user>\AppData\Roaming\holded-tt-cli`

Files created there:

- `config.toml`: saved CLI defaults
- `session.json`: saved Holded cookies and `saved_at` timestamp
- `holidays.json`: cached workplace holidays used by `track`

`config.toml` is created automatically on first run if it does not exist. `session.json` permissions are restricted on a best-effort basis.

## Commands

### `holded-tt login`
Authenticates with Holded interactively and saves the session locally.

The command always prompts for your email and password. If Holded requires two-factor authentication, it then prompts for the 2FA code and completes the login flow.

```bash
holded-tt login
```

---

### `holded-tt session`
Shows the saved session status, validation mode, and when it was last refreshed. By default it validates the saved cookies live against Holded using `/internal/real-time/discover`.

```bash
holded-tt session
holded-tt session --live
holded-tt session --offline
```

`--live` checks the current session against Holded. `--offline` only inspects the locally saved cookies and timestamp.

---

### `holded-tt workplaces`
Lists all workplace IDs and names available in your account. Use the ID to configure your default workplace.

```bash
holded-tt workplaces
```

---

### `holded-tt employee`
Shows your merged employee profile by combining the Holded employee and personal-info endpoints.

```bash
holded-tt employee
```

---

### `holded-tt organization`
Lists organization employees from the Holded Teamzone organization endpoint.

```bash
holded-tt organization
```

---

### `holded-tt track`
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
```

Notes:

- Use either `--today` or both `--from YYYY-MM-DD` and `--to YYYY-MM-DD`.
- `holded-tt track --today` uses your configured defaults (`workplace_id`, `start`, `end`, `timezone`, `pause`) and still skips weekends and holidays unless you opt in with `--include-weekends` or `--include-holidays`.
- `--pause` is repeatable and must use `HH:MM-HH:MM` format.
- Submissions larger than 10 resulting days require confirmation unless you pass `--yes`.
- `--dry-run` still uses `holidays.json` if that cache already exists.
- `--dry-run` does not fetch missing holidays from Holded. If the holiday cache is missing, the preview falls back to no holiday filtering for those uncached years.

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

---

### `holded-tt clock`
Real-time clock-in, clock-out, pause, and resume.

```bash
# Show current tracker status
holded-tt clock
holded-tt clock status

# Start and stop a live tracker
holded-tt clock in
holded-tt clock out

# Pause and resume the active tracker
holded-tt clock pause
holded-tt clock resume
```

`holded-tt clock` without a subcommand behaves like a status check.

---

### `holded-tt export`
Exports time-tracking records for a date range as PDF or Excel.

The PDF is the official Holded report. The Excel replicates the official layout: company, employee, month title, and a row per calendar day with schedule, hours, workplace, and approval status.

```bash
# Export as PDF (default)
holded-tt export --from 2026-04-01 --to 2026-04-30

# Export as Excel
holded-tt export --from 2026-04-01 --to 2026-04-30 --format xlsx

# Include company name in the Excel header
holded-tt export --from 2026-04-01 --to 2026-04-30 --format xlsx --company "ACME S.L."

# Save to a specific path
holded-tt export --from 2026-04-01 --to 2026-04-30 --out ~/Desktop/abril.pdf
```

If `--out` is omitted, the file is saved to the current directory as `holded-tt-{from}_{to}.{format}`.

---

### `holded-tt config`
Inspects or updates local defaults. Run without arguments to show current values.

```bash
holded-tt config
holded-tt config show
holded-tt config set <key> <value>
```

Actual built-in defaults used when `config.toml` is first created:

- `defaults.workplace_id`: empty
- `defaults.start`: `08:30`
- `defaults.end`: `17:30`
- `defaults.timezone`: `Europe/Paris`
- `defaults.pause`: empty list (`[]`)

Examples below are sample values you may want to change, not the shipped defaults.

**Available keys:**

| Key                      | Description                        | Example              |
|--------------------------|------------------------------------|----------------------|
| `defaults.workplace_id`  | Default workplace for `track`      | `a3f9c12b7e4d8...`     |
| `defaults.start`         | Default work start time (HH:MM)    | `09:00`              |
| `defaults.end`           | Default work end time (HH:MM)      | `18:00`              |
| `defaults.timezone`      | Timezone for submitted entries     | `Europe/Madrid`      |
| `defaults.pause`         | Default pauses (comma-separated)   | `14:00-14:30`        |

```bash
holded-tt config set defaults.workplace_id <workplace_id>
holded-tt config set defaults.start 09:00
holded-tt config set defaults.end 18:00
holded-tt config set defaults.timezone Europe/Madrid
holded-tt config set defaults.pause 14:00-14:30,17:00-17:15
```

---

## Session troubleshooting

- Run `holded-tt session` to inspect whether a saved session exists, whether live validation succeeds, and when it was last refreshed.
- Use `holded-tt session --offline` if you only want to inspect the locally saved cookies and timestamp.
- If commands report that no saved session is available or that the session is expired, run `holded-tt login` again.
- If `holded-tt login` fails during 2FA, verify the code and try again.

## Development

```bash
# Install runtime dependencies only
uv sync

# Install dev dependencies
uv sync --dev

# Run the CLI locally
uv run holded-tt --help

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src --cov-report=term-missing
```

If you prefer plain `pip` for local development:

```bash
pip install -e .
```

---

## Security note

`session.json` stores sensitive authentication cookies. The CLI must never log those cookies, and file permissions are applied on a best-effort basis (0600 where supported).
