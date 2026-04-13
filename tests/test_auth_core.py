from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest


def _iso8601(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class DummySessionStore:
    def __init__(self, cookies: dict[str, str], saved_at: str | None) -> None:
        self._state = {"cookies": cookies, "saved_at": saved_at}

    def load(self) -> dict[str, object]:
        return self._state


def test_describe_saved_session_returns_missing_without_cookies() -> None:
    from holded_cli.auth import describe_saved_session

    store = DummySessionStore(cookies={}, saved_at=None)

    assert describe_saved_session(store) == "missing"


def test_describe_saved_session_reports_likely_valid_for_recent_saved_at() -> None:
    from holded_cli.auth import describe_saved_session

    now = datetime(2026, 4, 12, 12, 0, tzinfo=UTC)
    store = DummySessionStore(
        cookies={"hat": "token"},
        saved_at=_iso8601(now - timedelta(days=7)),
    )

    assert describe_saved_session(store, now=now) == "likely valid"


@pytest.mark.parametrize(
    ("saved_at", "now"),
    [
        (None, datetime(2026, 4, 12, 12, 0, tzinfo=UTC)),
        ("not-a-timestamp", datetime(2026, 4, 12, 12, 0, tzinfo=UTC)),
        (
            _iso8601(datetime(2026, 3, 1, 12, 0, tzinfo=UTC)),
            datetime(2026, 4, 12, 12, 0, tzinfo=UTC),
        ),
    ],
)
def test_describe_saved_session_reports_unknown_for_untrusted_timestamps(
    saved_at: str | None, now: datetime
) -> None:
    from holded_cli.auth import describe_saved_session

    store = DummySessionStore(cookies={"hat": "token"}, saved_at=saved_at)

    assert describe_saved_session(store, now=now) == "unknown"


def test_require_saved_session_raises_missing_auth_with_login_hint() -> None:
    from holded_cli.auth import MissingAuthenticationError, require_saved_session

    store = DummySessionStore(cookies={}, saved_at=None)

    with pytest.raises(MissingAuthenticationError) as exc_info:
        require_saved_session(store)

    assert "holded login" in exc_info.value.hint


def test_require_saved_session_raises_expired_auth_with_login_hint() -> None:
    from holded_cli.auth import ExpiredAuthenticationError, require_saved_session

    store = DummySessionStore(
        cookies={"hat": "token"},
        saved_at=_iso8601(datetime(2026, 2, 1, 12, 0, tzinfo=UTC)),
    )

    with pytest.raises(ExpiredAuthenticationError) as exc_info:
        require_saved_session(
            store,
            now=datetime(2026, 4, 12, 12, 0, tzinfo=UTC),
        )

    assert "holded login" in exc_info.value.hint


def test_parse_saved_at_treats_naive_datetime_as_utc() -> None:
    from holded_cli.auth import _parse_saved_at

    # No timezone info → should be treated as UTC and returned with tzinfo
    result = _parse_saved_at("2026-04-10T08:00:00")

    assert result is not None
    assert result.tzinfo is not None
    assert result.year == 2026
    assert result.hour == 8


def test_require_saved_session_returns_cookies_when_valid() -> None:
    from holded_cli.auth import require_saved_session

    now = datetime(2026, 4, 12, 12, 0, tzinfo=UTC)
    store = DummySessionStore(
        cookies={"hat": "token", "PHPSESSID": "abc"},
        saved_at=_iso8601(now - timedelta(days=7)),
    )

    result = require_saved_session(store, now=now)

    assert result == {"hat": "token", "PHPSESSID": "abc"}


def test_primary_login_normalizes_two_factor_requirement() -> None:
    from holded_cli.auth import HoldedAuthClient

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, request=request)

        assert request.url.path == "/internal/auth/get-token"
        return httpx.Response(
            200,
            json={"status": "two_factor_required", "token": "confirm-me"},
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with HoldedAuthClient(transport=transport) as client:
        client.bootstrap()
        result = client.primary_login("dweller@example.com", "s3cret")

    assert result.two_factor_required is True
    assert result.masked_contact is None  # new flow: no token, server returns maskedContactMethod


def test_primary_login_returns_masked_contact_when_present() -> None:
    from holded_cli.auth import HoldedAuthClient

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, request=request)
        return httpx.Response(
            200,
            json={"maskedContactMethod": "m***@example.com"},
            request=request,
        )

    with HoldedAuthClient(transport=httpx.MockTransport(handler)) as client:
        client.bootstrap()
        result = client.primary_login("me@example.com", "pw")

    assert result.masked_contact == "m***@example.com"


