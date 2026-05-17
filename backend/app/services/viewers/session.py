from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import ViewerSession
from app.integrations.twitch.chat_filters import (
    CHAT_PRESENCE_SOURCES,
    is_valid_chatter_username,
)
from app.integrations.twitch.irc_chat import score_username_risk

CHAT_IP_PLACEHOLDER = "twitch:chat"
NON_CHAT_SOURCES = frozenset({"ingest", "widget", "api"})


def is_chat_presence_session(session: ViewerSession) -> bool:
    """Solo usuarios detectados en el chat IRC/Helix, no pings de widget ni IPs sueltas."""
    if session.ip_address != CHAT_IP_PLACEHOLDER:
        return False
    metrics = session.behavior_metrics or {}
    source = str(metrics.get("source", "")).lower()
    if source in NON_CHAT_SOURCES:
        return False
    if source and source not in CHAT_PRESENCE_SOURCES:
        return False
    return is_valid_chatter_username(session.platform_username or "")


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
    ) -> Optional[ViewerSession]:
        risk = max(score_username_risk(username, joins, messages), extra_risk)
        is_bot = risk >= 55.0

        uname = username.strip()
        if not is_valid_chatter_username(uname):
            return None

        result = await self.db.execute(
            select(ViewerSession).where(
                ViewerSession.stream_id == stream_id,
                func.lower(ViewerSession.platform_username) == uname.lower(),
            )
        )
        session = result.scalar_one_or_none()

        if session:
            session.is_active = True
            session.left_at = None
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

    async def sync_chat_presence(
        self,
        stream_id: UUID,
        chatters: List[Dict],
        *,
        full_resync: bool = True,
    ) -> Dict[str, int]:
        """Importa lista completa del chat; opcionalmente desactiva quien ya no esta."""
        seen_usernames: List[str] = []
        suspected = 0
        for chatter in chatters:
            username = chatter.get("username", "")
            if not is_valid_chatter_username(username):
                continue
            session = await self.upsert_chat_viewer(
                stream_id,
                username,
                chatter.get("user_id"),
                joins=chatter.get("joins", 1),
                messages=chatter.get("messages", 0),
                source=chatter.get("source", "irc"),
            )
            if not session:
                continue
            seen_usernames.append((session.platform_username or username).lower())
            if session.is_suspected_bot:
                suspected += 1

        await self.deactivate_non_chat_sessions(stream_id)

        if full_resync and seen_usernames:
            await self.db.execute(
                update(ViewerSession)
                .where(
                    ViewerSession.stream_id == stream_id,
                    ViewerSession.is_active == True,
                    func.lower(ViewerSession.platform_username).notin_(seen_usernames),
                )
                .values(
                    is_active=False,
                    left_at=datetime.now(timezone.utc),
                )
            )
            await self.db.flush()

        return {
            "total_synced": len(seen_usernames),
            "suspected_count": suspected,
        }

    async def deactivate_non_chat_sessions(self, stream_id: UUID) -> int:
        """Oculta sesiones de widget/ingest o usuarios que no son del chat."""
        result = await self.db.execute(
            select(ViewerSession).where(
                ViewerSession.stream_id == stream_id,
                ViewerSession.is_active == True,
            )
        )
        deactivated = 0
        now = datetime.now(timezone.utc)
        for session in result.scalars().all():
            if is_chat_presence_session(session):
                continue
            session.is_active = False
            session.left_at = now
            deactivated += 1
        if deactivated:
            await self.db.flush()
        return deactivated

    async def list_active(
        self,
        stream_id: UUID,
        *,
        suspected_only: bool = False,
        talking_only: bool = False,
        chat_only: bool = True,
        limit: int = 2000,
    ) -> List[ViewerSession]:
        query = select(ViewerSession).where(
            ViewerSession.stream_id == stream_id,
            ViewerSession.is_active == True,
            ViewerSession.ip_address == CHAT_IP_PLACEHOLDER,
        )
        if suspected_only:
            query = query.where(ViewerSession.is_suspected_bot == True)
        if talking_only:
            query = query.where(ViewerSession.chat_messages > 0)
        result = await self.db.execute(
            query.order_by(
                ViewerSession.is_suspected_bot.desc(),
                ViewerSession.chat_messages.desc(),
                ViewerSession.risk_score.desc(),
                ViewerSession.platform_username.asc(),
            ).limit(limit * 2 if chat_only else limit)
        )
        sessions = list(result.scalars().all())
        if chat_only:
            sessions = [s for s in sessions if is_chat_presence_session(s)][:limit]
        return sessions

    async def count_active(
        self,
        stream_id: UUID,
    ) -> Dict[str, int]:
        all_sessions = await self.list_active(stream_id, chat_only=True, limit=5000)
        talking = sum(1 for s in all_sessions if (s.chat_messages or 0) > 0)
        suspected = sum(1 for s in all_sessions if s.is_suspected_bot)
        return {
            "total": len(all_sessions),
            "talking": talking,
            "suspected": suspected,
        }

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
