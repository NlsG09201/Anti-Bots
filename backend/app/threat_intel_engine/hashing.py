"""Privacy-preserving hashes for threat entity keys."""

from __future__ import annotations

import hashlib
import re

from app.core.config import get_settings


def normalize_username(username: str | None) -> str:
    if not username:
        return ""
    return re.sub(r"[^a-z0-9_]", "", username.lower().strip())[:64]


def entity_key(
    *,
    platform: str | None = None,
    platform_user_id: str | None = None,
    username: str | None = None,
    fingerprint_hash: str | None = None,
    ip_address: str | None = None,
) -> str:
    parts = []
    if platform and platform_user_id:
        parts.append(f"p:{platform}:{platform_user_id}")
    un = normalize_username(username)
    if un:
        parts.append(f"u:{un}")
    if fingerprint_hash:
        parts.append(f"fp:{fingerprint_hash[:32]}")
    if ip_address:
        parts.append(f"ip:{hash_value(ip_address, 'ip')}")
    if not parts:
        return "unknown"
    return hash_value("|".join(parts), "entity")


def hash_value(value: str, prefix: str = "") -> str:
    secret = get_settings().app_secret_key[:24]
    raw = f"{secret}:{prefix}:{value}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]
