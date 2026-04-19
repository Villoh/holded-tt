from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from holded_tt.config import AppConfig, load_config
from holded_tt.paths import CONFIG_DIR, CONFIG_FILE, HOLIDAYS_FILE, SESSION_FILE
from holded_tt.session import SessionStore


@dataclass(slots=True)
class AppState:
    config: AppConfig
    session_store: SessionStore
    config_dir: Path
    config_file: Path
    session_file: Path
    holidays_file: Path


def create_app_state() -> AppState:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    return AppState(
        config=load_config(),
        session_store=SessionStore(),
        config_dir=CONFIG_DIR,
        config_file=CONFIG_FILE,
        session_file=SESSION_FILE,
        holidays_file=HOLIDAYS_FILE,
    )
