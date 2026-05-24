from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AnalystUser, get_db
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

logger = get_logger(__name__)
router = APIRouter(prefix="/analytics", tags=["Power BI Analytics"])


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
        result = await PowerBIService().sync_bundle(bundle)
        return {
            "generated_at": service.snapshot_at.isoformat(),
            "window_hours": hours,
            **result,
        }
    except Exception as exc:
        logger.exception("powerbi_sync_failed", tenant_id=str(current_user.tenant_id), error=str(exc)[:200])
        raise HTTPException(
            status_code=503,
            detail={
                "message": "No fue posible sincronizar el dataset con Power BI",
                "error": str(exc)[:300],
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
