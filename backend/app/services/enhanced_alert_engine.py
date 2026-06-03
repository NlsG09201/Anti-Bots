"""Enhanced Alert Engine with database persistence."""

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID, uuid4
import json
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import get_redis
from app.infrastructure.repositories.alert_repository import AlertRepository
from app.events.realtime import publish_realtime

logger = get_logger(__name__)
settings = get_settings()


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AlertType(str, Enum):
    """Alert types."""
    VIEWBOT_ATTACK = "VIEWBOT_ATTACK"
    FOLLOWBOT_ATTACK = "FOLLOWBOT_ATTACK"
    CHAT_SPAM = "CHAT_SPAM"
    MASS_JOIN = "MASS_JOIN"
    COORDINATED_ATTACK = "COORDINATED_ATTACK"
    VPN_SURGE = "VPN_SURGE"
    PROXY_SURGE = "PROXY_SURGE"
    DATACENTER_SURGE = "DATACENTER_SURGE"
    SUSPICIOUS_PATTERN = "SUSPICIOUS_PATTERN"
    RAID_ATTACK = "RAID_ATTACK"


class EnhancedAlertEngine:
    """Alert engine with database persistence."""

    def __init__(self, db_session: AsyncSession):
        self._cache = get_redis()
        self._db = db_session
        self._repo = AlertRepository(db_session)
        self._alert_cooldowns: Dict[str, float] = {}

    async def generate_alert(
        self,
        stream_id: str,
        tenant_id: str,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        description: str,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Generate an alert with database persistence.
        
        Implements deduplication and rate limiting via cooldown tracking.
        """
        alert_key = f"{stream_id}:{alert_type.value}"
        
        # Check cooldown (prevent duplicate alerts)
        now = datetime.utcnow().timestamp()
        cooldown_ttl = 300  # 5 minutes
        last_alert_time = self._alert_cooldowns.get(alert_key, 0)

        if now - last_alert_time < cooldown_ttl:
            return None

        # Update cooldown
        self._alert_cooldowns[alert_key] = now

        try:
            # Create alert in database
            alert_id = uuid4()
            alert = await self._repo.create_alert(
                alert_id=alert_id,
                stream_id=stream_id,
                tenant_id=UUID(tenant_id),
                alert_type=alert_type.value,
                severity=severity.value,
                title=title,
                description=description,
                data=data,
                source="threat_engine",
            )

            # Commit to database
            await self._db.commit()
            
            alert_dict = alert.to_dict()

            # Publish to WebSocket subscribers
            await publish_realtime(f"stream:{stream_id}:alert", alert_dict)

            # Send notifications
            await self._send_notifications(alert_dict)

            logger.info(
                "alert_generated",
                alert_id=alert_id,
                stream=stream_id,
                alert_type=alert_type.value,
                severity=severity.value,
            )

            return alert_dict

        except Exception as exc:
            logger.error("alert_generation_failed", error=str(exc), stream=stream_id)
            await self._db.rollback()
            return None

    async def dismiss_alert(
        self,
        alert_id: str,
        reason: Optional[str] = None,
        dismissed_by: Optional[str] = None,
    ) -> bool:
        """Dismiss an alert."""
        try:
            alert = await self._repo.dismiss_alert(
                alert_id=UUID(alert_id),
                reason=reason,
                dismissed_by=dismissed_by,
            )
            await self._db.commit()
            return alert is not None
        except Exception as exc:
            logger.error("alert_dismiss_failed", alert=alert_id, error=str(exc))
            await self._db.rollback()
            return False

    async def get_stream_alerts(
        self,
        stream_id: str,
        limit: int = 50,
        offset: int = 0,
        dismissed: Optional[bool] = None,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Get alerts for a stream from database."""
        try:
            alerts, total = await self._repo.get_stream_alerts(
                stream_id=stream_id,
                limit=limit,
                offset=offset,
                dismissed=dismissed,
            )
            return [a.to_dict() for a in alerts], total
        except Exception as exc:
            logger.error("get_stream_alerts_failed", stream=stream_id, error=str(exc))
            return [], 0

    async def generate_alerts_from_assessment(
        self,
        stream_id: str,
        tenant_id: str,
        assessment: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Generate alerts based on threat assessment."""
        alerts: List[Dict[str, Any]] = []

        overall_risk = assessment.get("overall_risk_score", 0)
        detected_attacks = assessment.get("detected_attacks", [])
        threat_components = assessment.get("threat_components", {})

        # CRITICAL: Multiple attacks detected
        if len(detected_attacks) >= 2:
            alert = await self.generate_alert(
                stream_id=stream_id,
                tenant_id=tenant_id,
                alert_type=AlertType.COORDINATED_ATTACK,
                severity=AlertSeverity.CRITICAL,
                title="🚨 Coordinated Attack Detected",
                description=f"Multiple attack vectors detected: {', '.join(detected_attacks)}",
                data={"attacks": detected_attacks, "risk_score": overall_risk},
            )
            if alert:
                alerts.append(alert)

        # HIGH: Viewbot attack
        if "VIEWBOT_ATTACK" in detected_attacks:
            ip_threats = threat_components.get("ip_threats", {})
            alert = await self.generate_alert(
                stream_id=stream_id,
                tenant_id=tenant_id,
                alert_type=AlertType.VIEWBOT_ATTACK,
                severity=AlertSeverity.HIGH,
                title="🤖 Viewbot Attack In Progress",
                description=f"Impossible growth pattern detected. {ip_threats.get('suspicious_ips', 0)} suspicious IPs.",
                data=ip_threats,
            )
            if alert:
                alerts.append(alert)

        # HIGH: Chat spam
        if "CHAT_SPAM_ATTACK" in detected_attacks:
            chat = threat_components.get("chat", {})
            alert = await self.generate_alert(
                stream_id=stream_id,
                tenant_id=tenant_id,
                alert_type=AlertType.CHAT_SPAM,
                severity=AlertSeverity.HIGH,
                title="💬 Chat Spam Attack",
                description=f"Coordinated spam detected. {chat.get('spam_indicators', 0)} spam indicators.",
                data=chat,
            )
            if alert:
                alerts.append(alert)

        # HIGH: VPN surge
        ip_threats = threat_components.get("ip_threats", {})
        vpn_count = len([t for t in ip_threats.get("threat_categories", []) if "vpn" in t])
        if vpn_count > 50:
            alert = await self.generate_alert(
                stream_id=stream_id,
                tenant_id=tenant_id,
                alert_type=AlertType.VPN_SURGE,
                severity=AlertSeverity.HIGH,
                title="🛡️ VPN Surge Detected",
                description=f"{vpn_count} VPN users detected. Possible botting activity.",
                data={"vpn_count": vpn_count},
            )
            if alert:
                alerts.append(alert)

        # MEDIUM: High overall risk
        if overall_risk >= 0.6:
            alert = await self.generate_alert(
                stream_id=stream_id,
                tenant_id=tenant_id,
                alert_type=AlertType.SUSPICIOUS_PATTERN,
                severity=AlertSeverity.MEDIUM,
                title="⚠️ Suspicious Activity",
                description=f"Overall threat score: {(overall_risk * 100):.0f}%. Monitor closely.",
                data={"risk_score": overall_risk},
            )
            if alert:
                alerts.append(alert)

        return alerts

    async def _send_notifications(self, alert: Dict[str, Any]) -> None:
        """Send alert notifications (Discord, webhooks, etc)."""
        tasks = []

        # Discord webhook
        if settings.discord_webhook_url:
            tasks.append(self._send_discord_notification(alert))

        # Custom webhooks
        if settings.alert_webhook_urls:
            tasks.append(self._send_webhook_notifications(alert))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_discord_notification(self, alert: Dict[str, Any]) -> None:
        """Send Discord notification."""
        if not settings.discord_webhook_url:
            return

        try:
            from discord_webhook import DiscordWebhook, DiscordEmbed

            webhook = DiscordWebhook(url=settings.discord_webhook_url)

            # Create embed
            color = self._get_color_for_severity(alert["severity"])
            embed = DiscordEmbed(
                title=alert["title"],
                description=alert["description"],
                color=color,
            )
            embed.add_embed_field(name="Type", value=alert["type"], inline=True)
            embed.add_embed_field(name="Severity", value=alert["severity"], inline=True)
            embed.add_embed_field(name="Stream ID", value=alert["stream_id"], inline=False)

            webhook.add_embed(embed)
            webhook.execute()
        except Exception as exc:
            logger.warning("discord_notification_failed", error=str(exc))

    async def _send_webhook_notifications(self, alert: Dict[str, Any]) -> None:
        """Send custom webhook notifications."""
        if not settings.alert_webhook_urls:
            return

        import httpx

        for webhook_url in settings.alert_webhook_urls:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(webhook_url, json=alert)
            except Exception as exc:
                logger.warning("webhook_notification_failed", webhook=webhook_url, error=str(exc))

    @staticmethod
    def _get_color_for_severity(severity: str) -> int:
        """Get Discord embed color for severity."""
        if severity == "CRITICAL":
            return 0xFF0000  # Red
        elif severity == "HIGH":
            return 0xFF6600  # Orange
        elif severity == "MEDIUM":
            return 0xFFCC00  # Yellow
        else:
            return 0x0066FF  # Blue


async def get_alert_engine(session: AsyncSession) -> EnhancedAlertEngine:
    """Get alert engine instance."""
    return EnhancedAlertEngine(session)
