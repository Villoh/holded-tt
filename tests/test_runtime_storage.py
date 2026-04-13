from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest


@pytest.fixture()
def runtime_paths_module(temp_config_dir):
    import importlib
    import sys

    for module_name in [
        "holded_cli.paths",
        "holded_cli.config",
        "holded_cli.session",
    ]:
        sys.modules.pop(module_name, None)

    return importlib.import_module("holded_cli.paths")


def test_runtime_paths_use_fixed_files_and_create_config_dir(
    runtime_paths_module,
) -> None:
    paths = runtime_paths_module

    assert paths.CONFIG_DIR.exists()
    assert paths.CONFIG_FILE.name == "config.toml"
    assert paths.SESSION_FILE.name == "session.json"
    assert paths.HOLIDAYS_FILE.name == "holidays.json"
    assert paths.CONFIG_FILE.parent == paths.CONFIG_DIR
    assert paths.SESSION_FILE.parent == paths.CONFIG_DIR
    assert paths.HOLIDAYS_FILE.parent == paths.CONFIG_DIR


def test_config_load_and_save_preserve_defaults(temp_config_dir) -> None:
    from holded_cli import config as config_module

    config_file = Path(temp_config_dir) / "holded-cli" / "config.toml"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_module.CONFIG_FILE = config_file

    AppConfig = config_module.AppConfig
    load_config = config_module.load_config
    save_config = config_module.save_config

    config = load_config()
    assert config == AppConfig(
        workplace_id="",
        start="08:30",
        end="17:30",
        timezone="Europe/Paris",
    )

    updated = AppConfig(
        workplace_id="wp-123",
        start="09:00",
        end="18:00",
        timezone="Europe/Paris",
    )
    save_config(updated)

    assert load_config() == updated


def test_session_store_persists_cookies_and_saved_at(
    temp_config_dir, monkeypatch
) -> None:
    from holded_cli import session as session_module

    chmod_calls: list[tuple[object, int]] = []

    def fake_chmod(path, mode: int) -> None:
        chmod_calls.append((path, mode))
        raise PermissionError("best-effort only")

    session_file = Path(temp_config_dir) / "holded-cli" / "session.json"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(session_module, "SESSION_FILE", session_file)
    monkeypatch.setattr(session_module.os, "chmod", fake_chmod)

    SessionStore = session_module.SessionStore

    store = SessionStore()
    store.save({"hat": "secret", "PHPSESSID": "abc"})

    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert payload["cookies"] == {"hat": "secret", "PHPSESSID": "abc"}
    assert payload["saved_at"].endswith("Z")
    assert chmod_calls == [(store.path, stat.S_IRUSR | stat.S_IWUSR)]

    reloaded = store.load()
    assert reloaded["cookies"] == {"hat": "secret", "PHPSESSID": "abc"}
    assert reloaded["saved_at"] == payload["saved_at"]


def test_session_store_loads_missing_files_as_empty_state(temp_config_dir) -> None:
    from holded_cli import session as session_module

    session_file = Path(temp_config_dir) / "holded-cli" / "session.json"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_module.SESSION_FILE = session_file

    SessionStore = session_module.SessionStore

    store = SessionStore()

    assert store.load() == {"cookies": {}, "saved_at": None}


def test_session_store_reports_presence_from_loaded_state(temp_config_dir) -> None:
    from holded_cli import session as session_module

    session_file = Path(temp_config_dir) / "holded-cli" / "session.json"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(
        json.dumps({"cookies": {"hat": "secret"}, "saved_at": "2026-04-13T10:00:00Z"}),
        encoding="utf-8",
    )
    session_module.SESSION_FILE = session_file

    store = session_module.SessionStore()

    assert store.is_present() is True
    assert store.saved_at() == "2026-04-13T10:00:00Z"


def test_config_get_state_rejects_non_app_state() -> None:
    import click
    import typer

    from holded_cli.commands.config import _get_state

    ctx = typer.Context(click.Command("config"))
    ctx.obj = object()

    with pytest.raises(RuntimeError, match="AppState is not available"):
        _get_state(ctx)
