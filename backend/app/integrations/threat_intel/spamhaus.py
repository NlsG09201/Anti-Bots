"""Spamhaus DNSBL — Real-time threat list lookups."""

from typing import Any, Dict, List, Optional
import socket
import asyncio

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class SpamhausClient:
    """Spamhaus DNSBL integration for threat list lookups."""

    # Spamhaus lists
    PBL = "pbl.spamhaus.net"  # Policy Block List (end-user networks)
    SBL = "sbl.spamhaus.net"  # Spamhaus Block List (direct spam sources)
    CSS = "css.spamhaus.net"  # CSS (compromised systems)
    DROP = "drop.spamhaus.net"  # Do Not Route Or Peer (networks)
    EDROP = "edrop.spamhaus.net"  # Extended DROP
    ZEN = "zen.spamhaus.net"  # Combined list

    @property
    def enabled(self) -> bool:
        return settings.spamhaus_enabled

    async def check(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """Check IP against Spamhaus lists."""
        if not self.enabled:
            return None

        try:
            # Reverse IP octets for DNSBL query
            octets = ip_address.split(".")
            if len(octets) != 4:
                return None

            reversed_ip = ".".join(reversed(octets))
            results = {}
            threats = []

            # Check each list
            for list_name, list_domain in [
                ("zen", self.ZEN),
                ("sbl", self.SBL),
                ("pbl", self.PBL),
                ("css", self.CSS),
                ("drop", self.DROP),
            ]:
                query = f"{reversed_ip}.{list_domain}"
                try:
                    # Use asyncio timeout for DNS query
                    result = await asyncio.wait_for(
                        asyncio.to_thread(socket.gethostbyname, query),
                        timeout=5.0,
                    )
                    results[list_name] = True
                    if "127.0.0.2" in result or "127.0.0" in result:
                        threats.append(f"spamhaus_{list_name}")
                except (socket.gaierror, asyncio.TimeoutError):
                    results[list_name] = False

            if not threats:
                return None

            return {
                "source": "spamhaus",
                "is_listed": True,
                "lists": results,
                "threat_categories": threats,
                "recommendation": "BLOCK" if any(results.values()) else "MONITOR",
            }
        except Exception as exc:
            logger.warning("spamhaus_check_failed", ip=ip_address, error=str(exc))
            return None

    async def check_bulk(self, ip_addresses: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Check multiple IPs efficiently."""
        tasks = [self.check(ip) for ip in ip_addresses]
        results = await asyncio.gather(*tasks)
        return {ip: result for ip, result in zip(ip_addresses, results)}
