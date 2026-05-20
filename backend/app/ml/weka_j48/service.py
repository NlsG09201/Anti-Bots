"""High-level Weka J48 bot classification service."""

from __future__ import annotations

import asyncio
from functools import lru_cache, partial
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.database.models import ViewerSession
from app.ml.weka_j48.dataset import load_session_row
from app.ml.weka_j48.sources import TrainingSource, build_training_dataset, preview_dataset
from app.ml.weka_j48.engine import J48Engine, weka_runtime_available
from app.ml.weka_j48.runtime import warm_weka_jvm

logger = get_logger(__name__)


class WekaJ48BotService:
    def __init__(self) -> None:
        settings = get_settings()
        model_dir = Path(settings.weka_j48_model_path)
        if not model_dir.is_absolute():
            model_dir = (Path.cwd() / model_dir).resolve()
        self.engine = J48Engine(
            model_dir,
            java_home=settings.weka_java_home or "",
            max_heap=settings.weka_jvm_max_heap,
        )
        self.enabled = settings.weka_j48_enabled
        self.python_enabled = settings.weka_python_enabled
        self.min_samples = settings.weka_j48_min_training_samples
        if self.enabled:
            self.engine.load()

    async def train_for_tenant(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        *,
        limit: int = 5000,
        source: TrainingSource = "mixed",
        include_twitch_insights: bool = True,
    ) -> Dict[str, Any]:
        rows, dataset_stats = await build_training_dataset(
            db,
            tenant_id,
            source=source,
            limit=limit,
            include_twitch_insights=include_twitch_insights,
        )
        yes = sum(1 for r in rows if r.label == "yes")
        no = sum(1 for r in rows if r.label == "no")
        if len(rows) < self.min_samples:
            return {
                "ok": False,
                "error": "insufficient_samples",
                "samples": len(rows),
                "required": self.min_samples,
                "dataset": dataset_stats,
                "bots": yes,
                "humans": no,
            }
        if yes < 2 or no < 2:
            return {
                "ok": False,
                "error": "imbalanced_classes",
                "samples": len(rows),
                "bots": yes,
                "humans": no,
                "dataset": dataset_stats,
                "hint": "Necesitas al menos 2 bots y 2 humanos. Prueba source=mixed o channel_flow tras escanear canales.",
            }
        cfg = get_settings()
        try:
            loop = asyncio.get_running_loop()
            meta = await loop.run_in_executor(
                None,
                partial(
                    self.engine.train,
                    rows,
                    prefer_weka=cfg.weka_j48_prefer_weka,
                ),
            )
        except ValueError as exc:
            return {
                "ok": False,
                "error": "train_validation_failed",
                "hint": str(exc),
                "samples": len(rows),
                "bots": yes,
                "humans": no,
                "dataset": dataset_stats,
            }
        except OSError as exc:
            logger.exception("weka_j48_model_write_failed", path=str(self.engine.model_dir))
            return {
                "ok": False,
                "error": "model_write_failed",
                "hint": str(exc),
                "samples": len(rows),
                "bots": yes,
                "humans": no,
                "dataset": dataset_stats,
            }
        except Exception as exc:
            logger.exception("weka_j48_train_failed")
            return {
                "ok": False,
                "error": "train_failed",
                "hint": str(exc)[:500],
                "samples": len(rows),
                "bots": yes,
                "humans": no,
                "dataset": dataset_stats,
            }
        return {
            "ok": True,
            "training": meta,
            "samples": len(rows),
            "bots": yes,
            "humans": no,
            "dataset": dataset_stats,
        }

    async def preview_for_tenant(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        *,
        source: TrainingSource = "mixed",
        include_twitch_insights: bool = True,
    ) -> Dict[str, Any]:
        return await preview_dataset(
            db,
            tenant_id,
            source=source,
            include_twitch_insights=include_twitch_insights,
        )

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

    def start_weka_jvm(self) -> Dict[str, Any]:
        if not self.python_enabled:
            return {"ok": False, "error": "weka_python_disabled"}
        settings = get_settings()
        return warm_weka_jvm(
            java_home=settings.weka_java_home or "",
            max_heap=settings.weka_jvm_max_heap,
        )

    def health(self) -> Dict[str, Any]:
        settings = get_settings()
        h = self.engine.health()
        h["enabled"] = self.enabled
        h["weka_python_enabled"] = self.python_enabled
        h["weka_runtime"] = weka_runtime_available(settings.weka_java_home or "")
        h["prefer_weka"] = settings.weka_j48_prefer_weka
        return h


@lru_cache
def get_weka_j48_service() -> WekaJ48BotService:
    return WekaJ48BotService()
