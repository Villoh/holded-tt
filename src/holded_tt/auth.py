from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from holded_tt.errors import HoldedCliError


HOLDED_BASE_URL = "https://app.holded.com"
AUTH_FRESHNESS_DAYS = 30
REAL_TIME_DISCOVER_PATH = "/internal/real-time/discover"
_REQUIRED_DISCOVER_KEYS = frozenset({"topics", "token", "connectionToken", "wsUrl"})


@dataclass(slots=True)
class LoginStep:
    two_factor_required: bool
    masked_contact: str | None = (
        None  # where the 2FA code was sent (e.g. "m***@domain.com")
    )


class MissingAuthenticationError(HoldedCliError):
    def __init__(self) -> None:
        super().__init__(
            message="No saved Holded session is available.",
            hint="Run `holded-tt login` to authenticate and save a new session.",
        )


class ExpiredAuthenticationError(HoldedCliError):
    def __init__(self) -> None:
        super().__init__(
            message="The saved Holded session is too old to trust.",
            hint="Run `holded-tt login` to refresh the saved session.",
        )


def _parse_saved_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def describe_saved_session(session_store, now: datetime | None = None) -> str:
    state = session_store.load()
    cookies = state.get("cookies")
    if not isinstance(cookies, dict) or not cookies:
        return "missing"

    saved_at = _parse_saved_at(state.get("saved_at"))
    if saved_at is None:
        return "unknown"

    reference_time = now or datetime.now(UTC)
    if saved_at >= reference_time - timedelta(days=AUTH_FRESHNESS_DAYS):
        return "likely valid"
    return "unknown"


def require_saved_session(session_store, now: datetime | None = None) -> dict[str, str]:
    state = session_store.load()
    cookies = state.get("cookies")
    if not isinstance(cookies, dict) or not cookies:
        raise MissingAuthenticationError()

    status = describe_saved_session(session_store, now=now)
    if status == "unknown":
        raise ExpiredAuthenticationError()

    return {str(key): str(value) for key, value in cookies.items()}


def validate_saved_session(
    session_store,
    *,
    transport: httpx.BaseTransport | None = None,
) -> str:
    state = session_store.load()
    cookies = state.get("cookies")
    if not isinstance(cookies, dict) or not cookies:
        return "missing"

    client = httpx.Client(
        base_url=HOLDED_BASE_URL,
        cookies={str(key): str(value) for key, value in cookies.items()},
        headers={
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
        follow_redirects=True,
        timeout=10.0,
        transport=transport,
    )
    try:
        response = client.get(REAL_TIME_DISCOVER_PATH)
    except httpx.HTTPError:
        return "unknown"
    finally:
        client.close()

    if response.status_code in (401, 403):
        return "expired"

    content_type = response.headers.get("content-type", "")
    if response.status_code == 200 and "text/html" in content_type:
        return "expired"

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        return "unknown"

    try:
        payload = response.json()
    except ValueError:
        return "unknown"

    if not isinstance(payload, dict):
        return "unknown"

    if _REQUIRED_DISCOVER_KEYS.issubset(payload):
        return "active"

    return "unknown"


class HoldedAuthClient:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=HOLDED_BASE_URL,
            follow_redirects=True,
            timeout=10.0,
            transport=transport,
        )

    def __enter__(self) -> HoldedAuthClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def bootstrap(self) -> None:
        """GET homepage to acquire session cookies (lang, PHPSESSID)."""
        response = self._send("GET", "/")
        if "hrt" not in self._client.cookies:
            self._extract_cookie_from_headers("hrt", response)

    def primary_login(self, email: str, password: str) -> LoginStep:
        """Step 1: send credentials to trigger a 2FA code by email."""
        response = self._send(
            "POST",
            "/internal/auth/get-token",
            params={"origin": "holded"},
            files={
                "email": (None, email),
                "pass": (None, password),
                "platform": (None, "web"),
            },
        )
        return self._normalize_login_step(response)

    def confirm_two_factor(self, code: str, email: str) -> None:
        """Step 2 + 3: confirm 2FA code, then exchange the one-time token for session cookies.

        Step 2 returns {"token": "_ott..."}.
        Step 3: GET /login/{token}?origin=web — sets hat and accountid cookies.
        """
        response = self._send(
            "POST",
            "/internal/auth/two-factor-confirm",
            files={
                "platform": (None, "web"),
                "email": (None, email),
                "code": (None, code),
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300].strip()
            raise HoldedCliError(
                message=f"2FA confirmation failed (HTTP {exc.response.status_code}): {body}",
                hint="Check your 2FA code and try `holded-tt login` again.",
            ) from exc

        try:
            payload = response.json()
            token = payload.get("token") if isinstance(payload, dict) else None
        except ValueError:
            token = None

        if token:
            self._exchange_one_time_token(token)

    def _exchange_one_time_token(self, token: str) -> None:
        """Step 3: GET /login/{token}?origin=web to acquire hat and accountid cookies."""
        response = self._send("GET", f"/login/{token}", params={"origin": "web"})
        for name in ("hat", "accountid"):
            if name not in self._client.cookies:
                self._extract_cookie_from_headers(name, response)

    def export_cookies(self) -> dict[str, str]:
        return {
            cookie.name: cookie.value
            for cookie in self._client.cookies.jar
            if cookie.value is not None
        }

    def _normalize_login_step(self, response: httpx.Response) -> LoginStep:
        """Parse the step-1 response.

        Holded always responds with a 2FA challenge containing:
          type, maskedContactMethod, nextTryAt
        A 2xx response means the code was sent; any error is raised by _read_payload.
        """
        payload = self._read_payload(response)
        masked = payload.get("maskedContactMethod") or payload.get("masked_contact")
        return LoginStep(two_factor_required=True, masked_contact=masked)

    def _read_payload(self, response: httpx.Response) -> dict[str, Any]:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300].strip()
            raise HoldedCliError(
                message=f"Holded rejected the authentication request (HTTP {exc.response.status_code}): {body}",
                hint="Check your credentials or 2FA code, then run `holded-tt login` again.",
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise HoldedCliError(
                message="Holded returned an unreadable authentication response.",
                hint="Try `holded-tt login` again. If the problem persists, Holded may have changed its auth flow.",
            ) from exc

        if not isinstance(payload, dict):
            raise HoldedCliError(
                message="Holded returned an unexpected authentication response.",
                hint="Try `holded-tt login` again. If the problem persists, Holded may have changed its auth flow.",
            )

        return payload

    def _extract_cookie_from_headers(self, name: str, response: httpx.Response) -> None:
        """Parse Set-Cookie headers from the full redirect chain as a fallback.

        httpx may skip cookies whose domain/path attributes don't exactly match
        the request URL. This manually finds the cookie and injects it into the jar.
        """
        for r in (*response.history, response):
            for header_value in r.headers.get_list("set-cookie"):
                cookie_part = header_value.split(";")[0].strip()
                if cookie_part.startswith(f"{name}="):
                    value = cookie_part.split("=", 1)[1]
                    self._client.cookies.set(name, value, domain="app.holded.com")
                    return

    def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise HoldedCliError(
                message="Holded authentication could not be completed.",
                hint="Check your network connection and run `holded-tt login` again.",
            ) from exc
