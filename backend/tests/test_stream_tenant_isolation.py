"""Tenant boundary tests for stream repository-backed API reads."""

from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.infrastructure.database.models import Platform, Stream, Tenant, User, UserRole


async def _seed_stream(db_session, suffix: str):
    tenant = Tenant(id=uuid4(), name=f"Stream tenant {suffix}", slug=f"stream-{suffix}-{uuid4().hex[:8]}")
    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email=f"stream-{suffix}-{uuid4().hex[:8]}@test.local",
        username=f"stream-{suffix}",
        hashed_password="unused",
        role=UserRole.ADMIN,
    )
    stream = Stream(
        id=uuid4(),
        tenant_id=tenant.id,
        owner_id=user.id,
        platform=Platform.TWITCH,
        external_id=f"external-{uuid4().hex}",
        channel_name=f"channel-{suffix}",
    )
    db_session.add_all([tenant, user, stream])
    await db_session.flush()
    return tenant, user, stream


@pytest.mark.asyncio
async def test_stream_detail_is_available_to_owning_tenant(client: AsyncClient, db_session):
    tenant, user, stream = await _seed_stream(db_session, "owner")
    token = create_access_token(str(user.id), str(tenant.id), user.role.value)

    response = await client.get(
        f"/api/v1/streams/{stream.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(stream.id)


@pytest.mark.asyncio
async def test_stream_detail_hides_another_tenants_stream(client: AsyncClient, db_session):
    tenant, user, _own_stream = await _seed_stream(db_session, "owner")
    _other_tenant, _other_user, other_stream = await _seed_stream(db_session, "other")
    token = create_access_token(str(user.id), str(tenant.id), user.role.value)

    response = await client.get(
        f"/api/v1/streams/{other_stream.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stream_list_contains_only_authenticated_tenant(client: AsyncClient, db_session):
    tenant, user, own_stream = await _seed_stream(db_session, "owner")
    _other_tenant, _other_user, other_stream = await _seed_stream(db_session, "other")
    token = create_access_token(str(user.id), str(tenant.id), user.role.value)

    response = await client.get(
        "/api/v1/streams",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    stream_ids = {item["id"] for item in response.json()}
    assert stream_ids == {str(own_stream.id)}
    assert str(other_stream.id) not in stream_ids


@pytest.mark.asyncio
async def test_watch_channel_uses_service_and_persists_monitor_settings(
    client: AsyncClient,
    db_session,
):
    tenant, user, _ = await _seed_stream(db_session, "watcher")
    token = create_access_token(str(user.id), str(tenant.id), user.role.value)

    async def keep_stream_offline(_db, stream):
        return stream

    with patch(
        "app.services.streams.watch.sync_stream_live_status",
        new=AsyncMock(side_effect=keep_stream_offline),
    ):
        response = await client.post(
            "/api/v1/streams/watch",
            headers={"Authorization": f"Bearer {token}"},
            json={"platform": "youtube", "login": "@creator"},
        )

    assert response.status_code == 200
    watched = response.json()
    assert watched["platform"] == "youtube"
    assert watched["channel_name"] == "creator"
    assert watched["monitor_mode"] is True
    assert watched["is_owned"] is False
