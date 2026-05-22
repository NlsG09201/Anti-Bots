"""
Stream Validation Engine: Multi-pass validation to prevent false offline states.
Ensures stability and robustness before updating stream status.
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, Optional, Tuple
from uuid import UUID

from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import get_redis
from app.infrastructure.database.models import Platform, Stream
from app.infrastructure.database.session import AsyncSessionLocal
from app.services.platforms.registry import get_platform_adapter

logger = get_logger(__name__)

# Configuración de validación
MAX_OFFLINE_ATTEMPTS = 3
VALIDATION_INTERVAL_SECONDS = 5
HEARTBEAT_STALE_SECONDS = 60

class StreamValidationEngine:
    def __init__(self) -> None:
        self._offline_attempts: Dict[str, int] = {}

    async def validate_live_status(self, stream_id: str) -> Tuple[bool, Optional[str]]:
        """
        Realiza una validación robusta del estado de un stream.
        Retorna (is_live, reason).
        """
        async with AsyncSessionLocal() as db:
            stream = await db.get(Stream, UUID(stream_id))
            if not stream:
                return False, "stream_not_found"

            adapter = get_platform_adapter(stream.platform)
            
            # 1. Check Platform API
            try:
                live = await adapter.fetch_live_status(stream)
                if live.is_live:
                    self._offline_attempts[stream_id] = 0
                    return True, "api_confirmed_live"
            except Exception as exc:
                logger.warning("validation_api_failed", stream_id=stream_id, error=str(exc))
                # Si la API falla, no marcamos como offline inmediatamente si teníamos un heartbeat reciente
            
            # 2. Check Redis Heartbeat (from chat or metrics poll)
            redis = await get_redis()
            hb_key = f"hb:live:{stream_id}"
            has_hb = await redis.get(hb_key)
            
            if has_hb:
                logger.info("validation_fallback_to_heartbeat", stream_id=stream_id)
                return True, "heartbeat_active"

            # 3. AI Pattern Validation
            from app.services.monitoring.ai_validation import get_ai_stream_validator
            ai_validator = get_ai_stream_validator()
            ai_result = await ai_validator.analyze_stream_patterns(stream_id)
            
            if ai_result["prediction"] == "likely_online" and ai_result["confidence"] > 0.7:
                logger.info("validation_ai_prevented_offline", stream_id=stream_id)
                return True, "ai_prediction_live"

            # 4. Multi-pass offline check
            attempts = self._offline_attempts.get(stream_id, 0) + 1
            self._offline_attempts[stream_id] = attempts
            
            if attempts < MAX_OFFLINE_ATTEMPTS:
                logger.info("validation_offline_retry", stream_id=stream_id, attempt=attempts)
                # Pretend we are still live until we reach max attempts
                return True, f"offline_pending_retry_{attempts}"

            # 4. Final confirmation
            logger.info("validation_confirmed_offline", stream_id=stream_id)
            self._offline_attempts[stream_id] = 0
            return False, "confirmed_offline"

    async def get_stream_health_score(self, stream_id: str) -> float:
        """Calcula un score de salud (0.0 a 1.0) para el monitoreo del stream."""
        redis = await get_redis()
        
        # Factores: Heartbeat reciente, Latencia de API, Errores recientes
        hb = await redis.get(f"hb:live:{stream_id}")
        latency = await redis.get(f"metrics:latency:{stream_id}")
        errors = await redis.get(f"metrics:errors:{stream_id}")
        
        score = 1.0
        if not hb: score -= 0.4
        if latency and float(latency) > 2000: score -= 0.2
        if errors and int(errors) > 5: score -= 0.3
        
        return max(0.0, score)

_VALIDATOR: Optional[StreamValidationEngine] = None

def get_stream_validation_engine() -> StreamValidationEngine:
    global _VALIDATOR
    if _VALIDATOR is None:
        _VALIDATOR = StreamValidationEngine()
    return _VALIDATOR
