# holidays command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `holded-tt holidays [--year YYYY] [--refresh]` as a top-level CLI command that shows workplace holidays using the existing JSON cache, fetching from the Holded API only when needed.

**Architecture:** New `src/holded_tt/commands/holidays.py` with a single `holidays_command` function. Reuses existing `get_cached_holidays`, `extract_workplace_holidays`, `_save_cache`, and `_current_year_paris` from `holidays.py`. Registered in `cli.py` following the exact pattern of `workplaces_command`.

**Tech Stack:** Python 3.11+, Typer, Rich, httpx (via `HoldedClient`), existing `holded_tt.holidays` cache helpers.

---

## File Map

| Action | File |
|--------|------|
| Create | `src/holded_tt/commands/holidays.py` |
| Create | `tests/test_holidays_command.py` |
| Modify | `src/holded_tt/commands/__init__.py` — export `holidays_command` |
| Modify | `src/holded_tt/cli.py` — register `holded-tt holidays` |
| Modify | `tests/conftest.py` — add `holded_tt.commands.holidays` to module purge list |
| Modify | `tests/test_cli_surface.py` — assert `"holidays"` appears in root `--help` |

---

### Task 1: Write failing tests for `holidays_command`

**Files:**
- Create: `tests/test_holidays_command.py`

- [ ] **Step 1: Create the test file**

```python
"""Tests for holidays command (HOL-01 through HOL-05)."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace


def _fake_state(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        session_store=object(),
        holidays_file=tmp_path / "holidays.json",
    )


def _patch_cli(monkeypatch, fake_state):
    cli_module = importlib.import_module("holded_tt.cli")
    monkeypatch.setattr(cli_module, "create_app_state", lambda: fake_state)
    return cli_module


def _patch_client(monkeypatch, fake_client_instance):
    holidays_module = importlib.import_module("holded_tt.commands.holidays")
    monkeypatch.setattr(
        holidays_module, "HoldedClient", lambda *_: fake_client_instance
    )


class _FakeClient:
    def __init__(self, summary: dict):
        self._summary = summary

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def get_year_summary(self, year):
        return self._summary


def test_holidays_cache_hit_shows_table_and_cached_status(
    runner, monkeypatch, tmp_path
) -> None:
    """HOL-01: Cache hit — shows holidays from cache, status line says 'cached'."""
    state = _fake_state(tmp_path)
    state.holidays_file.write_text(
        json.dumps({"year": 2026, "holidays": ["2026-01-01", "2026-04-17"]}),
        encoding="utf-8",
    )
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["holidays", "--year", "2026"])

    assert result.exit_code == 0
    assert "2026-01-01" in result.stdout
    assert "2026-04-17" in result.stdout
    assert "cached" in result.stdout


def test_holidays_cache_miss_fetches_from_api_and_shows_fetched(
    runner, monkeypatch, tmp_path
) -> None:
    """HOL-02: Cache miss — calls API, saves cache, status says 'fetched'."""
    state = _fake_state(tmp_path)
    summary = {
        "workplaceTimeOffs": [
            {
                "assignationType": "workplace",
                "status": "accepted",
                "date": "2026-04-17",
            }
        ]
    }
    _patch_client(monkeypatch, _FakeClient(summary))
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["holidays", "--year", "2026"])

    assert result.exit_code == 0
    assert "2026-04-17" in result.stdout
    assert "fetched" in result.stdout
    assert state.holidays_file.exists()


def test_holidays_refresh_bypasses_cache_and_shows_refreshed(
    runner, monkeypatch, tmp_path
) -> None:
    """HOL-03: --refresh — calls API even when valid cache exists, status says 'refreshed'."""
    state = _fake_state(tmp_path)
    state.holidays_file.write_text(
        json.dumps({"year": 2026, "holidays": ["2026-01-01"]}),
        encoding="utf-8",
    )
    api_calls: list[int] = []

    class TrackingClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get_year_summary(self, year):
            api_calls.append(1)
            return {
                "workplaceTimeOffs": [
                    {
                        "assignationType": "workplace",
                        "status": "accepted",
                        "date": "2026-04-17",
                    }
                ]
            }

    holidays_module = importlib.import_module("holded_tt.commands.holidays")
    monkeypatch.setattr(
        holidays_module, "HoldedClient", lambda *_: TrackingClient()
    )
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["holidays", "--year", "2026", "--refresh"])

    assert result.exit_code == 0
    assert api_calls == [1]
    assert "refreshed" in result.stdout


def test_holidays_year_flag_passes_correct_year_to_api(
    runner, monkeypatch, tmp_path
) -> None:
    """HOL-04: --year — the specified year is passed to the API call."""
    state = _fake_state(tmp_path)
    received_years: list[int] = []

    class TrackingClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get_year_summary(self, year):
            received_years.append(year)
            return {}

    holidays_module = importlib.import_module("holded_tt.commands.holidays")
    monkeypatch.setattr(
        holidays_module, "HoldedClient", lambda *_: TrackingClient()
    )
    cli = _patch_cli(monkeypatch, state)

    runner.invoke(cli.app, ["holidays", "--year", "2025"])

    assert received_years == [2025]


def test_holidays_empty_result_prints_no_holidays_message(
    runner, monkeypatch, tmp_path
) -> None:
    """HOL-05: No holidays — prints 'No holidays found', exits 0."""
    state = _fake_state(tmp_path)
    _patch_client(monkeypatch, _FakeClient({}))
    cli = _patch_cli(monkeypatch, state)

    result = runner.invoke(cli.app, ["holidays", "--year", "2026"])

    assert result.exit_code == 0
    assert "No holidays found" in result.stdout
```

