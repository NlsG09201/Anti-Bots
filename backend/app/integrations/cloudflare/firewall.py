from typing import Any, Dict, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class CloudflareFirewall:
    BASE_URL = "https://api.cloudflare.com/client/v4"

    def __init__(
        self,
        api_token: Optional[str] = None,
        zone_id: Optional[str] = None,
    ):
        self.api_token = api_token or settings.cloudflare_api_token
        self.zone_id = zone_id or settings.cloudflare_zone_id

    @property
    def enabled(self) -> bool:
        return bool(self.api_token and self.zone_id)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def block_ip(self, ip_address: str, reason: str = "StreamShield auto-block") -> bool:
        if not self.enabled:
            return False

        payload = {
            "mode": "block",
            "configuration": {"target": "ip", "value": ip_address},
            "notes": reason[:500],
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/zones/{self.zone_id}/firewall/access_rules/rules",
                    headers=self._headers(),
                    json=payload,
                )
                if response.status_code in (200, 201):
                    logger.info("cloudflare_ip_blocked", ip=ip_address)
                    return True
                logger.warning(
                    "cloudflare_block_failed",
                    ip=ip_address,
                    status=response.status_code,
                    body=response.text[:200],
                )
                return False
        except Exception as e:
            logger.error("cloudflare_block_error", ip=ip_address, error=str(e))
            return False

    async def unblock_ip(self, rule_id: str) -> bool:
        if not self.enabled:
            return False

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.delete(
                    f"{self.BASE_URL}/zones/{self.zone_id}/firewall/access_rules/rules/{rule_id}",
                    headers=self._headers(),
                )
                return response.status_code == 200
        except Exception as e:
            logger.error("cloudflare_unblock_error", rule_id=rule_id, error=str(e))
            return False