def test_confirm_two_factor_exchanges_one_time_token() -> None:
    """confirm_two_factor calls _exchange_one_time_token when response has a token."""
    from holded_cli.auth import HoldedAuthClient

    exchanged: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, request=request)
        if request.url.path == "/internal/auth/two-factor-confirm":
            return httpx.Response(200, json={"token": "_ott_abc"}, request=request)
        # Exchange step: GET /login/_ott_abc — set hat cookie via Set-Cookie header
        if request.url.path.startswith("/login/"):
            exchanged.append(request.url.path)
            return httpx.Response(
                200,
                headers={"set-cookie": "hat=tok123; Path=/; Domain=app.holded.com"},
                request=request,
            )
        return httpx.Response(200, request=request)

    with HoldedAuthClient(transport=httpx.MockTransport(handler)) as client:
        client.bootstrap()
        client.confirm_two_factor("123456", "me@example.com")

    assert any("/login/_ott_abc" in path for path in exchanged)


def test_confirm_two_factor_raises_on_http_error() -> None:
    from holded_cli.auth import HoldedAuthClient
    from holded_cli.errors import HoldedCliError

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, request=request)
        return httpx.Response(401, text="Unauthorized", request=request)

    with HoldedAuthClient(transport=httpx.MockTransport(handler)) as client:
        client.bootstrap()
        with pytest.raises(HoldedCliError) as exc_info:
            client.confirm_two_factor("bad-code", "me@example.com")

    assert "401" in exc_info.value.message


def test_export_cookies_returns_all_jar_cookies() -> None:
    from holded_cli.auth import HoldedAuthClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"set-cookie": "PHPSESSID=sess1; Path=/"},
            request=request,
        )

    with HoldedAuthClient(transport=httpx.MockTransport(handler)) as client:
        client._client.cookies.set("hat", "tok", domain="app.holded.com")
        cookies = client.export_cookies()

    assert "hat" in cookies
    assert cookies["hat"] == "tok"


def test_read_payload_raises_on_http_error_status() -> None:
    """_read_payload raises HoldedCliError when the response is a 4xx/5xx."""
    from holded_cli.auth import HoldedAuthClient
    from holded_cli.errors import HoldedCliError

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, request=request)
        return httpx.Response(403, text="Forbidden", request=request)

    with HoldedAuthClient(transport=httpx.MockTransport(handler)) as client:
        client.bootstrap()
        with pytest.raises(HoldedCliError) as exc_info:
            client.primary_login("me@example.com", "pw")

    assert "403" in exc_info.value.message


def test_read_payload_raises_on_invalid_json() -> None:
    from holded_cli.auth import HoldedAuthClient
    from holded_cli.errors import HoldedCliError

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, request=request)
        return httpx.Response(200, content=b"not-json", request=request)

    with HoldedAuthClient(transport=httpx.MockTransport(handler)) as client:
        client.bootstrap()
        with pytest.raises(HoldedCliError) as exc_info:
            client.primary_login("me@example.com", "pw")

    assert "unreadable" in exc_info.value.message.lower()


def test_read_payload_raises_on_non_dict_payload() -> None:
    from holded_cli.auth import HoldedAuthClient
    from holded_cli.errors import HoldedCliError

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, request=request)
        return httpx.Response(200, json=["list", "not", "dict"], request=request)

    with HoldedAuthClient(transport=httpx.MockTransport(handler)) as client:
        client.bootstrap()
        with pytest.raises(HoldedCliError) as exc_info:
            client.primary_login("me@example.com", "pw")

    assert "unexpected" in exc_info.value.message.lower()


def test_send_raises_holded_cli_error_on_network_failure() -> None:
    from holded_cli.auth import HoldedAuthClient
    from holded_cli.errors import HoldedCliError

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with HoldedAuthClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HoldedCliError) as exc_info:
            client.bootstrap()

    assert "network" in exc_info.value.hint.lower()


def test_extract_cookie_from_headers_injects_missing_cookie() -> None:
    """When a cookie is not in the jar, _extract_cookie_from_headers reads Set-Cookie."""
    from holded_cli.auth import HoldedAuthClient

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            # Return hrt in Set-Cookie but NOT via standard cookie mechanism
            return httpx.Response(
                200,
                headers={"set-cookie": "hrt=abc123; Path=/; Domain=other.com"},
                request=request,
            )
        return httpx.Response(200, request=request)

    with HoldedAuthClient(transport=httpx.MockTransport(handler)) as client:
        client.bootstrap()  # hrt not in jar → _extract_cookie_from_headers is called
        cookies = client.export_cookies()

    assert cookies.get("hrt") == "abc123"
