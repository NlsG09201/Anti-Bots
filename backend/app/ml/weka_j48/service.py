"""High-level Weka J48 bot classification service."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.database.models import ViewerSession
from app.ml.weka_j48.dataset import load_session_row, load_training_rows
from app.ml.weka_j48.engine import J48Engine, weka_runtime_available

logger = get_logger(__name__)


class WekaJ48BotService:
    def __init__(self) -> None:
        settings = get_settings()
        model_dir = Path(settings.weka_j48_model_path)
        self.engine = J48Engine(model_dir, java_home=settings.weka_java_home or "")
        self.enabled = settings.weka_j48_enabled
        self.min_samples = settings.weka_j48_min_training_samples
        if self.enabled:
            self.engine.load()

    async def train_for_tenant(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        *,
        limit: int = 5000,
    ) -> Dict[str, Any]:
        rows = await load_training_rows(db, tenant_id, limit=limit)
        if len(rows) < self.min_samples:
            return {
                "ok": False,
                "error": "insufficient_samples",
                "samples": len(rows),
                "required": self.min_samples,
            }
        cfg = get_settings()
        meta = self.engine.train(rows, prefer_weka=cfg.weka_j48_prefer_weka)
        return {"ok": True, "training": meta, "samples": len(rows)}

    async def predict_session(
        self,
        db: AsyncSession,
        session: ViewerSession,
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}
        row = await load_session_row(db, session)
        pred = self.engine.predict(row.features)
        return {
            "enabled": True,
            "session_id": str(session.id),
            "platform_username": session.platform_username,
            **pred,
        }

    async def predict_stream_viewers(
        self,
        db: AsyncSession,
        stream_id: UUID,
        *,
        active_only: bool = True,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []

        query = select(ViewerSession).where(ViewerSession.stream_id == stream_id)
        if active_only:
            query = query.where(ViewerSession.is_active == True)
        query = query.limit(limit)
        result = await db.execute(query)
        sessions = list(result.scalars().all())

        out: List[Dict[str, Any]] = []
        for session in sessions:
            pred = await self.predict_session(db, session)
            out.append(pred)
        return out

    def health(self) -> Dict[str, Any]:
        h = self.engine.health()
        h["enabled"] = self.enabled
        h["weka_runtime"] = weka_runtime_available()
        return h


@lru_cache
def get_weka_j48_service() -> WekaJ48BotService:
    return WekaJ48BotService()
