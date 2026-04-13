"""Authenticated Holded API client using persisted session cookies."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from holded_cli.auth import MissingAuthenticationError, require_saved_session
from holded_cli.errors import HoldedCliError
from holded_cli.session import SessionStore


HOLDED_BASE_URL = "https://app.holded.com"


def _make_datetime_param(d: date, t: time, tz_name: str) -> str:
    """Format a date+time as an ISO-8601 string with the correct UTC offset for the given timezone."""
    tz = ZoneInfo(tz_name)
    return datetime.combine(d, t, tzinfo=tz).isoformat()


class HoldedApiError(HoldedCliError):
    """Raised when the Holded API returns an error or unreadable response."""


class HoldedClient:
    """HTTP client for authenticated Holded API calls."""

    def __init__(
        self,
        session_store: SessionStore,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        cookies = require_saved_session(session_store)
        self._client = httpx.Client(
            base_url=HOLDED_BASE_URL,
            cookies=cookies,
            headers={
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
            follow_redirects=True,
            timeout=30.0,
            transport=transport,
        )

    def __enter__(self) -> HoldedClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # --- Public API methods ---

    def get_timetracking_pdf(
        self, from_date: date, to_date: date, timezone: str
    ) -> bytes:
        """Download the time-tracking PDF for a date range."""
        params = {
            "startDate": _make_datetime_param(from_date, time(0, 0, 0), timezone),
            "endDate": _make_datetime_param(to_date, time(23, 59, 59), timezone),
        }
        response = self._get("/internal/team/v2/daily-timetracking/pdf", params=params)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HoldedApiError(
                message=f"PDF export failed (HTTP {exc.response.status_code}).",
                hint="Check your session with `holded session` and try again.",
            ) from exc
        return response.content

    def get_timetracking_data(
        self, from_date: date, to_date: date, timezone: str
    ) -> list[dict[str, Any]]:
        """Fetch the time-tracking JSON data for a date range."""
        params = {
            "startDate": _make_datetime_param(from_date, time(0, 0, 0), timezone),
            "endDate": _make_datetime_param(to_date, time(23, 59, 59), timezone),
        }
        response = self._get("/internal/team/v2/daily-timetracking", params=params)
        data = self._parse_json(response)
        return data if isinstance(data, list) else []

    def get_workplaces(self) -> list[dict[str, Any]]:
        """Fetch the list of available workplaces."""
        response = self._get("/internal/team/v2/workplace/")
        data = self._parse_json(response)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("workplaces", "data", "items"):
                value = data.get(key)
                if isinstance(value, list):
                    return value
        return []

    def get_current_tracker(self) -> dict[str, Any] | None:
        """Return the active tracker, or None if there is none."""
        response = self._get("/internal/team/v2/current-tracker")
        if response.status_code == 404:
            return None
        data = self._parse_json(response)
        if not isinstance(data, dict):
            return None
        # No active tracker: status is absent or explicitly null/empty
        if not data.get("id"):
            return None
        return data

    def clock_in(self) -> str:
        """Start a new tracker. Returns the tracker ID."""
        response = self._post(
            "/internal/team/employee/tracker/clock-in",
            json={"location": None, "triggeredFrom": "timetracking"},
        )
        data = self._parse_json(response)
        if not isinstance(data, str):
            raise HoldedApiError(
                message="Unexpected clock-in response.",
                hint="The API may have changed. Check your session and try again.",
            )
        return data

    def clock_out(self, tracker_id: str) -> None:
        """Stop the active tracker."""
        response = self._post(
            f"/internal/team/employee/tracker/clock-out/{tracker_id}",
            json={"location": None, "offset": 0, "triggeredFrom": "timetracking"},
        )
        if response.status_code in (200, 422):
            # 422 with errorCode 4 means "duration too short" but Holded still
            # closes the tracker — treat it as success.
            return
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HoldedApiError(
                message=f"Clock-out failed (HTTP {exc.response.status_code}).",
                hint="Check your session with `holded session` and try again.",
            ) from exc

    def pause_tracker(self, tracker_id: str) -> dict[str, Any]:
        """Pause the active tracker. Returns the pause record."""
        response = self._post(
            "/internal/team/tracker/pause",
            json={"trackerId": tracker_id, "location": None},
        )
        return self._parse_json(response)

    def resume_tracker(self, tracker_id: str) -> dict[str, Any]:
        """Resume a paused tracker. Returns the resume record."""
        response = self._post(
            "/internal/team/tracker/resume",
            json={"trackerId": tracker_id, "location": None},
        )
        return self._parse_json(response)

    def get_year_summary(self, year: int, workplace_id: str = "") -> dict[str, Any]:
        """Fetch the time-off year summary for holiday extraction."""
        response = self._get(
            "/internal/team/v2/timeoff-year-summary",
            params={"year": str(year)},
        )
        data = self._parse_json(response)
        return data if isinstance(data, dict) else {}

    def check_bulk_timetracking(self, payload: dict[str, Any]) -> None:
        """Validate a set of timetracking entries without saving them (step 1). Returns None on success."""
        response = self._post(
            "/internal/team/v2/check-bulk-timetracking-request", json=payload
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            from holded_cli.holded_client import HoldedApiError
            body = exc.response.text[:300].strip()
            raise HoldedApiError(
                message=f"Validation failed (HTTP {exc.response.status_code}): {body}",
                hint="Check your workplace ID and time values, then try again.",
            ) from exc

    def submit_bulk_timetracking(self, payload: dict[str, Any]) -> None:
        """Save validated timetracking entries (step 2). Returns None on 204."""
        response = self._post(
            "/internal/team/v2/bulk-timetracking-request", json=payload
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            from holded_cli.holded_client import HoldedApiError
            body = exc.response.text[:300].strip()
            raise HoldedApiError(
                message=f"Submission failed (HTTP {exc.response.status_code}): {body}",
                hint="Some days may have already been tracked. Check Holded and try again.",
            ) from exc

    # --- Internal helpers ---

    def _get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._request("GET", path, **kwargs)

    def _post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._request("POST", path, **kwargs)

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise HoldedApiError(
                message="Could not reach Holded.",
                hint="Check your network connection and try again.",
            ) from exc

        self._check_auth(response)
        return response

    def _check_auth(self, response: httpx.Response) -> None:
        if response.status_code in (401, 403):
            raise MissingAuthenticationError()
        # Holded may return HTTP 200 with an HTML login page on session expiry
        content_type = response.headers.get("content-type", "")
        if response.status_code == 200 and "text/html" in content_type:
            raise MissingAuthenticationError()

    def _parse_json(self, response: httpx.Response) -> Any:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HoldedApiError(
                message=f"Holded API returned HTTP {exc.response.status_code}.",
                hint="Run `holded login` if your session has expired.",
            ) from exc
        try:
            return response.json()
        except ValueError as exc:
            raise HoldedApiError(
                message="Holded returned an unreadable response.",
                hint="The API may have changed. Check your session with `holded session`.",
            ) from exc
