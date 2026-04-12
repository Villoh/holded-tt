from __future__ import annotations

import importlib
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def read_pyproject() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)


def test_package_metadata_declares_cli_script_and_dependencies() -> None:
    pyproject = read_pyproject()

    assert pyproject["project"]["scripts"]["holded"] == "holded_cli.cli:app"
    deps = pyproject["project"]["dependencies"]
    assert "typer>=0.12" in deps
    assert "httpx>=0.28" in deps
    assert "rich>=13.0" in deps
    assert "platformdirs>=4.2" in deps
    assert "tomli-w>=1.1" in deps
    assert "tzdata>=2024.1" in deps


def test_package_exports_version_and_cli_app() -> None:
    package = importlib.import_module("holded_cli")
    cli = importlib.import_module("holded_cli.cli")

    assert package.__version__ == "0.1.0"
    assert cli.app is not None
