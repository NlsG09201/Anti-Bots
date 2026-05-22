"""SOC API — TwitchBots.info known bot directory integration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AnalystUser, get_db
from app.core.config import get_settings
from app.core.logging import get_logger
from app.integrations.twitchbots_info.mongo_store import TwitchBotsInfoMongoStore
from app.services.twitchbots.verification_service import get_twitchbots_verification_service

logger = get_logger(__name__)
router = APIRouter(prefix="/twitchbots", tags=["TwitchBots.info SOC"])


class VerifyUserBody(BaseModel):
    username: Optional[str] = None
    platform_user_id: Optional[str] = None
    stream_id: Optional[UUID] = None


class BatchUserEntry(BaseModel):
    username: Optional[str] = None
    platform_user_id: Optional[str] = None


class VerifyBatchBody(BaseModel):
    users: List[BatchUserEntry] = Field(..., min_length=1, max_length=500)
    stream_id: Optional[UUID] = None
    apply_sessions: bool = False


@router.get("/overview")
async def twitchbots_overview(current_user: AnalystUser) -> Dict[str, Any]:
    svc = get_twitchbots_verification_service()
    cfg = get_settings()
    if not svc.enabled:
        return {"enabled": False, "message": "TWITCHBOTS_INFO_ENABLED=false"}
    store = TwitchBotsInfoMongoStore()
    stats = await store.overview(str(current_user.tenant_id))
    return {
        "enabled": True,
        "mongodb": bool(cfg.mongodb_uri),
        "global_profiles_cached": await store.global_profile_count(),
        **stats.model_dump(),
    }


@router.get("/detections")
async def twitchbots_detections(
    current_user: AnalystUser,
    limit: int = Query(40, ge=1, le=200),
) -> Dict[str, Any]:
    svc = get_twitchbots_verification_service()
    if not svc.enabled:
        return {"enabled": False, "detections": []}
    items = await TwitchBotsInfoMongoStore().list_recent_detections(
        str(current_user.tenant_id), limit=limit
    )
    return {"enabled": True, "detections": items, "count": len(items)}


@router.post("/verify")
async def twitchbots_verify_one(
    body: VerifyUserBody,
    current_user: AnalystUser,
) -> Dict[str, Any]:
    svc = get_twitchbots_verification_service()
    if not svc.enabled:
        raise HTTPException(status_code=503, detail="TwitchBots.info integration disabled")
    if not body.username and not body.platform_user_id:
        raise HTTPException(status_code=422, detail="username or platform_user_id required")
    try:
        result = await svc.verify_user(
            tenant_id=str(current_user.tenant_id),
            username=body.username,
            platform_user_id=body.platform_user_id,
            stream_id=str(body.stream_id) if body.stream_id else None,
            persist=True,
            broadcast=True,
        )
        return {"result": result.model_dump(), "verdict": result.to_verdict_dict()}
    except Exception as exc:
        logger.exception("twitchbots_verify_one_failed", error=str(exc)[:200])
        raise HTTPException(status_code=503, detail="Verification failed") from exc


@router.post("/verify/batch")
async def twitchbots_verify_batch(
    body: VerifyBatchBody,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    svc = get_twitchbots_verification_service()
    if not svc.enabled:
        raise HTTPException(status_code=503, detail="TwitchBots.info integration disabled")
    users = [
        {"username": u.username, "platform_user_id": u.platform_user_id}
        for u in body.users
    ]
    try:
        if len(users) > 30 and get_settings().twitchbots_info_queue_enabled:
            job_id = await svc.enqueue_batch(
                str(current_user.tenant_id),
                users,
                stream_id=str(body.stream_id) if body.stream_id else None,
            )
            if job_id:
                return {"status": "queued", "job_id": job_id, "count": len(users)}
        results = await svc.verify_batch(
            str(current_user.tenant_id),
            users,
            stream_id=str(body.stream_id) if body.stream_id else None,
        )
        applied = 0
        if body.apply_sessions and body.stream_id:
            applied = await svc.apply_to_sessions(db, body.stream_id, results)
            await db.commit()
        known = sum(1 for r in results.values() if r.is_known_bot)
        return {
            "status": "ok",
            "verified": len(results),
            "known_bots": known,
            "sessions_updated": applied,
            "results": {k: v.model_dump() for k, v in results.items()},
        }
    except Exception as exc:
        logger.exception("twitchbots_verify_batch_failed", error=str(exc)[:200])
        raise HTTPException(status_code=503, detail="Batch verification failed") from exc


@router.post("/warm-cache")
async def twitchbots_warm_cache(_user: AnalystUser) -> Dict[str, Any]:
    svc = get_twitchbots_verification_service()
    if not svc.enabled:
        return {"enabled": False, "warmed": 0}
    warmed = await svc.warm_cache_sample()
    return {"enabled": True, "warmed": warmed}
