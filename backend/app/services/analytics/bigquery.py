"""Tenant-isolated BigQuery mirror for the live Power BI analytics bundle."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.services.analytics.powerbi import POWERBI_TABLE_DEFINITIONS


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

    async def sync_bundle(
        self, tenant_id: UUID | str, bundle: dict[str, list[dict[str, Any]]]
    ) -> dict[str, Any]:
        cfg = get_settings()
        if not self.configured:
            return {
                "enabled": cfg.bigquery_enabled,
                "configured": False,
                "message": "Google Cloud project or BigQuery integration is not configured.",
            }
        dataset_name = self.dataset_for_tenant(tenant_id)
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
        for table_name, columns in POWERBI_TABLE_DEFINITIONS.items():
            table_id = f"{dataset_id}.{table_name}"
            schema = [
                bigquery.SchemaField(column["name"], self._type_for_bigquery(column["dataType"]), mode="NULLABLE")
                for column in columns
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

    @staticmethod
    def _type_for_bigquery(data_type: str) -> str:
        return {
            "string": "STRING",
            "Int64": "INT64",
            "Double": "FLOAT64",
            "bool": "BOOL",
            "DateTime": "TIMESTAMP",
        }.get(data_type, "STRING")
