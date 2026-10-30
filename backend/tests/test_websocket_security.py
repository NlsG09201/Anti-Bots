from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.websocket import routes
from app.api.websocket.manager import ConnectionManager
from app.core.security import create_access_token


class FakeWebSocket:
    def __init__(self):
        self.headers = {}
        self.sent = []
        self.accepted = False
        self.closed = None

    async def close(self, code, reason=None):
        self.closed = code, reason

    async def accept(self, subprotocol=None, headers=None):
        self.accepted = True
        self.subprotocol = subprotocol

    async def send_json(self, data):
        self.sent.append(data)


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, user):
        self.user = user

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, _query):
        return FakeResult(self.user)


class FakeCache:
    revoked = False

    async def is_blacklisted(self, _jti):
        return self.revoked


def test_websocket_extracts_token_from_subprotocol_header_only():
    websocket = FakeWebSocket()
    websocket.headers["sec-websocket-protocol"] = "streamshield, bearer.access-token"

    assert routes._token_from_subprotocols(websocket) == "access-token"

    websocket.headers["sec-websocket-protocol"] = "bearer.access-token"
    assert routes._token_from_subprotocols(websocket) is None

    websocket.headers["sec-websocket-protocol"] = "streamshield, bearer.one, bearer.two"
    assert routes._token_from_subprotocols(websocket) is None


@pytest.mark.asyncio
async def test_websocket_rejects_access_token_in_query_string(monkeypatch):
    websocket = FakeWebSocket()
    websocket.query_params = {"token": "query-token"}
    monkeypatch.setattr(
        routes,
        "_authenticated_identity",
        lambda _token: pytest.fail("query-string credentials must not be authenticated"),
    )

    await routes.websocket_endpoint(websocket)

    assert websocket.closed == (4401, "Unauthorized")


@pytest.mark.asyncio
async def test_websocket_requires_active_user_matching_token_tenant(monkeypatch):
    user_id, tenant_id = uuid4(), uuid4()
    user = SimpleNamespace(id=user_id, tenant_id=tenant_id, is_active=True)
    monkeypatch.setattr(routes, "AsyncSessionLocal", lambda: FakeSession(user))
    monkeypatch.setattr(routes, "RedisCache", FakeCache)
    token = create_access_token(str(user_id), str(tenant_id), "streamer")

    assert await routes._authenticated_identity(token) == (str(user_id), str(tenant_id))

    user.tenant_id = uuid4()
    assert await routes._authenticated_identity(token) is None

    user.tenant_id = tenant_id
    user.is_active = False
    assert await routes._authenticated_identity(token) is None


@pytest.mark.asyncio
async def test_websocket_rejects_revoked_access_token(monkeypatch):
    user_id, tenant_id = uuid4(), uuid4()
    user = SimpleNamespace(id=user_id, tenant_id=tenant_id, is_active=True)
    monkeypatch.setattr(routes, "AsyncSessionLocal", lambda: FakeSession(user))

    class RevokedCache:
        async def is_blacklisted(self, _jti):
            return True

    monkeypatch.setattr(routes, "RedisCache", RevokedCache)
    token = create_access_token(str(user_id), str(tenant_id), "streamer")

    assert await routes._authenticated_identity(token) is None


@pytest.mark.asyncio
async def test_connection_manager_keeps_other_user_sockets_on_disconnect():
    manager = ConnectionManager()
    first, second = FakeWebSocket(), FakeWebSocket()
    await manager.connect(first, "tenant-a")
    await manager.connect(second, "tenant-a")

    await manager.disconnect(first, "tenant-a")

    assert manager.connection_count == 1
    assert manager.connection_count_for_tenant("tenant-b") == 0
    await manager.broadcast_to_tenant("tenant-a", {"type": "ping"})
    assert second.sent[-1] == {"type": "ping"}


@pytest.mark.asyncio
async def test_connection_manager_removes_dead_sockets_after_broadcast():
    class DeadSocket(FakeWebSocket):
        async def send_json(self, _data):
            raise RuntimeError("connection closed")

    manager = ConnectionManager()
    dead = DeadSocket()
    await manager.connect(dead, "tenant-a")
    await manager.broadcast_to_tenant("tenant-a", {"type": "ping"})

    assert manager.connection_count_for_tenant("tenant-a") == 0
