"""Tests for export command helpers and CLI validation (EXP-01 through EXP-12)."""

from __future__ import annotations

import importlib
import json
from io import BytesIO
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook


# ---------------------------------------------------------------------------
# Pure-function tests: _fmt_duration
# ---------------------------------------------------------------------------


def test_fmt_duration_zero_returns_empty() -> None:
    export_module = importlib.import_module("holded_tt.commands.export")

    assert export_module._fmt_duration(0) == ""


def test_fmt_duration_minutes_only() -> None:
    export_module = importlib.import_module("holded_tt.commands.export")

    # 30 minutes = 1800 seconds → "00h 30m"
    assert export_module._fmt_duration(1800) == "00h 30m"


def test_fmt_duration_hours_and_minutes() -> None:
    export_module = importlib.import_module("holded_tt.commands.export")

    # 8 hours 30 minutes = 30600 seconds
    assert export_module._fmt_duration(30600) == "08h 30m"


def test_fmt_duration_ignores_seconds() -> None:
    export_module = importlib.import_module("holded_tt.commands.export")

    # 3661 seconds = 1h 1m 1s → seconds are truncated
    assert export_module._fmt_duration(3661) == "01h 01m"


def test_default_export_path_uses_base_filename_when_unused(
    tmp_path: Path, monkeypatch
) -> None:
    export_module = importlib.import_module("holded_tt.commands.export")

    monkeypatch.chdir(tmp_path)

    path = export_module._default_export_path(
        datetime(2026, 4, 1).date(),
        datetime(2026, 4, 30).date(),
        "pdf",
    )

    assert path.name == "holded-tt-2026-04-01_2026-04-30.pdf"


def test_default_export_path_uses_incremental_suffix_when_file_exists(
    tmp_path: Path, monkeypatch
) -> None:
    export_module = importlib.import_module("holded_tt.commands.export")

    monkeypatch.chdir(tmp_path)
    (tmp_path / "holded-tt-2026-04-01_2026-04-30.pdf").write_bytes(b"first")
    (tmp_path / "holded-tt-2026-04-01_2026-04-30-2.pdf").write_bytes(b"second")

    path = export_module._default_export_path(
        datetime(2026, 4, 1).date(),
        datetime(2026, 4, 30).date(),
        "pdf",
    )

    assert path.name == "holded-tt-2026-04-01_2026-04-30-3.pdf"


# ---------------------------------------------------------------------------
# Pure-function tests: _utc_to_local_hhmm
# ---------------------------------------------------------------------------


def test_utc_to_local_hhmm_converts_to_paris_time() -> None:
    export_module = importlib.import_module("holded_tt.commands.export")

    # 2026-04-13T08:30:00+00:00 → Europe/Paris in summer is UTC+2 → 10:30
    result = export_module._utc_to_local_hhmm(
        "2026-04-13T08:30:00+00:00", "Europe/Paris"
    )

    assert result == "10:30"


def test_utc_to_local_hhmm_converts_to_utc() -> None:
    export_module = importlib.import_module("holded_tt.commands.export")

    result = export_module._utc_to_local_hhmm("2026-04-13T17:00:00+00:00", "UTC")

    assert result == "17:00"


# ---------------------------------------------------------------------------
# CLI surface: input validation (no HTTP needed)
# ---------------------------------------------------------------------------


