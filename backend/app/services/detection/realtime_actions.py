"""Aplica evaluaciones del motor realtime: alertas, ataques y auto-bloqueo."""

from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.database.models import AttackType, Stream
from app.services.ai.service import AIService
from app.services.correlation.service import CorrelationService
from app.services.detection.realtime_viewbot import ViewbotAssessment
from app.services.mitigation.service import MitigationService
from app.services.streams.helpers import stream_auto_mitigate, stream_monitor_mode
from app.workers.tasks import send_discord_alert

settings = get_settings()
_ai = AIService()


async def apply_viewbot_assessment(
    db: AsyncSession,
    stream: Stream,
    tenant_id: UUID,
    assessment: ViewbotAssessment,
    *,
    correlation_id: Optional[str] = None,
    source_ips: Optional[list[str]] = None,
    fingerprints: Optional[list[str]] = None,
    targets: Optional[list[Dict[str, str]]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Crea o actualiza ataque/alerta según score. Devuelve (attack_payload, alert_payload).
    """
    if not assessment.alert_recommended:
        return None, None

    correlation = CorrelationService(db)
    mitigation = MitigationService(db)

    evidence: Dict[str, Any] = {
        "viewbot_intelligence": assessment.to_dict(),
        "classification": assessment.classification,
        "signals": assessment.signals,
    }

    ai_insight = await _ai.analyze_threat(
        "viewbot",
        assessment.risk_score,
        stream.channel_name,
        evidence,
        monitor_mode=stream_monitor_mode(stream),
    )
    evidence["ai_insight"] = ai_insight

    attack_type = (
        AttackType.COORDINATED
        if assessment.classification == "coordinated_bot"
        else AttackType.VIEWBOT
    )

    existing = await correlation.get_active_attack(stream.id, attack_type)
    is_new = existing is None
    if existing:
        attack = existing
        if assessment.risk_score > attack.risk_score:
            attack.risk_score = assessment.risk_score
            merged = dict(attack.evidence or {})
            merged.update(evidence)
            attack.evidence = merged
    else:
        attack = await correlation.create_attack_record(
            stream_id=stream.id,
            attack_type=attack_type,
            risk_score=assessment.risk_score,
            confidence=assessment.confidence,
            evidence=evidence,
            source_ips=source_ips or [],
            fingerprints=fingerprints or [],
            correlation_id=correlation_id,
        )

    alert = None
    if is_new:
        alert = await correlation.create_alert(
            tenant_id=tenant_id,
            attack=attack,
            title=f"Viewbot detectado ({assessment.classification})",
            message=ai_insight.get(
                "summary",
                f"Riesgo {assessment.risk_score:.0f} en {stream.channel_name}",
            ),
        )
        if settings.discord_webhook_url:
            try:
                send_discord_alert.delay(
                    alert.title,
                    alert.message,
                    alert.severity.value,
                )
            except Exception:
                pass

    attack_payload = {
        "id": str(attack.id),
        "attack_type": attack.attack_type.value,
        "severity": attack.severity.value,
        "risk_score": attack.risk_score,
        "stream_id": str(stream.id),
        "channel_name": stream.channel_name,
        "classification": assessment.classification,
    }
    alert_payload = None
    if alert:
        alert_payload = {
            "id": str(alert.id),
            "title": alert.title,
            "message": alert.message,
            "severity": alert.severity.value,
            "status": alert.status,
            "created_at": alert.created_at.isoformat(),
        }

    if assessment.auto_block and stream_auto_mitigate(stream) and targets:
        await mitigation.progressive_mitigation(
            stream_id=stream.id,
            tenant_id=tenant_id,
            attack_id=attack.id,
            risk_score=assessment.risk_score,
            threat_type=attack_type.value,
            targets=targets,
            evidence=evidence,
            stream=stream,
        )

    return attack_payload, alert_payload
