from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import ViewerSession
from app.integrations.twitch.irc_chat import score_username_risk

CHAT_IP_PLACEHOLDER = "twitch:chat"


class ViewerSessionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_chat_viewer(
        self,
        stream_id: UUID,
        username: str,
        platform_user_id: Optional[str] = None,
        *,
        joins: int = 1,
        messages: int = 0,
        extra_risk: float = 0.0,
        source: str = "irc",
    ) -> ViewerSession:
        risk = max(score_username_risk(username, joins, messages), extra_risk)
        is_bot = risk >= 55.0

        result = await self.db.execute(
            select(ViewerSession).where(
                and_(
                    ViewerSession.stream_id == stream_id,
                    ViewerSession.platform_username == username,
                    ViewerSession.is_active == True,
                )
            )
        )
        session = result.scalar_one_or_none()

        if session:
            session.chat_messages += messages
            session.risk_score = max(session.risk_score, risk)
            session.is_suspected_bot = session.is_suspected_bot or is_bot
            metrics = dict(session.behavior_metrics or {})
            metrics["joins"] = metrics.get("joins", 0) + joins
            metrics["source"] = source
            metrics["last_seen"] = datetime.now(timezone.utc).isoformat()
            session.behavior_metrics = metrics
            if platform_user_id:
                session.platform_user_id = platform_user_id
        else:
            session = ViewerSession(
                stream_id=stream_id,
                platform_user_id=platform_user_id or username.lower(),
                platform_username=username,
                ip_address=CHAT_IP_PLACEHOLDER,
                risk_score=risk,
                is_suspected_bot=is_bot,
                is_active=True,
                chat_messages=messages,
                behavior_metrics={
                    "joins": joins,
                    "messages": messages,
                    "source": source,
                    "first_seen": datetime.now(timezone.utc).isoformat(),
                },
            )
            self.db.add(session)

        await self.db.flush()
        return session

    async def upsert_from_event(
        self,
        stream_id: UUID,
        platform_username: Optional[str],
        platform_user_id: Optional[str],
        ip_address: Optional[str],
        fingerprint_hash: Optional[str],
        risk_score: float,
        event_type: str,
    ) -> Optional[ViewerSession]:
        if not platform_username and not platform_user_id:
            return None

        username = platform_username or platform_user_id or "unknown"
        ip = ip_address or CHAT_IP_PLACEHOLDER

        result = await self.db.execute(
            select(ViewerSession).where(
                and_(
                    ViewerSession.stream_id == stream_id,
                    ViewerSession.platform_user_id == (platform_user_id or username.lower()),
                )
            )
        )
        session = result.scalar_one_or_none()
        is_bot = risk_score >= 55.0

        if event_type in ("viewer_leave", "part"):
            if session:
                session.is_active = False
                session.left_at = datetime.now(timezone.utc)
                await self.db.flush()
            return session

        if session:
            session.is_active = True
            session.risk_score = max(session.risk_score, risk_score)
            session.is_suspected_bot = session.is_suspected_bot or is_bot
            if ip_address:
                session.ip_address = ip_address
            if fingerprint_hash:
                session.fingerprint_hash = fingerprint_hash
            if platform_username:
                session.platform_username = platform_username
        else:
            session = ViewerSession(
                stream_id=stream_id,
                platform_user_id=platform_user_id or username.lower(),
                platform_username=username,
                ip_address=ip,
                fingerprint_hash=fingerprint_hash,
                risk_score=risk_score,
                is_suspected_bot=is_bot,
                is_active=True,
                behavior_metrics={"source": "ingest"},
            )
            self.db.add(session)

        await self.db.flush()
        return session

    async def list_active(
        self,
        stream_id: UUID,
        suspected_only: bool = False,
        limit: int = 200,
    ) -> List[ViewerSession]:
        query = select(ViewerSession).where(
            ViewerSession.stream_id == stream_id,
            ViewerSession.is_active == True,
        )
        if suspected_only:
            query = query.where(ViewerSession.is_suspected_bot == True)
        result = await self.db.execute(
            query.order_by(ViewerSession.risk_score.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def deactivate(self, session_id: UUID, stream_id: UUID) -> Optional[ViewerSession]:
        result = await self.db.execute(
            select(ViewerSession).where(
                ViewerSession.id == session_id,
                ViewerSession.stream_id == stream_id,
            )
        )
        session = result.scalar_one_or_none()
        if session:
            session.is_active = False
            session.left_at = datetime.now(timezone.utc)
            await self.db.flush()
        return session
