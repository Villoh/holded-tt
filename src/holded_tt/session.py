from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import stat
from pathlib import Path

from holded_tt.paths import SESSION_FILE


EMPTY_SESSION = {"cookies": {}, "saved_at": None}


@dataclass(slots=True)
class SessionStore:
    path: Path = field(default_factory=lambda: SESSION_FILE)
    _state: dict[str, object] = field(
        default_factory=lambda: EMPTY_SESSION.copy(), init=False
    )
    _loaded: bool = field(default=False, init=False)

    def load(self) -> dict[str, object]:
        if self._loaded:
            return self._state

        if not self.path.exists():
            # Allow tests and other in-memory callers to pre-seed the store
            # without requiring a backing file on disk.
            cookies = self._state.get("cookies")
            if isinstance(cookies, dict) and cookies:
                self._loaded = True
                return self._state

            self._state = EMPTY_SESSION.copy()
            self._loaded = True
            return self._state

        self._state = json.loads(self.path.read_text(encoding="utf-8"))
        self._loaded = True
        return self._state

    def save(self, cookies: dict[str, str]) -> dict[str, object]:
        payload = {
            "cookies": cookies,
            "saved_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        try:
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

        self._state = payload
        self._loaded = True
        return payload

    def is_present(self) -> bool:
        state = self.load()
        return bool(state["cookies"])

    def saved_at(self) -> str | None:
        state = self.load()
        saved_at = state["saved_at"]
        return saved_at if isinstance(saved_at, str) else None
