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

To have your days clocked for you (on Linux), run `holded-tt clock install` once. See [Automatic clocking](https://github.com/Villoh/holded-tt/blob/main/docs/automation.md).

## Documentation

| Guide | What is in it |
|---|---|
| [Account](https://github.com/Villoh/holded-tt/blob/main/docs/account.md) | `login`, `session`, `workplaces`, `employee`, `organization`, session troubleshooting |
| [Configuration](https://github.com/Villoh/holded-tt/blob/main/docs/configuration.md) | `config`, every default and per-weekday overrides, where files are stored |
| [Track](https://github.com/Villoh/holded-tt/blob/main/docs/track.md) | Register, inspect and update days in bulk, with jitter |
| [Clock](https://github.com/Villoh/holded-tt/blob/main/docs/clock.md) | Real-time clock-in, clock-out, pause and resume |
| [Automatic clocking](https://github.com/Villoh/holded-tt/blob/main/docs/automation.md) | `clock tick`, `clock install`, the systemd units, retries and failure handling |
| [Time off](https://github.com/Villoh/holded-tt/blob/main/docs/timeoff.md) | Vacation availability, requests and holidays |
| [Export](https://github.com/Villoh/holded-tt/blob/main/docs/export.md) | PDF and Excel reports |
| [Development](https://github.com/Villoh/holded-tt/blob/main/docs/development.md) | Running from source, tests |

Every command also has `--help`.

## Security note

`session.json` stores sensitive authentication cookies. The CLI must never log those cookies, and file permissions are applied on a best-effort basis (0600 where supported).

## License

MIT — see [LICENSE](LICENSE).
