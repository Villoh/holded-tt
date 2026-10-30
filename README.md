# Holded TT

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
# Install from PyPI (recommended for end users)
pipx install holded-tt

# or
uv tool install holded-tt

# or, inside an existing virtualenv
pip install holded-tt
```

With Nix, the repository is a flake:

```bash
nix run github:Villoh/holded-tt -- --help
```

To install it declaratively, add it as an input and use `inputs.holded-tt.packages.${system}.default`.

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

The CLI stores its runtime files in a per-user config directory resolved via `platformdirs` as `holded-tt`.

- Linux: `~/.config/holded-tt`
- macOS: `~/Library/Application Support/holded-tt`
- Windows: `C:\Users\<user>\AppData\Roaming\holded-tt`

Files created there:

- `config.toml`: saved CLI defaults
- `session.json`: saved Holded cookies and `saved_at` timestamp

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

---

### `holded-tt timeoff`
Shows personal absences, workplace holidays, and vacation availability. It can also create, cancel, and inspect time-off requests.

```bash
# Show vacation availability, your absences, and workplace holidays
holded-tt timeoff show

# Show only your personal time-off requests
holded-tt timeoff show --mine

# Show only workplace holidays for the current year
holded-tt timeoff show --holidays

# Query a specific year
holded-tt timeoff show --year 2026

# Request a single vacation day
holded-tt timeoff request --date 2026-06-15

# Request a date range
holded-tt timeoff request --from 2026-06-15 --to 2026-06-20

# Request a half day
holded-tt timeoff request --date 2026-06-15 --period morning
holded-tt timeoff request --date 2026-06-15 --period afternoon

# Cancel or inspect a request by ID
holded-tt timeoff cancel --id <timeoff_id>
holded-tt timeoff details --id <timeoff_id>
```

Notes:

- `timeoff show` reads Holded's time-off year summary directly; no holiday cache is stored locally.
- `--holidays` and `--mine` are mutually exclusive filters.
- `timeoff request` accepts either `--date` for one day or `--from`/`--to` for a range.
- Valid `--period` values are `full_day`, `morning`, and `afternoon`. The default is `full_day`.
- Vacation requests use the first Holded time-off type that discounts days and requires approval.

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

#### Automatic clocking (`clock tick`)

`holded-tt clock tick` advances today's plan once. On its first run of the day it plans the day from your config (start, end, pauses, per-weekday overrides) with `defaults.jitter` applied, saves the plan to `plan.json` next to `config.toml`, and from then on clocks in, pauses, resumes and clocks out as each time comes due.

Two ways to run it:

- **Linux, event-driven (recommended):** `clock tick --schedule` runs once a day (and at boot); after acting it arms a one-shot systemd timer for the **next** planned event and exits. Nothing runs or sleeps in between: about 5 runs a day, each at the planned second (random seconds per event, so entries are not always at `:00`).
- **Any OS, periodic:** run `clock tick` (without `--schedule`) from a timer every 5 minutes. It does nothing and calls nothing until something is due, but entries then land on the 5-minute grid.

```bash
holded-tt config set defaults.jitter 15      # optional randomness, see `config`
holded-tt config set defaults.max_late 90    # skip a clock-in later than this (default 90)
holded-tt clock tick --dry-run               # show what would happen, change nothing
holded-tt clock tick --schedule --dry-run    # ...and when the next event would be armed
```

How it behaves:

- **Skips** weekends, workplace holidays and accepted time off, without touching the tracker.
- **Quiet:** with nothing due it prints nothing and makes no API call.
- **Resilient:** every step checks the real tracker in Holded first, so a missed run, a reboot or a tracker you started by hand never causes a duplicate. If you clock in by hand, the plan adopts your real start time.
- **Net hours hold:** a late clock-in (machine switched on late) or a late resume pushes the clock-out back by the same amount, so the day never nets less than the configured hours. Within `max_late` this holds for any jitter.
- **Too late:** if the clock-in is more than `max_late` minutes after plan, the day is dropped, `tick` exits with code 3 once, and the rest of the plan is cancelled. Clock in by hand if you still want the day.
- **A tracker left open from a previous day** blocks `tick` (exit 2) until you close it.
- Clock-out is never skipped: if you were away at the planned time it happens as soon as `tick` runs again.

**Failures and retries.** With `--schedule` nothing polls, so a failed run must not break the chain. Exit code 2 (network error, expired session, systemd error) is retried by systemd every 2 minutes for about 30 minutes; code 3 (missed clock-in, no `systemd-run`, executable not found) is not, because retrying cannot fix it. Every failed attempt runs `holded-tt-failed.service`; rate-limit it (below) so you are alerted once. After an expired session, `holded-tt login` is enough: the next retry carries on. If a run is killed before it can arm the next event, the chain stops until the next daily or boot run, and the alert is how you find out.

`tick` only works while the machine is on and the session is valid (`holded-tt session`); when the session expires you need to `holded-tt login` again (2FA).

**Linux (systemd user units).** `~/.config/systemd/user/holded-tt-tick.service` (the retry lines also apply to every timer it arms):

```ini
[Unit]
Description=holded-tt clock tick
OnFailure=holded-tt-failed.service
StartLimitBurst=15
StartLimitIntervalSec=1h

