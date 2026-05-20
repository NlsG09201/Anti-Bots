"""Cruce de usuarios en chat con Twitch Insights + heurísticas locales + IA."""

import json
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.integrations.twitch.chat_filters import TWITCH_CHAT_BOTS, is_valid_chatter_username
from app.integrations.twitchinsights.bot_database import (
    TI_ATTRIBUTION,
    TwitchInsightsBotRecord,
    get_twitch_insights_db,
)
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
        usernames = [
            c["username"]
            for c in chatters
            if is_valid_chatter_username(c.get("username", ""))
        ]
        if not usernames:
            return {
                "screened": 0,
                "flagged": 0,
                "twitch_insights_matched": 0,
                "twitch_insights_db_size": 0,
            }

        insights_db = get_twitch_insights_db()
        await insights_db.ensure_loaded()

        verdicts = await self.analyze_usernames(channel_name, usernames)
        viewer_svc = ViewerSessionService(db)
        sessions = await viewer_svc.list_active(stream_id, chat_only=True, limit=500)
        flagged = 0
        insights_matched = 0

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
            if verdict.get("is_malicious"):
                session.is_suspected_bot = True
                session.risk_score = max(session.risk_score, float(verdict.get("risk_score", 55)))
                flagged += 1

        await db.flush()
        return {
            "screened": len(usernames),
            "flagged": flagged,
            "twitch_insights_matched": insights_matched,
            "twitch_insights_db_size": insights_db.size,
        }

    async def analyze_usernames(
        self,
        channel_name: str,
        usernames: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Devuelve dict keyed by lowercase username."""
        insights_db = get_twitch_insights_db()
        await insights_db.ensure_loaded()

        results: Dict[str, Dict[str, Any]] = {}
        needs_ai: List[str] = []

        for name in usernames:
            local = self._local_verdict(name, insights_db.lookup(name))
            key = name.lower()
            results[key] = local
            if local.get("needs_ai") and len(needs_ai) < 40:
                needs_ai.append(name)

        if needs_ai and settings.ai_enabled and settings.openai_api_key:
            try:
                ai_map = await self._ai_screen_batch(
                    channel_name,
                    needs_ai,
                    insights_db_size=insights_db.size,
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
    ) -> Dict[str, Any]:
        lower = username.lower()
        if lower in TWITCH_CHAT_BOTS:
            return {
                "is_malicious": False,
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
                    "is_malicious": True,
                    "risk_score": 88.0,
                    "risk_description": f"Nombre asociado a patron de bot malicioso ({ind}).",
                    "source": "malicious_db",
                    "needs_ai": False,
                }

        for pat in VIEWBOT_NAME_PATTERNS:
            if pat.search(username):
                return {
                    "is_malicious": True,
                    "risk_score": 72.0,
                    "risk_description": "Patron de nombre tipico de viewbot o cuenta automatizada.",
                    "source": "pattern_db",
                    "needs_ai": True,
                }

        if len(username) >= 10 and sum(c.isdigit() for c in username) >= 4:
            return {
                "is_malicious": False,
                "risk_score": 45.0,
                "risk_description": "Nombre con muchos digitos; requiere revision.",
                "source": "heuristic",
                "needs_ai": True,
            }

        return {
            "is_malicious": False,
            "risk_score": 10.0,
            "risk_description": "Sin coincidencias en Twitch Insights ni heurísticas locales.",
            "source": "local_db",
            "needs_ai": False,
        }

    def _merge_verdict(self, local: Dict[str, Any], ai: Dict[str, Any]) -> Dict[str, Any]:
        risk = max(float(local.get("risk_score", 0)), float(ai.get("risk_score", 0)))
        malicious = local.get("is_malicious") or ai.get("is_malicious")
        desc = ai.get("risk_description") or local.get("risk_description", "")
        source = local.get("source", "local_db")
        if ai.get("source") == "openai":
            source = "twitch_insights+openai" if source == "twitch_insights" else "local+openai"
        return {
            "is_malicious": malicious,
            "risk_score": risk,
            "risk_description": desc,
            "source": source,
            "needs_ai": False,
            "ai_confidence": ai.get("confidence"),
            **({"twitch_insights": local["twitch_insights"]} if local.get("twitch_insights") else {}),
        }

    async def _ai_screen_batch(
        self,
        channel_name: str,
        usernames: List[str],
        *,
        insights_db_size: int = 0,
    ) -> Dict[str, Dict[str, Any]]:
        prompt = (
            f"Canal Twitch: {channel_name}. Usuarios actualmente en el chat:\n"
            f"{', '.join(usernames[:40])}\n\n"
            "Usa como referencia la base comunitaria Twitch Insights "
            f"({TI_ATTRIBUTION}), que cataloga ~{insights_db_size} cuentas conocidas de "
            "viewbots en listas de espectadores desde 2018. Compara patrones de nombres, "
            "viewbots, followbots y cuentas compradas. NO marques viewers normales ni mods.\n"
            "Responde JSON: {\"users\": [{\"username\": \"...\", \"is_malicious\": bool, "
            "\"risk_score\": 0-100, \"risk_description\": \"una frase en español\"}]}"
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
                                "Analista anti-viewbot para Twitch. Conoces la base Twitch "
                                "Insights de viewbots, patrones de nombres generados y ataques "
                                "coordinados en listas de espectadores. Solo JSON valido."
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
                    "risk_description": str(
                        item.get("risk_description", "Evaluacion IA sin detalle.")
                    )[:500],
                    "source": "openai",
                    "confidence": 0.75,
                }
            return out
