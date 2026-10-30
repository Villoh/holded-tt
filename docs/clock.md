# `holded-tt clock`
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

## Automatic clocking

`clock tick`, `clock install` and `clock uninstall` run all of the above for you on a schedule, with jitter, skipping weekends, holidays and time off. `clock skip` rules out a day by hand. See [Automatic clocking](automation.md).
