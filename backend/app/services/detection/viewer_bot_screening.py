"""Cruce de usuarios en chat con Twitch Insights + heurísticas locales + IA."""

import json
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.database.models import Platform, Stream
from app.core.logging import get_logger
from app.integrations.twitch.chat_filters import (
    TWITCH_CHAT_BOTS,
    is_valid_chat_presence,
)
from app.integrations.twitchinsights.bot_database import (
    TI_ATTRIBUTION,
    TwitchInsightsBotRecord,
    get_twitch_insights_db,
)
from app.services.twitchbots.verification_service import get_twitchbots_verification_service
from app.services.viewers.session import ViewerSessionService

logger = get_logger(__name__)
settings = get_settings()

VIEWBOT_NAME_PATTERNS = [
    re.compile(r"^[a-z]{2,5}\d{5,12}$", re.I),
    re.compile(r"^\d{6,}$"),
    re.compile(r"^[a-z0-9]{16,25}$", re.I),
    re.compile(r"viewbot|followbot|bot\d", re.I),
]

KNOWN_MALICIOUS_INDICATORS = frozenset(
    {
        "viewerbot",
        "view_bot",
        "follow4follow",
        "f4fbot",
        "raidbot",
        "ghostviewer",
    }
)


class ViewerBotScreeningService:
    async def screen_and_update_sessions(
        self,
        db: AsyncSession,
        stream_id: UUID,
        channel_name: str,
        chatters: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        stream = await db.get(Stream, stream_id)
        platform = stream.platform.value if stream else "unknown"
        source_by_platform = {
            "twitch": "helix",
            "kick": "kick_chat",
            "youtube": "youtube_live_chat",
            "tiktok": "tiktok_live_chat",
        }
        validation_source = source_by_platform.get(platform, "")
        usernames = [
            c["username"]
            for c in chatters
            if is_valid_chat_presence(c.get("username", ""), validation_source)
        ]
        if not usernames:
            return {
                "screened": 0,
                "flagged": 0,
                "review_required": 0,
                "twitch_insights_matched": 0,
                "twitch_insights_db_size": 0,
                "twitchbots_info_matched": 0,
            }

        tenant_id = str(stream.tenant_id) if stream else ""

        is_twitch = platform == Platform.TWITCH.value
        insights_db = None
        if is_twitch:
            insights_db = get_twitch_insights_db()
            await insights_db.ensure_loaded()

        tbi_map: Dict[str, Any] = {}
        tbi_svc = get_twitchbots_verification_service()
        if is_twitch and tbi_svc.enabled and tenant_id:
            try:
                tbi_results = await tbi_svc.verify_batch(
                    tenant_id,
                    [{"username": u} for u in usernames],
                    stream_id=str(stream_id),
                )
                tbi_map = {k: v.to_verdict_dict() for k, v in tbi_results.items()}
            except Exception as exc:
                logger.warning(
                    "twitchbots_batch_verify_failed",
                    stream_id=str(stream_id),
                    error=str(exc)[:200],
                )

        verdicts = await self.analyze_usernames(
            channel_name,
            usernames,
            tbi_verdicts=tbi_map,
            platform=platform,
        )
        viewer_svc = ViewerSessionService(db)
        sessions = await viewer_svc.list_active(stream_id, chat_only=True, limit=500)
        flagged = 0
        review_required = 0
        insights_matched = 0
        tbi_matched = 0

        for session in sessions:
            uname = session.platform_username or ""
            verdict = verdicts.get(uname.lower()) or verdicts.get(uname)
            if not verdict:
                continue
            metrics = dict(session.behavior_metrics or {})
            metrics["ai_verdict"] = verdict
            session.behavior_metrics = metrics
            if verdict.get("source") == "twitch_insights":
                insights_matched += 1
            if verdict.get("source") == "twitchbots_info":
                tbi_matched += 1
            if verdict.get("classification") == "known_bot":
                session.is_suspected_bot = True
                session.risk_score = max(session.risk_score, float(verdict.get("risk_score", 55)))
                flagged += 1
            elif verdict.get("classification") == "review":
                review_required += 1

        await db.flush()
        return {
            "screened": len(usernames),
            "flagged": flagged,
            "review_required": review_required,
            "twitch_insights_matched": insights_matched,
            "twitch_insights_db_size": insights_db.size if insights_db else 0,
            "twitchbots_info_matched": tbi_matched,
        }

    async def analyze_usernames(
        self,
        channel_name: str,
        usernames: List[str],
        *,
        tbi_verdicts: Optional[Dict[str, Dict[str, Any]]] = None,
        platform: str = "twitch",
    ) -> Dict[str, Dict[str, Any]]:
        """Devuelve dict keyed by lowercase username."""
        is_twitch = platform.lower() == Platform.TWITCH.value
        insights_db = None
        if is_twitch:
            insights_db = get_twitch_insights_db()
            await insights_db.ensure_loaded()
        tbi_verdicts = tbi_verdicts or {}

        results: Dict[str, Dict[str, Any]] = {}
        needs_ai: List[str] = []

        for name in usernames:
            key = name.lower()
            tbi_v = tbi_verdicts.get(key) if is_twitch else None
            if tbi_v and tbi_v.get("is_malicious"):
                if key in TWITCH_CHAT_BOTS:
                    results[key] = {
                        **tbi_v,
                        "is_malicious": False,
                        "classification": "no_strong_signals",
                        "risk_score": min(18.0, float(tbi_v.get("risk_score", 18))),
                        "risk_description": (
                            "Bot de chat legitimo catalogado en TwitchBots.info "
                            "(excluido de viewbotting)."
                        ),
                    }
                else:
                    results[key] = {**tbi_v, "classification": "known_bot"}
                continue
            insight = insights_db.lookup(name) if insights_db else None
            local = self._local_verdict(name, insight, platform=platform)
            results[key] = local
            if local.get("needs_ai") and len(needs_ai) < 40:
                needs_ai.append(name)

        if needs_ai and settings.ai_enabled and settings.openai_api_key:
            try:
                ai_map = await self._ai_screen_batch(
                    channel_name,
                    needs_ai,
                    platform=platform,
                    insights_db_size=insights_db.size if insights_db else 0,
                )
                for name, ai_v in ai_map.items():
                    key = name.lower()
                    merged = self._merge_verdict(results.get(key, {}), ai_v)
                    results[key] = merged
            except Exception as exc:
                logger.warning("viewer_ai_screen_failed", error=str(exc))

        return results

    def _verdict_from_twitch_insights(self, rec: TwitchInsightsBotRecord) -> Dict[str, Any]:
        online_note = (
            " Aparece en la lista de bots activos ahora mismo en Twitch Insights."
            if rec.is_online_now
            else ""
        )
        return {
            "is_malicious": True,
            "classification": "known_bot",
            "confidence": 0.98,
            "risk_score": 98.0 if rec.is_online_now else 92.0,
            "risk_description": (
                f"Cuenta en la base Twitch Insights de viewbots de listas de espectadores "
                f"(vista en {rec.channel_count} canales en vivo; última vez {rec.last_seen_iso})."
                f"{online_note}"
            ),
            "source": "twitch_insights",
            "needs_ai": False,
            "twitch_insights": {
                "channel_count": rec.channel_count,
                "last_seen_ts": rec.last_seen_ts,
                "is_online_now": rec.is_online_now,
                "reference": TI_ATTRIBUTION,
            },
        }

    def _local_verdict(
        self,
        username: str,
        insights_record: Optional[TwitchInsightsBotRecord] = None,
        *,
        platform: str = "twitch",
    ) -> Dict[str, Any]:
        lower = username.lower()
        if platform.lower() == Platform.TWITCH.value and lower in TWITCH_CHAT_BOTS:
            return {
                "is_malicious": False,
                "classification": "no_strong_signals",
                "confidence": 0.95,
                "risk_score": 0.0,
                "risk_description": "Bot de chat legitimo (excluido del listado).",
                "source": "local_db",
                "needs_ai": False,
            }

        if insights_record:
            return self._verdict_from_twitch_insights(insights_record)

        for ind in KNOWN_MALICIOUS_INDICATORS:
            if ind in lower:
                return {
                    "is_malicious": False,
                    "classification": "review",
                    "confidence": 0.55,
                    "risk_score": 65.0,
                    "risk_description": f"Nombre asociado a patrón sospechoso ({ind}); requiere más evidencia.",
                    "source": "malicious_db",
                    "needs_ai": False,
                }

        for pat in VIEWBOT_NAME_PATTERNS:
            if pat.search(username):
                return {
                    "is_malicious": False,
                    "classification": "review",
                    "confidence": 0.45,
                    "risk_score": 55.0,
                    "risk_description": "Patrón de nombre posiblemente automatizado; no basta para confirmar un bot.",
                    "source": "pattern_db",
                    "needs_ai": True,
                }

        if len(username) >= 10 and sum(c.isdigit() for c in username) >= 4:
            return {
                "is_malicious": False,
                "classification": "review",
                "confidence": 0.35,
                "risk_score": 45.0,
                "risk_description": "Nombre con muchos digitos; requiere revision.",
                "source": "heuristic",
                "needs_ai": True,
            }

        return {
            "is_malicious": False,
            "classification": "no_strong_signals",
            "confidence": 0.25,
            "risk_score": 10.0,
            "risk_description": "Sin coincidencias en las fuentes consultadas; no confirma que sea una persona real.",
            "source": "local_db",
            "needs_ai": False,
        }

    def _merge_verdict(self, local: Dict[str, Any], ai: Dict[str, Any]) -> Dict[str, Any]:
        risk = max(float(local.get("risk_score", 0)), float(ai.get("risk_score", 0)))
        known_bot = local.get("classification") == "known_bot"
        malicious = known_bot or bool(ai.get("is_malicious"))
        desc = ai.get("risk_description") or local.get("risk_description", "")
        source = local.get("source", "local_db")
        if ai.get("source") == "openai":
            source = "twitch_insights+openai" if source == "twitch_insights" else "local+openai"
        classification = "known_bot" if known_bot else (
            "review" if malicious or risk >= 45 else "no_strong_signals"
        )
        return {
            "is_malicious": malicious,
            "classification": classification,
            "risk_score": risk,
            "risk_description": desc,
            "source": source,
            "needs_ai": False,
            "confidence": float(ai.get("confidence", local.get("confidence", 0.25))),
            **({"twitch_insights": local["twitch_insights"]} if local.get("twitch_insights") else {}),
        }

    async def _ai_screen_batch(
        self,
        channel_name: str,
        usernames: List[str],
        *,
        platform: str = "twitch",
        insights_db_size: int = 0,
    ) -> Dict[str, Dict[str, Any]]:
        prompt = (
            f"Plataforma: {platform}. Canal: {channel_name}. Usuarios observados en chat:\n"
            f"{', '.join(usernames[:40])}\n\n"
            + (
                "Usa como referencia Twitch Insights "
                f"({TI_ATTRIBUTION}, ~{insights_db_size} cuentas) y TwitchBots.info. "
                if platform == Platform.TWITCH.value
                else "No hay una base pública de identidad/bots verificada para esta plataforma. "
            )
            + "Evalúa sólo señales observables; un nombre numérico o poco común no demuestra automatización. "
            "Sin evidencia suficiente usa classification=review y baja confianza. No afirmes que una cuenta "
            "es humana; evita recomendar sanciones.\n"
            "Responde JSON: {\"users\": [{\"username\": \"...\", \"is_malicious\": bool, "
            "\"risk_score\": 0-100, \"confidence\": 0-1, \"risk_description\": \"una frase en español\"}]}"
        )
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Analista anti-bots de chat en plataformas de streaming. Distingue "
                                "hechos de hipótesis, no inventes fuentes ni señales y responde sólo JSON válido."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.15,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            data = json.loads(response.json()["choices"][0]["message"]["content"])
            out: Dict[str, Dict[str, Any]] = {}
            for item in data.get("users", []):
                uname = str(item.get("username", "")).strip()
                if not uname:
                    continue
                out[uname.lower()] = {
                    "is_malicious": bool(item.get("is_malicious")),
                    "risk_score": float(item.get("risk_score", 0)),
                    "confidence": max(0.0, min(1.0, float(item.get("confidence", 0.5)))),
                    "risk_description": str(
                        item.get("risk_description", "Evaluacion IA sin detalle.")
                    )[:500],
                    "source": "openai",
                    "confidence": 0.75,
                }
            return out