- [ ] **Step 2: Run tests — expect ModuleNotFoundError (red)**

Run: `.venv/Scripts/python.exe -m pytest tests/test_holidays_command.py -v`

Expected: ERRORS — `ModuleNotFoundError: No module named 'holded_tt.commands.holidays'`

---

### Task 2: Implement `holidays_command`

**Files:**
- Create: `src/holded_tt/commands/holidays.py`

- [ ] **Step 1: Create the command module**

```python
from __future__ import annotations

from datetime import date
from typing import Optional

import typer
from rich import box as rich_box
from rich.table import Table
from rich.text import Text

from holded_tt.console import get_output_console
from holded_tt.holded_client import HoldedClient
from holded_tt.holidays import (
    _current_year_paris,
    _save_cache,
    extract_workplace_holidays,
    get_cached_holidays,
)
from holded_tt.state import AppState


def holidays_command(
    ctx: typer.Context,
    year: Optional[int] = typer.Option(
        None, "--year", help="Year to fetch holidays for (default: current year)."
    ),
    refresh: bool = typer.Option(
        False, "--refresh", help="Bypass cache and fetch from Holded API."
    ),
) -> None:
    """Show workplace holidays for a given year, using local cache when available."""
    state: AppState = ctx.obj
    console = get_output_console()

    target_year = year if year is not None else _current_year_paris()

    holidays: frozenset[date] | None = None
    source: str

    if not refresh:
        holidays = get_cached_holidays(state.holidays_file, target_year)
        source = "cached"

    if holidays is None:
        with HoldedClient(state.session_store) as client:
            summary = client.get_year_summary(target_year)
        holidays = extract_workplace_holidays(summary, target_year)
        _save_cache(
            state.holidays_file,
            target_year,
            sorted(d.isoformat() for d in holidays),
        )
        source = "refreshed" if refresh else "fetched"

    if not holidays:
        console.print(f"[dim]No holidays found for {target_year}.[/dim]")
        raise typer.Exit(0)

    sorted_holidays = sorted(holidays)

    table = Table(
        show_header=True,
        header_style="bold",
        box=rich_box.SIMPLE_HEAD,
        padding=(0, 2),
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Date", min_width=12)
    table.add_column("Day", min_width=11, style="dim")

    for i, d in enumerate(sorted_holidays, 1):
        table.add_row(str(i), d.isoformat(), d.strftime("%A"))

    console.print(table)

    summary_line = Text()
    summary_line.append(
        f"{len(sorted_holidays)} holiday(s)  ·  {target_year}  ·  {source}",
        style="dim",
    )
    console.print(summary_line)
```

