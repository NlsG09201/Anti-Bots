import secrets
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.api.v1.schemas import EventIngest
from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.security import hash_fingerprint
from app.infrastructure.database.models import Stream
from app.infrastructure.database.session import get_db
from app.services.detection.engine import BotDetectionEngine
from app.services.ingest.event_ingest import process_stream_event
from app.services.streams.helpers import stream_to_response_dict

router = APIRouter(tags=["Widget"])
settings = get_settings()
fp_engine = BotDetectionEngine()

WIDGET_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Stream-Key",
    "Access-Control-Max-Age": "86400",
}


def _cors_response(content: dict, status_code: int = 200) -> Response:
    import orjson

    return Response(
        content=orjson.dumps(content),
        status_code=status_code,
        media_type="application/json",
        headers=WIDGET_CORS_HEADERS,
    )


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For") or request.headers.get("CF-Connecting-IP")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return ""


def _ensure_ingest_key(stream: Stream) -> str:
    meta = dict(stream.settings or {})
    key = meta.get("ingest_key")
    if not key:
        key = secrets.token_urlsafe(24)
        meta["ingest_key"] = key
        stream.settings = meta
    return key


async def _stream_by_ingest_key(db: AsyncSession, stream_key: str) -> Optional[Stream]:
    if not stream_key or len(stream_key) < 16:
        return None
    result = await db.execute(select(Stream))
    for stream in result.scalars().all():
        settings_map = stream.settings or {}
        if settings_map.get("ingest_key") == stream_key:
            return stream
    return None


class WidgetFingerprint(BaseModel):
    screen: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    platform: Optional[str] = None
    canvas_hash: Optional[str] = None
    webgl_hash: Optional[str] = None
    user_agent: Optional[str] = None
    plugins_count: Optional[int] = None
    hardware_concurrency: Optional[int] = None


class WidgetPing(BaseModel):
    stream_key: str = Field(..., min_length=16, max_length=128)
    event_type: str = Field(default="viewer_pulse", max_length=50)
    platform_username: Optional[str] = Field(default=None, max_length=255)
    platform_user_id: Optional[str] = Field(default=None, max_length=255)
    fingerprint: Optional[WidgetFingerprint] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


@router.options("/widget/ping")
async def widget_ping_options():
    return Response(status_code=204, headers=WIDGET_CORS_HEADERS)


@router.post("/widget/ping")
async def widget_ping(
    body: WidgetPing,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint publico para el script embebible.
    Captura IP del visitante (desde cabeceras del proxy) + fingerprint del navegador.
    """
    stream = await _stream_by_ingest_key(db, body.stream_key.strip())
    if not stream:
        return _cors_response({"ok": False, "error": "invalid_stream_key"}, 401)

    client_ip = get_client_ip(request)
    if not client_ip:
        return _cors_response({"ok": False, "error": "no_client_ip"}, 400)

    fp_hash: Optional[str] = None
    fp_risk = 0.0
    if body.fingerprint:
        fp_dict = body.fingerprint.model_dump(exclude_none=True)
        if not fp_dict.get("user_agent"):
            fp_dict["user_agent"] = request.headers.get("user-agent", "")[:512]
        fp_hash = hash_fingerprint(fp_dict)
        detection = fp_engine.analyze_fingerprint(
            {
                "screen_resolution": fp_dict.get("screen"),
                "timezone": fp_dict.get("timezone"),
                "language": fp_dict.get("language"),
                "platform": fp_dict.get("platform"),
                "user_agent": fp_dict.get("user_agent"),
                "plugins": [],
                "fonts": [],
                "selenium": False,
                "puppeteer": False,
                "playwright": False,
            }
        )
        fp_risk = detection.risk_score

    meta = dict(body.metadata)
    meta["fingerprint_risk"] = fp_risk
    meta["widget_version"] = body.metadata.get("widget_version", "1.0")
    meta["page_url"] = body.metadata.get("page_url") or str(request.headers.get("referer", ""))[:512]

    event = EventIngest(
        event_type=body.event_type,
        platform_user_id=body.platform_user_id,
        platform_username=body.platform_username,
        ip_address=client_ip,
        fingerprint_hash=fp_hash,
        metadata=meta,
    )

    result = await process_stream_event(
        db,
        stream,
        stream.tenant_id,
        event,
        source="widget",
    )
    await db.commit()

    return _cors_response(
        {
            "ok": True,
            "risk_score": result["risk_score"],
            "attack_created": result["attack_created"],
            "is_proxy": result.get("is_proxy", False),
            "is_vpn": result.get("is_vpn", False),
            "channel": stream.channel_name,
        }
    )


@router.get("/streams/{stream_id}/widget/embed")
async def get_widget_embed(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    from app.api.v1.streams import _get_stream

    stream = await _get_stream(db, stream_id, current_user.tenant_id)
    ingest_key = _ensure_ingest_key(stream)
    await db.flush()

    api_public = settings.app_public_url.rstrip("/")
    frontend_public = settings.app_frontend_url.rstrip("/")

    script_src = f"{frontend_public}/streamshield-widget.js"
    snippet = (
        f'<script src="{script_src}" async\n'
        f'  data-stream-key="{ingest_key}"\n'
        f'  data-api-url="{api_public}"\n'
        f'  data-interval="60"></script>'
    )

    obs_snippet = (
        f'<html><head><meta charset="utf-8"></head><body style="margin:0;background:transparent;">\n'
        f"{snippet}\n"
        f"</body></html>"
    )

    return {
        "stream": stream_to_response_dict(stream),
        "ingest_key": ingest_key,
        "script_url": script_src,
        "api_url": api_public,
        "embed_html": snippet,
        "obs_browser_source_html": obs_snippet,
        "instructions": [
            "Pega el snippet en tu web del canal, panel de extension o fuente de navegador OBS.",
            "El widget envia la IP del visitante al API (via proxy) y fingerprint del navegador.",
            "Usa data-username en el script si quieres asociar un login de Twitch.",
        ],
    }


@router.post("/streams/{stream_id}/widget/key")
async def regenerate_widget_key(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    from app.api.v1.streams import _get_stream

    stream = await _get_stream(db, stream_id, current_user.tenant_id)
    meta = dict(stream.settings or {})
    meta["ingest_key"] = secrets.token_urlsafe(24)
    stream.settings = meta
    await db.flush()
    return {"ingest_key": meta["ingest_key"], "status": "regenerated"}
