from __future__ import annotations

from dataclasses import asdict, dataclass, field
import tomllib

import tomli_w

from holded_tt_cli.paths import CONFIG_FILE


@dataclass(slots=True)
class AppConfig:
    workplace_id: str = ""
    start: str = "08:30"
    end: str = "17:30"
    timezone: str = "Europe/Paris"
    pause: list[str] = field(default_factory=list)


def load_config() -> AppConfig:
    if not CONFIG_FILE.exists():
        config = AppConfig()
        save_config(config)
        return config

    with CONFIG_FILE.open("rb") as file:
        data = tomllib.load(file)

    pause = data.get("pause", [])
    data["pause"] = (
        [item for item in pause if isinstance(item, str)]
        if isinstance(pause, list)
        else []
    )

    return AppConfig(**data)


def save_config(config: AppConfig) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

    with CONFIG_FILE.open("wb") as file:
        tomli_w.dump(asdict(config), file)
