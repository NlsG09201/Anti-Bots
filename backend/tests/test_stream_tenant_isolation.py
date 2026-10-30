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
async def test_streamer_cannot_subscribe_eventsub_for_another_owner_stream(
    client: AsyncClient,
    db_session,
):
    tenant = Tenant(id=uuid4(), name="OAuth owner tenant", slug=f"oauth-owner-{uuid4().hex[:8]}")
    owner = User(
        id=uuid4(), tenant_id=tenant.id, email=f"owner-{uuid4().hex[:8]}@test.local",
        username="stream-owner", hashed_password="unused", role=UserRole.STREAMER,
    )
    actor = User(
        id=uuid4(), tenant_id=tenant.id, email=f"actor-{uuid4().hex[:8]}@test.local",
        username="other-streamer", hashed_password="unused", role=UserRole.STREAMER,
    )
    stream = Stream(
        id=uuid4(), tenant_id=tenant.id, owner_id=owner.id, platform=Platform.TWITCH,
        external_id="twitch-channel", channel_name="channel", oauth_token_encrypted="ciphertext",
    )
    db_session.add_all([tenant, owner, actor, stream])
    await db_session.flush()
    token = create_access_token(str(actor.id), str(tenant.id), actor.role.value)

    response = await client.post(
        f"/api/v1/integrations/twitch/subscribe/{stream.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_streamer_cannot_rotate_another_owner_widget_key(client: AsyncClient, db_session):
    tenant = Tenant(id=uuid4(), name="Widget tenant", slug=f"widget-{uuid4().hex[:8]}")
    owner = User(
        id=uuid4(), tenant_id=tenant.id, email=f"owner-{uuid4().hex[:8]}@test.local",
        username="widget-owner", hashed_password="unused", role=UserRole.STREAMER,
    )
    actor = User(
        id=uuid4(), tenant_id=tenant.id, email=f"actor-{uuid4().hex[:8]}@test.local",
        username="other-streamer", hashed_password="unused", role=UserRole.STREAMER,
    )
    stream = Stream(
        id=uuid4(), tenant_id=tenant.id, owner_id=owner.id, platform=Platform.TWITCH,
        external_id="widget-channel", channel_name="widget-channel",
        settings={"ingest_key": "existing-widget-ingest-key"},
    )
    db_session.add_all([tenant, owner, actor, stream])
    await db_session.flush()
    token = create_access_token(str(actor.id), str(tenant.id), actor.role.value)

    response = await client.post(
        f"/api/v1/streams/{stream.id}/widget/key",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert stream.settings["ingest_key"] == "existing-widget-ingest-key"


@pytest.mark.asyncio
async def test_streamer_cannot_read_another_owner_widget_key(client: AsyncClient, db_session):
    tenant = Tenant(id=uuid4(), name="Widget embed tenant", slug=f"widget-embed-{uuid4().hex[:8]}")
    owner = User(
        id=uuid4(), tenant_id=tenant.id, email=f"owner-{uuid4().hex[:8]}@test.local",
        username="widget-owner", hashed_password="unused", role=UserRole.STREAMER,
    )
    actor = User(
        id=uuid4(), tenant_id=tenant.id, email=f"actor-{uuid4().hex[:8]}@test.local",
        username="other-streamer", hashed_password="unused", role=UserRole.STREAMER,
    )
    stream = Stream(
        id=uuid4(), tenant_id=tenant.id, owner_id=owner.id, platform=Platform.TWITCH,
        external_id="widget-embed-channel", channel_name="widget-embed-channel",
        settings={"ingest_key": "sensitive-existing-widget-key"},
    )
    db_session.add_all([tenant, owner, actor, stream])
    await db_session.flush()
    token = create_access_token(str(actor.id), str(tenant.id), actor.role.value)

    response = await client.get(
        f"/api/v1/streams/{stream.id}/widget/embed",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert "sensitive-existing-widget-key" not in response.text


@pytest.mark.asyncio
async def test_streamer_cannot_create_oauth_invite_for_another_owner(client: AsyncClient, db_session):
    tenant = Tenant(id=uuid4(), name="Invite tenant", slug=f"invite-{uuid4().hex[:8]}")
    owner = User(
        id=uuid4(), tenant_id=tenant.id, email=f"owner-{uuid4().hex[:8]}@test.local",
        username="invite-owner", hashed_password="unused", role=UserRole.STREAMER,
    )
    actor = User(
        id=uuid4(), tenant_id=tenant.id, email=f"actor-{uuid4().hex[:8]}@test.local",
        username="other-streamer", hashed_password="unused", role=UserRole.STREAMER,
    )
    stream = Stream(
        id=uuid4(), tenant_id=tenant.id, owner_id=owner.id, platform=Platform.TWITCH,
        external_id="invite-channel", channel_name="invite-channel",
    )
    db_session.add_all([tenant, owner, actor, stream])
    await db_session.flush()
    token = create_access_token(str(actor.id), str(tenant.id), actor.role.value)

    response = await client.post(
        f"/api/v1/streams/{stream.id}/channel-invite",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_batch_analysis_hides_stream_from_another_tenant(client: AsyncClient, db_session):
    tenant = Tenant(id=uuid4(), name="Analysis tenant", slug=f"analysis-{uuid4().hex[:8]}")
    analyst = User(
        id=uuid4(), tenant_id=tenant.id, email=f"analyst-{uuid4().hex[:8]}@test.local",
        username="analyst", hashed_password="unused", role=UserRole.ANALYST,
    )
    other_tenant = Tenant(id=uuid4(), name="Other analysis tenant", slug=f"other-analysis-{uuid4().hex[:8]}")
    owner = User(
        id=uuid4(), tenant_id=other_tenant.id, email=f"owner-{uuid4().hex[:8]}@test.local",
        username="other-owner", hashed_password="unused", role=UserRole.STREAMER,
    )
    stream = Stream(
        id=uuid4(), tenant_id=other_tenant.id, owner_id=owner.id, platform=Platform.TWITCH,
        external_id="private-analysis-stream", channel_name="private-analysis-stream",
    )
    db_session.add_all([tenant, analyst, other_tenant, owner, stream])
    await db_session.flush()
    token = create_access_token(str(analyst.id), str(tenant.id), analyst.role.value)

    response = await client.post(
        "/api/v1/detection/analyze-batch",
        params={"stream_id": str(stream.id)},
        json=[{"platform_user_id": "sample-user"}],
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


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
