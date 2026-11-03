# Automatic clocking

`holded-tt clock tick` clocks you in, out and through your pauses by itself, at the times in your [configuration](configuration.md) (with optional [jitter](track.md)). It is meant to be run by a timer, not by hand.

On its first run of the day it plans the day (start, end, pauses, per-weekday overrides, `defaults.jitter`), saves the plan to `plan.json` next to `config.toml`, and from then on clocks in, pauses, resumes and clocks out as each time comes due.

## Set it up

`clock install` sets up automatic clocking with the scheduler your system has: systemd on Linux, the Task Scheduler on Windows. macOS has neither backend yet: see [Without a scheduler backend](#without-a-scheduler-backend-macos-or-by-preference).

### Linux (systemd)

```bash
holded-tt clock tick --dry-run             # check first: what a tick would do right now; clocks and saves nothing
holded-tt clock install --dry-run            # see the unit files it would write
holded-tt clock install                      # write them and enable the timer
```

`clock install` writes three systemd user units to `~/.config/systemd/user/`, then enables them:

| Unit | What it does |
|---|---|
| `holded-tt-tick.timer` | Every weekday at 06:00 (`--plan-at HH:MM` to change it) runs the service. `Persistent=true` runs it right after boot if the machine was off at that time. |
| `holded-tt-tick.service` | Runs `holded-tt clock tick --schedule`. Also started when your user manager starts (boot or login), which re-arms the chain after a reboot. |
| `holded-tt-failed.service` | The alert, run when a tick fails: `notify-send` if you have it, else a line in the journal. Limited to one alert per hour. |

Things worth knowing:

- **The service is enabled but not started.** Starting it runs a real tick: it plans today and, if a clock-in is already due and within `max_late`, clocks in. The timer only waits for the next morning. To plan today right away, run `holded-tt clock tick --schedule` yourself.
- **The executable path is baked into the units**, and every timer they arm reuses it. `install` uses the path you ran it from. Under Nix, Python only sees `/nix/store/...`, which changes on every rebuild and is garbage-collected, so `install` looks on your `PATH` for the same program under a stable name (on NixOS, `/etc/profiles/per-user/<user>/bin/holded-tt`) and uses that. If there is none it falls back to the store path and warns.
- **The plan time must be before your earliest possible clock-in** (start minus jitter).
- **It never overwrites a unit it did not generate**, and refuses symlinks (home-manager and similar). In that case declare the three units yourself: `clock install --dry-run` prints the exact text.
- `loginctl enable-linger $USER` is optional. It only matters if you want clocking with no open login session. Without it the morning plan runs when you log in.

Check it:

```bash
holded-tt clock plan                         # today's plan, what is armed, when planning runs next
systemctl --user list-timers                 # the same, as systemd sees it (holded-tt-next-*)
journalctl --user -u 'holded-tt-*' -n 30     # what each run did
```

### Windows (Task Scheduler)

```powershell
holded-tt clock install --dry-run            # prints the task definition, creates nothing
holded-tt clock install                      # creates the task
holded-tt clock plan
holded-tt clock uninstall
```

`install` creates one task, `\holded-tt\holded-tt-plan`, that runs `holded-tt clock tick --schedule` every weekday at 06:00 (`--plan-at HH:MM`) and at every logon, and is set to run a missed start as soon as possible. Each run arms a one-shot task `\holded-tt\holded-tt-next-<UTC time>` for the next event, exactly like the systemd timers, and are set to expire an hour after they fire (the next run also deletes any that are over an hour old; the scheduler's own expiry cleanup has not been observed).

- **It does not start a tick**, so nothing is clocked until the task's next trigger. Run `holded-tt clock tick --schedule` yourself to plan today.
- **Runs only while you are logged on**, as you and without elevation. No password is stored, which is also why it cannot run with the session closed.
- **Retries are done by the app**, not by Windows. Task Scheduler's own "restart on failure" does not restart a task whose program exits with an error (measured on a real Windows runner), so after a failed run `tick --schedule` arms a retry task for 2 minutes later, up to 15 attempts a day, as systemd does. A failure that retrying cannot fix (a missed clock-in) is not retried. There is no `OnFailure` alert: look at the task history (`taskschd.msc`) or `holded-tt clock plan`, which warns when the next event is not armed.
- **The executable** is the one you ran `install` from (`holded-tt.exe` in the Scripts folder of `pipx`, `uv tool` or your virtualenv). Reinstall after moving or upgrading it to a new location.
- `clock skip` deletes the armed one-shot tasks, like it stops the timers on Linux.

## See the plan

`holded-tt clock plan` is read-only: it reads `plan.json`, `skips.json` and what systemd has armed, and does not call Holded.

```
Tuesday 2026-11-03  active
  in     08:13  done  (actual 08:23)
  pause  14:12  next  armed for 14:12:38
  resume 14:42  pending
  out    17:33  pending
net planned: 8h40  (08:23 -> 17:33)
next planning: Wed 2026-11-04 08:00:00 CET
skipped days: 2026-11-05
```

- **`next`** is the first event still to happen, with the second its timer will fire at. **`next planning`** is the daily timer.
- **`actual`** is when you really clocked in, shown while it can be recovered from the plan (not after a late resume moved the clock-out).
- A day that is not worked says why instead: `skipped: holiday ...`, `skipped: weekend`, `skipped: skipped by you`, or `missed: clock-in was planned for ...`.
- **`warning: nothing is armed`** (on Windows it reads the one-shot tasks) means the next event has no timer, so it will not happen until the next planning run. Run `holded-tt clock tick --schedule` to re-arm. It is not shown where systemd cannot be asked, and it is expected if you run `tick` from a periodic timer without `--schedule`.
- The times of events already done are the planned ones; the real tracker is in `holded-tt clock status`, and `holded-tt track show --today` shows what Holded recorded.

To remove it, `holded-tt clock uninstall` disables and deletes the units it generated and stops any armed timer. It leaves other files alone.

## Skip a day

Sick, travelling, or just not working a day that is not registered in Holded as time off? Tell `tick` not to clock it:

```bash
holded-tt clock skip                                   # today
holded-tt clock skip --date 2026-11-03                 # one day
holded-tt clock skip --from 2026-11-02 --to 2026-11-06 # a range
holded-tt clock skip --date 2026-11-03 --undo          # change your mind
```

Skipped days are stored in `skips.json` next to `config.toml`; past days are dropped from it, so it never grows. Only today and future days can be skipped.

Skipping **today** also cancels what is left of today's plan and stops the timer armed for the next event, so nothing fires later. If you were already clocked in, it tells you so: nothing will clock you out now, so run `holded-tt clock out` yourself. Undoing today's skip does not re-plan the day on its own, because the timer was stopped; it tells you to run `holded-tt clock tick --schedule` (or leave it for tomorrow's timer).

A tick also obeys the list on its own, so a timer that was somehow not stopped still clocks nothing.

## How it behaves

- **Event-driven.** With `--schedule`, each run arms a one-shot systemd timer for the **next** planned event and exits. Nothing runs or sleeps in between: about 5 runs a day, each at the planned second (random seconds per event, so entries are not always at `:00`).
- **Skips** weekends, workplace holidays and accepted time off, without touching the tracker.
- **Quiet:** with nothing due it prints nothing and makes no API call.
- **Resilient:** every step checks the real tracker in Holded first, so a missed run, a reboot or a tracker you started by hand never causes a duplicate. If you clock in by hand, the plan adopts your real start time.
- **Net hours hold:** a late clock-in (machine switched on late) or a late resume pushes the clock-out back by the same amount, so the day never nets less than the configured hours. With jitter on, a day nets between the configured hours and those plus `defaults.max_extra` minutes (default 15). Pauses vary too: each may last up to `defaults.max_pause_extra` minutes (default 5) longer than set, and the clock-out moves by the same amount, so the net hours do not change. If you clock in by hand, the day keeps its planned length from your real start, so an early manual clock-in does not make it longer.
- **Too late:** if the clock-in is more than `max_late` minutes after plan (default 90, `holded-tt config set defaults.max_late <minutes>`), the day is dropped, `tick` exits with code 3 once, and the rest of the plan is cancelled. Clock in by hand if you still want the day.
- **A tracker left open from a previous day** blocks `tick` (exit 2) until you close it.
- **Clock-out is never skipped:** if you were away at the planned time it happens as soon as `tick` runs again.

## Failures and retries

With `--schedule` nothing polls, so a failed run must not break the chain.

| Exit code | Meaning | What systemd does |
|---|---|---|
| 0 | Done, next event armed | nothing |
| 2 | Network error, expired session, systemd error | Retries every 2 minutes for about 30 minutes |
| 3 | Missed clock-in, no `systemd-run`, executable not found | Does **not** retry: retrying cannot fix it |

Every failed attempt runs `holded-tt-failed.service`, which is limited to one alert an hour. After an expired session, `holded-tt login` is enough: the next retry carries on.

If a run is killed before it can arm the next event, the chain stops until the next morning or boot run, and the alert is how you find out. `tick` only works while the machine is on and the session is valid (`holded-tt session`).

## Without a scheduler backend (macOS, or by preference)

Run `clock tick` **without** `--schedule` from a timer every 5 minutes, for example a `launchd` agent with `StartInterval=300` on macOS. It does nothing and calls nothing until something is due. The cost is that entries land on the 5-minute grid, because each event happens at the first tick after its planned time.

## Command reference

```bash
holded-tt clock tick                      # advance today's plan once
holded-tt clock plan                      # today's plan, the armed event, next planning (read-only)
holded-tt clock tick --dry-run            # show what would happen; clock and save nothing
holded-tt clock tick --schedule           # ...then arm a one-shot timer for the next event (Linux, Windows)
holded-tt clock install [--plan-at HH:MM] [--dry-run]
holded-tt clock uninstall
holded-tt clock skip [--date D | --from D --to D] [--undo]
```

## Limits

- `--schedule` and `install` need systemd (Linux) or the Task Scheduler (Windows). macOS has no backend.
- **The Windows backend is tested on a real Windows runner in CI** (task creation, replacement, the one-shot firing, removal), but not on a desktop: a console window may flash when a task runs, and a task that fires while the machine is asleep is untested. The real `holded-tt.exe` has not been run end to end by a task.
- `tick` records hours whether or not you actually worked that day. Time off registered in Holded is respected; a sick day or a trip is not.
- A timer that comes due while the machine is suspended should run when it wakes; this has not been verified.
