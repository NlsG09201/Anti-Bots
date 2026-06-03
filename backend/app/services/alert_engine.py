"""Alert Engine — Real-time alert generation and management."""

from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID
import json
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import get_redis
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


class ThreatAlert:
    """Alert data structure."""

    def __init__(
        self,
        alert_id: str,
        stream_id: str,
        tenant_id: str,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        description: str,
        data: Dict[str, Any],
        timestamp: Optional[int] = None,
    ):
        self.alert_id = alert_id
        self.stream_id = stream_id
        self.tenant_id = tenant_id
        self.alert_type = alert_type
        self.severity = severity
        self.title = title
        self.description = description
        self.data = data
        self.timestamp = timestamp or int(__import__("time").time())
        self.dismissed = False
        self.ack_timestamp: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.alert_id,
            "stream_id": self.stream_id,
            "tenant_id": self.tenant_id,
            "type": self.alert_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "data": self.data,
            "timestamp": self.timestamp,
            "dismissed": self.dismissed,
            "ack_timestamp": self.ack_timestamp,
        }


class AlertEngine:
    """Generate and manage real-time alerts."""

    def __init__(self):
        self._cache = get_redis()
        self._active_alerts: Dict[str, Set[str]] = {}  # stream_id -> alert_ids
        self._alert_cooldowns: Dict[str, float] = {}  # alert_key -> timestamp

    async def generate_alert(
        self,
        stream_id: str,
        tenant_id: str,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        description: str,
        data: Dict[str, Any],
    ) -> Optional[ThreatAlert]:
        """
        Generate an alert if conditions are met.
        
        Implements deduplication and rate limiting to prevent alert spam.
        """
        import uuid

        alert_key = f"{stream_id}:{alert_type.value}"

        # Check cooldown (prevent duplicate alerts)
        now = __import__("time").time()
        cooldown_ttl = 300  # 5 minutes
        last_alert_time = self._alert_cooldowns.get(alert_key, 0)

        if now - last_alert_time < cooldown_ttl:
            # Already alerted recently for this type
            return None

        # Update cooldown
        self._alert_cooldowns[alert_key] = now

        # Create alert
        alert_id = str(uuid.uuid4())
        alert = ThreatAlert(
            alert_id=alert_id,
            stream_id=stream_id,
            tenant_id=tenant_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            description=description,
            data=data,
        )

        # Store alert
        await self._store_alert(alert)

        # Publish to WebSocket
        await publish_realtime(f"stream:{stream_id}:alert", alert.to_dict())

        # Send notifications
        await self._send_notifications(alert)

        return alert

    async def _store_alert(self, alert: ThreatAlert) -> None:
        """Store alert in cache and database."""
        cache_key = f"alert:{alert.stream_id}:{alert.alert_id}"
        try:
            await self._cache.set(
                cache_key,
                json.dumps(alert.to_dict()),
                ttl=86400,  # 24 hours
            )
        except Exception as exc:
            logger.warning("alert_cache_failed", error=str(exc))

    async def _send_notifications(self, alert: ThreatAlert) -> None:
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

    async def _send_discord_notification(self, alert: ThreatAlert) -> None:
        """Send Discord notification."""
        if not settings.discord_webhook_url:
            return

        try:
            from discord_webhook import DiscordWebhook, DiscordEmbed

            webhook = DiscordWebhook(url=settings.discord_webhook_url)

            # Create embed
            color = self._get_color_for_severity(alert.severity)
            embed = DiscordEmbed(
                title=alert.title,
                description=alert.description,
                color=color,
            )
            embed.add_embed_field(name="Type", value=alert.alert_type.value, inline=True)
            embed.add_embed_field(name="Severity", value=alert.severity.value, inline=True)
            embed.add_embed_field(name="Stream ID", value=alert.stream_id, inline=False)

            webhook.add_embed(embed)
            webhook.execute()
        except Exception as exc:
            logger.warning("discord_notification_failed", error=str(exc))

    async def _send_webhook_notifications(self, alert: ThreatAlert) -> None:
        """Send custom webhook notifications."""
        if not settings.alert_webhook_urls:
            return

        import httpx

        payload = alert.to_dict()

        for webhook_url in settings.alert_webhook_urls:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(webhook_url, json=payload)
            except Exception as exc:
                logger.warning("webhook_notification_failed", webhook=webhook_url, error=str(exc))

    @staticmethod
    def _get_color_for_severity(severity: AlertSeverity) -> int:
        """Get Discord embed color for severity."""
        if severity == AlertSeverity.CRITICAL:
            return 0xFF0000  # Red
        elif severity == AlertSeverity.HIGH:
            return 0xFF6600  # Orange
        elif severity == AlertSeverity.MEDIUM:
            return 0xFFCC00  # Yellow
        else:
            return 0x0066FF  # Blue

    async def dismiss_alert(self, alert_id: str) -> None:
        """Mark alert as dismissed."""
        cache_key = f"alert:*:{alert_id}"
        # Would update in database
        logger.info("alert_dismissed", alert_id=alert_id)

    async def get_stream_alerts(
        self,
        stream_id: str,
        limit: int = 50,
        severity: Optional[AlertSeverity] = None,
    ) -> List[Dict[str, Any]]:
        """Get alerts for a stream."""
        # Would query from database
        return []

    async def generate_alerts_from_assessment(
        self,
        stream_id: str,
        tenant_id: str,
        assessment: Dict[str, Any],
    ) -> List[ThreatAlert]:
        """Generate alerts based on threat assessment."""
        alerts: List[ThreatAlert] = []

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
