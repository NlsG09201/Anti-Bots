"""Tenant isolation tests for the active alert API."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.infrastructure.database.models import (
    Alert,
    AlertSeverity,
    Attack,
    AttackType,
    Platform,
    Stream,
    Tenant,
    User,
    UserRole,
)


async def _seed_user(db_session, label: str):
    tenant = Tenant(id=uuid4(), name=f"Alert tenant {label}", slug=f"alert-{label}-{uuid4().hex[:8]}")
    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email=f"alert-{label}-{uuid4().hex[:8]}@test.local",
        username=f"alert-{label}",
        hashed_password="unused",
        role=UserRole.ADMIN,
    )
    db_session.add_all([tenant, user])
    await db_session.flush()
    return tenant, user


def _alert(tenant_id, title: str) -> Alert:
    return Alert(
        id=uuid4(),
        tenant_id=tenant_id,
        title=title,
        message=f"Message for {title}",
        severity=AlertSeverity.HIGH,
        status="open",
    )


@pytest.mark.asyncio
async def test_alert_list_is_limited_to_authenticated_tenant(client: AsyncClient, db_session):
    tenant, user = await _seed_user(db_session, "owner")
    other_tenant, _ = await _seed_user(db_session, "other")
    own_alert = _alert(tenant.id, "own")
    other_alert = _alert(other_tenant.id, "other")
    db_session.add_all([own_alert, other_alert])
    await db_session.flush()
    token = create_access_token(str(user.id), str(tenant.id), user.role.value)

    response = await client.get(
        "/api/v1/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(own_alert.id)]


@pytest.mark.asyncio
async def test_cannot_dismiss_another_tenants_alert(client: AsyncClient, db_session):
    tenant, user = await _seed_user(db_session, "owner")
    other_tenant, _ = await _seed_user(db_session, "other")
    alert = _alert(other_tenant.id, "protected")
    db_session.add(alert)
    await db_session.flush()
    token = create_access_token(str(user.id), str(tenant.id), user.role.value)

    response = await client.patch(
        f"/api/v1/alerts/{alert.id}/dismiss",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    await db_session.refresh(alert)
    assert alert.status == "open"


@pytest.mark.asyncio
async def test_alert_list_can_be_scoped_to_a_tenant_stream(client: AsyncClient, db_session):
    tenant, user = await _seed_user(db_session, "stream-owner")
    stream = Stream(
        id=uuid4(),
        tenant_id=tenant.id,
        owner_id=user.id,
        platform=Platform.TWITCH,
        external_id=f"stream-{uuid4().hex}",
        channel_name="scoped-channel",
    )
    db_session.add(stream)
    await db_session.flush()
    attack = Attack(
        id=uuid4(),
        stream_id=stream.id,
        attack_type=AttackType.VIEWBOT,
        correlation_id=uuid4().hex,
    )
    db_session.add(attack)
    await db_session.flush()
    alert = _alert(tenant.id, "stream-scoped")
    alert.attack_id = attack.id
    db_session.add(alert)
    await db_session.flush()
    token = create_access_token(str(user.id), str(tenant.id), user.role.value)

    response = await client.get(
        f"/api/v1/alerts?stream_id={stream.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(alert.id)]
