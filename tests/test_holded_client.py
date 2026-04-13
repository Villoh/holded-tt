"""Tests for HoldedClient internal helpers (HC-01 through HC-04)."""

from __future__ import annotations

from datetime import date, time, timedelta, timezone

import httpx
import pytest


def _session_store():
    from holded_cli.session import SessionStore

    store = SessionStore()
    store._state = {"cookies": {"hat": "tok"}, "saved_at": "2026-04-10T08:00:00Z"}
    return store


def test_make_datetime_param_includes_utc_offset(monkeypatch) -> None:
    import holded_cli.holded_client as holded_client

    monkeypatch.setattr(holded_client, "ZoneInfo", lambda _: timezone.utc)

    result = holded_client._make_datetime_param(date(2026, 4, 7), time(8, 30, 0), "UTC")

    assert result.startswith("2026-04-07T08:30:00")
    assert "+00:00" in result


def test_make_datetime_param_applies_timezone_offset(monkeypatch) -> None:
    import holded_cli.holded_client as holded_client

    monkeypatch.setattr(
        holded_client,
        "ZoneInfo",
        lambda _: timezone(timedelta(hours=2)),
    )

    # Europe/Paris in summer is UTC+2 → 08:30 local = 06:30 UTC offset +02:00
    result = holded_client._make_datetime_param(
        date(2026, 4, 7), time(8, 30, 0), "Europe/Paris"
    )

    assert "2026-04-07T08:30:00" in result
    assert "+02:00" in result


def test_check_auth_raises_on_401_response() -> None:
    from holded_cli.auth import MissingAuthenticationError
    from holded_cli.holded_client import HoldedClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, request=request)

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(MissingAuthenticationError):
            client.get_workplaces()


def test_check_auth_raises_on_html_response() -> None:
    """Holded returns HTTP 200 with an HTML login page on session expiry."""
    from holded_cli.auth import MissingAuthenticationError
    from holded_cli.holded_client import HoldedClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html><body>Login</body></html>",
            headers={"content-type": "text/html; charset=utf-8"},
            request=request,
        )

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(MissingAuthenticationError):
            client.get_workplaces()


def test_parse_json_raises_on_invalid_json_body() -> None:
    from holded_cli.holded_client import HoldedApiError, HoldedClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", request=request)

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(HoldedApiError) as exc_info:
            client.get_workplaces()

    assert "unreadable" in exc_info.value.message.lower()


def test_get_employee_requests_expected_endpoint() -> None:
    from holded_cli.holded_client import HoldedClient

    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(
            200, json={"id": "emp-1", "name": "Alice"}, request=request
        )

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        result = client.get_employee()

    assert seen_paths == ["/internal/teamzone/v2/employee"]
    assert result == {"id": "emp-1", "name": "Alice"}


def test_get_personal_info_requests_expected_endpoint() -> None:
    from holded_cli.holded_client import HoldedClient

    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(200, json={"phone": "+34 555 0101"}, request=request)

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        result = client.get_personal_info()

    assert seen_paths == ["/internal/teamzone/v2/personal-info"]
    assert result == {"phone": "+34 555 0101"}


def test_get_organization_employees_requests_expected_endpoint() -> None:
    from holded_cli.holded_client import HoldedClient

    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(
            200,
            json=[{"id": "emp-1", "fullName": "Alice Example"}],
            request=request,
        )

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        result = client.get_organization_employees()

    assert seen_paths == ["/internal/teamzone/v2/employees/organization"]
    assert result == [{"id": "emp-1", "fullName": "Alice Example"}]


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ([{"id": "emp-1"}], [{"id": "emp-1"}]),
        ({"employees": [{"id": "emp-2"}]}, [{"id": "emp-2"}]),
        ({"data": [{"id": "emp-3"}]}, [{"id": "emp-3"}]),
        ({"items": [{"id": "emp-4"}]}, [{"id": "emp-4"}]),
        ({"unexpected": True}, []),
    ],
)
def test_get_organization_employees_supports_multiple_response_shapes(
    payload, expected
) -> None:
    from holded_cli.holded_client import HoldedClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        assert client.get_organization_employees() == expected


def test_get_timetracking_pdf_returns_response_bytes(monkeypatch) -> None:
    import holded_cli.holded_client as holded_client
    from holded_cli.holded_client import HoldedClient

    monkeypatch.setattr(holded_client, "_make_datetime_param", lambda *_: "stubbed")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-1.4", request=request)

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        assert (
            client.get_timetracking_pdf(date(2026, 4, 1), date(2026, 4, 2), "UTC")
            == b"%PDF-1.4"
        )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ([{"id": "wp-1"}], [{"id": "wp-1"}]),
        ({"workplaces": [{"id": "wp-2"}]}, [{"id": "wp-2"}]),
        ({"data": [{"id": "wp-3"}]}, [{"id": "wp-3"}]),
        ({"items": [{"id": "wp-4"}]}, [{"id": "wp-4"}]),
        ({"unexpected": True}, []),
    ],
)
def test_get_workplaces_supports_multiple_response_shapes(payload, expected) -> None:
    from holded_cli.holded_client import HoldedClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        assert client.get_workplaces() == expected


