from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import SimpleNamespace

from holded_tt_cli.errors import HoldedCliError


@dataclass
class DummyLoginStep:
    two_factor_required: bool
    masked_contact: str | None = None


class FakeSessionStore:
    def __init__(self) -> None:
        self.saved_payload: dict[str, object] | None = None

    def save(self, cookies: dict[str, str]) -> dict[str, object]:
        self.saved_payload = {"cookies": cookies, "saved_at": "2026-04-12T12:00:00Z"}
        return self.saved_payload


def test_login_prompts_for_two_factor_only_when_required(runner, monkeypatch) -> None:
    cli_module = importlib.import_module("holded_tt_cli.cli")
    login_module = importlib.import_module("holded_tt_cli.commands.login")

    session_store = FakeSessionStore()
    state = SimpleNamespace(session_store=session_store)
    events: list[tuple[str, str, str | None]] = []

    class FakeAuthClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def bootstrap(self) -> None:
            events.append(("bootstrap", "", None))

        def primary_login(self, email: str, password: str) -> DummyLoginStep:
            events.append(("primary", email, password))
            return DummyLoginStep(True, "confirm-token")

        def confirm_two_factor(self, code: str, email: str) -> None:
            events.append(("confirm", code, email))

        def export_cookies(self) -> dict[str, str]:
            return {"hat": "redacted"}

    monkeypatch.setattr(cli_module, "create_app_state", lambda: state)
    monkeypatch.setattr(login_module, "HoldedAuthClient", FakeAuthClient)

    result = runner.invoke(
        cli_module.app,
        ["login"],
        input="dweller@example.com\nsecret-password\n123456\n",
    )

    assert result.exit_code == 0
    assert "Email" in result.stdout
    assert "Password" in result.stdout
    assert "2FA code" in result.stdout
    assert "Authenticated" in result.stdout
    assert "2026-04-12T12:00:00Z" in result.stdout
    assert session_store.saved_payload == {
        "cookies": {"hat": "redacted"},
        "saved_at": "2026-04-12T12:00:00Z",
    }
    assert events == [
        ("bootstrap", "", None),
        ("primary", "dweller@example.com", "secret-password"),
        ("confirm", "123456", "dweller@example.com"),
    ]
    assert "redacted" not in result.stdout
    assert "secret-password" not in result.stdout


def test_login_skips_two_factor_prompt_when_not_required(runner, monkeypatch) -> None:
    cli_module = importlib.import_module("holded_tt_cli.cli")
    login_module = importlib.import_module("holded_tt_cli.commands.login")

    session_store = FakeSessionStore()
    state = SimpleNamespace(session_store=session_store)
    confirmed: list[bool] = []

    class FakeAuthClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def bootstrap(self) -> None:
            return None

        def primary_login(self, email: str, password: str) -> DummyLoginStep:
            return DummyLoginStep(False, None)

        def confirm_two_factor(self, code: str, email: str) -> None:
            confirmed.append(True)

        def export_cookies(self) -> dict[str, str]:
            return {"hat": "redacted"}

    monkeypatch.setattr(cli_module, "create_app_state", lambda: state)
    monkeypatch.setattr(login_module, "HoldedAuthClient", FakeAuthClient)

    result = runner.invoke(
        cli_module.app,
        ["login"],
        input="dweller@example.com\nsecret-password\n",
    )

    assert result.exit_code == 0
    assert "2FA code" not in result.stdout
    assert confirmed == []


def test_login_surfaces_auth_failures_without_traceback(runner, monkeypatch) -> None:
    cli_module = importlib.import_module("holded_tt_cli.cli")
    login_module = importlib.import_module("holded_tt_cli.commands.login")

    state = SimpleNamespace(session_store=FakeSessionStore())

    class FakeAuthClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def bootstrap(self) -> None:
            return None

        def primary_login(self, email: str, password: str) -> DummyLoginStep:
            raise HoldedCliError(
                message="Authentication failed.",
                hint="Run `holded-tt login` again after checking your credentials.",
            )

    monkeypatch.setattr(cli_module, "create_app_state", lambda: state)
    monkeypatch.setattr(login_module, "HoldedAuthClient", FakeAuthClient)

    result = runner.invoke(
        cli_module.app,
        ["login"],
        input="dweller@example.com\nsecret-password\n",
    )

    assert result.exit_code == 2
    assert "Error: Authentication failed." in result.stderr
    assert (
        "Hint: Run `holded-tt login` again after checking your credentials."
        in result.stderr
    )
    assert "Traceback" not in result.stderr
