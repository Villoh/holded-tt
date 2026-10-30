# Configuration

## `holded-tt config`
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

## Runtime storage

The CLI stores its runtime files in a per-user config directory resolved via `platformdirs` as `holded-tt`.

- Linux: `~/.config/holded-tt`
- macOS: `~/Library/Application Support/holded-tt`
- Windows: `C:\Users\<user>\AppData\Roaming\holded-tt`

Files created there:

- `config.toml`: saved CLI defaults
- `session.json`: saved Holded cookies and `saved_at` timestamp
- `plan.json`: today's automatic clocking plan (see [Automatic clocking](automation.md))
- `skips.json`: days you asked `clock skip` not to clock

`config.toml` is created automatically on first run if it does not exist. `session.json` permissions are restricted on a best-effort basis.
