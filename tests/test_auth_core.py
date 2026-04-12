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
