from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

SEVERITY_COLORS = {
    "low": 0x3498DB,
    "medium": 0xF39C12,
    "high": 0xE74C3C,
    "critical": 0x992D22,
}


class DiscordNotifier:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or settings.discord_webhook_url

    async def send_alert(self, title: str, message: str, severity: str = "medium") -> bool:
        if not self.webhook_url:
            logger.warning("discord_webhook_not_configured")
            return False

        embed = {
            "title": f"🛡️ {title}",
            "description": message,
            "color": SEVERITY_COLORS.get(severity, 0xF39C12),
            "footer": {"text": "StreamShield Security Platform"},
        }

        payload = {"embeds": [embed]}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.webhook_url, json=payload)
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error("discord_webhook_failed", error=str(e))
            return False

    async def send_attack_notification(
        self,
        attack_type: str,
        stream_name: str,
        risk_score: float,
        source_ips: list,
    ) -> bool:
        message = (
            f"**Stream:** {stream_name}\n"
            f"**Type:** {attack_type}\n"
            f"**Risk Score:** {risk_score:.1f}/100\n"
            f"**Source IPs:** {len(source_ips)} detected\n"
        )
        severity = "critical" if risk_score >= 85 else "high" if risk_score >= 70 else "medium"
        return await self.send_alert(
            f"Attack Detected: {attack_type}",
            message,
            severity,
        )