def test_get_timetracking_data_returns_empty_list_for_non_list_payload(
    monkeypatch,
) -> None:
    import holded_cli.holded_client as holded_client
    from holded_cli.holded_client import HoldedClient

    monkeypatch.setattr(holded_client, "_make_datetime_param", lambda *_: "stubbed")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"entries": []}, request=request)

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        assert (
            client.get_timetracking_data(date(2026, 4, 1), date(2026, 4, 2), "UTC")
            == []
        )


def test_get_current_tracker_handles_missing_and_active_trackers() -> None:
    from holded_cli.holded_client import HoldedClient

    responses = iter(
        [
            {"status_code": 404},
            {"status_code": 200, "json": []},
            {"status_code": 200, "json": {"id": ""}},
            {"status_code": 200, "json": {"id": "trk-1", "status": "running"}},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = next(responses)
        return httpx.Response(request=request, **payload)

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        assert client.get_current_tracker() is None
        assert client.get_current_tracker() is None
        assert client.get_current_tracker() is None
        assert client.get_current_tracker() == {"id": "trk-1", "status": "running"}


def test_clock_in_raises_when_api_returns_non_string() -> None:
    from holded_cli.holded_client import HoldedApiError, HoldedClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "trk-1"}, request=request)

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(HoldedApiError) as exc_info:
            client.clock_in()

    assert "unexpected clock-in response" in exc_info.value.message.lower()


def test_clock_in_returns_tracker_id() -> None:
    from holded_cli.holded_client import HoldedClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json="trk-1", request=request)

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        assert client.clock_in() == "trk-1"


def test_clock_out_treats_422_as_success() -> None:
    from holded_cli.holded_client import HoldedClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"errorCode": 4}, request=request)

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        client.clock_out("trk-1")


def test_clock_out_wraps_http_errors() -> None:
    from holded_cli.holded_client import HoldedApiError, HoldedClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"}, request=request)

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(HoldedApiError) as exc_info:
            client.clock_out("trk-1")

    assert "clock-out failed" in exc_info.value.message.lower()


def test_pause_and_resume_tracker_return_api_payloads() -> None:
    from holded_cli.holded_client import HoldedClient

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pause"):
            return httpx.Response(
                200, json={"id": "pause-1", "trackerId": "trk-1"}, request=request
            )
        return httpx.Response(
            200, json={"id": "resume-1", "trackerId": "trk-1"}, request=request
        )

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        assert client.pause_tracker("trk-1") == {"id": "pause-1", "trackerId": "trk-1"}
        assert client.resume_tracker("trk-1") == {
            "id": "resume-1",
            "trackerId": "trk-1",
        }


def test_get_year_summary_returns_dict_or_empty_dict() -> None:
    from holded_cli.holded_client import HoldedClient

    responses = iter(
        [
            {"status_code": 200, "json": {"year": 2026, "holidays": []}},
            {"status_code": 200, "json": []},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(request=request, **next(responses))

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        assert client.get_year_summary(2026) == {"year": 2026, "holidays": []}
        assert client.get_year_summary(2026) == {}


def test_get_timetracking_pdf_wraps_http_errors(monkeypatch) -> None:
    import holded_cli.holded_client as holded_client
    from holded_cli.holded_client import HoldedApiError, HoldedClient

    monkeypatch.setattr(holded_client, "_make_datetime_param", lambda *_: "stubbed")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"fail", request=request)

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(HoldedApiError) as exc_info:
            client.get_timetracking_pdf(date(2026, 4, 1), date(2026, 4, 2), "UTC")

    assert "pdf export failed" in exc_info.value.message.lower()


def test_bulk_timetracking_errors_include_response_body() -> None:
    from holded_cli.holded_client import HoldedApiError, HoldedClient

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("check-bulk-timetracking-request"):
            return httpx.Response(400, text="bad validation payload", request=request)
        return httpx.Response(409, text="already tracked", request=request)

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(HoldedApiError) as check_exc:
            client.check_bulk_timetracking({"days": []})
        with pytest.raises(HoldedApiError) as submit_exc:
            client.submit_bulk_timetracking({"days": []})

    assert "validation failed" in check_exc.value.message.lower()
    assert "bad validation payload" in check_exc.value.message
    assert "submission failed" in submit_exc.value.message.lower()
    assert "already tracked" in submit_exc.value.message


def test_request_wraps_transport_errors() -> None:
    from holded_cli.holded_client import HoldedApiError, HoldedClient

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(HoldedApiError) as exc_info:
            client.get_workplaces()

    assert exc_info.value.message == "Could not reach Holded."


def test_parse_json_wraps_http_status_errors() -> None:
    from holded_cli.holded_client import HoldedApiError, HoldedClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"}, request=request)

    with HoldedClient(
        _session_store(), transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(HoldedApiError) as exc_info:
            client.get_employee()

    assert "holded api returned http 500" in exc_info.value.message.lower()
