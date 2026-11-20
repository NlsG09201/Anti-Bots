from __future__ import annotations

from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AnalystUser, get_db
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.analytics.powerbi import (
    EXPORT_DATASETS,
    AnalyticsWarehouseService,
    PowerBIService,
    csv_bytes,
    excel_bytes,
    json_bytes,
    powerbi_model_manifest,
    powerbi_package_bytes,
)
from app.services.analytics.bigquery import BigQueryWarehouseService

logger = get_logger(__name__)
router = APIRouter(prefix="/analytics", tags=["Power BI Analytics"])


@router.get("/exports/powerbi-report")
async def analytics_export_published_powerbi_report(
    current_user: AnalystUser,
    format: str = Query(..., pattern="^(pdf|pptx|pbix)$"),
):
    """Download an export of the published report bound to one tenant."""
    service = PowerBIService()
    if not service.report_export_configured:
        raise HTTPException(
            status_code=503,
            detail="La exportación del informe publicado requiere configurar Power BI y el tenant del informe.",
        )
    if str(current_user.tenant_id) != get_settings().powerbi_report_tenant_id:
        raise HTTPException(status_code=404, detail="Report not found")
    try:
        content, media_type, filename = await service.export_report(format)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "powerbi_report_export_rejected",
            tenant_id=str(current_user.tenant_id),
            format=format,
            provider_status=exc.response.status_code,
        )
        raise HTTPException(
            status_code=502,
            detail="Power BI no pudo exportar el informe. Verifica permisos, publicación y capacidad del workspace.",
        ) from exc
    except (RuntimeError, TimeoutError) as exc:
        logger.error(
            "powerbi_report_export_failed",
            tenant_id=str(current_user.tenant_id),
            format=format,
            error_type=type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail="No se pudo generar el archivo desde Power BI.") from exc
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _validate_dataset(dataset: str) -> str:
    if dataset not in EXPORT_DATASETS:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Dataset no soportado para exportacion",
                "allowed": list(EXPORT_DATASETS),
            },
        )
    return dataset


@router.get("/bigquery/config")
async def analytics_bigquery_config(current_user: AnalystUser):
    service = BigQueryWarehouseService()
    cfg = get_settings()
    return {
        "enabled": cfg.bigquery_enabled,
        "configured": service.configured,
        "project_id": cfg.google_cloud_project_id or None,
        "dataset": service.dataset_for_tenant(current_user.tenant_id) if service.configured else None,
        "location": cfg.bigquery_location,
        "tables": list(EXPORT_DATASETS),
    }


@router.post("/bigquery/sync")
async def analytics_bigquery_sync(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(2160, ge=1, le=2160),
):
    service = BigQueryWarehouseService()
    if not service.configured:
        raise HTTPException(status_code=503, detail="Google BigQuery no está configurado en el backend.")
    warehouse = AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours)
    bundle = await warehouse.build_export_bundle()
    try:
        return {
            "generated_at": warehouse.snapshot_at.isoformat(),
            "window_hours": hours,
            **await service.sync_bundle(current_user.tenant_id, bundle),
        }
    except Exception as exc:
        logger.error(
            "bigquery_sync_failed",
            tenant_id=str(current_user.tenant_id),
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="No se pudo cargar la analítica del tenant en BigQuery; revisa permisos y logs del backend.",
        ) from exc


@router.get("/overview")
async def analytics_overview(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(168, ge=1, le=2160),
):
    return await AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours).overview()


@router.get("/live-metrics")
async def analytics_live_metrics(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(24, ge=1, le=168),
):
    return await AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours).live_metrics()


@router.get("/suspicious-activity")
async def analytics_suspicious_activity(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(72, ge=1, le=720),
):
    return await AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours).suspicious_activity()


@router.get("/stream-analytics")
async def analytics_streams(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(168, ge=1, le=2160),
):
    return await AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours).stream_analytics()


@router.get("/ai-analytics")
async def analytics_ai(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(168, ge=1, le=2160),
):
    return await AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours).ai_analytics()


@router.get("/engagement-analytics")
async def analytics_engagement(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(168, ge=1, le=2160),
):
    return await AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours).engagement_analytics()


