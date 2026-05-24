"""Legacy Power BI endpoints backed by the active analytics warehouse.

This module intentionally avoids app.power_bi.export_service. That older service
references ORM models and columns that no longer exist, so importing it can stop
the API process during startup.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AnalystUser, get_db
from app.services.analytics.powerbi import (
    AnalyticsWarehouseService,
    EXPORT_DATASETS,
    csv_bytes,
    excel_bytes,
)

router = APIRouter(prefix="/power-bi", tags=["Power BI Legacy"])


class ExportRequest(BaseModel):
    format: Literal["csv", "excel", "json"] = "csv"
    table_type: str = "streams"
    hours: int = 168
    platform_filter: str | None = None


def _service(db: AsyncSession, current_user: AnalystUser, hours: int = 168) -> AnalyticsWarehouseService:
    return AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours)


@router.get("/metrics/global")
async def get_global_metrics(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(168, ge=1, le=2160),
):
    overview = await _service(db, current_user, hours).overview()
    metrics = overview["metrics_globales"]
    realtime = overview["metricas_tiempo_real"]
    return {
        "timestamp": overview["updated_at"],
        "total_streams_monitored": metrics["streams_activos"],
        "total_suspicious_viewers": metrics["viewers_sospechosos"],
        "total_attacks_detected": metrics["ataques_detectados"],
        "active_streams": metrics["streams_activos"],
        "detected_bots": metrics["bots_detectados"],
        "suspicious_follows": metrics["follows_sospechosos"],
        "engagement_score": metrics["engagement_score"],
        "global_threat_score": metrics["threat_score"],
        "risk_score": metrics["riesgo_global"],
        "viewers_per_minute": realtime["viewers_por_minuto"],
        "follows_per_minute": realtime["follows_por_minuto"],
        "messages_per_minute": realtime["mensajes_por_minuto"],
        "anomalies": realtime["anomalias"],
    }


@router.get("/metrics/kpis")
async def get_kpis(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(168, ge=1, le=2160),
):
    overview = await _service(db, current_user, hours).overview()
    return {
        "timestamp": overview["updated_at"],
        **overview["kpis"],
    }


@router.get("/streams/snapshots")
async def get_stream_snapshots(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    platform: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    hours: int = Query(168, ge=1, le=2160),
):
    analytics = await _service(db, current_user, hours).stream_analytics()
    rows = analytics["streams"]
    if platform:
        rows = [row for row in rows if row["platform_key"] == platform.lower()]
    return rows[:limit]


@router.get("/viewers/suspicious")
async def get_suspicious_viewers(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    min_score: float = Query(0.7, ge=0, le=100),
    limit: int = Query(1000, ge=1, le=5000),
    hours: int = Query(168, ge=1, le=2160),
):
    min_score_normalized = min_score * 100 if min_score <= 1 else min_score
    analytics = await _service(db, current_user, hours).suspicious_activity()
    return [
        row
        for row in analytics["top_viewers"]
        if float(row.get("risk_score") or 0) >= min_score_normalized
    ][:limit]


@router.get("/attacks/list")
async def get_attacks(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(None),
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(500, ge=1, le=5000),
):
    analytics = await _service(db, current_user, hours).attack_analytics()
    rows = analytics["attacks"]
    if status:
        rows = [row for row in rows if row["status"] == status]
    return rows[:limit]


@router.get("/dataset/json")
async def export_dataset_json(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    tables: str = Query("all"),
    hours: int = Query(168, ge=1, le=2160),
):
    bundle = await _service(db, current_user, hours).build_export_bundle()
    if tables == "all":
        return bundle
    selected = [name.strip() for name in tables.split(",") if name.strip()]
    invalid = [name for name in selected if name not in EXPORT_DATASETS]
    if invalid:
        raise HTTPException(status_code=400, detail={"invalid": invalid, "allowed": list(EXPORT_DATASETS)})
    return {name: bundle[name] for name in selected}


@router.post("/export")
async def export_data(
    request: ExportRequest,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
):
    table_name = request.table_type
    if table_name == "all":
        table_name = "streams"
    if table_name not in EXPORT_DATASETS:
        raise HTTPException(
            status_code=400,
            detail={"message": "Dataset no soportado", "allowed": list(EXPORT_DATASETS)},
        )

    bundle = await _service(db, current_user, request.hours).build_export_bundle()
    rows = bundle[table_name]
    if request.platform_filter and "platform_key" in (rows[0] if rows else {}):
        rows = [row for row in rows if row["platform_key"] == request.platform_filter.lower()]

    if request.format == "csv":
        return {
            "status": "ok",
            "format": "csv",
            "content": csv_bytes(rows).decode("utf-8"),
            "rows": len(rows),
        }
    if request.format == "excel":
        return {
            "status": "ok",
            "format": "excel",
            "content": excel_bytes({table_name: rows}).hex(),
            "rows": len(rows),
        }
    return {"status": "ok", "format": "json", "data": rows, "rows": len(rows)}


@router.get("/health")
async def power_bi_health():
    return {
        "status": "operational",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.0.0",
        "backend": "analytics_warehouse",
    }