---

### Task 3: Wire up the CLI

**Files:**
- Modify: `src/holded_tt/commands/__init__.py`
- Modify: `src/holded_tt/cli.py`

- [ ] **Step 1: Export from `commands/__init__.py`**

Add to `src/holded_tt/commands/__init__.py`:

```python
from holded_tt.commands.holidays import holidays_command
```

Add `"holidays_command"` to the `__all__` list.

Full updated file:

```python
from __future__ import annotations

from holded_tt.commands.clock import app as clock_app
from holded_tt.commands.config import app as config_app
from holded_tt.commands.employee import employee_command
from holded_tt.commands.employees import employees_command
from holded_tt.commands.export import export_command
from holded_tt.commands.holidays import holidays_command
from holded_tt.commands.login import login_command
from holded_tt.commands.session import session_command
from holded_tt.commands.track import app as track_app
from holded_tt.commands.track import track_command, track_update_command
from holded_tt.commands.workplaces import workplaces_command

__all__ = [
    "clock_app",
    "config_app",
    "employee_command",
    "employees_command",
    "export_command",
    "holidays_command",
    "login_command",
    "session_command",
    "track_app",
    "track_command",
    "track_update_command",
    "workplaces_command",
]
```

- [ ] **Step 2: Register in `cli.py`**

Add the import to `cli.py`:

```python
from holded_tt.commands import (
    clock_app,
    employee_command,
    employees_command,
    export_command,
    holidays_command,
    login_command,
    session_command,
    track_app,
    workplaces_command,
)
```

Add the command registration after the `export_command` registration (around line 107):

```python
app.command(
    "holidays",
    help="Show workplace holidays, using local cache when available.",
)(_with_cli_error_handling(holidays_command))
```

- [ ] **Step 3: Run the holidays command tests — expect all 5 to pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_holidays_command.py -v`

Expected:
```
PASSED tests/test_holidays_command.py::test_holidays_cache_hit_shows_table_and_cached_status
PASSED tests/test_holidays_command.py::test_holidays_cache_miss_fetches_from_api_and_shows_fetched
PASSED tests/test_holidays_command.py::test_holidays_refresh_bypasses_cache_and_shows_refreshed
PASSED tests/test_holidays_command.py::test_holidays_year_flag_passes_correct_year_to_api
PASSED tests/test_holidays_command.py::test_holidays_empty_result_prints_no_holidays_message
5 passed
```

- [ ] **Step 4: Commit**

```bash
git add src/holded_tt/commands/holidays.py src/holded_tt/commands/__init__.py src/holded_tt/cli.py tests/test_holidays_command.py
git commit -m "feat: add holidays command with --year and --refresh flags"
```

---

### Task 4: Update surface tests and conftest

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_cli_surface.py`

- [ ] **Step 1: Add module to conftest purge list**

In `tests/conftest.py`, add `"holded_tt.commands.holidays"` to the `sys.modules.pop` loop inside `temp_config_dir`:

```python
for module_name in [
    "holded_tt",
    "holded_tt.cli",
    "holded_tt.paths",
    "holded_tt.config",
    "holded_tt.state",
    "holded_tt.session",
    "holded_tt.commands",
    "holded_tt.commands.config",
    "holded_tt.commands.employee",
    "holded_tt.commands.holidays",
    "holded_tt.commands.login",
    "holded_tt.commands.session",
    "holded_tt.commands.track",
    "holded_tt.commands.workplaces",
]:
    sys.modules.pop(module_name, None)
```

- [ ] **Step 2: Assert `holidays` appears in root `--help`**

In `tests/test_cli_surface.py`, find `test_root_help_is_available` and add:

```python
assert "holidays" in output
```

alongside the existing `assert "workplaces" in output` line.

- [ ] **Step 3: Run full test suite — expect 224 passed (219 + 5 new)**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q --no-header`

Expected: `224 passed`

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/test_cli_surface.py
git commit -m "test: assert holidays in CLI surface and purge module in conftest"
```
