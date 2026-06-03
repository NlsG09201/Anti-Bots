"""Real-time Threat Correlation Engine — Unified threat assessment."""

from typing import Any, Dict, List, Optional, Set
from uuid import UUID
from datetime import datetime, timedelta
import json
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import get_redis
from app.integrations.threat_intel.aggregator import IPIntelligenceAggregator
from app.ai_intel.reputation.network_score import NetworkReputationScorer
from app.threat_intel_engine.behavioral_advanced import BehavioralAnalyzer
from app.threat_intel_engine.chat_intelligence import ChatIntelligenceEngine
from app.threat_intel_engine.graph_engine import ThreatGraphBuilder

logger = get_logger(__name__)
settings = get_settings()

CACHE_TTL = 600  # 10 minutes
ALERT_CACHE_TTL = 3600  # 1 hour


class ThreatCorrelationEngine:
    """
    Real-time threat correlation combining:
    - IP Intelligence
    - Network Reputation
    - Behavioral Analysis
    - Chat Intelligence
    - Graph-based Correlation
    """

    def __init__(self):
        self._ip_aggregator = IPIntelligenceAggregator()
        self._reputation_scorer = NetworkReputationScorer()
        self._behavioral = BehavioralAnalyzer()
        self._chat = ChatIntelligenceEngine()
        self._graph = ThreatGraphBuilder()
        self._cache = get_redis()

    async def assess_stream_threat(
        self,
        stream_id: str,
        tenant_id: UUID,
        current_viewer_count: int,
        viewers_data: List[Dict[str, Any]],
        recent_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Comprehensive stream threat assessment."""
        cache_key = f"threat:stream:{stream_id}:correlation"
        
        # Try cache first
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        assessment_time = int(__import__("time").time())

        # Parallel threat assessment
        assessment = {
            "stream_id": str(stream_id),
            "tenant_id": str(tenant_id),
            "assessment_timestamp": assessment_time,
            "viewer_count": current_viewer_count,
            "threat_components": {},
            "overall_risk_score": 0.0,
            "recommendations": [],
            "detected_attacks": [],
            "active_alerts": [],
        }

        # Parallel tasks
        tasks = {
            "ip_threats": self._assess_ip_threats(stream_id, viewers_data),
            "behavioral": self._assess_behavioral_threats(stream_id, viewers_data, current_viewer_count),
            "chat": self._assess_chat_threats(stream_id, recent_messages),
            "graph_correlation": self._assess_graph_correlations(stream_id, viewers_data),
        }

        results = await asyncio.gather(
            *tasks.values(),
            return_exceptions=True,
        )

        for key, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.warning(f"threat_assessment_{key}_failed", error=str(result))
                assessment["threat_components"][key] = {"error": str(result)}
            else:
                assessment["threat_components"][key] = result

        # Calculate overall risk
        assessment["overall_risk_score"] = self._calculate_overall_risk(
            assessment["threat_components"]
        )

        # Generate recommendations
        assessment["recommendations"] = self._generate_recommendations(
            assessment["overall_risk_score"],
            assessment["threat_components"],
        )

        # Detect active attacks
        assessment["detected_attacks"] = self._detect_active_attacks(
            assessment["threat_components"]
        )

        # Cache result
        await self._cache_result(cache_key, assessment, CACHE_TTL)

        return assessment

    async def _assess_ip_threats(
        self, stream_id: str, viewers_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Assess threats from IP intelligence."""
        if not viewers_data:
            return {"total_viewers": 0, "suspicious_ips": 0, "threat_score": 0}

        # Extract unique IPs
        ips = list(set(v.get("ip_address") for v in viewers_data if v.get("ip_address")))
        
        if not ips:
            return {"total_viewers": 0, "suspicious_ips": 0, "threat_score": 0}

        # Batch assess IPs
        ip_assessments = await self._ip_aggregator.batch_assess(ips)

        # Calculate threat metrics
        suspicious_count = sum(
            1
            for ip_assessment in ip_assessments.values()
            if ip_assessment.get("combined_threat_score", 0) >= 0.5
        )

        threat_score = sum(
            ip_assessment.get("combined_threat_score", 0)
            for ip_assessment in ip_assessments.values()
        ) / len(ip_assessments)

        # Get reputation scores
        reputation_results = await self._reputation_scorer.calculate_batch_reputation(
            {ip: assessment.get("sources", {}) for ip, assessment in ip_assessments.items()}
        )

        return {
            "total_viewers": len(viewers_data),
            "total_unique_ips": len(ips),
            "suspicious_ips": suspicious_count,
            "threat_score": threat_score,
            "ip_recommendations": [
                assessment.get("recommendation")
                for assessment in reputation_results.values()
            ],
            "threat_categories": self._aggregate_threat_categories(ip_assessments),
        }

    async def _assess_behavioral_threats(
        self,
        stream_id: str,
        viewers_data: List[Dict[str, Any]],
        current_viewer_count: int,
    ) -> Dict[str, Any]:
        """Assess behavioral threats."""
        if current_viewer_count < 10:
            return {"behavioral_threat_score": 0, "patterns_detected": []}

        # Record recent viewer joins
        for viewer in viewers_data[-10:]:
            await self._behavioral.record_viewer_join(
                str(stream_id),
                current_viewer_count,
                ip_address=viewer.get("ip_address"),
                fingerprint=viewer.get("fingerprint"),
                platform_user_id=viewer.get("platform_user_id"),
            )

        # Get behavioral risk
        behavioral_risk = await self._behavioral.get_behavioral_risk_score(str(stream_id))

        # Get specific patterns
        current_time = int(__import__("time").time())
        patterns = await self._behavioral._detect_patterns(str(stream_id), current_viewer_count)

        detected_patterns = [
            name
            for name, data in patterns.items()
            if data.get("detected", False)
        ]

        return {
            "behavioral_threat_score": behavioral_risk,
            "patterns_detected": detected_patterns,
            "patterns_detail": patterns,
        }

    async def _assess_chat_threats(
        self, stream_id: str, recent_messages: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Assess chat-based threats."""
        if not recent_messages:
            return {"chat_threat_score": 0, "spam_indicators": 0}

        # Analyze recent messages
        chat_risk = 0.0
        spam_indicators = 0

        for message in recent_messages[-30:]:
            analysis = await self._chat.analyze_message(
                str(stream_id),
                message.get("user_id", "unknown"),
                message.get("username", "unknown"),
                message.get("message", ""),
                message.get("timestamp"),
            )

            chat_risk += (
                analysis.get("spam_score", {}).get("confidence", 0) * 0.3
                + analysis.get("automation_score", {}).get("confidence", 0) * 0.3
                + analysis.get("coordinated_score", {}).get("confidence", 0) * 0.2
                + analysis.get("repetition_score", {}).get("confidence", 0) * 0.2
            )

            if analysis.get("spam_score", {}).get("spam_detected", False):
                spam_indicators += 1

        avg_chat_risk = chat_risk / len(recent_messages) if recent_messages else 0

        return {
            "chat_threat_score": min(1.0, avg_chat_risk),
            "spam_indicators": spam_indicators,
            "coordinated_spam_detected": spam_indicators >= 3,
        }

    async def _assess_graph_correlations(
        self, stream_id: str, viewers_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Assess graph-based correlations and coordination."""
        if len(viewers_data) < 5:
            return {
                "graph_threat_score": 0,
                "detected_clusters": 0,
                "coordination_score": 0,
            }

        # Build correlation edges
        for i, viewer1 in enumerate(viewers_data):
            for viewer2 in viewers_data[i + 1:]:
                # Link if same IP or fingerprint
                shared_attr = False
                if (
                    viewer1.get("ip_address")
                    == viewer2.get("ip_address")
                ):
                    shared_attr = True
                if (
                    viewer1.get("fingerprint")
                    == viewer2.get("fingerprint")
                ):
                    shared_attr = True

                if shared_attr:
                    self._graph.link(
                        str(stream_id),
                        str(viewer1.get("viewer_id", "v1")),
                        str(viewer2.get("viewer_id", "v2")),
                        reason="shared_attribute",
                    )

        # Build snapshot
        snapshot = self._graph.build_snapshot(str(stream_id))

        return {
            "graph_threat_score": snapshot.coordination_score,
            "detected_clusters": len(snapshot.clusters),
            "cluster_size": (
                max(len(c) for c in snapshot.clusters) if snapshot.clusters else 0
            ),
            "coordination_score": snapshot.coordination_score,
        }

    @staticmethod
    def _calculate_overall_risk(threat_components: Dict[str, Any]) -> float:
        """Calculate overall risk score from components."""
        scores = []

        ip_threats = threat_components.get("ip_threats", {})
        if not isinstance(ip_threats, dict) or "error" not in ip_threats:
            scores.append(ip_threats.get("threat_score", 0) * 0.35)

        behavioral = threat_components.get("behavioral", {})
        if not isinstance(behavioral, dict) or "error" not in behavioral:
            scores.append(behavioral.get("behavioral_threat_score", 0) * 0.3)

        chat = threat_components.get("chat", {})
        if not isinstance(chat, dict) or "error" not in chat:
            scores.append(chat.get("chat_threat_score", 0) * 0.2)

        graph = threat_components.get("graph_correlation", {})
        if not isinstance(graph, dict) or "error" not in graph:
            scores.append(graph.get("graph_threat_score", 0) * 0.15)

        return sum(scores) if scores else 0.0

    @staticmethod
    def _generate_recommendations(risk_score: float, threat_components: Dict) -> List[str]:
        """Generate security recommendations."""
        recommendations = []

        if risk_score >= 0.8:
            recommendations.append("BLOCK_STREAM")
            recommendations.append("INVESTIGATE_ATTACK")
            recommendations.append("ENABLE_FOLLOWER_ONLY_MODE")
        elif risk_score >= 0.6:
            recommendations.append("ENABLE_SLOW_MODE")
            recommendations.append("REQUIRE_VERIFICATION")
            recommendations.append("MONITOR_VIEWERS")
        elif risk_score >= 0.4:
            recommendations.append("INCREASE_MONITORING")
            recommendations.append("BLOCK_SUSPICIOUS_IPS")
        else:
            recommendations.append("STANDARD_MONITORING")

        return recommendations

    @staticmethod
    def _detect_active_attacks(threat_components: Dict[str, Any]) -> List[str]:
        """Detect specific active attacks."""
        attacks = []

        behavioral = threat_components.get("behavioral", {})
        if not isinstance(behavioral, dict) or "error" not in behavioral:
            patterns = behavioral.get("patterns_detected", [])
            if "impossible_growth" in patterns:
                attacks.append("VIEWBOT_ATTACK")
            if "mass_entry" in patterns:
                attacks.append("MASS_JOIN_ATTACK")
            if "synchronized_entries" in patterns:
                attacks.append("COORDINATED_ATTACK")

        chat = threat_components.get("chat", {})
        if not isinstance(chat, dict) or "error" not in chat:
            if chat.get("coordinated_spam_detected"):
                attacks.append("CHAT_SPAM_ATTACK")

        return attacks

    @staticmethod
    def _aggregate_threat_categories(ip_assessments: Dict) -> List[str]:
        """Aggregate threat categories from IP assessments."""
        all_threats: Set[str] = set()
        for assessment in ip_assessments.values():
            threats = assessment.get("threats", [])
            if isinstance(threats, list):
                all_threats.update(threats)
        return sorted(list(all_threats))

    async def _get_cached(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached assessment."""
        try:
            cached = await self._cache.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass
        return None

    async def _cache_result(
        self, cache_key: str, result: Dict[str, Any], ttl: int
    ) -> None:
        """Cache assessment result."""
        try:
            await self._cache.set(cache_key, json.dumps(result), ttl=ttl)
        except Exception as exc:
            logger.warning("threat_correlation_cache_failed", error=str(exc))
