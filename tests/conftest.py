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
        "holded_cli",
        "holded_cli.cli",
        "holded_cli.paths",
        "holded_cli.config",
        "holded_cli.state",
        "holded_cli.session",
        "holded_cli.commands",
        "holded_cli.commands.config",
        "holded_cli.commands.login",
        "holded_cli.commands.session",
        "holded_cli.commands.track",
        "holded_cli.commands.workplaces",
    ]:
        sys.modules.pop(module_name, None)

    return config_dir
