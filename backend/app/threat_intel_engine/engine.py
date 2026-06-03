"""Central Threat Intelligence Engine — orchestrates all TI subsystems."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_intel.orchestrator import get_ai_orchestrator
from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.realtime import publish_realtime
from app.infrastructure.cache.redis_client import get_redis
from app.threat_intel_engine.behavioral import BehavioralAnomalyEngine
from app.threat_intel_engine.chat_lexical import ChatLexicalAnalyzer
from app.threat_intel_engine.chat_intelligence import ChatIntelligenceEngine
from app.threat_intel_engine.cross_platform import CrossPlatformCorrelator
from app.threat_intel_engine.engagement import EngagementAnalyzer
from app.threat_intel_engine.graph_engine import ThreatGraphBuilder
from app.threat_intel_engine.hashing import entity_key, hash_value, normalize_username
from app.threat_intel_engine.mongo_store import ThreatIntelMongoStore
from app.threat_intel_engine.schemas import (
    EngagementMetrics,
    EntityReputation,
    ThreatGraphSnapshot,
    ThreatIntelAssessment,
)

logger = get_logger(__name__)
_settings = get_settings()

_ENGINE: Optional["ThreatIntelligenceEngine"] = None

CACHE_TTL = 45
REDIS_PREFIX = "ti:stream:"


class ThreatIntelligenceEngine:
    def __init__(self) -> None:
        self._store = ThreatIntelMongoStore()
        self._engagement = EngagementAnalyzer()
        self._chat = ChatLexicalAnalyzer()
        self._chat_intel = ChatIntelligenceEngine()
        self._behavioral = BehavioralAnomalyEngine()
        self._graph = ThreatGraphBuilder()
        self._cross = CrossPlatformCorrelator(self._store)
        self._session_entities: Dict[str, set[str]] = {}

    @property
    def enabled(self) -> bool:
        return bool(_settings.threat_intel_engine_enabled)

    async def process_event(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        stream_id: UUID,
        platform: str,
        event_type: str,
        metadata: Dict[str, Any],
        skip_ai: bool = False,
    ) -> Optional[ThreatIntelAssessment]:
        if not self.enabled:
            return None

        tid = str(tenant_id)
        sid = str(stream_id)
        username = (
            metadata.get("username")
            or metadata.get("user_name")
            or metadata.get("display_name")
        )
        platform_user_id = metadata.get("user_id") or metadata.get("platform_user_id")
        ip = metadata.get("ip_address") or metadata.get("ip")
        fp = metadata.get("fingerprint_hash") or metadata.get("fingerprint")
        network_reputation = metadata.get("network_reputation")
        if not isinstance(network_reputation, dict):
            network_reputation = {}

        ekey = entity_key(
            platform=platform,
            platform_user_id=str(platform_user_id) if platform_user_id else None,
            username=str(username) if username else None,
            fingerprint_hash=str(fp) if fp else None,
            ip_address=str(ip) if ip else None,
        )

        known_tbi = bool(metadata.get("known_public_bot"))
        tbi_meta = metadata.get("twitchbots_info")
        if not isinstance(tbi_meta, dict):
            tbi_meta = {}

        suspected = bool(
            metadata.get("is_bot")
            or metadata.get("suspected")
            or metadata.get("risk_score", 0) >= 60
            or known_tbi
        )

        et = (event_type or "").lower()
        behavioral = self._behavioral.record_event(
            sid,
            ekey,
            et,
            {
                **metadata,
                "ip_hash": hash_value(str(ip), "ip") if ip else metadata.get("ip_hash"),
                "fingerprint_hash": str(fp)[:64] if fp else metadata.get("fingerprint_hash"),
            },
            network_reputation=network_reputation,
        )
        if et in ("chat_message", "message", "chat"):
            self._engagement.record_chat(sid, ekey)
            msg = str(metadata.get("message") or metadata.get("text") or "")
            if msg:
                chat_analysis = self._chat.analyze(sid, ekey, msg)
                advanced_chat = await self._chat_intel.analyze_message(
                    sid,
                    str(platform_user_id or ekey),
                    str(username or "unknown"),
                    msg,
                    metadata.get("timestamp"),
                )
                chat_analysis["advanced"] = advanced_chat
                chat_analysis["spam_probability"] = max(
                    float(chat_analysis.get("spam_probability", 0)),
                    float(advanced_chat.get("spam_score", {}).get("confidence", 0)),
                    float(advanced_chat.get("coordinated_score", {}).get("confidence", 0)),
                )
                await self._store.append_chat_pattern(
                    tid, ekey, sid, msg, chat_analysis
                )
                await self._update_entity(
                    tid,
                    ekey,
                    platform,
                    username,
                    chat_analysis=chat_analysis,
                    ip=ip,
                    fp=fp,
                    known_twitchbots=known_tbi,
                    tbi_meta=tbi_meta,
                    behavioral=behavioral.to_dict(),
                    network_reputation=network_reputation,
                )
        elif et in ("viewer_join", "join", "viewer", "presence"):
            vc = metadata.get("viewer_count")
            self._engagement.record_viewer(
                sid,
                ekey,
                suspected=suspected,
                viewer_count=int(vc) if vc is not None else None,
            )
            await self._update_entity(
                tid,
                ekey,
                platform,
                username,
                ip=ip,
                fp=fp,
                suspected=suspected,
                known_twitchbots=known_tbi,
                tbi_meta=tbi_meta,
                behavioral=behavioral.to_dict(),
                network_reputation=network_reputation,
            )
        elif et in ("follow", "subscription", "raid"):
            await self._update_entity(
                tid,
                ekey,
                platform,
                username,
                follow_burst=True,
                ip=ip,
                fp=fp,
                known_twitchbots=known_tbi,
                tbi_meta=tbi_meta,
                behavioral=behavioral.to_dict(),
                network_reputation=network_reputation,
            )

        sess = self._session_entities.setdefault(sid, set())
        if len(sess) < 500:
            sess.add(ekey)
            others = list(sess - {ekey})[-8:]
            for o in others:
                self._graph.link(sid, ekey, o, reason="co_session")
        if fp:
            fp_key = hash_value(str(fp), "fp")
            for o in sess:
                if o != ekey and fp_key in o:
                    self._graph.link(sid, ekey, o, reason="shared_fingerprint", weight=3)

        self._graph.set_node_meta(
            sid,
            ekey,
            label=str(username)[:32] if username else ekey[:8],
            platform=platform,
            threat_score=metadata.get("risk_score", 0) or 0,
            bot_probability=metadata.get("bot_probability", 0) or 0,
        )

        await self._cross.register_identity(
            tid, platform=platform, username=str(username) if username else None, entity_key=ekey
        )

        engagement = self._engagement.compute(sid)
        engagement.lexical_diversity = round(
            self._chat.stream_lexical_diversity(sid), 4
        )
        await self._store.save_engagement(tid, sid, engagement.model_dump())

        ai_assessment = None
        ai_cached = metadata.get("ai_intel")
        if skip_ai and ai_cached:
            from app.ai_intel.schemas import AIAssessment, ThreatClassification, ThreatLevel

            try:
                ai_assessment = AIAssessment(
                    risk_score=float(ai_cached.get("risk_score", 0)),
                    attack_probability=float(ai_cached.get("attack_probability", 0)),
                    threat_level=ThreatLevel(ai_cached.get("threat_level", "low")),
                    classification=ThreatClassification(
                        ai_cached.get("classification", "none")
                    ),
                    early_warning=bool(ai_cached.get("early_warning")),
                    confidence=float(ai_cached.get("confidence", 0.5)),
                    false_positive_likelihood=float(
                        ai_cached.get("false_positive_likelihood", 0.2)
                    ),
                    anomaly_score=float(ai_cached.get("anomaly_score", 0)),
                    bot_probability=float(ai_cached.get("bot_probability", 0)),
                    raid_probability=float(ai_cached.get("raid_probability", 0)),
                    viewbot_probability=float(ai_cached.get("viewbot_probability", 0)),
                    automation_probability=float(
                        ai_cached.get("automation_probability", 0)
                    ),
                    coordination_score=float(ai_cached.get("coordination_score", 0)),
                    flags=list(ai_cached.get("flags") or []),
                    model_contributions=dict(ai_cached.get("model_contributions") or {}),
                    features_snapshot=dict(ai_cached.get("features_snapshot") or {}),
                    recommended_action=str(ai_cached.get("recommended_action", "monitor")),
                    recommendations=list(ai_cached.get("recommendations") or []),
                    auto_mitigate=bool(ai_cached.get("auto_mitigate")),
                    model_version=str(ai_cached.get("model_version", "")),
                    inference_ms=float(ai_cached.get("inference_ms", 0)),
                )
            except Exception:
                ai_assessment = None
        elif not skip_ai:
            try:
                ai_assessment = await get_ai_orchestrator().assess_event(
                    db,
                    stream_id=stream_id,
                    tenant_id=tenant_id,
                    event_type=event_type,
                    metadata=metadata,
                )
            except Exception as exc:
                logger.debug("ti_ai_assess_skip", error=str(exc))

        entity_doc = await self._store.get_entity(tid, ekey)
        reputation = self._doc_to_reputation(entity_doc, ekey) if entity_doc else None

        graph = self._graph.build_snapshot(sid)
        await self._store.replace_graph_edges(
            tid,
            sid,
            [e.model_dump() for e in graph.edges],
        )

        bot_p = reputation.bot_probability if reputation else 0.0
        bot_p = max(bot_p, behavioral.bot_probability)
        if ai_assessment:
            bot_p = max(bot_p, ai_assessment.bot_probability)

        cross_matches = await self._cross.find_matches(
            tid, str(username) if username else None
        )

        assessment = ThreatIntelAssessment(
            entity_key=ekey,
            reputation=reputation,
            engagement=engagement,
            graph=graph,
            bot_probability=round(bot_p, 4),
            attack_severity=round(
                (ai_assessment.risk_score / 100.0 if ai_assessment else 0)
                * max(bot_p, graph.coordination_score, behavioral.anomaly_score),
                4,
            ),
            coordination_score=max(graph.coordination_score, behavioral.sync_score),
            spam_probability=reputation.spam_probability if reputation else 0.0,
            raid_likelihood=max(
                ai_assessment.raid_probability if ai_assessment else 0.0,
                behavioral.raid_probability,
            ),
            synthetic_audience_score=max(
                engagement.synthetic_engagement_score / 100.0,
                behavioral.synthetic_audience_score,
            ),
            trust_score=behavioral.trust_score,
            behavioral=behavioral.to_dict(),
            network_reputation=network_reputation,
            flags=list(dict.fromkeys(
                (ai_assessment.flags if ai_assessment else []) + behavioral.flags
            ))[:16],
            ai_insights=self._insights(engagement, graph, reputation, ai_assessment),
            cross_platform_matches=cross_matches,
        )

        if ai_assessment:
            await self._store.save_prediction(
                tid,
                sid,
                {
                    "entity_key": ekey,
                    "risk_score": ai_assessment.risk_score,
                    "bot_probability": ai_assessment.bot_probability,
                    "classification": ai_assessment.classification.value,
                    "threat_level": ai_assessment.threat_level.value,
                    "coordination_score": ai_assessment.coordination_score,
                    "attack_probability": ai_assessment.attack_probability,
                    "viewbot_probability": ai_assessment.viewbot_probability,
                    "automation_probability": ai_assessment.automation_probability,
                    "reputation_delta": ai_assessment.reputation_delta,
                    "flags": ai_assessment.flags,
                },
            )
        else:
            await self._store.save_prediction(
                tid,
                sid,
                {
                    "entity_key": ekey,
                    "risk_score": assessment.attack_severity * 100,
                    "bot_probability": assessment.bot_probability,
                    "classification": "none",
                    "threat_level": "low",
                    "coordination_score": assessment.coordination_score,
                    "attack_probability": max(
                        assessment.bot_probability,
                        assessment.raid_likelihood,
                        assessment.synthetic_audience_score,
                    ),
                    "viewbot_probability": assessment.bot_probability,
                    "automation_probability": behavioral.anomaly_score,
                    "reputation_delta": 0.0,
                    "flags": assessment.flags,
                },
            )

        await self._cache_stream_snapshot(tid, sid, assessment)
        await publish_realtime(
            tid,
            "threat_intel_update",
            {"stream_id": sid, "payload": assessment.to_dict()},
        )
        if assessment.bot_probability >= 0.7 or assessment.raid_likelihood >= 0.6:
            await publish_realtime(
                tid,
                "threat_intel_alert",
                {
                    "stream_id": sid,
                    "entity_key": ekey,
                    "risk_score": assessment.attack_severity,
                    "bot_probability": assessment.bot_probability,
                    "raid_likelihood": assessment.raid_likelihood,
                    "flags": assessment.flags,
                    "alerts": assessment.graph.high_centrality_nodes if assessment.graph else [],
                },
            )
        return assessment

    async def _update_entity(
        self,
        tenant_id: str,
        ekey: str,
        platform: str,
        username: Optional[str],
        *,
        chat_analysis: Optional[Dict[str, Any]] = None,
        ip: Optional[str] = None,
        fp: Optional[str] = None,
        suspected: bool = False,
        follow_burst: bool = False,
        known_twitchbots: bool = False,
        tbi_meta: Optional[Dict[str, Any]] = None,
        behavioral: Optional[Dict[str, Any]] = None,
        network_reputation: Optional[Dict[str, Any]] = None,
    ) -> None:
        existing = await self._store.get_entity(tenant_id, ekey) or {}
        threat = float(existing.get("threat_score", 0))
        trust = float(existing.get("trust_score", 50))
        bot_p = float(existing.get("bot_probability", 0))
        spam_p = float(existing.get("spam_probability", 0))
        engagement_s = float(existing.get("engagement_score", 50))
        coord = float(existing.get("coordination_score", 0))
        flags = list(existing.get("flags") or [])

        if suspected:
            threat = min(100, threat + 8)
            trust = max(0, trust - 6)
            bot_p = min(1.0, bot_p + 0.12)
            if "suspected_viewer" not in flags:
                flags.append("suspected_viewer")
        if follow_burst:
            threat = min(100, threat + 4)
            bot_p = min(1.0, bot_p + 0.05)
        if known_twitchbots:
            threat = min(100, threat + 22)
            trust = max(0, trust - 35)
            bot_p = min(1.0, max(bot_p, 0.88))
            if "known_twitchbots_info" not in flags:
                flags.append("known_twitchbots_info")
        if chat_analysis:
            spam_p = max(spam_p, float(chat_analysis.get("spam_probability", 0)))
            synth = float(chat_analysis.get("synthetic_chat_score", 0))
            bot_p = max(bot_p, synth * 0.8)
            for f in chat_analysis.get("flags") or []:
                if f not in flags:
                    flags.append(f)
        if behavioral:
            threat = max(threat, float(behavioral.get("bot_probability", 0)) * 100)
            trust = min(trust, float(behavioral.get("trust_score", trust)))
            bot_p = max(bot_p, float(behavioral.get("bot_probability", 0)))
            coord = max(coord, float(behavioral.get("sync_score", 0)))
            for f in behavioral.get("flags") or []:
                if f not in flags:
                    flags.append(f)
        if network_reputation:
            threat_score = float(
                network_reputation.get(
                    "risk_score",
                    network_reputation.get("combined_threat_score", 0),
                )
                or 0
            )
            if threat_score <= 1:
                threat_score *= 100
            threat = max(threat, threat_score)
            for key in ("is_vpn", "is_proxy", "is_tor", "is_datacenter"):
                if network_reputation.get(key) and key not in flags:
                    flags.append(key)

        trust = max(0, 100 - threat * 0.85 - bot_p * 40)
        engagement_s = max(0, min(100, engagement_s + (5 if chat_analysis else 0)))

        patch = {
            "username": username,
            "platform": platform,
            "canonical_username": normalize_username(username),
            "threat_score": round(threat, 2),
            "trust_score": round(trust, 2),
            "engagement_score": round(engagement_s, 2),
            "bot_probability": round(bot_p, 4),
            "spam_probability": round(spam_p, 4),
            "coordination_score": round(coord, 4),
            "flags": flags[-20:],
        }
        if known_twitchbots and tbi_meta:
            patch["bot_known_score"] = float(tbi_meta.get("bot_known_score", 100))
            patch["suspicious_score"] = float(
                tbi_meta.get("suspicious_score", _settings.twitchbots_info_known_bot_risk_score)
            )
            patch["bot_type"] = tbi_meta.get("bot_type")
            patch["source_detection"] = tbi_meta.get(
                "source_detection", "twitchbots_info"
            )
        if ip:
            patch["ip_hash"] = hash_value(str(ip), "ip")
        if fp:
            patch["fingerprint_hash"] = str(fp)[:64]
        if behavioral:
            patch["behavioral"] = behavioral
            patch["synthetic_audience_score"] = float(
                behavioral.get("synthetic_audience_score", 0)
            )
            patch["raid_likelihood"] = float(behavioral.get("raid_probability", 0))
        if network_reputation:
            patch["network_reputation"] = network_reputation
        streams = list(existing.get("streams_seen") or [])
        await self._store.upsert_entity(tenant_id, ekey, patch)

    def _doc_to_reputation(
        self, doc: Dict[str, Any], ekey: str
    ) -> EntityReputation:
        return EntityReputation(
            entity_key=ekey,
            username=doc.get("username"),
            platform=doc.get("platform"),
            trust_score=float(doc.get("trust_score", 50)),
            threat_score=float(doc.get("threat_score", 0)),
            engagement_score=float(doc.get("engagement_score", 50)),
            bot_probability=float(doc.get("bot_probability", 0)),
            coordination_score=float(doc.get("coordination_score", 0)),
            spam_probability=float(doc.get("spam_probability", 0)),
            activity_count=int(doc.get("activity_count", 0)),
            streams_seen=(doc.get("streams_seen") or [])[:20],
            flags=doc.get("flags") or [],
        )

    def _insights(self, engagement, graph, reputation, ai) -> List[str]:
        insights: List[str] = []
        if engagement.growth_anomaly:
            insights.append("Anomalía de crecimiento de viewers detectada.")
        if engagement.engagement_health_score < 35:
            insights.append("Engagement health crítico — posible viewbotting.")
        if engagement.synthetic_engagement_score > 60:
            insights.append("Engagement sintético elevado.")
        if graph.coordination_score > 0.5:
            insights.append("Comportamiento coordinado entre clusters de usuarios.")
        if graph.bot_clusters:
            insights.append(
                f"{len(graph.bot_clusters)} cluster(s) bot con ≥3 nodos correlacionados."
            )
        if reputation and reputation.bot_probability > 0.7:
            insights.append("Entidad con alta probabilidad de bot.")
        if ai and ai.early_warning:
            insights.append("Early warning IA activo.")
        return insights[:8]

    async def _cache_stream_snapshot(
        self, tenant_id: str, stream_id: str, assessment: ThreatIntelAssessment
    ) -> None:
        redis = await get_redis()
        if not redis:
            return
        key = f"{REDIS_PREFIX}{tenant_id}:{stream_id}"
        payload = {
            "updated_at": time.time(),
            "assessment": assessment.to_dict(),
        }
        await redis.setex(key, CACHE_TTL, json.dumps(payload, default=str))

    async def get_stream_intel(
        self, tenant_id: UUID, stream_id: UUID
    ) -> Optional[Dict[str, Any]]:
        tid, sid = str(tenant_id), str(stream_id)
        redis = await get_redis()
        if redis:
            raw = await redis.get(f"{REDIS_PREFIX}{tid}:{sid}")
            if raw:
                return json.loads(raw)

        engagement = await self._store.get_engagement(tid, sid)
        graph_edges = await self._store.get_graph_edges(tid, sid)
        if not engagement and not graph_edges:
            return None
        graph = self._graph.build_snapshot(sid)
        return {
            "updated_at": time.time(),
            "assessment": {
                "engagement": engagement,
                "graph": graph.model_dump(),
            },
        }

    def live_engagement(self, stream_id: str) -> EngagementMetrics:
        return self._engagement.compute(stream_id)

    def live_graph(self, stream_id: str) -> ThreatGraphSnapshot:
        return self._graph.build_snapshot(stream_id)

    async def overview(self, tenant_id: UUID) -> Dict[str, Any]:
        tid = str(tenant_id)
        stats = await self._store.global_stats(tid)
        top = await self._store.top_threat_entities(tid, limit=25)
        return {
            "global": stats,
            "top_threats": [
                {
                    "entity_key": e.get("entity_key"),
                    "username": e.get("username"),
                    "platform": e.get("platform"),
                    "threat_score": e.get("threat_score"),
                    "bot_probability": e.get("bot_probability"),
                    "flags": (e.get("flags") or [])[:5],
                }
                for e in top
            ],
        }


def get_threat_intel_engine() -> ThreatIntelligenceEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = ThreatIntelligenceEngine()
    return _ENGINE
