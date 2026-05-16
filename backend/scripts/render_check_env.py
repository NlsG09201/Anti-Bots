#!/usr/bin/env python3
"""Comprueba variables obligatorias antes de uvicorn (Render logs)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.startup import INSECURE_DEFAULTS, validate_production_settings

REQUIRED_ON_RENDER = (
    "DATABASE_URL",
    "APP_SECRET_KEY",
    "JWT_SECRET_KEY",
    "AES_ENCRYPTION_KEY",
)


def _missing_env_keys() -> list[str]:
    missing = []
    for key in REQUIRED_ON_RENDER:
        if not os.environ.get(key, "").strip():
            missing.append(key)
    return missing


def main() -> None:
    settings = get_settings()
    on_render = bool(os.getenv("RENDER"))
    print(
        f"StreamShield preflight — APP_ENV={settings.app_env}"
        f" render={on_render}",
        flush=True,
    )

    missing = _missing_env_keys()
    if missing:
        print("\n=== RENDER STARTUP BLOCKED ===", file=sys.stderr, flush=True)
        print("Variables NO definidas en Render → Environment:", file=sys.stderr, flush=True)
        for key in missing:
            print(f"  - {key}", file=sys.stderr, flush=True)
        print(
            "\nSolución:\n"
            "  1. Abre deploy/render.env en tu PC (no está en GitHub)\n"
            "  2. Render → tu servicio → Environment → Add from .env\n"
            "  3. Pega TODO el archivo → Save Changes → Manual Deploy\n",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    if not settings.is_production:
        print(
            "WARNING: APP_ENV is not 'production'.",
            flush=True,
        )

    errors = validate_production_settings()
    if settings.is_production and errors:
        print("\n=== RENDER STARTUP BLOCKED ===", file=sys.stderr, flush=True)
        for err in errors:
            print(f"  - {err}", file=sys.stderr, flush=True)
        sys.exit(1)

    if "localhost" in settings.database_url or "127.0.0.1" in settings.database_url:
        print(
            "ERROR: DATABASE_URL apunta a localhost. Usa la URL pooled de Neon.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    if not settings.database_url.startswith("postgresql"):
        print("ERROR: DATABASE_URL debe ser postgresql+asyncpg://...", file=sys.stderr, flush=True)
        sys.exit(1)

    if settings.app_secret_key in INSECURE_DEFAULTS:
        print("ERROR: APP_SECRET_KEY sigue siendo el valor por defecto.", file=sys.stderr, flush=True)
        sys.exit(1)

    print("Preflight OK — starting uvicorn", flush=True)


if __name__ == "__main__":
    main()
