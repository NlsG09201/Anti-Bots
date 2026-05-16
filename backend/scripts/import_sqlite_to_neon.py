"""Importa datos de streamshield.db (SQLite local) a PostgreSQL (Neon).

Uso:
  cd backend
  set DATABASE_URL=postgresql+asyncpg://...@neon.../neondb?sslmode=require
  python -m scripts.import_sqlite_to_neon
"""
import asyncio
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID

from dateutil import parser as date_parser
from sqlalchemy import text

from app.core.config import get_settings
from app.infrastructure.database.session import engine

SQLITE_PATH = Path(__file__).resolve().parents[1] / "streamshield.db"

TABLES = [
    "tenants",
    "users",
    "token_blacklist",
    "fingerprints",
    "ip_reputations",
    "refresh_tokens",
    "streams",
    "stream_events",
    "attacks",
    "bans",
    "viewer_sessions",
    "alerts",
    "audit_logs",
]

JSON_COLUMNS = frozenset({
    "settings",
    "metadata",
    "evidence",
    "behavior_metrics",
    "details",
    "raw_payload",
})

UUID_COLUMNS = frozenset({"id", "tenant_id", "user_id", "stream_id", "attack_id", "created_by", "acknowledged_by", "owner_id"})
DATETIME_COLUMNS = frozenset({
    "created_at",
    "updated_at",
    "expires_at",
    "last_login",
    "mitigated_at",
    "resolved_at",
    "acknowledged_at",
    "joined_at",
    "left_at",
})

BOOL_COLUMNS = frozenset({
    "is_active",
    "is_revoked",
    "is_live",
    "is_proxy",
    "is_vpn",
    "is_tor",
    "is_datacenter",
    "is_suspected_bot",
    "is_automated",
    "mfa_enabled",
    "is_verified",
    "is_headless",
    "is_selenium",
    "is_puppeteer",
    "is_playwright",
    "webdriver",
    "selenium",
    "puppeteer",
    "playwright",
})


def _normalize(col: str, val):
    if val is None:
        return None
    if col in JSON_COLUMNS:
        if isinstance(val, str):
            try:
                parsed = json.loads(val) if val else {}
            except json.JSONDecodeError:
                parsed = {}
        elif isinstance(val, dict):
            parsed = val
        else:
            parsed = {}
        return json.dumps(parsed)
    if col in BOOL_COLUMNS:
        return bool(val)
    if col in UUID_COLUMNS:
        return UUID(str(val).replace("-", "")) if len(str(val).replace("-", "")) == 32 else UUID(str(val))
    if col in DATETIME_COLUMNS and isinstance(val, str):
        return date_parser.parse(val)
    if col == "role" and isinstance(val, str):
        return val.upper()
    return val


async def import_table(pg_conn, sqlite_conn: sqlite3.Connection, table: str) -> int:
    pragma = sqlite_conn.execute(f"PRAGMA table_info([{table}])").fetchall()
    if not pragma:
        return 0

    columns = [p[1] for p in pragma]
    sqlite_conn.row_factory = sqlite3.Row
    rows = sqlite_conn.execute(f"SELECT * FROM [{table}]").fetchall()
    if not rows:
        print(f"  {table}: 0 filas")
        return 0

    col_list = ", ".join(columns)
    placeholders = ", ".join(f":{c}" for c in columns)
    sql = (
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT (id) DO NOTHING"
    )

    count = 0
    for row in rows:
        data = {col: _normalize(col, row[col]) for col in columns}
        result = await pg_conn.execute(text(sql), data)
        if result.rowcount:
            count += 1

    print(f"  {table}: {count}/{len(rows)} importadas")
    return count


async def main() -> None:
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        print("ERROR: DATABASE_URL debe ser la URL de Neon (PostgreSQL).", file=sys.stderr)
        sys.exit(1)

    if not SQLITE_PATH.exists():
        print(f"ERROR: No existe {SQLITE_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Origen:  {SQLITE_PATH}")
    print("Destino: Neon (PostgreSQL)\n")

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    total = 0

    async with engine.begin() as pg_conn:
        for table in TABLES:
            try:
                total += await import_table(pg_conn, sqlite_conn, table)
            except Exception as exc:
                print(f"  {table}: ERROR - {exc}", file=sys.stderr)

    sqlite_conn.close()
    await engine.dispose()
    print(f"\nOK: {total} filas importadas.")


if __name__ == "__main__":
    asyncio.run(main())
