"""Resolución de IP del cliente con anti-spoofing (OWASP: trust boundaries)."""

import ipaddress
import re
from typing import Any, Dict, Optional, Tuple

from fastapi import Request

from app.core.config import get_settings

settings = get_settings()

_PRIVATE_NETS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
)


def _is_valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value.strip())
        return True
    except ValueError:
        return False


def _is_private_ip(value: str) -> bool:
    try:
        addr = ipaddress.ip_address(value.strip())
        return any(addr in net for net in _PRIVATE_NETS)
    except ValueError:
        return False


def _direct_peer_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _trusted_forwarded_chain(request: Request) -> Optional[str]:
    """
    Solo confía en cabeceras de proxy si el peer es de confianza o
    SECURITY_TRUST_PROXY_HEADERS=true (Render/Vercel/Cloudflare delante).
    """
    peer = _direct_peer_ip(request)
    trust_headers = settings.security_trust_proxy_headers
    if not trust_headers and peer not in ("127.0.0.1", "::1"):
        if not _is_private_ip(peer):
            return None

    cf_ip = request.headers.get("CF-Connecting-IP", "").strip()
    if cf_ip and _is_valid_ip(cf_ip):
        return cf_ip

    true_client = request.headers.get("True-Client-IP", "").strip()
    if true_client and _is_valid_ip(true_client):
        return true_client

    xff = request.headers.get("X-Forwarded-For", "").strip()
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        for candidate in parts:
            if _is_valid_ip(candidate) and not _is_private_ip(candidate):
                return candidate
        if parts and _is_valid_ip(parts[0]):
            return parts[0]

    x_real = request.headers.get("X-Real-IP", "").strip()
    if x_real and _is_valid_ip(x_real):
        return x_real

    return None


def resolve_client_ip(request: Request) -> Tuple[str, Dict[str, Any]]:
    """
    Devuelve (ip_cliente, metadatos).
    Anti-spoofing: ignora X-Forwarded-For si no hay proxy de confianza.
    """
    peer = _direct_peer_ip(request)
    forwarded = _trusted_forwarded_chain(request)
    spoof_risk = False

    raw_xff = request.headers.get("X-Forwarded-For", "")
    if raw_xff and not forwarded:
        spoof_risk = True

    client_ip = forwarded or peer
    if not _is_valid_ip(client_ip):
        client_ip = peer if _is_valid_ip(peer) else "unknown"

    return client_ip, {
        "peer_ip": peer,
        "forwarded_ip": forwarded,
        "xff_spoof_risk": spoof_risk,
        "xff_raw": raw_xff[:200] if raw_xff else None,
    }
