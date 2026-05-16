from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models import (
    Attack,
    Ban,
    MitigationAction,
    Stream,
)
from app.core.config import get_settings
from app.infrastructure.cache.redis_client import RedisCache
from app.integrations.cloudflare.firewall import CloudflareFirewall

logger = get_logger(__name__)
settings = get_settings()


class MitigationService:
    ACTION_THRESHOLDS = {
        "monitor": 30.0,
        "rate_limit": 40.0,
        "quarantine": 50.0,
        "timeout": 55.0,
        "mute": 60.0,
        "shadow_ban": 65.0,
        "js_challenge": 70.0,
        "captcha": 75.0,
        "ban": 80.0,
    }

    def __init__(self, db: AsyncSession, cache: Optional[RedisCache] = None):
        self.db = db
        self.cache = cache or RedisCache()

    def determine_action(self, risk_score: float, threat_type: str) -> MitigationAction:
        if risk_score >= self.ACTION_THRESHOLDS["ban"]:
            return MitigationAction.BAN
        if risk_score >= self.ACTION_THRESHOLDS["captcha"]:
            return MitigationAction.CAPTCHA
        if risk_score >= self.ACTION_THRESHOLDS["js_challenge"]:
            return MitigationAction.JS_CHALLENGE
        if threat_type == "spam" and risk_score >= self.ACTION_THRESHOLDS["mute"]:
            return MitigationAction.MUTE
        if risk_score >= self.ACTION_THRESHOLDS["shadow_ban"]:
            return MitigationAction.SHADOW_BAN
        if risk_score >= self.ACTION_THRESHOLDS["timeout"]:
            return MitigationAction.TIMEOUT
        if risk_score >= self.ACTION_THRESHOLDS["quarantine"]:
            return MitigationAction.QUARANTINE
        if risk_score >= self.ACTION_THRESHOLDS["rate_limit"]:
            return MitigationAction.RATE_LIMIT
        return MitigationAction.NONE

    async def apply_mitigation(
        self,
        stream_id: UUID,
        tenant_id: UUID,
        attack_id: UUID,
        action: MitigationAction,
        targets: List[Dict[str, str]],
        evidence: Dict[str, Any],
        duration_hours: Optional[int] = None,
    ) -> List[Ban]:
        bans: List[Ban] = []
        expires_at = None
        if duration_hours:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=duration_hours)

        ban_type_map = {
            MitigationAction.BAN: "ban",
            MitigationAction.SHADOW_BAN: "shadow_ban",
            MitigationAction.MUTE: "mute",
            MitigationAction.TIMEOUT: "timeout",
            MitigationAction.QUARANTINE: "quarantine",
        }

        for target in targets:
            target_type = target.get("type", "user")
            target_value = target.get("value", "")
            if not target_value:
                continue

            ban = Ban(
                stream_id=stream_id,
                tenant_id=tenant_id,
                target_type=target_type,
                target_value=target_value,
                reason=f"Automated {action.value} - attack {attack_id}",
                ban_type=ban_type_map.get(action, "quarantine"),
                expires_at=expires_at,
                is_automated=True,
                evidence=evidence,
            )
            self.db.add(ban)
            bans.append(ban)

            cache_key = f"ban:{stream_id}:{target_type}:{target_value}"
            await self.cache.set(cache_key, {
                "ban_type": ban.ban_type,
                "expires_at": expires_at.isoformat() if expires_at else None,
            }, ttl=duration_hours * 3600 if duration_hours else 86400)

        await self.db.execute(
            update(Attack)
            .where(Attack.id == attack_id)
            .values(
                mitigation_action=action,
                mitigated_at=datetime.now(timezone.utc),
            )
        )

        risk = evidence.get("risk_score", 0)
        if (
            settings.cloudflare_auto_block
            and risk >= settings.cloudflare_block_risk_threshold
        ):
            cf = CloudflareFirewall()
            for target in targets:
                if target.get("type") == "ip":
                    await cf.block_ip(
                        target["value"],
                        reason=f"StreamShield attack {attack_id}",
                    )

        logger.info(
            "mitigation_applied",
            stream_id=str(stream_id),
            attack_id=str(attack_id),
            action=action.value,
            target_count=len(bans),
        )
        return bans

    async def is_banned(
        self,
        stream_id: UUID,
        target_type: str,
        target_value: str,
    ) -> Optional[Dict[str, Any]]:
        cache_key = f"ban:{stream_id}:{target_type}:{target_value}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        result = await self.db.execute(
            select(Ban).where(
                Ban.stream_id == stream_id,
                Ban.target_type == target_type,
                Ban.target_value == target_value,
                Ban.is_active == True,
            )
        )
        ban = result.scalar_one_or_none()
        if not ban:
            return None

        if ban.expires_at and ban.expires_at < datetime.now(timezone.utc):
            ban.is_active = False
            await self.db.flush()
            return None

        return {"ban_type": ban.ban_type, "reason": ban.reason, "expires_at": ban.expires_at}

    async def progressive_mitigation(
        self,
        stream_id: UUID,
        tenant_id: UUID,
        attack_id: UUID,
        risk_score: float,
        threat_type: str,
        targets: List[Dict[str, str]],
        evidence: Dict[str, Any],
    ) -> MitigationAction:
        action = self.determine_action(risk_score, threat_type)
        if action == MitigationAction.NONE:
            return action

        duration_map = {
            MitigationAction.TIMEOUT: 1,
            MitigationAction.MUTE: 2,
            MitigationAction.QUARANTINE: 6,
            MitigationAction.SHADOW_BAN: 24,
            MitigationAction.BAN: None,
        }

        await self.apply_mitigation(
            stream_id=stream_id,
            tenant_id=tenant_id,
            attack_id=attack_id,
            action=action,
            targets=targets,
            evidence=evidence,
            duration_hours=duration_map.get(action),
        )
        return action

    async def revoke_ban(self, ban_id: UUID) -> bool:
        result = await self.db.execute(select(Ban).where(Ban.id == ban_id))
        ban = result.scalar_one_or_none()
        if not ban:
            return False
        ban.is_active = False
        cache_key = f"ban:{ban.stream_id}:{ban.target_type}:{ban.target_value}"
        await self.cache.delete(cache_key)
        return True
