"""Tests for HoldedClient internal helpers (HC-01 through HC-04)."""

from __future__ import annotations

from datetime import date, time

import httpx
import pytest


def test_make_datetime_param_includes_utc_offset() -> None:
    from holded_cli.holded_client import _make_datetime_param

    result = _make_datetime_param(date(2026, 4, 7), time(8, 30, 0), "UTC")

    assert result.startswith("2026-04-07T08:30:00")
    assert "+00:00" in result


def test_make_datetime_param_applies_timezone_offset() -> None:
    from holded_cli.holded_client import _make_datetime_param

    # Europe/Paris in summer is UTC+2 → 08:30 local = 06:30 UTC offset +02:00
    result = _make_datetime_param(date(2026, 4, 7), time(8, 30, 0), "Europe/Paris")

    assert "2026-04-07T08:30:00" in result
    assert "+02:00" in result


def test_check_auth_raises_on_401_response() -> None:
    from holded_cli.auth import MissingAuthenticationError
    from holded_cli.holded_client import HoldedClient
    from holded_cli.session import SessionStore

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, request=request)

    store = SessionStore()
    store._state = {"cookies": {"hat": "tok"}, "saved_at": "2026-04-10T08:00:00Z"}

    with HoldedClient(store, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MissingAuthenticationError):
            client.get_workplaces()


def test_check_auth_raises_on_html_response() -> None:
    """Holded returns HTTP 200 with an HTML login page on session expiry."""
    from holded_cli.auth import MissingAuthenticationError
    from holded_cli.holded_client import HoldedClient
    from holded_cli.session import SessionStore

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html><body>Login</body></html>",
            headers={"content-type": "text/html; charset=utf-8"},
            request=request,
        )

    store = SessionStore()
    store._state = {"cookies": {"hat": "tok"}, "saved_at": "2026-04-10T08:00:00Z"}

    with HoldedClient(store, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MissingAuthenticationError):
            client.get_workplaces()


def test_parse_json_raises_on_invalid_json_body() -> None:
    from holded_cli.holded_client import HoldedApiError, HoldedClient
    from holded_cli.session import SessionStore

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", request=request)

    store = SessionStore()
    store._state = {"cookies": {"hat": "tok"}, "saved_at": "2026-04-10T08:00:00Z"}

    with HoldedClient(store, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HoldedApiError) as exc_info:
            client.get_workplaces()

    assert "unreadable" in exc_info.value.message.lower()
