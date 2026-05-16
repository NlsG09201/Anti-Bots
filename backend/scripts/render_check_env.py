#!/usr/bin/env python3
"""Comprueba variables obligatorias antes de uvicorn (Render logs)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings, invalidate_settings_cache, render_secret_env_path
from app.core.startup import INSECURE_DEFAULTS, validate_production_settings


def main() -> None:
    invalidate_settings_cache()
    settings = get_settings()
    on_render = bool(os.getenv("RENDER"))
    secret_file = render_secret_env_path() is not None
    db_host = settings.database_url.split("@")[-1].split("/")[0] if "@" in settings.database_url else "?"

    print(
        f"StreamShield preflight — APP_ENV={settings.app_env}"
        f" render={on_render} secret_file={secret_file} db={db_host}",
        flush=True,
    )

    errors = validate_production_settings()
    if settings.is_production and errors:
        print("\n=== RENDER STARTUP BLOCKED ===", file=sys.stderr, flush=True)
        for err in errors:
            print(f"  - {err}", file=sys.stderr, flush=True)
        print(
            "\nSolucion: Render -> anti-bots-api -> Environment\n"
            "  Add from .env -> pega deploy/render.import.env -> Save -> Manual Deploy\n",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    if "localhost" in settings.database_url or "127.0.0.1" in settings.database_url:
        print("ERROR: DATABASE_URL falta. Importa deploy/render.import.env en Render.", file=sys.stderr, flush=True)
        sys.exit(1)

    if not settings.database_url.startswith("postgresql"):
        print("ERROR: DATABASE_URL debe ser postgresql+asyncpg://...", file=sys.stderr, flush=True)
        sys.exit(1)

    if settings.app_secret_key in INSECURE_DEFAULTS:
        print("ERROR: APP_SECRET_KEY no configurada.", file=sys.stderr, flush=True)
        sys.exit(1)

    print("Preflight OK — starting uvicorn", flush=True)


if __name__ == "__main__":
    main()
