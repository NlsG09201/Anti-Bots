"""Tenant-isolated BigQuery mirror for the live Power BI analytics bundle."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.config import get_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


WAREHOUSE_SCHEMAS = {
    "dim_date": [
        ("date_key", "INT64"), ("full_date", "DATE"), ("year", "INT64"),
        ("quarter", "INT64"), ("month", "INT64"), ("month_name", "STRING"),
        ("day_of_month", "INT64"), ("iso_week", "INT64"), ("day_of_week", "INT64"),
    ],
    "dim_platform": [("platform_key", "STRING"), ("platform_name", "STRING")],
    "dim_streamer": [
        ("streamer_key", "INT64"), ("streamer_id", "STRING"),
        ("tenant_id", "STRING"), ("username", "STRING"), ("role", "STRING"),
        ("created_at", "TIMESTAMP"),
    ],
    "dim_stream": [
        ("stream_key", "INT64"), ("stream_id", "STRING"),
        ("tenant_id", "STRING"), ("streamer_id", "STRING"),
        ("platform_key", "STRING"), ("channel_name", "STRING"),
        ("created_at", "TIMESTAMP"), ("updated_at", "TIMESTAMP"),
    ],
    "vw_powerbi_stream_snapshot": [
        ("snapshot_date", "DATE"), ("tenant_id", "STRING"), ("stream_id", "STRING"),
        ("streamer_id", "STRING"), ("platform_key", "STRING"),
        ("platform_name", "STRING"), ("channel_name", "STRING"), ("is_live", "BOOL"),
        ("viewer_count", "INT64"), ("active_chatters", "INT64"),
        ("suspicious_viewers", "INT64"), ("active_attacks", "INT64"),
        ("engagement_rate", "FLOAT64"), ("threat_score", "FLOAT64"),
        ("loaded_at", "TIMESTAMP"),
    ],
    "vw_powerbi_viewer_session": [
        ("tenant_id", "STRING"), ("session_id", "STRING"), ("stream_id", "STRING"),
        ("platform_key", "STRING"), ("channel_name", "STRING"),
        ("joined_date", "DATE"), ("joined_at", "TIMESTAMP"),
        ("left_at", "TIMESTAMP"), ("is_active", "BOOL"),
        ("is_suspected_bot", "BOOL"), ("risk_score", "FLOAT64"),
        ("chat_messages", "INT64"), ("watch_duration_seconds", "INT64"),
        ("source", "STRING"),
    ],
    "vw_powerbi_attack": [
        ("tenant_id", "STRING"), ("attack_id", "STRING"), ("stream_id", "STRING"),
        ("platform_key", "STRING"), ("channel_name", "STRING"),
        ("created_date", "DATE"), ("attack_type", "STRING"),
        ("severity", "STRING"), ("status", "STRING"),
        ("risk_score", "FLOAT64"), ("confidence", "FLOAT64"),
        ("affected_users", "INT64"), ("mitigation_action", "STRING"),
        ("created_at", "TIMESTAMP"), ("mitigated_at", "TIMESTAMP"),
        ("resolved_at", "TIMESTAMP"),
    ],
    "vw_powerbi_chat_activity": [
        ("tenant_id", "STRING"), ("stream_id", "STRING"),
        ("platform_key", "STRING"), ("channel_name", "STRING"),
        ("activity_date", "DATE"), ("event_type", "STRING"),
        ("messages", "INT64"), ("unique_users", "INT64"),
        ("suspicious_messages", "INT64"), ("average_risk_score", "FLOAT64"),
    ],
}

TENANT_QUERIES = {
    "dim_date": "SELECT date_key, full_date, year, quarter, month, month_name, day_of_month, iso_week, day_of_week FROM bi.dim_date",
    "dim_platform": "SELECT platform_key, platform_name FROM bi.dim_platform",
    "dim_streamer": "SELECT streamer_key, streamer_id::text AS streamer_id, tenant_id::text AS tenant_id, username, role, created_at FROM bi.dim_streamer WHERE tenant_id = :tenant_id",
    "dim_stream": "SELECT stream_key, stream_id::text AS stream_id, tenant_id::text AS tenant_id, streamer_id::text AS streamer_id, platform_key, channel_name, created_at, updated_at FROM bi.dim_stream WHERE tenant_id = :tenant_id",
    "vw_powerbi_stream_snapshot": "SELECT f.snapshot_date, s.tenant_id::text AS tenant_id, f.stream_id::text AS stream_id, s.streamer_id::text AS streamer_id, p.platform_key, p.platform_name, s.channel_name, f.is_live, f.viewer_count, f.active_chatters, f.suspicious_viewers, f.active_attacks, f.engagement_rate::float8 AS engagement_rate, f.threat_score::float8 AS threat_score, f.loaded_at FROM bi.fact_stream_snapshot f JOIN bi.dim_stream s USING (stream_id) JOIN bi.dim_platform p ON p.platform_key = f.platform_key WHERE s.tenant_id = :tenant_id",
    "vw_powerbi_viewer_session": "SELECT s.tenant_id::text AS tenant_id, v.session_id::text AS session_id, v.stream_id::text AS stream_id, d.platform_key, s.channel_name, v.joined_date, v.joined_at, v.left_at, v.is_active, v.is_suspected_bot, v.risk_score::float8 AS risk_score, v.chat_messages, v.watch_duration_seconds, v.source FROM bi.fact_viewer_session v JOIN bi.dim_stream s USING (stream_id) JOIN bi.dim_platform d USING (platform_key) WHERE s.tenant_id = :tenant_id",
    "vw_powerbi_attack": "SELECT s.tenant_id::text AS tenant_id, a.attack_id::text AS attack_id, a.stream_id::text AS stream_id, p.platform_key, s.channel_name, a.created_date, a.attack_type, a.severity, a.status, a.risk_score::float8 AS risk_score, a.confidence::float8 AS confidence, a.affected_users, a.mitigation_action, a.created_at, a.mitigated_at, a.resolved_at FROM bi.fact_attack a JOIN bi.dim_stream s USING (stream_id) JOIN bi.dim_platform p USING (platform_key) WHERE s.tenant_id = :tenant_id",
    "vw_powerbi_chat_activity": "SELECT s.tenant_id::text AS tenant_id, c.stream_id::text AS stream_id, p.platform_key, s.channel_name, c.activity_date, c.event_type, c.messages, c.unique_users, c.suspicious_messages, c.average_risk_score::float8 AS average_risk_score FROM bi.fact_chat_activity c JOIN bi.dim_stream s USING (stream_id) JOIN bi.dim_platform p USING (platform_key) WHERE s.tenant_id = :tenant_id",
}


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return float(value) if isinstance(value, Decimal) else str(value)
    raise TypeError(f"Unsupported BigQuery JSON value: {type(value).__name__}")


class BigQueryWarehouseService:
    @property
    def configured(self) -> bool:
        cfg = get_settings()
        return bool(cfg.bigquery_enabled and cfg.google_cloud_project_id)

    def dataset_for_tenant(self, tenant_id: UUID | str) -> str:
        cfg = get_settings()
        prefix = cfg.bigquery_dataset_prefix.lower()
        suffix = UUID(str(tenant_id)).hex
        return f"{prefix}_{suffix}"

    async def sync_tenant(self, db: AsyncSession, tenant_id: UUID | str) -> dict[str, Any]:
        cfg = get_settings()
        if not self.configured:
            return {
                "enabled": cfg.bigquery_enabled,
                "configured": False,
                "message": "Google Cloud project or BigQuery integration is not configured.",
            }
        dataset_name = self.dataset_for_tenant(tenant_id)
        params = {"tenant_id": str(tenant_id)}
        bundle: dict[str, list[dict[str, Any]]] = {}
        for table_name, query in TENANT_QUERIES.items():
            rows = (await db.execute(text(query), params if ":tenant_id" in query else {})).mappings().all()
            bundle[table_name] = [dict(row) for row in rows]
        result = await asyncio.to_thread(self._sync_bundle, dataset_name, bundle)
        return {
            "enabled": True,
            "configured": True,
            "project_id": cfg.google_cloud_project_id,
            "dataset": dataset_name,
            "tables_loaded": result,
        }

    def _sync_bundle(self, dataset_name: str, bundle: dict[str, list[dict[str, Any]]]) -> list[dict]:
        from google.cloud import bigquery

        cfg = get_settings()
        client = bigquery.Client(project=cfg.google_cloud_project_id, location=cfg.bigquery_location)
        dataset_id = f"{cfg.google_cloud_project_id}.{dataset_name}"
        try:
            client.get_dataset(dataset_id)
        except Exception as exc:
            if getattr(exc, "code", None) != 404:
                raise
            dataset = bigquery.Dataset(dataset_id)
            dataset.location = cfg.bigquery_location
            dataset.description = "Tenant-scoped StreamShield operational analytics; managed by the application."
            client.create_dataset(dataset)

        loaded = []
        for table_name, columns in WAREHOUSE_SCHEMAS.items():
            table_id = f"{dataset_id}.{table_name}"
            schema = [
                bigquery.SchemaField(name, field_type, mode="NULLABLE")
                for name, field_type in columns
            ]
            table = bigquery.Table(table_id, schema=schema)
            table.description = f"StreamShield {table_name} analytics for tenant {dataset_name[-32:]}"
            client.create_table(table, exists_ok=True)
            rows = list(bundle.get(table_name, []))[: cfg.bigquery_max_rows_per_table]
            if rows:
                normalized = [json.loads(json.dumps(row, default=_json_value)) for row in rows]
                job_config = bigquery.LoadJobConfig(
                    schema=schema,
                    write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                    source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                )
                client.load_table_from_json(normalized, table_id, job_config=job_config).result()
            else:
                client.query(f"TRUNCATE TABLE `{table_id}`").result()
            loaded.append({"table": table_name, "rows": len(rows)})
        return loaded
