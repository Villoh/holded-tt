# Holded CLI

`holded` is a Python CLI for automating time tracking on [Holded](https://app.holded.com).

## Install

### Requirements

- Python 3.11+
- A Holded account with time tracking enabled
- An interactive terminal for `holded login` (email/password prompt, plus 2FA prompt when required)

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
holded --version
```

## Quick start

```bash
# 1. Authenticate
holded login

# 2. Check your workplace ID
holded workplaces

# Optional: inspect your profile
holded employee
# aliases
holded me
holded whoami

# 3. Save your defaults
holded config set defaults.workplace_id <id>
holded config set defaults.start 09:00
holded config set defaults.end 18:00
holded config set defaults.timezone Europe/Madrid

# 4. Register a date range (preview first)
holded track --from 2026-01-07 --to 2026-04-07 --dry-run
holded track --from 2026-01-07 --to 2026-04-07
```

## Runtime storage

The CLI stores its runtime files in a per-user config directory resolved via `platformdirs` as `holded-cli`.

- Linux: `~/.config/holded-cli`
- macOS: `~/Library/Application Support/holded-cli`
- Windows: `C:\Users\<user>\AppData\Roaming\holded-cli`

Files created there:

- `config.toml`: saved CLI defaults
- `session.json`: saved Holded cookies and `saved_at` timestamp
- `holidays.json`: cached workplace holidays used by `track`

`config.toml` is created automatically on first run if it does not exist. `session.json` permissions are restricted on a best-effort basis.

## Commands

### `holded login`
Authenticates with Holded interactively and saves the session locally.

The command always prompts for your email and password. If Holded requires two-factor authentication, it then prompts for the 2FA code and completes the login flow.

```bash
holded login
```

---

### `holded session`
Shows the saved session status and when it was last refreshed.

```bash
holded session
```

---

### `holded workplaces`
Lists all workplace IDs and names available in your account. Use the ID to configure your default workplace.

```bash
holded workplaces
```

---

### `holded employee`
Shows your merged employee profile by combining the Holded employee and personal-info endpoints.

Aliases: `holded me`, `holded whoami`

```bash
holded employee
holded me
holded whoami
```

---

### `holded track`
Registers working days on Holded for a date range. Weekends and workplace holidays are skipped automatically.

```bash
# Register a full month
holded track --from 2026-04-01 --to 2026-04-30

# Register today only
holded track --today

# Preview without submitting
holded track --from 2026-04-01 --to 2026-04-30 --dry-run

# Override defaults for a single run
holded track --from 2026-04-01 --to 2026-04-30 \
             --start 08:30 --end 17:00 \
             --pause 13:00-14:00 \
             --workplace <id>

# Include weekends or holidays
holded track --from 2026-04-01 --to 2026-04-30 \
             --include-weekends \
             --include-holidays

# Skip confirmation for large submissions
holded track --from 2026-01-01 --to 2026-12-31 --yes
```

Notes:

- Use either `--today` or both `--from YYYY-MM-DD` and `--to YYYY-MM-DD`.
- `--pause` is repeatable and must use `HH:MM-HH:MM` format.
- Submissions larger than 10 resulting days require confirmation unless you pass `--yes`.
- `--dry-run` still uses `holidays.json` if that cache already exists.
- `--dry-run` does not fetch missing holidays from Holded. If the holiday cache is missing, the preview falls back to no holiday filtering for those uncached years.

---

### `holded clock`
Real-time clock-in, clock-out, pause, and resume.

```bash
# Show current tracker status
holded clock
holded clock status

# Start and stop a live tracker
holded clock in
holded clock out

# Pause and resume the active tracker
holded clock pause
holded clock resume
```

`holded clock` without a subcommand behaves like a status check.

---

### `holded export`
Exports time-tracking records for a date range as PDF or Excel.

The PDF is the official Holded report. The Excel replicates the official layout: company, employee, month title, and a row per calendar day with schedule, hours, workplace, and approval status.

```bash
# Export as PDF (default)
holded export --from 2026-04-01 --to 2026-04-30

# Export as Excel
holded export --from 2026-04-01 --to 2026-04-30 --format xlsx

# Include company name in the Excel header
holded export --from 2026-04-01 --to 2026-04-30 --format xlsx --company "ACME S.L."

# Save to a specific path
holded export --from 2026-04-01 --to 2026-04-30 --out ~/Desktop/abril.pdf
```

If `--out` is omitted, the file is saved to the current directory as `holded-{from}_{to}.{format}`.

---

### `holded config`
Inspects or updates local defaults. Run without arguments to show current values.

```bash
holded config
holded config show
holded config set <key> <value>
```

Actual built-in defaults used when `config.toml` is first created:

- `defaults.workplace_id`: empty
- `defaults.start`: `08:30`
- `defaults.end`: `17:30`
- `defaults.timezone`: `Europe/Paris`

Examples below are sample values you may want to change, not the shipped defaults.

**Available keys:**

| Key                      | Description                        | Example              |
|--------------------------|------------------------------------|----------------------|
| `defaults.workplace_id`  | Default workplace for `track`      | `a3f9c12b7e4d8...`     |
| `defaults.start`         | Default work start time (HH:MM)    | `09:00`              |
| `defaults.end`           | Default work end time (HH:MM)      | `18:00`              |
| `defaults.timezone`      | Timezone for submitted entries     | `Europe/Madrid`      |

```bash
holded config set defaults.workplace_id <workplace_id>
holded config set defaults.start 09:00
holded config set defaults.end 18:00
holded config set defaults.timezone Europe/Madrid
```

---

## Session troubleshooting

- Run `holded session` to inspect whether a saved session exists and when it was last refreshed.
- If commands report that no saved session is available, run `holded login` again.
- If commands report that the saved session is too old to trust, re-run `holded login` to refresh it.
- If `holded login` fails during 2FA, verify the code and try again.

## Development

```bash
# Install runtime dependencies only
uv sync

# Install dev dependencies
uv sync --dev

# Run the CLI locally
uv run holded --help

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=holded_cli
```

If you prefer plain `pip` for local development:

```bash
pip install -e .
```

---

## Security note

`session.json` stores sensitive authentication cookies. The CLI must never log those cookies, and file permissions are applied on a best-effort basis (0600 where supported).
