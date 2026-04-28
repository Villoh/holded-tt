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

    return config_dir
