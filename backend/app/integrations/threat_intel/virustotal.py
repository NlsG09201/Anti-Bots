from typing import Any, Dict, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class VirusTotalClient:
    BASE_URL = "https://www.virustotal.com/api/v3"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.virustotal_api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def check_ip(self, ip_address: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/ip_addresses/{ip_address}",
                    headers={"x-apikey": self.api_key},
                )
                if response.status_code == 404:
                    return {"malicious_votes": 0, "reputation_score": 50}
                if response.status_code != 200:
                    return None

                data = response.json().get("data", {}).get("attributes", {})
                stats = data.get("last_analysis_stats", {})
                malicious = stats.get("malicious", 0)
                total = sum(stats.values()) or 1
                reputation = max(0, 100 - int((malicious / total) * 100))

                return {
                    "malicious_votes": malicious,
                    "total_engines": total,
                    "reputation_score": reputation,
                    "is_malicious": malicious >= 3,
                    "country": data.get("country"),
                    "as_owner": data.get("as_owner"),
                }
        except Exception as e:
            logger.warning("virustotal_check_failed", ip=ip_address, error=str(e))
            return None
