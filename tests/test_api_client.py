import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from smarter_flair_vents.api import FlairApi, FlairApiAuthError, FlairApiError


class _FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload

    async def text(self):
        if isinstance(self._payload, str):
            return self._payload
        if isinstance(self._payload, dict):
            import json

            return json.dumps(self._payload)
        return str(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, response):
        self.response = response
        self.last_headers = None
        self.last_request = None
        self.post_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        self.last_request = ("POST", url, kwargs)
        return self.response

    async def request(self, method, url, **kwargs):
        self.last_request = (method, url, kwargs)
        self.last_headers = kwargs.get("headers", {})
        return self.response


class _SequencedSession(_FakeSession):
    def __init__(self, responses):
        self.responses = list(responses)
        super().__init__(self.responses[0])

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        self.last_request = ("POST", url, kwargs)
        return self.responses.pop(0)


def test_authenticate_success_sets_token():
    response = _FakeResponse(200, {"access_token": "abc", "expires_in": 3600})
    session = _FakeSession(response)
    api = FlairApi(session, "id", "secret")

    asyncio.run(api.async_authenticate())
    assert api._access_token == "abc"
    assert api._token_expires_at is not None
    assert session.last_request[2]["headers"]["Content-Type"] == "application/x-www-form-urlencoded"


def test_authenticate_invalid_credentials():
    response = _FakeResponse(401, {})
    session = _FakeSession(response)
    api = FlairApi(session, "id", "secret")

    with pytest.raises(FlairApiAuthError):
        asyncio.run(api.async_authenticate())


def test_authenticate_error_body_includes_message():
    response = _FakeResponse(400, "invalid_client")
    session = _FakeSession(response)
    api = FlairApi(session, "id", "secret")

    with pytest.raises(FlairApiError) as err:
        asyncio.run(api.async_authenticate())
    assert "invalid_client" in str(err.value)


def test_authenticate_timeout_raises_flair_error():
    class _TimeoutSession(_FakeSession):
        def post(self, url, **kwargs):
            raise asyncio.TimeoutError

    session = _TimeoutSession(_FakeResponse(200, {}))
    api = FlairApi(session, "id", "secret")

    with pytest.raises(FlairApiError):
        asyncio.run(api.async_authenticate())


def test_authenticate_retries_on_invalid_scope():
    responses = [
        _FakeResponse(400, '{"error": "invalid_scope"}'),
        _FakeResponse(200, {"access_token": "abc", "expires_in": 3600}),
    ]
    session = _SequencedSession(responses)
    api = FlairApi(session, "id", "secret")

    asyncio.run(api.async_authenticate())
    assert api._access_token == "abc"
    assert len(session.post_calls) == 2


def test_authenticate_skips_when_token_valid():
    response = _FakeResponse(200, {"access_token": "abc", "expires_in": 3600})
    session = _FakeSession(response)
    api = FlairApi(session, "id", "secret")
    api._access_token = "cached"
    api._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    asyncio.run(api.async_authenticate())
    assert api._access_token == "cached"
    assert session.last_request is None


def test_async_request_adds_auth_headers():
    response = _FakeResponse(200, {"data": []})
    session = _FakeSession(response)
    api = FlairApi(session, "id", "secret")
    api._access_token = "token"
    api._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    result = asyncio.run(api._async_request("GET", "/api/test"))
    assert result == {"data": []}
    assert session.last_headers["Authorization"] == "Bearer token"
    assert session.last_headers["Accept"] == "application/vnd.api+json"


def test_async_request_unauthorized_resets_token():
    response = _FakeResponse(401, {})
    session = _FakeSession(response)
    api = FlairApi(session, "id", "secret")
    api._access_token = "token"
    api._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    with pytest.raises(FlairApiAuthError):
        asyncio.run(api._async_request("GET", "/api/test"))
    assert api._access_token is None


def test_async_get_structures_parses_names():
    api = FlairApi(_FakeSession(_FakeResponse(200, {})), "id", "secret")

    async def fake_request(method, path, **kwargs):
        return {
            "data": [
                {"id": "1", "attributes": {"name": "Home"}},
                {"id": "2", "attributes": {}},
                {"id": None, "attributes": {"name": "Skip"}},
            ]
        }

    api._async_request = fake_request
    structures = asyncio.run(api.async_get_structures())
    assert structures == [{"id": "1", "name": "Home"}, {"id": "2", "name": "2"}]


def test_set_room_setpoint_payload():
    api = FlairApi(_FakeSession(_FakeResponse(200, {})), "id", "secret")
    calls = {}

    async def fake_request(method, path, **kwargs):
        calls["method"] = method
        calls["path"] = path
        calls["json"] = kwargs.get("json")
        return {}

    api._async_request = fake_request
    asyncio.run(api.async_set_room_setpoint("room-1", 22.5, "2024-01-01T00:00:00Z"))

    assert calls["method"] == "PATCH"
    assert calls["path"] == "/api/rooms/room-1"
    assert calls["json"]["data"]["attributes"]["set-point-c"] == 22.5
    assert calls["json"]["data"]["attributes"]["hold-until"] == "2024-01-01T00:00:00Z"


def test_set_structure_mode_payload():
    api = FlairApi(_FakeSession(_FakeResponse(200, {})), "id", "secret")
    calls = {}

    async def fake_request(method, path, **kwargs):
        calls["method"] = method
        calls["path"] = path
        calls["json"] = kwargs.get("json")
        return {}

    api._async_request = fake_request
    asyncio.run(api.async_set_structure_mode("struct-1", "manual"))
    assert calls["path"] == "/api/structures/struct-1"
    assert calls["json"]["data"]["attributes"]["mode"] == "manual"


def test_set_room_active_payload():
    api = FlairApi(_FakeSession(_FakeResponse(200, {})), "id", "secret")
    calls = {}

    async def fake_request(method, path, **kwargs):
        calls["method"] = method
        calls["path"] = path
        calls["json"] = kwargs.get("json")
        return {}

    api._async_request = fake_request
    asyncio.run(api.async_set_room_active("room-2", True))
    assert calls["path"] == "/api/rooms/room-2"
    assert calls["json"]["data"]["attributes"]["active"] is True


def test_async_request_error_status():
    response = _FakeResponse(500, {})
    session = _FakeSession(response)
    api = FlairApi(session, "id", "secret")
    api._access_token = "token"
    api._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    with pytest.raises(FlairApiError):
        asyncio.run(api._async_request("GET", "/api/test"))
