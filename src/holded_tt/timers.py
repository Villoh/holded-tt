"""One front for the platform's scheduler: systemd on Linux, Task Scheduler on Windows.

`clock install`, `--schedule`, `skip` and `plan` call these; each forwards to the backend for
the current platform. macOS has no backend, so it gets the systemd one and its clear
"needs systemd" error, and runs `clock tick` from a periodic job instead.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from types import ModuleType
from typing import Any

from holded_tt import units, wintasks


def backend() -> ModuleType:
    return wintasks if sys.platform == "win32" else units


def install(exe: str, plan_at: str = "06:00", dry_run: bool = False) -> list[str]:
    return backend().install(exe, plan_at, dry_run)


def uninstall() -> list[str]:
    return backend().uninstall()


def arm_at(when: datetime, exe: str, run: Any = subprocess.run) -> None:
    backend().arm_at(when, exe, run)


def armed_events() -> list[datetime] | None:
    return backend().armed_events()


def next_planning() -> str | None:
    return backend().next_planning()


def disarm() -> None:
    backend().disarm()


def retries_natively() -> bool:
    """Does the scheduler itself retry a failed run? (systemd yes, Task Scheduler no.)"""
    return bool(backend().RETRIES_NATIVELY)
