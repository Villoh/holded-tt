# Holded CLI

`holded` is a Python CLI for automating time tracking on [Holded](https://app.holded.com).

## Install

```bash
# Editable install for development
pip install -e .

# Isolated tool install (recommended for end users)
pipx install .
# or
uv tool install .
```

## Quick start

```bash
# 1. Authenticate
holded login

# 2. Check your workplace ID
holded workplaces

# 3. Save your defaults
holded config set defaults.workplace_id <id>
holded config set defaults.start 09:00
holded config set defaults.end 18:00
holded config set defaults.timezone Europe/Madrid

# 4. Register a date range (preview first)
holded track --from 2026-01-07 --to 2026-04-07 --dry-run
holded track --from 2026-01-07 --to 2026-04-07
```

## Commands

### `holded login`
Authenticates with Holded via email + 2FA and saves the session locally.

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

## Security note

`session.json` stores sensitive authentication cookies. The CLI must never log those cookies, and file permissions are applied on a best-effort basis (0600 where supported).
