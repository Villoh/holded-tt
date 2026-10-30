# `holded-tt export`
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
