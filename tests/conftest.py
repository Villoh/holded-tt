from __future__ import annotations

from pathlib import Path
import sys

import pytest
from typer.testing import CliRunner


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def temp_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_dir = tmp_path / "config-home"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir))
    monkeypatch.setenv("LOCALAPPDATA", str(config_dir))
    monkeypatch.setenv("APPDATA", str(config_dir))

    for module_name in [
        "holded_tt_cli",
        "holded_tt_cli.cli",
        "holded_tt_cli.paths",
        "holded_tt_cli.config",
        "holded_tt_cli.state",
        "holded_tt_cli.session",
        "holded_tt_cli.commands",
        "holded_tt_cli.commands.config",
        "holded_tt_cli.commands.employee",
        "holded_tt_cli.commands.login",
        "holded_tt_cli.commands.session",
        "holded_tt_cli.commands.track",
        "holded_tt_cli.commands.workplaces",
    ]:
        sys.modules.pop(module_name, None)

    return config_dir
