"""Power BI REST APIs — Endpoints para exportación y consumo de datos en Power BI."""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AnalystUser
from app.core.logging import get_logger
from app.infrastructure.database.session import get_db
from app.power_bi.export_service import PowerBIExportService
from app.power_bi.schemas import (
    ExportRequest,
    ExportResponse,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/power-bi", tags=["Power BI"])


@router.get("/metrics/global")
async def get_global_metrics(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
):
    """Obtiene métricas globales del SOC."""
    service = PowerBIExportService(db)
    metrics = await service.compute_global_metrics(current_user.tenant_id)
    return metrics.model_dump()


@router.get("/metrics/kpis")
async def get_kpis(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
):
    """Obtiene KPIs principales."""
    service = PowerBIExportService(db)
    kpis = await service.compute_kpis(current_user.tenant_id)
    return kpis.model_dump()


@router.get("/streams/snapshots")
async def get_stream_snapshots(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    platform: Optional[str] = Query(None, description="Filtrar por plataforma"),
    limit: int = Query(100, ge=1, le=500),
):
    """Obtiene snapshots de streams activos."""
    service = PowerBIExportService(db)
    snapshots = await service.get_stream_snapshots(
        current_user.tenant_id,
        platform_filter=platform,
        limit=limit,
    )
    return [s.model_dump() for s in snapshots]


@router.get("/viewers/suspicious")
async def get_suspicious_viewers(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    min_score: float = Query(0.7, ge=0, le=1),
    limit: int = Query(1000, ge=1, le=5000),
):
    """Obtiene viewers sospechosos."""
    service = PowerBIExportService(db)
    viewers = await service.get_suspicious_viewers(
        current_user.tenant_id,
        min_score=min_score,
        limit=limit,
    )
    return [v.model_dump() for v in viewers]


@router.get("/attacks/list")
async def get_attacks(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(500, ge=1, le=5000),
):
    """Obtiene ataques detectados."""
    service = PowerBIExportService(db)
    attacks = await service.get_attacks(
        current_user.tenant_id,
        status=status,
        hours=hours,
        limit=limit,
    )
    return [a.model_dump() for a in attacks]


@router.get("/dataset/json")
async def export_dataset_json(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    tables: str = Query("all", description="Tablas a incluir: all, streams, suspicious_viewers, attacks"),
):
    """Exporta dataset completo en JSON."""
    service = PowerBIExportService(db)
    
    if tables == "all":
        table_list = ["streams", "suspicious_viewers", "attacks"]
    else:
        table_list = [t.strip() for t in tables.split(",") if t.strip()]

    dataset = await service.generate_powerbi_dataset(
        current_user.tenant_id,
        include_tables=table_list,
    )
    return dataset


@router.post("/export")
async def export_data(
    request: ExportRequest,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
):
    """Exporta datos en múltiples formatos."""
    service = PowerBIExportService(db)

    # Obtener datos según tipo de tabla
    if request.table_type == "streams":
        snapshots = await service.get_stream_snapshots(
            current_user.tenant_id,
            platform_filter=request.platform_filter,
            limit=1000,
        )
        data = service.generate_powerbi_stream_table(snapshots)
        table_name = "Streams"

    elif request.table_type == "suspicious_viewers":
        viewers = await service.get_suspicious_viewers(
            current_user.tenant_id,
            limit=5000,
        )
        data = [v.model_dump() for v in viewers]
        table_name = "SuspiciousViewers"

    elif request.table_type == "attacks":
        attacks = await service.get_attacks(
            current_user.tenant_id,
            status=None,
            hours=168,  # 1 semana
            limit=5000,
        )
        data = [a.model_dump() for a in attacks]
        table_name = "Attacks"

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de tabla inválido: {request.table_type}",
        )

    # Exportar según formato
    if request.format == "csv":
        csv_content = service.generate_csv_export(data)
        return {
            "status": "ok",
            "format": "csv",
            "content": csv_content.getvalue(),
            "rows": len(data),
        }

    elif request.format == "excel":
        excel_bytes = service.generate_excel_export(data, filename=table_name)
        return {
            "status": "ok",
            "format": "excel",
            "content": excel_bytes.hex(),  # Codificar como hex para JSON
            "rows": len(data),
        }

    elif request.format == "json":
        return {
            "status": "ok",
            "format": "json",
            "data": data,
            "rows": len(data),
        }

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado: {request.format}",
        )


@router.get("/health")
async def power_bi_health():
    """Health check para Power BI."""
    return {
        "status": "operational",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
    }
