#!/usr/bin/env python3
"""Comprueba variables obligatorias antes de uvicorn (Render logs)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import _RENDER_SECRET_ENV, get_settings
from app.core.startup import INSECURE_DEFAULTS, validate_production_settings


def main() -> None:
    settings = get_settings()
    on_render = bool(os.getenv("RENDER"))
    secret_file = _RENDER_SECRET_ENV.is_file()
    print(
        f"StreamShield preflight — APP_ENV={settings.app_env}"
        f" render={on_render} secret_file={secret_file}",
        flush=True,
    )

    errors = validate_production_settings()
    if settings.is_production and errors:
        print("\n=== RENDER STARTUP BLOCKED ===", file=sys.stderr, flush=True)
        for err in errors:
            print(f"  - {err}", file=sys.stderr, flush=True)
        print(
            "\nSolucion (elige UNA):\n"
            "  A) Environment → Add from .env → pega deploy/render.import.env\n"
            "  B) Environment → Secret Files → sube render.import.env como '.env'\n"
            "  Luego: Save Changes → Manual Deploy\n",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    if "localhost" in settings.database_url or "127.0.0.1" in settings.database_url:
        print(
            "ERROR: DATABASE_URL falta o apunta a localhost.",
            file=sys.stderr,
            flush=True,
        )
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
