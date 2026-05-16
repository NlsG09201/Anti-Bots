"""Prueba conexión a Neon. Uso:
  cd backend
  $env:DATABASE_URL="postgresql+asyncpg://neondb_owner:CONTRASEÑA_NUEVA@ep-....neon.tech/neondb?sslmode=require"
  python -m scripts.test_neon_connection
"""
import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import text

RENDER_ENV = Path(__file__).resolve().parents[2] / "deploy" / "render.env"


def _load_url() -> str | None:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if RENDER_ENV.exists():
        for line in RENDER_ENV.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    return None


async def main() -> None:
    url = _load_url()
    if not url:
        print("ERROR: Define DATABASE_URL o ponla en deploy/render.env", file=sys.stderr)
        sys.exit(1)

    if "TU_PASSWORD" in url or "PEGAR_" in url:
        print("ERROR: DATABASE_URL tiene un placeholder, no la contraseña real.", file=sys.stderr)
        sys.exit(1)

    os.environ["DATABASE_URL"] = url
    from app.infrastructure.database.session import engine

    host = url.split("@")[-1].split("?")[0]
    print(f"Probando: {host}")

    try:
        async with engine.connect() as conn:
            version = await conn.scalar(text("SELECT version()"))
            tables = await conn.scalar(
                text("SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public'")
            )
        print("OK: Conexión exitosa")
        print(f"  PostgreSQL: {version[:60]}...")
        print(f"  Tablas public: {tables}")
    except Exception as exc:
        if "password authentication failed" in str(exc).lower():
            print(
                "\nFALLO: Contraseña incorrecta para 'neondb_owner'.\n\n"
                "Solución:\n"
                "  1. https://console.neon.tech → tu proyecto\n"
                "  2. Dashboard → Connection string → Reset password\n"
                "  3. Copia la URL nueva (Pooled)\n"
                "  4. Cambia postgresql:// por postgresql+asyncpg://\n"
                "  5. Actualiza deploy/render.env línea DATABASE_URL\n"
                "  6. Vuelve a ejecutar este script",
                file=sys.stderr,
            )
        else:
            print(f"\nFALLO: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
