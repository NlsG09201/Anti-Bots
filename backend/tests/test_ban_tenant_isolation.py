"""Tenant isolation tests for ban management endpoints."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token
from app.infrastructure.database.models import Ban, Platform, Stream, Tenant, User, UserRole


async def _seed_tenant(db_session, suffix: str):
    tenant = Tenant(id=uuid4(), name=f"Tenant {suffix}", slug=f"ban-{suffix}-{uuid4().hex[:8]}")
    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email=f"ban-{suffix}-{uuid4().hex[:8]}@test.local",
        username=f"ban-{suffix}",
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
async def test_cannot_create_ban_for_another_tenants_stream(client: AsyncClient, db_session):
    _tenant, user, _own_stream = await _seed_tenant(db_session, "owner")
    _other_tenant, _other_user, other_stream = await _seed_tenant(db_session, "other")
    token = create_access_token(str(user.id), str(user.tenant_id), user.role.value)

    response = await client.post(
        f"/api/v1/bans?stream_id={other_stream.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "target_type": "user",
            "target_value": "outsider",
            "reason": "tenant boundary test",
        },
    )

    assert response.status_code == 404
    result = await db_session.execute(select(Ban).where(Ban.stream_id == other_stream.id))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_cannot_revoke_another_tenants_ban(client: AsyncClient, db_session):
    _tenant, user, _own_stream = await _seed_tenant(db_session, "owner")
    other_tenant, _other_user, other_stream = await _seed_tenant(db_session, "other")
    ban = Ban(
        id=uuid4(),
        stream_id=other_stream.id,
        tenant_id=other_tenant.id,
        target_type="user",
        target_value="protected-user",
        reason="tenant boundary test",
    )
    db_session.add(ban)
    await db_session.flush()
    token = create_access_token(str(user.id), str(user.tenant_id), user.role.value)

    response = await client.delete(
        f"/api/v1/bans/{ban.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    await db_session.refresh(ban)
    assert ban.is_active is True
