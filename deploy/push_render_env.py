#!/usr/bin/env python3
"""Sube variables a Render y lanza deploy. Requiere RENDER_API_KEY o deploy/render.api.key"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent
IMPORT_FILE = DEPLOY_DIR / "render.import.env"
API_KEY_FILE = DEPLOY_DIR / "render.api.key"
SERVICE_NAME = os.environ.get("RENDER_SERVICE_NAME", "anti-bots-api")
API_BASE = "https://api.render.com/v1"

EXTRA_VARS = {
    "PYTHON_VERSION": "3.11.9",
    "RENDER": "true",
}


def _api_key() -> str:
    key = os.environ.get("RENDER_API_KEY", "").strip()
    if not key and API_KEY_FILE.exists():
        # utf-8-sig quita BOM que PowerShell a veces añade al guardar el archivo
        key = API_KEY_FILE.read_text(encoding="utf-8-sig").strip()
    key = key.lstrip("\ufeff").strip()
    if not key:
        print(
            "ERROR: Falta RENDER_API_KEY.\n"
            "  1. https://dashboard.render.com/u/settings#api-keys -> Create\n"
            "  2. Guarda solo la clave rnd_... en deploy/render.api.key\n"
            "     o: set RENDER_API_KEY=rnd_xxx",
            file=sys.stderr,
        )
        sys.exit(1)
    if not key.startswith("rnd_"):
        print(
            f"ERROR: La API key no es valida (debe empezar con rnd_, recibido: {key[:12]}...).\n"
            "  Borra deploy/render.api.key y vuelve a ejecutar push-render-env.ps1",
            file=sys.stderr,
        )
        sys.exit(1)
    return key


def _request(method: str, path: str, key: str, body: dict | None = None) -> object:
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        print(f"HTTP {e.code} {method} {path}\n{err_body}", file=sys.stderr)
        raise


def _find_service(key: str, name: str) -> dict:
    cursor: str | None = None
    all_names: list[str] = []
    while True:
        path = "/services?limit=100"
        if cursor:
            path += "&" + urllib.parse.urlencode({"cursor": cursor})
        page = _request("GET", path, key)
        if not isinstance(page, list):
            raise RuntimeError(f"Respuesta inesperada: {page!r}")
        if not page:
            break
        for item in page:
            svc = item.get("service") or item
            svc_name = svc.get("name", "")
            all_names.append(svc_name)
            if svc_name == name:
                return svc
        last = page[-1]
        cursor = last.get("cursor") if isinstance(last, dict) else None
        if not cursor:
            break
    print("Servicios en tu cuenta:", ", ".join(sorted(set(n for n in all_names if n))), file=sys.stderr)
    raise SystemExit(f"No existe el servicio '{name}'")


def _parse_env_file(path: Path) -> dict[str, str]:
    vars_map: dict[str, str] = dict(EXTRA_VARS)
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            v = v[1:-1]
        vars_map[k] = v
    return vars_map


def _upsert_env_vars(service_id: str, key: str, env: dict[str, str]) -> None:
    for env_key, value in sorted(env.items()):
        _request("PUT", f"/services/{service_id}/env-vars/{env_key}", key, {"value": value})
        print(f"  OK {env_key}")


def _trigger_deploy(service_id: str, key: str) -> None:
    _request("POST", f"/services/{service_id}/deploys", key, {"clearCache": "do_not_clear"})


def _wait_health(url: str, attempts: int = 36) -> bool:
    health = url.rstrip("/") + "/health"
    for i in range(1, attempts + 1):
        try:
            req = urllib.request.Request(health, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status == 200:
                    body = resp.read().decode()
                    print(f"Health OK ({health}): {body[:120]}")
                    return True
        except Exception as exc:
            print(f"  {i}/{attempts}: {exc}")
        time.sleep(10)
    return False


def main() -> None:
    import_path = IMPORT_FILE
    if not import_path.exists():
        prepare = DEPLOY_DIR / "prepare-render-import.ps1"
        if prepare.exists():
            os.system(f'powershell -File "{prepare}"')
        if not import_path.exists():
            sys.exit("Falta deploy/render.import.env")

    api_key = _api_key()
    env = _parse_env_file(import_path)
    print(f"Buscando {SERVICE_NAME}...")
    service = _find_service(api_key, SERVICE_NAME)
    sid = service["id"]
    print(f"ID: {sid}")

    print(f"Subiendo {len(env)} variables...")
    _upsert_env_vars(sid, api_key, env)

    print("Deploy...")
    _trigger_deploy(sid, api_key)

    base = (service.get("serviceDetails") or {}).get("url") or f"https://{SERVICE_NAME}.onrender.com"
    print(f"Esperando {base} (hasta 6 min)...")
    if not _wait_health(base):
        sys.exit("Deploy enviado; /health no respondio a tiempo. Revisa logs en Render.")
    print("Listo.")


if __name__ == "__main__":
    main()