@router.get("/attack-analytics")
async def analytics_attacks(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(168, ge=1, le=2160),
):
    return await AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours).attack_analytics()


@router.get("/executive-report")
async def analytics_executive_report(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(168, ge=1, le=2160),
):
    return await AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours).executive_report()


@router.get("/powerbi/model")
async def analytics_powerbi_model():
    return powerbi_model_manifest()


@router.get("/powerbi/dax")
async def analytics_powerbi_dax():
    manifest = powerbi_model_manifest()
    return {"dataset_name": manifest["dataset_name"], "measures": manifest["measures"]}


@router.get("/powerbi/metadata")
async def analytics_powerbi_metadata(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(168, ge=1, le=2160),
):
    service = AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours)
    return await service.powerbi_metadata()


@router.get("/powerbi/datasets")
async def analytics_powerbi_datasets(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(168, ge=1, le=2160),
):
    service = AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours)
    bundle = await service.build_export_bundle()
    return {
        "generated_at": service.snapshot_at.isoformat(),
        "window_hours": hours,
        "datasets": [{"name": name, "rows": len(rows)} for name, rows in bundle.items()],
    }


@router.get("/powerbi/datasets/{dataset_name}")
async def analytics_powerbi_dataset(
    dataset_name: str,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(168, ge=1, le=2160),
):
    dataset_name = _validate_dataset(dataset_name)
    service = AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours)
    bundle = await service.build_export_bundle()
    return {
        "generated_at": service.snapshot_at.isoformat(),
        "dataset": dataset_name,
        "rows": bundle[dataset_name],
        "count": len(bundle[dataset_name]),
        "columns": powerbi_model_manifest()["tables"][dataset_name],
    }


@router.post("/powerbi/sync")
async def analytics_powerbi_sync(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(168, ge=1, le=2160),
):
    try:
        service = AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours)
        bundle = await service.build_export_bundle()
        tenant_suffix = current_user.tenant_id.hex[:8]
        result = await PowerBIService().sync_bundle(
            bundle,
            dataset_name=f"{get_settings().powerbi_dataset_name}-{tenant_suffix}",
        )
        return {
            "generated_at": service.snapshot_at.isoformat(),
            "window_hours": hours,
            **result,
        }
    except Exception as exc:
        logger.error(
            "powerbi_sync_failed",
            tenant_id=str(current_user.tenant_id),
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "message": "No fue posible sincronizar el dataset con Power BI",
                "error": "sync_failed",
            },
        ) from exc


@router.get("/exports/json")
async def analytics_export_json(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    dataset: str | None = Query(None),
    hours: int = Query(168, ge=1, le=2160),
):
    service = AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours)
    bundle = await service.build_export_bundle()
    payload = bundle if dataset is None else {dataset: bundle[_validate_dataset(dataset)]}
    return Response(
        content=json_bytes(payload),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="streamshield-analytics.json"'},
    )


@router.get("/exports/csv")
async def analytics_export_csv(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    dataset: str = Query(...),
    hours: int = Query(168, ge=1, le=2160),
):
    dataset = _validate_dataset(dataset)
    service = AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours)
    bundle = await service.build_export_bundle()
    return Response(
        content=csv_bytes(bundle[dataset]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{dataset}.csv"'},
    )


@router.get("/exports/excel")
async def analytics_export_excel(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    dataset: str | None = Query(None),
    hours: int = Query(168, ge=1, le=2160),
):
    service = AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours)
    bundle = await service.build_export_bundle()
    if dataset is not None:
        dataset = _validate_dataset(dataset)
        bundle = {dataset: bundle[dataset]}
    return Response(
        content=excel_bytes(bundle),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="streamshield-analytics.xlsx"'},
    )


@router.get("/exports/powerbi-package")
async def analytics_export_powerbi_package(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    hours: int = Query(168, ge=1, le=2160),
):
    service = AnalyticsWarehouseService(db, current_user.tenant_id, hours=hours)
    bundle = await service.build_export_bundle()
    metadata = await service.powerbi_metadata()
    return Response(
        content=powerbi_package_bytes(bundle, metadata=metadata),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="streamshield-powerbi-package.zip"'},
    )
