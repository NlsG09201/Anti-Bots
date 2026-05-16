"""Importa datos de streamshield.db (SQLite local) a PostgreSQL (Neon).

Uso:
  cd backend
  $env:DATABASE_URL="postgresql+asyncpg://neondb_owner:CONTRASEÑA_REAL@ep-....neon.tech/neondb?sslmode=require"
  python -m scripts.import_sqlite_to_neon

La contraseña la copias en Neon Console → Connection string (no uses TU_PASSWORD).
"""
import asyncio
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from uuid import UUID

from dateutil import parser as date_parser
from sqlalchemy import text

from app.core.config import get_settings
from app.infrastructure.database.session import engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
SQLITE_PATH = BACKEND_DIR / "streamshield.db"
RENDER_ENV = BACKEND_DIR.parent / "deploy" / "render.env"

PLACEHOLDER_MARKERS = ("TU_PASSWORD", "PEGAR_", "CHANGE_ME", "your-password", "password@")

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


def _load_database_url_from_render_env() -> str | None:
    if not RENDER_ENV.exists():
        return None
    for line in RENDER_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("DATABASE_URL=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip()
    return None


def _validate_database_url(url: str) -> None:
    if url.startswith("sqlite"):
        print(
            "ERROR: DATABASE_URL apunta a SQLite.\n"
            "Define la URL de Neon antes de ejecutar:\n"
            '  $env:DATABASE_URL="postgresql+asyncpg://neondb_owner:CONTRASEÑA@ep-....neon.tech/neondb?sslmode=require"',
            file=sys.stderr,
        )
        sys.exit(1)
    if not url.startswith("postgresql"):
        print(f"ERROR: DATABASE_URL no es PostgreSQL: {url[:40]}...", file=sys.stderr)
        sys.exit(1)
    if "postgresql://" in url and "+asyncpg" not in url:
        print(
            "ERROR: Usa postgresql+asyncpg:// (no postgresql://)",
            file=sys.stderr,
        )
        sys.exit(1)
    for marker in PLACEHOLDER_MARKERS:
        if marker.lower() in url.lower():
            print(
                f"ERROR: DATABASE_URL contiene '{marker}' — es un placeholder.\n"
                "Copia la connection string REAL desde https://console.neon.tech\n"
                "  → tu proyecto → Connection string → Pooled → asyncpg",
                file=sys.stderr,
            )
            sys.exit(1)
    if not re.search(r"://[^:]+:[^@]+@", url):
        print("ERROR: DATABASE_URL sin contraseña en la URL.", file=sys.stderr)
        sys.exit(1)


async def main() -> None:
    if not os.environ.get("DATABASE_URL"):
        from_file = _load_database_url_from_render_env()
        if from_file:
            os.environ["DATABASE_URL"] = from_file
            print("Usando DATABASE_URL de deploy/render.env\n")

    settings = get_settings()
    _validate_database_url(settings.database_url)

    if not SQLITE_PATH.exists():
        print(f"ERROR: No existe {SQLITE_PATH}", file=sys.stderr)
        sys.exit(1)

    host = settings.database_url.split("@")[-1].split("?")[0]
    print(f"Origen:  {SQLITE_PATH}")
    print(f"Destino: Neon ({host})\n")

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    total = 0

    try:
        async with engine.begin() as pg_conn:
            for table in TABLES:
                try:
                    total += await import_table(pg_conn, sqlite_conn, table)
                except Exception as exc:
                    print(f"  {table}: ERROR - {exc}", file=sys.stderr)
    except Exception as exc:
        err = str(exc).lower()
        if "password authentication failed" in err or "invalidpassword" in err:
            print(
                "\nERROR: Contraseña de Neon incorrecta.\n"
                "1. Entra en https://console.neon.tech\n"
                "2. Tu proyecto → Connection details → Reset password (si hace falta)\n"
                "3. Copia la URL pooled y cambia postgresql:// por postgresql+asyncpg://\n"
                "4. Ejecuta de nuevo con la contraseña nueva en DATABASE_URL y en Render",
                file=sys.stderr,
            )
        else:
            print(f"\nERROR de conexión: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        sqlite_conn.close()
        await engine.dispose()

    print(f"\nOK: {total} filas importadas.")


if __name__ == "__main__":
    asyncio.run(main())
