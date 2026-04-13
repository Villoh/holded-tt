from __future__ import annotations

import importlib
import pytest
from pathlib import Path


def _patch_runtime_files(base_dir: Path, monkeypatch) -> None:
    paths_module = importlib.import_module("holded_cli.paths")
    config_module = importlib.import_module("holded_cli.config")
    session_module = importlib.import_module("holded_cli.session")
    state_module = importlib.import_module("holded_cli.state")

    config_dir = base_dir / "holded-cli"
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


def test_version_reports_package_version(runner) -> None:
    package = importlib.import_module("holded_cli")
    cli_module = importlib.import_module("holded_cli.cli")

    result = runner.invoke(cli_module.app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == package.__version__


def test_root_help_is_available(runner) -> None:
    cli_module = importlib.import_module("holded_cli.cli")

    result = runner.invoke(cli_module.app, ["--help"])

    assert result.exit_code == 0
    assert "Holded time-tracking CLI." in result.stdout
    assert "login" in result.stdout
    assert "session" in result.stdout
    assert "workplaces" in result.stdout
    assert "employee" in result.stdout
    assert "organization" in result.stdout
    assert "personal-info" not in result.stdout
    assert " whoami " not in result.stdout
    assert "track" in result.stdout
    assert "config" in result.stdout
    assert "export" in result.stdout
    assert "clock" in result.stdout


def test_root_callback_bootstraps_shared_state(
    temp_config_dir, runner, monkeypatch
) -> None:
    del temp_config_dir
    cli_module = importlib.import_module("holded_cli.cli")
    state_module = importlib.import_module("holded_cli.state")

    calls: list[bool] = []
    sentinel_state = state_module.AppState(
        config=state_module.load_config(),
        session_store=state_module.SessionStore(),
        config_dir=state_module.CONFIG_DIR,
        config_file=state_module.CONFIG_FILE,
        session_file=state_module.SESSION_FILE,
        holidays_file=state_module.HOLIDAYS_FILE,
    )

    def fake_create_app_state() -> state_module.AppState:
        calls.append(True)
        sentinel_state.config_dir.mkdir(parents=True, exist_ok=True)
        return sentinel_state

    monkeypatch.setattr(cli_module, "create_app_state", fake_create_app_state)

    result = runner.invoke(cli_module.app, [])

    assert result.exit_code == 0
    assert calls == [True]
    assert sentinel_state.config_dir.exists()


def test_track_help_includes_usage_example(runner) -> None:
    cli_module = importlib.import_module("holded_cli.cli")

    result = runner.invoke(cli_module.app, ["track", "--help"])

    assert result.exit_code == 0
    assert "holded track --from 2026-04-01 --to 2026-04-30" in result.stdout
    assert "show" in result.stdout
    assert "update" in result.stdout


def test_config_help_lists_show_and_set(runner) -> None:
    cli_module = importlib.import_module("holded_cli.cli")

    result = runner.invoke(cli_module.app, ["config", "--help"])

    assert result.exit_code == 0
    assert "show" in result.stdout
    assert "set" in result.stdout


def test_config_without_subcommand_defaults_to_show(
    temp_config_dir, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    _patch_runtime_files(temp_config_dir, monkeypatch)

    result = runner.invoke(cli_module.app, ["config"])

    assert result.exit_code == 0
    assert "Configuration" in result.stdout
    assert "workplace_id" in result.stdout


def test_workplaces_without_session_shows_auth_error(
    tmp_path: Path, runner, monkeypatch
) -> None:
    _patch_runtime_files(tmp_path, monkeypatch)
    # No session file written → MissingAuthenticationError
    cli_module = importlib.import_module("holded_cli.cli")

    result = runner.invoke(cli_module.app, ["workplaces"])

    # No session → operational error (exit 2) with a plain-language hint
    assert result.exit_code == 2
    assert "Traceback" not in result.stdout
    assert "holded login" in result.stderr


def test_config_show_prints_defaults_and_local_paths(
    temp_config_dir, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    _patch_runtime_files(temp_config_dir, monkeypatch)

    result = runner.invoke(cli_module.app, ["config", "show"])

    assert result.exit_code == 0
    assert "workplace_id" in result.stdout
    assert "08:30" in result.stdout
    assert "17:30" in result.stdout
    assert "Europe/Paris" in result.stdout
    assert "config" in result.stdout
    assert "session" in result.stdout
    assert "holidays" in result.stdout


def test_config_set_persists_allowed_keys(temp_config_dir, runner, monkeypatch) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    config_module = importlib.import_module("holded_cli.config")
    _patch_runtime_files(temp_config_dir, monkeypatch)

    result = runner.invoke(
        cli_module.app,
        ["config", "set", "defaults.workplace_id", "123"],
    )

    assert result.exit_code == 0
    assert "defaults.workplace_id" in result.stdout
    assert "123" in result.stdout
    assert config_module.load_config().workplace_id == "123"


def test_config_set_rejects_unknown_keys_with_friendly_error(
    temp_config_dir, runner, monkeypatch
) -> None:
    cli_module = importlib.import_module("holded_cli.cli")
    _patch_runtime_files(temp_config_dir, monkeypatch)

    result = runner.invoke(
        cli_module.app,
        ["config", "set", "defaults.unknown", "123"],
    )

    assert result.exit_code == 1
    assert "Error:" in result.stderr
    assert "Hint:" in result.stderr
    assert "Traceback" not in result.stderr
