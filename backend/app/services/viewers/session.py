from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import ViewerSession
from app.integrations.twitch.chat_filters import (
    CHAT_PRESENCE_SOURCES,
    is_valid_chat_presence,
)
from app.integrations.twitch.irc_chat import score_username_risk

CHAT_IP_PLACEHOLDER = "twitch:chat"
NON_CHAT_SOURCES = frozenset({"ingest", "widget", "api"})


def is_chat_presence_session(session: ViewerSession) -> bool:
    """Acepta presencia de chat de plataformas y excluye pings o IPs sueltas."""
    metrics = session.behavior_metrics or {}
    source = str(metrics.get("source", "")).lower()
    source = {
        "platform_kick": "kick_chat",
        "platform_youtube": "youtube_live_chat",
        "platform_tiktok": "tiktok_live_chat",
    }.get(source, source)
    if source in NON_CHAT_SOURCES:
        return False
    if source in CHAT_PRESENCE_SOURCES:
        # Los eventos oficiales de chat de Kick/YouTube identifican al usuario
        # por su ID de plataforma, no por IP. El pipeline puede conservar una
        # IP de red si otra fuente enriqueció el evento; eso no debe ocultarlo.
        if source in {"kick_chat", "youtube_live_chat", "tiktok_live_chat"}:
            return is_valid_chat_presence(session.platform_username or "", source)
        return (
            session.ip_address == CHAT_IP_PLACEHOLDER
            and is_valid_chat_presence(session.platform_username or "", source)
        )
    if session.ip_address != CHAT_IP_PLACEHOLDER:
        return False
    return not source and is_valid_chat_presence(session.platform_username or "", source)


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
        source_name = source.strip().lower()
        twitch_source = source_name in {"irc", "helix", "helix+irc", "helix_chatters"}
        risk = max(
            score_username_risk(username, joins, messages) if twitch_source else 0.0,
            extra_risk,
        )
        is_bot = risk >= 55.0

        uname = username.strip()
        if not is_valid_chat_presence(uname, source_name):
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
            # `joins` is a count from this observed chat window, not a count of
            # API polling cycles. Repeated snapshots must not inflate bot risk.
            metrics["joins"] = max(int(metrics.get("joins", 0)), joins)
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
        source: str = "ingest",
    ) -> Optional[ViewerSession]:
        if not platform_username and not platform_user_id:
            return None

        username = platform_username or platform_user_id or "unknown"
        ip = ip_address or CHAT_IP_PLACEHOLDER
        source_name = {
            "platform_kick": "kick_chat",
            "platform_youtube": "youtube_live_chat",
            "platform_tiktok": "tiktok_live_chat",
            "twitch_eventsub": "helix",
        }.get(source, source)
        if event_type == "chat_message" and source_name not in CHAT_PRESENCE_SOURCES:
            source_name = "ingest"

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
            if event_type == "chat_message":
                session.chat_messages += 1
            metrics = dict(session.behavior_metrics or {})
            metrics["source"] = source_name
            if event_type == "chat_message":
                metrics["messages"] = int(metrics.get("messages", 0)) + 1
            metrics["last_seen"] = datetime.now(timezone.utc).isoformat()
            session.behavior_metrics = metrics
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
                chat_messages=1 if event_type == "chat_message" else 0,
                behavior_metrics={
                    "source": source_name,
                    "messages": 1 if event_type == "chat_message" else 0,
                },
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
        clear_if_empty: bool = False,
    ) -> Dict[str, int]:
        """Importa lista completa del chat; opcionalmente desactiva quien ya no esta."""
        seen_usernames: List[str] = []
        suspected = 0
        for chatter in chatters:
            username = chatter.get("username", "")
            source = chatter.get("source", "irc")
            if not is_valid_chat_presence(username, source):
                continue
            session = await self.upsert_chat_viewer(
                stream_id,
                username,
                chatter.get("user_id"),
                joins=chatter.get("joins", 1),
                messages=chatter.get("messages", 0),
                source=source,
            )
            if not session:
                continue
            seen_usernames.append((session.platform_username or username).lower())
            if session.is_suspected_bot:
                suspected += 1

        await self.deactivate_non_chat_sessions(stream_id)

        if full_resync and (seen_usernames or clear_if_empty):
            stale_query = update(ViewerSession).where(
                ViewerSession.stream_id == stream_id,
                ViewerSession.is_active == True,
            )
            if seen_usernames:
                stale_query = stale_query.where(
                    func.lower(ViewerSession.platform_username).notin_(seen_usernames)
                )
            await self.db.execute(
                stale_query.values(
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
            or_(
                ViewerSession.ip_address == CHAT_IP_PLACEHOLDER,
                ViewerSession.behavior_metrics["source"].as_string().in_(
                    (
                        "kick_chat",
                        "youtube_live_chat",
                        "tiktok_live_chat",
                        "platform_kick",
                        "platform_youtube",
                        "platform_tiktok",
                    )
                ),
            ),
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

    async def deactivate_suspected(self, stream_id: UUID) -> int:
        result = await self.db.execute(
            select(ViewerSession).where(
                ViewerSession.stream_id == stream_id,
                ViewerSession.is_active == True,
                ViewerSession.is_suspected_bot == True,
            )
        )
        count = 0
        now = datetime.now(timezone.utc)
        for session in result.scalars().all():
            session.is_active = False
            session.left_at = now
            count += 1
        if count:
            await self.db.flush()
        return count

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
