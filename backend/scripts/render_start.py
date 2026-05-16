#!/usr/bin/env python3
"""Arranque unificado para Render: bootstrap env, preflight, uvicorn."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# RENDER=true lo fija render.yaml; asegurar antes de importar app
os.environ.setdefault("RENDER", "true")

from app.core.config import invalidate_settings_cache  # noqa: E402


def main() -> None:
    invalidate_settings_cache()

    from scripts.render_check_env import main as preflight

    preflight()

    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    print(f"Starting uvicorn on 0.0.0.0:{port}", flush=True)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
