"""Rule-based Twitch chat moderation driven by verified EventSub messages."""

from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import decrypt_value, encrypt_value
from app.infrastructure.cache.redis_client import optional_get_redis
from app.infrastructure.database.models import AuditLog, Ban, Stream
from app.integrations.twitch.moderation import (
    ban_user_on_twitch,
    delete_chat_message_on_twitch,
)

logger = get_logger(__name__)
_repeat_state: dict[tuple[str, str], dict[str, Any]] = {}
_seen_message_ids: dict[str, float] = {}
_URL_RE = re.compile(r"(?i)(?:https?://|www\.)[^\s]+|\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?")


def _normalise_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def _has_blocked_word(message: str, terms: list[str]) -> bool:
    normalized_message = f" {_normalise_text(message)} "
    return any(
        f" {_normalise_text(term)} " in normalized_message
        for term in terms
        if _normalise_text(term)
    )


def _contains_disallowed_link(message: str, allowed_domains: list[str]) -> bool:
    allowed = [domain.strip().lower().lstrip(".") for domain in allowed_domains if domain.strip()]
    for match in _URL_RE.findall(message):
        candidate = match.rstrip(".,!?;:)]}")
        parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
        host = (parsed.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if host and not any(host == domain or host.endswith(f".{domain}") for domain in allowed):
            return True
    return False


def _is_repeated(stream_id: str, user_id: str, message: str, *, limit: int, window: int) -> bool:
    now = time.monotonic()
    key = (stream_id, user_id)
    fingerprint = hashlib.sha256(_normalise_text(message).encode()).hexdigest()
    state = _repeat_state.get(key)
    if not state or now - state["started"] > window or state["fingerprint"] != fingerprint:
        _repeat_state[key] = {
            "fingerprint": fingerprint,
            "started": now,
            "count": 1,
            "triggered": False,
        }
    else:
        state["count"] += 1
    if len(_repeat_state) > 10000:
        for old_key, old_state in list(_repeat_state.items()):
            if now - old_state["started"] > max(window, 120):
                _repeat_state.pop(old_key, None)
    state = _repeat_state[key]
    if state["count"] >= limit and not state["triggered"]:
        state["triggered"] = True
        return True
    return False


async def get_twitch_bot_credentials(stream: Stream) -> tuple[str | None, str | None, str | None]:
    """Return refreshed bot access token, Twitch user ID, and login."""
    from datetime import datetime, timedelta, timezone

    from app.core.security import encrypt_value
    from app.integrations.twitch.oauth import TwitchOAuth

    metadata = dict(stream.settings or {})
    encrypted_access = metadata.get("twitch_bot_access_token_encrypted")
    user_id = metadata.get("twitch_bot_user_id")
    login = metadata.get("twitch_bot_login")
    if not encrypted_access or not user_id:
        return None, None, None
    try:
        access_token = decrypt_value(encrypted_access)
    except Exception:
        logger.error("twitch_bot_token_decryption_failed", stream_id=str(stream.id))
        return None, str(user_id), str(login or "")

    refresh_encrypted = metadata.get("twitch_bot_refresh_token_encrypted")
    expiry_raw = metadata.get("twitch_bot_access_expires_at")
    needs_refresh = True
    if expiry_raw:
        try:
            expiry = datetime.fromisoformat(str(expiry_raw).replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            needs_refresh = expiry <= datetime.now(timezone.utc) + timedelta(minutes=2)
        except (TypeError, ValueError):
            needs_refresh = True
    if needs_refresh and refresh_encrypted:
        try:
            refresh = decrypt_value(str(refresh_encrypted))
            data = await TwitchOAuth().refresh_token(refresh)
            access_token = data.get("access_token") or access_token
            new_refresh = data.get("refresh_token")
            metadata["twitch_bot_access_token_encrypted"] = encrypt_value(access_token)
            metadata["twitch_bot_access_expires_at"] = (
                datetime.now(timezone.utc)
                + timedelta(seconds=max(int(data.get("expires_in") or 14400), 60))
            ).isoformat()
            if new_refresh:
                metadata["twitch_bot_refresh_token_encrypted"] = encrypt_value(new_refresh)
            stream.settings = metadata
        except Exception as exc:
            logger.warning(
                "twitch_bot_token_refresh_failed",
                stream_id=str(stream.id),
                error_type=type(exc).__name__,
            )
            return None, str(user_id), str(login or "")
    return access_token, str(user_id), str(login or "")


async def _reserve_message(stream_id: str, message_id: str) -> bool:
    key = f"twitch-moderation-event:{stream_id}:{message_id}"
    redis = await optional_get_redis()
    if redis:
        try:
            return bool(await redis.set(key, "1", ex=86400, nx=True))
        except Exception:
            pass
    now = time.monotonic()
    for old_key, expiry in list(_seen_message_ids.items()):
        if expiry <= now:
            _seen_message_ids.pop(old_key, None)
    if key in _seen_message_ids:
        return False
    _seen_message_ids[key] = now + 86400
    return True


async def process_twitch_chat_message(
    db: AsyncSession,
    stream: Stream,
    event: dict[str, Any],
) -> dict[str, Any] | None:
    metadata = dict(stream.settings or {})
    config = metadata.get("twitch_chat_moderation", {})
    if not config.get("enabled"):
        return None

    message_id = str(event.get("message_id") or "")
    user_id = str(event.get("chatter_user_id") or event.get("user_id") or "")
    username = str(event.get("chatter_user_name") or event.get("chatter_user_login") or "")
    message = str((event.get("message") or {}).get("text") or "")
    if not message_id or not user_id or not username or not message:
        return None
    bot_id = str(metadata.get("twitch_bot_user_id") or "")
    if user_id in {stream.external_id, bot_id}:
        return None
    badges = event.get("badges") or []
    protected_badges = {"broadcaster", "moderator", "staff", "admin", "global_mod"}
    if any(str(item.get("set_id", "")).lower() in protected_badges for item in badges if isinstance(item, dict)):
        return None
    if not await _reserve_message(str(stream.id), message_id):
        return None

    rule: str | None = None
    action: str | None = None
    if config.get("links_enabled") and _contains_disallowed_link(
        message, config.get("allowed_domains") or []
    ):
        rule, action = "disallowed_link", config.get("link_action", "delete")
    elif config.get("blocked_words") and _has_blocked_word(
        message, config.get("blocked_words", [])
    ):
        rule, action = "blocked_word", config.get("word_action", "timeout")
    elif config.get("repeated_messages_enabled") and _is_repeated(
        str(stream.id),
        user_id,
        message,
        limit=int(config.get("repeat_limit", 3)),
        window=int(config.get("repeat_window_seconds", 20)),
    ):
        rule, action = "repeated_message", config.get("repeat_action", "timeout")

    if not rule or not action:
        return None
    bot_token, moderator_id, _ = await get_twitch_bot_credentials(stream)
    observe_only = bool(config.get("observe_only", True))
    applied = {
        "ok": False,
        "status": None if observe_only else 401,
        "detail": "observed" if observe_only else "Conecta la cuenta bot moderadora de Twitch.",
    }
    if bot_token and moderator_id and not observe_only:
        if action == "delete":
            applied = await delete_chat_message_on_twitch(
                stream.external_id,
                moderator_id,
                bot_token,
                message_id,
            )
        elif action in {"timeout", "ban"}:
            duration = int(config.get("timeout_seconds", 600)) if action == "timeout" else None
            applied = await ban_user_on_twitch(
                stream.external_id,
                bot_token,
                user_id,
                reason=f"StreamShield automatic moderation: {rule}",
                duration_seconds=duration,
                moderator_id=moderator_id,
            )
        else:
            applied = {"ok": False, "status": 422, "detail": "Acción de moderación no válida."}

    if applied.get("ok") and action in {"timeout", "ban"}:
        from datetime import datetime, timedelta, timezone

        db.add(Ban(
            stream_id=stream.id,
            tenant_id=stream.tenant_id,
            target_type="user",
            target_value=user_id,
            reason=f"StreamShield automatic moderation: {rule}",
            ban_type=action,
            expires_at=(
                datetime.now(timezone.utc) + timedelta(seconds=int(config.get("timeout_seconds", 600)))
                if action == "timeout"
                else None
            ),
            is_automated=True,
            created_by=stream.owner_id,
            evidence={"rule": rule, "message_id": message_id},
        ))

    db.add(AuditLog(
        tenant_id=stream.tenant_id,
        user_id=stream.owner_id,
        action=f"twitch_chat_moderation.{rule}",
        resource_type="twitch_chat_message",
        resource_id=message_id,
        details={
            "stream_id": str(stream.id),
            "platform_user_id": user_id,
            "platform_username": username,
            "rule": rule,
            "action": action,
            "timeout_seconds": int(config.get("timeout_seconds", 600)) if action == "timeout" else None,
            "observe_only": observe_only,
            "platform_applied": bool(applied.get("ok")),
            "platform_status": applied.get("status"),
        },
    ))
    logger.info(
        "twitch_chat_moderation_rule_matched",
        stream_id=str(stream.id),
        rule=rule,
        action=action,
        observe_only=observe_only,
        platform_applied=bool(applied.get("ok")),
    )
    return {"rule": rule, "action": action, "platform_applied": bool(applied.get("ok"))}
