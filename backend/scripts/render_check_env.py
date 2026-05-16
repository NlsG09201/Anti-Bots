#!/usr/bin/env python3
"""Comprueba variables obligatorias antes de uvicorn (Render logs)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings, invalidate_settings_cache, render_secret_env_path
from app.core.startup import INSECURE_DEFAULTS, validate_production_settings

REQUIRED_ENV_KEYS = (
    "DATABASE_URL",
    "APP_SECRET_KEY",
    "JWT_SECRET_KEY",
    "AES_ENCRYPTION_KEY",
)


def _missing_required_env_keys() -> list[str]:
    missing: list[str] = []
    for key in REQUIRED_ENV_KEYS:
        raw = os.environ.get(key, "").strip()
        if not raw:
            missing.append(key)
    return missing


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

    missing_keys = _missing_required_env_keys()
    if missing_keys:
        print(
            "\n=== RENDER STARTUP BLOCKED ===",
            flush=True,
        )
        print(
            "Variables NO definidas en Render Environment:",
            ", ".join(missing_keys),
            flush=True,
        )
        print(
            "\nSolucion: Render -> anti-bots-api -> Environment\n"
            "  Add from .env -> pega deploy/render.import.env -> Save -> Manual Deploy\n"
            "  (Dashboard Start Command debe coincidir con render.yaml o dejarse vacio)",
            flush=True,
        )
        sys.exit(1)

    errors = validate_production_settings()
    if settings.is_production and errors:
        print("\n=== RENDER STARTUP BLOCKED ===", flush=True)
        for err in errors:
            print(f"  - {err}", flush=True)
        print(
            "\nSolucion: Render -> anti-bots-api -> Environment\n"
            "  Add from .env -> pega deploy/render.import.env -> Save -> Manual Deploy\n",
            flush=True,
        )
        sys.exit(1)

    if "localhost" in settings.database_url or "127.0.0.1" in settings.database_url:
        print("ERROR: DATABASE_URL falta. Importa deploy/render.import.env en Render.", flush=True)
        sys.exit(1)

    if not settings.database_url.startswith("postgresql"):
        print("ERROR: DATABASE_URL debe ser postgresql+asyncpg://...", flush=True)
        sys.exit(1)

    if settings.app_secret_key in INSECURE_DEFAULTS:
        print("ERROR: APP_SECRET_KEY no configurada.", flush=True)
        sys.exit(1)

    print("Preflight OK — starting uvicorn", flush=True)


if __name__ == "__main__":
    main()
