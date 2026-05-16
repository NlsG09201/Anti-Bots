#!/usr/bin/env python3
"""Comprueba variables obligatorias antes de uvicorn (Render logs)."""
import sys
from pathlib import Path

# python scripts/render_check_env.py → sys.path[0] es scripts/, no backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.startup import validate_production_settings


def main() -> None:
    settings = get_settings()
    print(f"StreamShield preflight — APP_ENV={settings.app_env}", flush=True)

    if not settings.is_production:
        print(
            "WARNING: APP_ENV is not 'production'. Set APP_ENV=production on Render.",
            flush=True,
        )

    errors = validate_production_settings()
    if settings.is_production and errors:
        print("\n=== RENDER STARTUP BLOCKED ===", file=sys.stderr, flush=True)
        for err in errors:
            print(f"  - {err}", file=sys.stderr, flush=True)
        print(
            "\nFix: Render Dashboard → Environment → import deploy/render.env\n",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    # En Render no hay Postgres local; sin DATABASE_URL en el dashboard usa el default localhost.
    if "localhost" in settings.database_url or "127.0.0.1" in settings.database_url:
        print(
            "ERROR: DATABASE_URL not set (still localhost). "
            "Render Dashboard → Environment → paste Neon postgresql+asyncpg://...",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    if not settings.database_url.startswith("postgresql"):
        print(
            "ERROR: DATABASE_URL must be postgresql+asyncpg://...",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    print("Preflight OK — starting uvicorn", flush=True)


if __name__ == "__main__":
    main()