[Service]
Type=oneshot
ExecStart=%h/.local/bin/holded-tt clock tick --schedule   # the path from `which holded-tt`, see below
Restart=on-failure
RestartSec=120
RestartPreventExitStatus=3

[Install]
WantedBy=default.target    # also run it when your user manager starts (boot/login)
```

`holded-tt-tick.timer` plans the day once, every weekday morning:

```ini
[Unit]
Description=Plan the holded-tt day

[Timer]
OnCalendar=Mon..Fri *-*-* 06:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

`holded-tt-failed.service` runs on a failed attempt; the start limit makes it alert once an hour:

```ini
[Unit]
Description=holded-tt tick failed
StartLimitBurst=1
StartLimitIntervalSec=1h

[Service]
Type=oneshot
ExecStart=notify-send "holded-tt" "clock tick failed, see: journalctl --user -u 'holded-tt-*'"
```

The path in `ExecStart` is also the one every armed timer reuses, so give it a path that survives updates. On NixOS use the profile path (`/etc/profiles/per-user/<user>/bin/holded-tt`), not the `/nix/store/...` one, which changes with every rebuild and is removed by garbage collection.

```bash
holded-tt clock tick --schedule --dry-run    # first: today's plan and the next event, changing nothing
systemctl --user daemon-reload
systemctl --user enable --now holded-tt-tick.timer
systemctl --user enable holded-tt-tick.service   # no --now: starting it runs a real tick immediately
loginctl enable-linger $USER                 # optional: run without an open login session
systemctl --user list-timers                 # the armed next event shows as holded-tt-next-*
journalctl --user -u 'holded-tt-*' -n 30
```

`enable --now` on the timer only waits for 06:00. Starting `holded-tt-tick.service` (or rebooting) does a real tick: it plans today and, if a clock-in is already due and within `max_late`, clocks in.

Why two entry points besides the chain: `Persistent=true` runs the morning plan right after boot if the machine was off at 06:00, and the `default.target` hook re-arms the chain after a reboot, because one-shot timers do not survive one. If you suspend the machine, a timer that came due while asleep runs when it wakes.

**macOS / Windows.** `--schedule` needs `systemd-run`. Use a `launchd` agent with `StartInterval=300`, or a Task Scheduler task repeating every 5 minutes, running `holded-tt clock tick`.

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
- `defaults.jitter`: `0` (no randomisation)
- `defaults.max_late`: `90` (minutes; used by `clock tick`)

Examples below are sample values you may want to change, not the shipped defaults.

**Available keys:**

| Key                      | Description                        | Example              |
|--------------------------|------------------------------------|----------------------|
| `defaults.workplace_id`  | Default workplace for `track`      | `a3f9c12b7e4d8...`     |
| `defaults.start`         | Default work start time (HH:MM)    | `09:00`              |
| `defaults.end`           | Default work end time (HH:MM)      | `18:00`              |
| `defaults.timezone`      | Timezone for submitted entries     | `Europe/Madrid`      |
| `defaults.pause`         | Default pauses (comma-separated)   | `14:00-14:30`        |
| `defaults.jitter`        | Max random minutes on start/end/pause, `0` = off | `15`   |
| `defaults.max_late`      | `clock tick` skips a clock-in later than this (minutes) | `90` |
| `defaults.<day>.<field>` | Per-weekday override (see below)   | `defaults.fri.end 15:00` |

**Per-weekday overrides:** `<day>` is `mon`, `tue`, `wed`, `thu`, `fri`, `sat` or `sun`, and `<field>` is `start`, `end` or `pause`. Anything not overridden falls back to the base defaults. `track` sends one batch per distinct schedule, and explicit `--start`/`--end`/`--pause` flags apply to every day.

```bash
# Short Fridays: same start and pause, finish at 15:00
holded-tt config set defaults.fri.end 15:00
```

Overrides are stored in `config.toml` as `[days.fri]` tables. To remove one, delete its entry from the file.

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

---

## License

MIT — see [LICENSE](LICENSE).
