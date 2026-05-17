from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import decrypt_value
from app.infrastructure.database.models import Attack, AttackType, Platform, Stream
from app.integrations.twitch.helix import TwitchHelixClient
from app.integrations.twitch.irc_chat import collect_chat_presence
from app.services.ai.service import AIService
from app.services.correlation.service import CorrelationService
from app.services.realtime.notify import push_dashboard_realtime
from app.services.streams.helpers import stream_monitor_mode, sync_stream_live_status
from app.services.viewers.session import ViewerSessionService

logger = get_logger(__name__)
ai_service = AIService()


def _detect_viewer_spike(history: List[Dict[str, Any]], current: int) -> Optional[Dict[str, Any]]:
    if len(history) < 3 or current <= 0:
        return None
    counts = [h.get("count", 0) for h in history[-10:] if h.get("count")]
    if not counts:
        return None
    avg = sum(counts) / len(counts)
    if avg < 50:
        return None
    jump_pct = ((current - avg) / avg) * 100
    if jump_pct >= 40 and (current - avg) >= 100:
        return {
            "from_avg": round(avg),
            "to": current,
            "jump_percent": round(jump_pct, 1),
        }
    return None


class ChannelMonitorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.viewers = ViewerSessionService(db)
        self.helix = TwitchHelixClient()

    async def run_cycle(
        self,
        stream: Stream,
        tenant_id: UUID,
        *,
        irc_duration: float = 30.0,
    ) -> Dict[str, Any]:
        stream = await sync_stream_live_status(self.db, stream)
        meta = dict(stream.settings or {})
        login = meta.get("login") or stream.channel_name.lower()

        summary: Dict[str, Any] = {
            "stream_id": str(stream.id),
            "channel": stream.channel_name,
            "is_live": stream.is_live,
            "viewer_count": stream.viewer_count,
            "chatters_synced": 0,
            "suspected_count": 0,
            "attack_created": False,
        }

        if not stream.is_live:
            meta["last_monitor"] = datetime.now(timezone.utc).isoformat()
            stream.settings = meta
            await self.db.flush()
            return summary

        history: List[Dict[str, Any]] = list(meta.get("viewer_history", []))
        history.append({
            "t": datetime.now(timezone.utc).isoformat(),
            "count": stream.viewer_count,
        })
        history = history[-72:]
        meta["viewer_history"] = history
        stream.settings = meta

        spike = _detect_viewer_spike(history, stream.viewer_count)
        chatters_data: List[Dict[str, Any]] = []

        if stream.oauth_token_encrypted and stream.platform == Platform.TWITCH:
            try:
                token = decrypt_value(stream.oauth_token_encrypted)
                names = await self.helix.get_chatters(
                    stream.external_id,
                    stream.external_id,
                    token,
                )
                for item in names:
                    chatters_data.append({
                        "username": item["user_login"],
                        "user_id": item["user_id"],
                        "joins": 1,
                        "messages": 0,
                    })
            except Exception as exc:
                logger.warning("helix_chatters_failed", stream=str(stream.id), error=str(exc))

        if not chatters_data and stream_monitor_mode(stream) and login:
            snapshot = await collect_chat_presence(login, duration_seconds=irc_duration)
            for _key, data in snapshot.users.items():
                chatters_data.append({
                    "username": data["username"],
                    "user_id": None,
                    "joins": data.get("joins", 1),
                    "messages": data.get("messages", 0),
                })

        suspected_usernames: List[str] = []
        for chatter in chatters_data:
            session = await self.viewers.upsert_chat_viewer(
                stream.id,
                chatter["username"],
                chatter.get("user_id"),
                joins=chatter.get("joins", 1),
                messages=chatter.get("messages", 0),
                source="helix" if chatter.get("user_id") else "irc",
            )
            if session.is_suspected_bot:
                suspected_usernames.append(session.platform_username or chatter["username"])

        summary["chatters_synced"] = len(chatters_data)
        summary["suspected_count"] = len(suspected_usernames)

        attack_payload = None
        alert_payload = None
        correlation = CorrelationService(self.db)

        join_burst = len(chatters_data) >= 15 and len(suspected_usernames) >= 5
        if spike or join_burst:
            risk = 72.0 if spike else 65.0
            if len(suspected_usernames) >= 8:
                risk = min(risk + 10, 95)

            evidence: Dict[str, Any] = {
                "monitor_cycle": True,
                "viewer_count": stream.viewer_count,
                "chatters_sampled": len(chatters_data),
                "suspected_usernames": suspected_usernames[:30],
                "spike": spike,
                "join_burst": join_burst,
            }

            attack_type = AttackType.VIEWBOT if spike else AttackType.COORDINATED
            ai_insight = await ai_service.analyze_threat(
                attack_type.value,
                risk,
                stream.channel_name,
                evidence,
                monitor_mode=stream_monitor_mode(stream),
            )
            evidence["ai_insight"] = ai_insight

            existing = await self.db.execute(
                select(Attack).where(
                    Attack.stream_id == stream.id,
                    Attack.status == "active",
                    Attack.attack_type == attack_type,
                ).limit(1)
            )
            if not existing.scalar_one_or_none():
                attack = await correlation.create_attack_record(
                    stream_id=stream.id,
                    attack_type=attack_type,
                    risk_score=risk,
                    confidence=0.75,
                    evidence=evidence,
                    source_ips=[],
                    fingerprints=[],
                )
                alert = await correlation.create_alert(
                    tenant_id=tenant_id,
                    attack=attack,
                    title=f"Posible ataque en {stream.channel_name}",
                    message=ai_insight.get("summary", "Actividad anomala detectada"),
                )
                summary["attack_created"] = True
                attack_payload = {
                    "id": str(attack.id),
                    "attack_type": attack.attack_type.value,
                    "severity": attack.severity.value,
                    "risk_score": attack.risk_score,
                    "stream_id": str(stream.id),
                    "channel_name": stream.channel_name,
                }
                alert_payload = {
                    "id": str(alert.id),
                    "title": alert.title,
                    "message": alert.message,
                    "severity": alert.severity.value,
                    "status": alert.status,
                    "created_at": alert.created_at.isoformat(),
                }

        meta["last_monitor"] = datetime.now(timezone.utc).isoformat()
        meta["last_chatters"] = len(chatters_data)
        stream.settings = meta
        await self.db.flush()

        from app.services.dashboard.metrics import get_tenant_stream_ids

        stream_ids = await get_tenant_stream_ids(self.db, tenant_id)
        await push_dashboard_realtime(
            self.db,
            tenant_id,
            stream_ids,
            alert=alert_payload,
            attack=attack_payload,
        )

        return summary
