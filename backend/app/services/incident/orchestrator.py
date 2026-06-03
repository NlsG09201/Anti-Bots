import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models import (
    Incident,
    Playbook,
    PlaybookExecution,
)
from app.services.mitigation.service import MitigationService
from app.services.mitigation.targets import build_target_from_incident

logger = get_logger(__name__)


class PlaybookExecutor:
    """Executes incident response playbooks with action orchestration."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.mitigation = MitigationService(db)

    async def execute_playbook(
        self,
        playbook: Playbook,
        incident: Incident,
        tenant_id: UUID,
    ) -> PlaybookExecution:
        """Execute a playbook against an incident."""
        execution = PlaybookExecution(
            playbook_id=playbook.id,
            incident_id=incident.id,
            status="pending",
        )
        self.db.add(execution)
        await self.db.flush()

        start_time = datetime.now(timezone.utc)

        try:
            if not self._conditions_match(playbook.conditions, incident):
                execution.status = "skipped"
                await self.db.flush()
                return execution

            executed_actions = []
            failed_actions = []

            for action_config in playbook.actions or []:
                try:
                    result = await self._execute_action(
                        action_config,
                        incident,
                        tenant_id,
                    )
                    executed_actions.append({
                        "action": action_config.get("action"),
                        "status": "success",
                        "result": result,
                        "executed_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as exc:
                    logger.exception(
                        "playbook_action_failed",
                        playbook_id=str(playbook.id),
                        action=action_config.get("action"),
                        error=str(exc)[:200],
                    )
                    failed_actions.append({
                        "action": action_config.get("action"),
                        "error": str(exc)[:200],
                        "failed_at": datetime.now(timezone.utc).isoformat(),
                    })

            execution.status = "completed" if not failed_actions else "partial"
            execution.executed_actions = executed_actions
            execution.failed_actions = failed_actions
        except Exception as exc:
            logger.exception(
                "playbook_execution_failed",
                playbook_id=str(playbook.id),
                incident_id=str(incident.id),
                error=str(exc)[:300],
            )
            execution.status = "failed"
            execution.error_message = str(exc)[:500]

        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        execution.execution_duration_ms = duration_ms

        playbook.execution_count += 1
        playbook.last_executed_at = end_time
        await self.db.flush()

        return execution

    def _conditions_match(self, conditions: Dict[str, Any], incident: Incident) -> bool:
        """Check if incident matches playbook conditions."""
        if not conditions:
            return True

        # severity check
        severity_condition = conditions.get("severity")
        if severity_condition:
            if isinstance(severity_condition, dict):
                min_severity = severity_condition.get("min", 0.0)
                if incident.severity < min_severity:
                    return False
            elif isinstance(severity_condition, (int, float)):
                if incident.severity < severity_condition:
                    return False

        # confidence check
        confidence_condition = conditions.get("confidence")
        if confidence_condition:
            if isinstance(confidence_condition, dict):
                min_confidence = confidence_condition.get("min", 0.0)
                if incident.confidence < min_confidence:
                    return False
            elif isinstance(confidence_condition, (int, float)):
                if incident.confidence < confidence_condition:
                    return False

        return True

    async def _execute_action(
        self,
        action_config: Dict[str, Any],
        incident: Incident,
        tenant_id: UUID,
    ) -> Dict[str, Any]:
        """Execute a single action (ban, alert, escalate, etc.)."""
        action_type = action_config.get("action")

        if action_type == "ban":
            return await self._action_ban(action_config, incident, tenant_id)
        elif action_type == "alert":
            return await self._action_alert(action_config, incident)
        elif action_type == "escalate":
            return await self._action_escalate(action_config, incident)
        elif action_type == "notify":
            return await self._action_notify(action_config, incident)
        else:
            raise ValueError(f"Unknown action type: {action_type}")

    async def _action_ban(
        self,
        config: Dict[str, Any],
        incident: Incident,
        tenant_id: UUID,
    ) -> Dict[str, Any]:
        """Ban IPs or fingerprints from incident."""
        target_type = config.get("target_type", "ip")
        targets = []

        if target_type == "ip":
            targets = [
                {"type": "ip", "value": ip}
                for ip in (incident.related_ips or [])
            ]
        elif target_type == "fingerprint":
            targets = [
                {"type": "fingerprint", "value": fp}
                for fp in (incident.related_fingerprints or [])
            ]

        if not targets:
            return {"banned": 0, "reason": "no_targets"}

        duration_hours = config.get("duration_hours", 24)

        from app.infrastructure.database.models import MitigationAction

        action = MitigationAction.BAN
        bans = await self.mitigation.apply_mitigation(
            stream_id=incident.stream_id,
            tenant_id=tenant_id,
            action=action,
            targets=targets,
            evidence={"playbook_auto_ban": True, "incident_id": str(incident.id)},
            duration_hours=duration_hours,
        )

        return {"banned": len(bans), "targets": [t["value"] for t in targets]}

    async def _action_alert(
        self,
        config: Dict[str, Any],
        incident: Incident,
    ) -> Dict[str, Any]:
        """Create alert for incident."""
        from app.infrastructure.database.models import Alert, AlertSeverity

        severity_map = {
            "low": AlertSeverity.LOW,
            "medium": AlertSeverity.MEDIUM,
            "high": AlertSeverity.HIGH,
            "critical": AlertSeverity.CRITICAL,
        }

        severity = severity_map.get(
            config.get("severity", "high"),
            AlertSeverity.HIGH,
        )

        title = config.get("title", f"Incident {incident.id}")
        message = config.get("message", f"Auto-generated alert for incident {incident.id}")

        alert = Alert(
            tenant_id=incident.stream_id,
            title=title,
            message=message,
            severity=severity,
            status="open",
            source="playbook",
        )
        self.db.add(alert)
        await self.db.flush()

        return {"alert_id": str(alert.id), "severity": severity.value}

    async def _action_escalate(
        self,
        config: Dict[str, Any],
        incident: Incident,
    ) -> Dict[str, Any]:
        """Escalate incident status."""
        from app.infrastructure.database.models import IncidentStatus

        incident.status = IncidentStatus.ESCALATED
        await self.db.flush()

        return {"escalated": True, "status": incident.status.value}

    async def _action_notify(
        self,
        config: Dict[str, Any],
        incident: Incident,
    ) -> Dict[str, Any]:
        """Send notification (Discord, Slack, etc.)."""
        channel = config.get("channel", "discord")
        message = config.get("message", f"Incident detected: {incident.id}")

        if channel == "discord":
            from app.integrations.discord.webhook import send_discord_webhook

            try:
                await send_discord_webhook(message)
                return {"notified": True, "channel": channel}
            except Exception as exc:
                logger.warning("discord_notification_failed", error=str(exc)[:100])
                return {"notified": False, "channel": channel, "error": str(exc)[:100]}

        return {"notified": False, "reason": f"unknown_channel: {channel}"}
