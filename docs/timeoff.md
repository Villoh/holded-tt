# `holded-tt timeoff`
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
