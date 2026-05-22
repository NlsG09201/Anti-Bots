"""
AI Stream Validation: Detects false offline states and API freezes using historical data.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import get_redis
from app.infrastructure.database.models import Stream
from app.infrastructure.database.session import AsyncSessionLocal

logger = get_logger(__name__)

class AIStreamValidator:
    async def analyze_stream_patterns(self, stream_id: str) -> Dict[str, Any]:
        """Analyzes historical metrics to determine if an offline state is likely false."""
        redis = await get_redis()
        
        # Get historical viewers from Redis (populated by metrics poll)
        history_key = f"health:latency:history:{stream_id}"
        latency_history = await redis.lrange(history_key, 0, -1)
        
        # If latency is high or spiking, API might be failing but stream is live
        is_api_struggling = False
        if latency_history:
            avg_latency = sum(float(l) for l in latency_history) / len(latency_history)
            if avg_latency > 3000:
                is_api_struggling = True

        # Check chat activity (if we have any recent events in Redis)
        # This is a simplified check
        last_event_ts = await redis.get(f"health:last_event_ts:{stream_id}")
        has_recent_chat = False
        if last_event_ts and (time.time() - float(last_event_ts)) < 300:
            has_recent_chat = True

        prediction = "likely_online" if has_recent_chat or is_api_struggling else "uncertain"
        confidence = 0.8 if has_recent_chat else 0.5
        
        return {
            "prediction": prediction,
            "confidence": confidence,
            "is_api_struggling": is_api_struggling,
            "has_recent_chat": has_recent_chat
        }

_AI_VALIDATOR: Optional[AIStreamValidator] = None

def get_ai_stream_validator() -> AIStreamValidator:
    global _AI_VALIDATOR
    if _AI_VALIDATOR is None:
        _AI_VALIDATOR = AIStreamValidator()
    return _AI_VALIDATOR
