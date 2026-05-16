"""Crea extensiones y tablas en PostgreSQL (Neon). Uso:
  cd backend
  set DATABASE_URL=postgresql+asyncpg://...
  python -m scripts.init_postgres
"""
import asyncio
import sys

from sqlalchemy import text

from app.infrastructure.database import models  # noqa: F401
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import engine
from app.core.config import get_settings


async def main() -> None:
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        print("ERROR: DATABASE_URL apunta a SQLite. Usa la URL de Neon.", file=sys.stderr)
        sys.exit(1)

    print(f"Conectando a PostgreSQL ({settings.app_env})...")

    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pg_trgm"'))
        await conn.run_sync(Base.metadata.create_all)

    # Listar tablas creadas
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            )
        )
        tables = [row[0] for row in result.fetchall()]

    await engine.dispose()

    print(f"OK: {len(tables)} tablas en schema public:")
    for name in tables:
        print(f"  - {name}")


if __name__ == "__main__":
    asyncio.run(main())
