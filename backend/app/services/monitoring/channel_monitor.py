from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import decrypt_value
from app.infrastructure.database.models import Attack, AttackType, Platform, Stream
from app.integrations.twitch.helix import TwitchHelixClient
from app.integrations.twitch.chat_filters import is_valid_chatter_username
from app.integrations.twitch.irc_chat import collect_chat_presence, score_username_risk
from app.services.ai.service import AIService
from app.services.correlation.service import CorrelationService
from app.services.realtime.notify import push_dashboard_realtime
from app.services.streams.helpers import (
    stream_auto_mitigate,
    stream_monitor_mode,
    sync_stream_live_status,
)
from app.services.monitoring.proxy_intel import (
    collect_proxy_threats,
    merge_attack_proxy_evidence,
)
from app.services.detection.realtime_viewbot import get_realtime_viewbot_engine
from app.services.detection.realtime_actions import apply_viewbot_assessment
from app.services.detection.viewer_bot_screening import ViewerBotScreeningService
from app.services.viewers.session import ViewerSessionService
from app.services.mitigation.service import MitigationService
from app.services.mitigation.targets import (
    build_targets_from_suspected_sessions,
    dedupe_targets,
    suspected_sessions_snapshot,
)

logger = get_logger(__name__)
ai_service = AIService()
settings = get_settings()


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
        self.bot_screening = ViewerBotScreeningService()

    async def _screen_viewers_ai(
        self,
        stream: Stream,
        chatters_data: List[Dict[str, Any]],
        summary: Dict[str, Any],
    ) -> None:
        stats = await self.bot_screening.screen_and_update_sessions(
            self.db,
            stream.id,
            stream.channel_name,
            chatters_data,
        )
        summary["ai_screened"] = stats["screened"]
        summary["ai_flagged"] = stats["flagged"]
        counts = await self.viewers.count_active(stream.id)
        summary["suspected_count"] = counts["suspected"]

    async def _fetch_chatters(
        self,
        stream: Stream,
        login: str,
        *,
        irc_duration: float = 0,
    ) -> tuple[List[Dict[str, Any]], str]:
        by_login: Dict[str, Dict] = {}

        if stream.oauth_token_encrypted and stream.platform == Platform.TWITCH:
            try:
                token = decrypt_value(stream.oauth_token_encrypted)
                names = await self.helix.get_chatters(
                    stream.external_id,
                    stream.external_id,
                    token,
                )
                for item in names:
                    login_name = item.get("user_login") or item.get("user_name", "")
                    if login_name and is_valid_chatter_username(login_name):
                        by_login[login_name.lower()] = {
                            "username": login_name,
                            "user_id": item.get("user_id"),
                            "joins": 1,
                            "messages": 0,
                            "source": "helix",
                        }
            except Exception as exc:
                logger.warning("helix_chatters_failed", stream=str(stream.id), error=str(exc))

        if login and irc_duration > 0:
            snapshot = await collect_chat_presence(login, duration_seconds=irc_duration)
            for _key, data in snapshot.users.items():
                uname = data["username"]
                if not is_valid_chatter_username(uname):
                    continue
                key = uname.lower()
                if key in by_login:
                    by_login[key]["joins"] = max(
                        by_login[key].get("joins", 0),
                        data.get("joins", 1),
                    )
                    by_login[key]["messages"] = max(
                        by_login[key].get("messages", 0),
                        data.get("messages", 0),
                    )
                    if not by_login[key].get("user_id"):
                        by_login[key]["source"] = "helix+irc"
                else:
                    by_login[key] = {
                        "username": uname,
                        "user_id": None,
                        "joins": data.get("joins", 1),
                        "messages": data.get("messages", 0),
                        "source": "irc",
                    }

        source = "helix+irc" if by_login and stream.oauth_token_encrypted and irc_duration > 0 else (
            "helix" if stream.oauth_token_encrypted and by_login else "irc"
        )
        return list(by_login.values()), source

    async def run_full_viewer_load(
        self,
        stream: Stream,
        tenant_id: UUID,
    ) -> Dict[str, Any]:
        """
        Carga maxima del listado en chat: Helix (paginado) + IRC (~65s).
        Es lo mas completo que permite Twitch (no hay API de viewers silenciosos).
        """
        stream = await sync_stream_live_status(self.db, stream)
        meta = dict(stream.settings or {})
        login = meta.get("login") or stream.channel_name.lower()
        has_oauth = bool(stream.oauth_token_encrypted)

        summary: Dict[str, Any] = {
            "stream_id": str(stream.id),
            "channel": stream.channel_name,
            "is_live": stream.is_live,
            "viewer_count": stream.viewer_count,
            "chatters_synced": 0,
            "suspected_count": 0,
            "talking_count": 0,
            "sync_mode": "full_viewers",
            "has_broadcaster_oauth": has_oauth,
            "attack_created": False,
        }

        if not stream.is_live:
            summary["status"] = "offline"
            summary["message"] = "El canal no esta en vivo"
            return summary

        helix_count = 0
        if has_oauth:
            try:
                token = decrypt_value(stream.oauth_token_encrypted)
                names = await self.helix.get_chatters(
                    stream.external_id,
                    stream.external_id,
                    token,
                )
                helix_count = len(names)
            except Exception as exc:
                logger.warning("full_load_helix_failed", error=str(exc))
                summary["helix_error"] = str(exc)[:200]

        irc_seconds = max(10.0, min(float(settings.viewer_load_irc_seconds), 55.0))
        chatters_data, source = await self._fetch_chatters(
            stream,
            login,
            irc_duration=irc_seconds if login else 0,
        )
        summary["helix_chatters"] = helix_count
        summary["merged_chatters"] = len(chatters_data)
        summary["source"] = source

        if not chatters_data:
            summary["status"] = "empty"
            summary["message"] = (
                "No se detectaron usuarios en chat. Si es canal ajeno, pide al streamer "
                "que conecte Twitch (Invitar streamer en Channels) para listado Helix completo."
            )
            return summary

        sync_stats = await self.viewers.sync_chat_presence(
            stream.id,
            chatters_data,
            full_resync=True,
        )
        await self._screen_viewers_ai(stream, chatters_data, summary)
        counts = await self.viewers.count_active(stream.id)
        summary["chatters_synced"] = counts["total"]
        summary["talking_count"] = counts["talking"]
        summary["suspected_count"] = counts["suspected"]

        silent = max(0, (stream.viewer_count or 0) - counts["total"])
        summary["silent_viewers_estimate"] = silent
        if stream.viewer_count and counts["total"]:
            summary["chat_coverage_percent"] = round(
                (counts["total"] / stream.viewer_count) * 100, 1
            )

        meta["last_full_viewer_load"] = datetime.now(timezone.utc).isoformat()
        meta["last_monitor"] = meta["last_full_viewer_load"]
        stream.settings = meta
        await self.db.flush()

        summary["status"] = "ok"
        if has_oauth:
            summary["message"] = (
                f"Listado en chat: {counts['total']} usuarios "
                f"(Twitch reporta {stream.viewer_count} viewers totales)."
            )
        else:
            summary["message"] = (
                f"Listado IRC: {counts['total']} en chat. Para listado Helix completo en canal ajeno, "
                f"usa Invitar streamer en Channels."
            )
        if silent > 50:
            summary["message"] += (
                f" ~{silent} viewers no aparecen en chat (viewbots silenciosos o lurkers)."
            )

        from app.services.dashboard.metrics import get_tenant_stream_ids

        stream_ids = await get_tenant_stream_ids(self.db, tenant_id)
        try:
            await push_dashboard_realtime(self.db, tenant_id, stream_ids)
        except Exception as exc:
            logger.warning("push_dashboard_skip", phase="full_load", error=str(exc))
        return summary

    async def run_quick_sync(
        self,
        stream: Stream,
        tenant_id: UUID,
    ) -> Dict[str, Any]:
        """Sincronizacion rapida: Helix chatters (sin IRC largo)."""
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
            "talking_count": 0,
            "sync_mode": "quick",
            "attack_created": False,
        }

        if not stream.is_live:
            meta["last_quick_sync"] = datetime.now(timezone.utc).isoformat()
            stream.settings = meta
            await self.db.flush()
            return summary

        chatters_data, source = await self._fetch_chatters(stream, login, irc_duration=0)
        if not chatters_data and login:
            summary["note"] = (
                "Sin OAuth del streamer: conecta via invitacion para listar chat al cargar. "
                "Usa escaneo completo (IRC ~55s) mientras tanto."
            )
            counts = await self.viewers.count_active(stream.id)
            summary["chatters_synced"] = counts["total"]
            summary["suspected_count"] = counts["suspected"]
            summary["talking_count"] = counts["talking"]
            return summary

        sync_stats = await self.viewers.sync_chat_presence(
            stream.id,
            chatters_data,
            full_resync=True,
        )
        await self._screen_viewers_ai(stream, chatters_data, summary)
        counts = await self.viewers.count_active(stream.id)
        summary["chatters_synced"] = sync_stats["total_synced"]
        summary["talking_count"] = counts["talking"]
        summary["source"] = source

        meta["last_quick_sync"] = datetime.now(timezone.utc).isoformat()
        meta["last_monitor"] = meta["last_quick_sync"]
        stream.settings = meta
        await self.db.flush()

        from app.services.dashboard.metrics import get_tenant_stream_ids

        stream_ids = await get_tenant_stream_ids(self.db, tenant_id)
        try:
            await push_dashboard_realtime(self.db, tenant_id, stream_ids)
        except Exception as exc:
            logger.warning("push_dashboard_skip", phase="quick_sync", error=str(exc))
        return summary

    async def run_cycle(
        self,
        stream: Stream,
        tenant_id: UUID,
        *,
        irc_duration: float = 55.0,
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
        chatters_data, source = await self._fetch_chatters(
            stream,
            login,
            irc_duration=irc_duration if login else 0,
        )
        talking_usernames = [
            c["username"] for c in chatters_data if c.get("messages", 0) > 0
        ]
        sync_stats = await self.viewers.sync_chat_presence(
            stream.id,
            chatters_data,
            full_resync=True,
        )
        await self._screen_viewers_ai(stream, chatters_data, summary)
        suspected_sessions = await suspected_sessions_snapshot(self.db, stream.id)
        suspected_usernames = [s["username"] for s in suspected_sessions if s.get("username")]
        for c in chatters_data:
            uname = c.get("username")
            if not uname:
                continue
            if score_username_risk(
                uname,
                c.get("joins", 1),
                c.get("messages", 0),
            ) >= 55.0 and uname not in suspected_usernames:
                suspected_usernames.append(uname)

        counts = await self.viewers.count_active(stream.id)
        summary["chatters_synced"] = sync_stats["total_synced"]
        summary["suspected_count"] = counts["suspected"]
        summary["talking_count"] = counts["talking"]
        summary["source"] = source
        summary["sync_mode"] = "full"

        proxy_intel = await collect_proxy_threats(self.db, stream.id)
        silent_estimate = max(0, (stream.viewer_count or 0) - counts["total"])
        if silent_estimate > 50:
            summary["silent_viewbots_estimate"] = silent_estimate

        rt_engine = get_realtime_viewbot_engine()
        intelligence = await rt_engine.assess_stream_sessions(
            self.db, stream.id, chatters_data
        )
        summary["viewbot_intelligence"] = intelligence.to_dict()

        attack_payload = None
        alert_payload = None
        correlation = CorrelationService(self.db)

        join_burst = sync_stats["total_synced"] >= 15 and sync_stats["suspected_count"] >= 5
        proxy_attack = proxy_intel["event_count"] >= 3 or len(proxy_intel["proxy_ips"]) >= 2
        bot_invasion = counts["suspected"] >= settings.bot_suspected_attack_threshold
        intel_attack = intelligence.alert_recommended
        if spike or join_burst or proxy_attack or bot_invasion or intel_attack:
            risk = max(intelligence.risk_score, 72.0 if spike else 65.0)
            if len(suspected_usernames) >= 8:
                risk = min(risk + 10, 95)
            if proxy_attack:
                risk = min(risk + 12, 98)
            if bot_invasion:
                risk = min(risk + 15, 99)

            evidence: Dict[str, Any] = merge_attack_proxy_evidence(
                {
                    "monitor_cycle": True,
                    "viewbot_intelligence": intelligence.to_dict(),
                    "viewer_count": stream.viewer_count,
                    "chatters_sampled": len(chatters_data),
                    "suspected_usernames": suspected_usernames[:30],
                    "suspected_sessions": suspected_sessions[:30],
                    "talking_usernames": talking_usernames[:50],
                    "spike": spike,
                    "join_burst": join_burst,
                    "proxy_attack": proxy_attack,
                    "bot_invasion": bot_invasion,
                    "twitch_insights_matches": sum(
                        1 for s in suspected_sessions if s.get("source") == "twitch_insights"
                    ),
                    "silent_viewbots_estimate": silent_estimate if silent_estimate > 50 else None,
                },
                proxy_intel,
            )
            source_ips = list(proxy_intel["proxy_ips"])[:20]
            fingerprints = list(proxy_intel["fingerprints"])[:10]

            if bot_invasion or (proxy_attack and spike):
                attack_type = AttackType.VIEWBOT
            elif proxy_attack:
                attack_type = AttackType.COORDINATED
            else:
                attack_type = AttackType.VIEWBOT if spike else AttackType.COORDINATED
            ai_insight = await ai_service.analyze_threat(
                attack_type.value,
                risk,
                stream.channel_name,
                evidence,
                monitor_mode=stream_monitor_mode(stream),
            )
            evidence["ai_insight"] = ai_insight

            if not await correlation.get_active_attack(stream.id, attack_type):
                attack = await correlation.create_attack_record(
                    stream_id=stream.id,
                    attack_type=attack_type,
                    risk_score=risk,
                    confidence=0.8 if proxy_attack else 0.75,
                    evidence=evidence,
                    source_ips=source_ips,
                    fingerprints=fingerprints,
                )
                if stream_auto_mitigate(stream) and risk >= 70.0:
                    mitigation = MitigationService(self.db)
                    targets = await build_targets_from_suspected_sessions(
                        self.db, stream.id, limit=40
                    )
                    for ip in source_ips[:15]:
                        targets.append({"type": "ip", "value": ip})
                    for fp in fingerprints[:5]:
                        targets.append({"type": "fingerprint", "value": fp})
                    targets = dedupe_targets(targets)[:80]
                    if targets:
                        action = await mitigation.progressive_mitigation(
                            stream_id=stream.id,
                            tenant_id=tenant_id,
                            attack_id=attack.id,
                            risk_score=risk,
                            threat_type=attack_type.value,
                            targets=targets,
                            evidence=evidence,
                            stream=stream,
                        )
                        summary["auto_mitigated"] = True
                        summary["mitigation_action"] = action.value
                        summary["mitigation_targets"] = len(targets)
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
        try:
            await push_dashboard_realtime(
                self.db,
                tenant_id,
                stream_ids,
                alert=alert_payload,
                attack=attack_payload,
            )
        except Exception as exc:
            logger.warning("push_dashboard_skip", phase="monitor_cycle", error=str(exc))

        return summary
