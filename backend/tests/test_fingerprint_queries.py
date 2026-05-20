"""Tests for tenant-scoped fingerprint listing."""

import pytest
from uuid import uuid4

from app.infrastructure.database.models import Platform, Stream, StreamEvent, Tenant
from app.services.detection.fingerprint_queries import list_tenant_fingerprints


async def _seed_tenant_stream(db_session):
    tenant = Tenant(id=uuid4(), name="Test Org", slug=f"t-{uuid4().hex[:8]}")
    stream = Stream(
        id=uuid4(),
        tenant_id=tenant.id,
        platform=Platform.TWITCH,
        external_id="12345",
        channel_name="testchannel",
        is_live=True,
    )
    db_session.add(tenant)
    db_session.add(stream)
    await db_session.flush()
    return tenant, stream


@pytest.mark.asyncio
async def test_list_tenant_fingerprints_empty(db_session):
    tenant, _stream = await _seed_tenant_stream(db_session)
    result = await list_tenant_fingerprints(db_session, tenant.id)
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_list_filters_by_hash_and_stream(db_session):
    tenant, stream = await _seed_tenant_stream(db_session)
    fp_hash = "abc123def456" + "0" * 52

    db_session.add(
        StreamEvent(
            stream_id=stream.id,
            event_type="viewer_join",
            fingerprint_hash=fp_hash,
            ip_address="1.2.3.4",
            risk_score=80.0,
        )
    )
    await db_session.flush()

    found = await list_tenant_fingerprints(db_session, tenant.id, q="abc123", min_risk=0)
    assert found["count"] == 1
    assert found["fingerprints"][0]["hash"] == fp_hash
    assert found["fingerprints"][0]["channels"][0]["channel_name"] == "testchannel"

    by_stream = await list_tenant_fingerprints(
        db_session, tenant.id, stream_id=stream.id, min_risk=0
    )
    assert by_stream["count"] == 1

    other_stream = uuid4()
    assert (
        await list_tenant_fingerprints(
            db_session, tenant.id, stream_id=other_stream, min_risk=0
        )
    )["count"] == 0
