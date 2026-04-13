from __future__ import annotations

from pathlib import Path

from platformdirs import user_config_path


CONFIG_DIR: Path = user_config_path(
    "holded-tt-cli", appauthor=False, roaming=True, ensure_exists=True
)
CONFIG_FILE: Path = CONFIG_DIR / "config.toml"
SESSION_FILE: Path = CONFIG_DIR / "session.json"
HOLIDAYS_FILE: Path = CONFIG_DIR / "holidays.json"
