"""Tenant-scoped persistence operations for stream records."""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Platform, Stream


class StreamRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id_for_tenant(self, stream_id: UUID, tenant_id: UUID) -> Optional[Stream]:
        result = await self.session.execute(
            select(Stream).where(Stream.id == stream_id, Stream.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_platform_and_external_id(
        self,
        tenant_id: UUID,
        platform: Platform,
        external_id: str,
    ) -> Optional[Stream]:
        result = await self.session.execute(
            select(Stream).where(
                Stream.tenant_id == tenant_id,
                Stream.platform == platform,
                Stream.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_channel_name(
        self,
        tenant_id: UUID,
        platform: Platform,
        channel_name: str,
    ) -> Optional[Stream]:
        result = await self.session.execute(
            select(Stream).where(
                Stream.tenant_id == tenant_id,
                Stream.platform == platform,
                Stream.channel_name.ilike(channel_name),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_tenant(self, tenant_id: UUID) -> list[Stream]:
        result = await self.session.execute(
            select(Stream).where(Stream.tenant_id == tenant_id)
        )
        return list(result.scalars().all())