def _patch_runtime_files(base_dir: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    paths_module = importlib.import_module("holded_tt.paths")
    session_module = importlib.import_module("holded_tt.session")
    state_module = importlib.import_module("holded_tt.state")
    config_module = importlib.import_module("holded_tt.config")

    config_dir = base_dir / "holded-tt"
    config_file = config_dir / "config.toml"
    session_file = config_dir / "session.json"
    holidays_file = config_dir / "holidays.json"

    monkeypatch.setattr(paths_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(paths_module, "CONFIG_FILE", config_file)
    monkeypatch.setattr(paths_module, "SESSION_FILE", session_file)
    monkeypatch.setattr(paths_module, "HOLIDAYS_FILE", holidays_file)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
    monkeypatch.setattr(session_module, "SESSION_FILE", session_file)
    monkeypatch.setattr(state_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(state_module, "CONFIG_FILE", config_file)
    monkeypatch.setattr(state_module, "SESSION_FILE", session_file)
    monkeypatch.setattr(state_module, "HOLIDAYS_FILE", holidays_file)

    return {"session_file": session_file}


def _write_session(session_file: Path) -> None:
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(
        json.dumps(
            {
                "cookies": {"hat": "tok", "PHPSESSID": "sid"},
                "saved_at": "2026-04-10T08:00:00Z",
            }
        ),
        encoding="utf-8",
    )


def test_export_without_session_shows_auth_error(
    tmp_path: Path, runner, monkeypatch
) -> None:
    _patch_runtime_files(tmp_path, monkeypatch)
    # No session file written
    cli_module = importlib.import_module("holded_tt.cli")

    result = runner.invoke(
        cli_module.app,
        ["export", "--from", "2026-04-01", "--to", "2026-04-30"],
    )

    assert result.exit_code != 0
    assert "Traceback" not in result.stdout
    assert "holded-tt login" in result.stderr


def test_export_rejects_unknown_format(tmp_path: Path, runner, monkeypatch) -> None:
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(paths["session_file"])
    cli_module = importlib.import_module("holded_tt.cli")

    result = runner.invoke(
        cli_module.app,
        ["export", "--from", "2026-04-01", "--to", "2026-04-30", "--format", "csv"],
    )

    assert result.exit_code != 0
    assert "Traceback" not in result.stdout
    assert "csv" in result.stderr


def test_export_rejects_inverted_date_range(
    tmp_path: Path, runner, monkeypatch
) -> None:
    paths = _patch_runtime_files(tmp_path, monkeypatch)
    _write_session(paths["session_file"])
    cli_module = importlib.import_module("holded_tt.cli")

    result = runner.invoke(
        cli_module.app,
        ["export", "--from", "2026-04-30", "--to", "2026-04-01"],
    )

    assert result.exit_code != 0
    assert "Traceback" not in result.stdout


# ---------------------------------------------------------------------------
# _build_xlsx — pure bytes generation (no HTTP)
# ---------------------------------------------------------------------------


def test_build_xlsx_generates_non_empty_bytes() -> None:
    export_module = importlib.import_module("holded_tt.commands.export")

    data = [
        {
            "date": "2026-04-07",
            "trackers": [
                {
                    "start": "2026-04-07T07:30:00+00:00",
                    "end": "2026-04-07T16:30:00+00:00",
                    "time": 32400,
                    "effectiveWorkedTime": 28800,
                    "pausedTime": 3600,
                    "workplaceId": "wp-1",
                    "approvedStatus": "approved",
                    "employeeName": "Alice",
                }
            ],
            "timeoffs": [],
            "stats": {"expectedTime": 28800},
        },
        {
            "date": "2026-04-08",
            "trackers": [],
            "timeoffs": [],
            "stats": {"expectedTime": 28800},
        },
        {
            "date": "2026-04-12",  # weekend
            "trackers": [],
            "timeoffs": [],
            "stats": {},
        },
    ]

    content = export_module._build_xlsx(
        data=data,
        tz_name="UTC",
        from_date=datetime(2026, 4, 7),
        to_date=datetime(2026, 4, 8),
        workplace_map={"wp-1": "Oficina Madrid"},
        employee_name="Alice",
        company_name="ACME S.L.",
    )

    assert isinstance(content, bytes)
    assert len(content) > 0
    # xlsx files start with PK (zip magic bytes)
    assert content[:2] == b"PK"


def test_build_xlsx_with_holiday_entry() -> None:
    export_module = importlib.import_module("holded_tt.commands.export")

    data = [
        {
            "date": "2026-04-17",
            "trackers": [],
            "timeoffs": [{"name": "Viernes Santo"}],
            "stats": {},
        }
    ]

    content = export_module._build_xlsx(
        data=data,
        tz_name="UTC",
        from_date=datetime(2026, 4, 17),
        to_date=datetime(2026, 4, 17),
        workplace_map={},
        employee_name="Bob",
        company_name="",
    )

    assert isinstance(content, bytes)
    assert len(content) > 0


def test_build_xlsx_uses_date_range_title_for_multi_month_exports() -> None:
    export_module = importlib.import_module("holded_tt.commands.export")

    content = export_module._build_xlsx(
        data=[],
        tz_name="UTC",
        from_date=datetime(2026, 4, 30),
        to_date=datetime(2026, 5, 1),
        workplace_map={},
        employee_name="Alice",
        company_name="",
    )

    workbook = load_workbook(BytesIO(content))
    worksheet = workbook.active

    assert (
        worksheet["A4"].value
        == "Registros de control horario - 30/04/2026 - 01/05/2026"
    )


# ---------------------------------------------------------------------------
# Export CLI — mocked HoldedClient
# ---------------------------------------------------------------------------


def _fake_state() -> SimpleNamespace:
    config_module = importlib.import_module("holded_tt.config")
    return SimpleNamespace(
        session_store=object(),
        config=config_module.load_config(),
    )


def _patch_export_client(monkeypatch, cli_module, fake_state, **client_methods):
    export_module = importlib.import_module("holded_tt.commands.export")

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    for name, fn in client_methods.items():
        setattr(FakeClient, name, fn)

    monkeypatch.setattr(cli_module, "create_app_state", lambda: fake_state)
    monkeypatch.setattr(export_module, "HoldedClient", lambda *_: FakeClient())


def test_export_pdf_writes_file(tmp_path: Path, runner, monkeypatch) -> None:
    cli_module = importlib.import_module("holded_tt.cli")
    fake_pdf = b"%PDF-1.4 fake"
    _patch_export_client(
        monkeypatch,
        cli_module,
        _fake_state(),
        get_timetracking_pdf=lambda self, *_: fake_pdf,
    )
    out_file = tmp_path / "report.pdf"

    result = runner.invoke(
        cli_module.app,
        [
            "export",
            "--from",
            "2026-04-01",
            "--to",
            "2026-04-30",
            "--format",
            "pdf",
            "--out",
            str(out_file),
        ],
    )

    assert result.exit_code == 0
    assert out_file.exists()
    assert out_file.read_bytes() == fake_pdf


def test_export_xlsx_writes_file(tmp_path: Path, runner, monkeypatch) -> None:
    cli_module = importlib.import_module("holded_tt.cli")

    fake_data = [
        {
            "date": "2026-04-07",
            "trackers": [
                {
                    "start": "2026-04-07T07:30:00+00:00",
                    "end": "2026-04-07T16:30:00+00:00",
                    "time": 32400,
                    "effectiveWorkedTime": 28800,
                    "pausedTime": 0,
                    "workplaceId": "wp-1",
                    "approvedStatus": None,
                    "employeeName": "Alice",
                }
            ],
            "timeoffs": [],
            "stats": {"expectedTime": 28800},
        }
    ]
    fake_workplaces = [{"id": "wp-1", "name": "Oficina"}]

    _patch_export_client(
        monkeypatch,
        cli_module,
        _fake_state(),
        get_timetracking_data=lambda self, *_: fake_data,
        get_workplaces=lambda self: fake_workplaces,
    )
    out_file = tmp_path / "report.xlsx"

    result = runner.invoke(
        cli_module.app,
        [
            "export",
            "--from",
            "2026-04-07",
            "--to",
            "2026-04-07",
            "--format",
            "xlsx",
            "--out",
            str(out_file),
        ],
    )

    assert result.exit_code == 0
    assert out_file.exists()
    assert out_file.stat().st_size > 0


def test_export_pdf_without_out_uses_unsuffixed_default_filename(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_tt.cli")
    fake_pdf = b"%PDF-1.4 fake"

    _patch_export_client(
        monkeypatch,
        cli_module,
        _fake_state(),
        get_timetracking_pdf=lambda self, *_: fake_pdf,
    )
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        cli_module.app,
        [
            "export",
            "--from",
            "2026-04-01",
            "--to",
            "2026-04-30",
            "--format",
            "pdf",
        ],
    )

    out_file = tmp_path / "holded-tt-2026-04-01_2026-04-30.pdf"

    assert result.exit_code == 0
    assert out_file.exists()
    assert out_file.read_bytes() == fake_pdf


def test_export_pdf_without_out_uses_incremental_suffix_when_needed(
    tmp_path: Path, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_tt.cli")
    fake_pdf = b"%PDF-1.4 fake"

    _patch_export_client(
        monkeypatch,
        cli_module,
        _fake_state(),
        get_timetracking_pdf=lambda self, *_: fake_pdf,
    )
    monkeypatch.chdir(tmp_path)
    (tmp_path / "holded-tt-2026-04-01_2026-04-30.pdf").write_bytes(b"existing")

    result = runner.invoke(
        cli_module.app,
        [
            "export",
            "--from",
            "2026-04-01",
            "--to",
            "2026-04-30",
            "--format",
            "pdf",
        ],
    )

    out_file = tmp_path / "holded-tt-2026-04-01_2026-04-30-2.pdf"

    assert result.exit_code == 0
    assert out_file.exists()
    assert out_file.read_bytes() == fake_pdf
