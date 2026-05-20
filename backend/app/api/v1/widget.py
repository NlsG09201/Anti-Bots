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
    "Access-Control-Allow-Headers": (
        "Content-Type, X-Stream-Key, X-SS-Nonce, X-SS-Timestamp, X-SS-Signature"
    ),
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
    if hasattr(request.state, "client_ip"):
        return request.state.client_ip
    from app.infrastructure.security.client_ip import resolve_client_ip

    ip, _ = resolve_client_ip(request)
    return ip if ip != "unknown" else ""


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
    model_config = {"extra": "allow"}

    screen: Optional[str] = None
    screen_resolution: Optional[str] = None
    timezone: Optional[str] = None
    timezone_offset_minutes: Optional[int] = None
    language: Optional[str] = None
    languages: Optional[list] = None
    platform: Optional[str] = None
    canvas_hash: Optional[str] = None
    canvas_duplicate_hash: Optional[str] = None
    canvas_noise_detected: Optional[bool] = None
    webgl_hash: Optional[str] = None
    webgl_vendor: Optional[str] = None
    webgl_renderer: Optional[str] = None
    audio_hash: Optional[str] = None
    webrtc_local_ips: Optional[list] = None
    webrtc_mdns_host: Optional[str] = None
    webrtc_failed: Optional[bool] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    plugins_count: Optional[int] = None
    hardware_concurrency: Optional[int] = None
    webdriver: bool = False
    selenium: bool = False
    puppeteer: bool = False
    playwright: bool = False
    headless_hints: Optional[Dict[str, Any]] = None


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

    from app.core.exceptions import ValidationError
    from app.infrastructure.security.ip_analysis import analyze_client_ip
    from app.infrastructure.security.replay import ReplayProtection

    ts_header = request.headers.get("X-SS-Timestamp")
    timestamp_ms = int(ts_header) if ts_header and ts_header.isdigit() else None
    try:
        await ReplayProtection().validate_request(
            scope=f"widget:{stream.id}",
            nonce=request.headers.get("X-SS-Nonce"),
            timestamp_ms=timestamp_ms,
            signature=request.headers.get("X-SS-Signature"),
            body=body.model_dump_json().encode("utf-8"),
            secret=body.stream_key.strip() if settings.security_widget_hmac_enabled else None,
        )
    except ValidationError as exc:
        from app.infrastructure.security.metrics_recorder import get_security_metrics_recorder

        await get_security_metrics_recorder().record("replay_400")
        return _cors_response({"ok": False, "error": exc.message}, 400)

    client_ip = get_client_ip(request)
    if not client_ip:
        return _cors_response({"ok": False, "error": "no_client_ip"}, 400)

    ip_meta = getattr(request.state, "ip_meta", {}) or {}
    ip_analysis = await analyze_client_ip(
        db,
        client_ip,
        spoof_risk=bool(ip_meta.get("xff_spoof_risk")),
    )
    if ip_analysis.get("is_threat") and ip_analysis.get("risk_score", 0) >= 70:
        from app.infrastructure.security.metrics_recorder import get_security_metrics_recorder

        await get_security_metrics_recorder().record("widget_blocked_403")
        return _cors_response(
            {
                "ok": False,
                "error": "connection_blocked",
                "risk_score": ip_analysis["risk_score"],
            },
            403,
        )

    fp_hash: Optional[str] = None
    fp_risk = 0.0
    trust_score = 100.0
    device_hash: Optional[str] = None
    session_key: Optional[str] = None
    automation_flags: list[str] = []
    if body.fingerprint:
        from app.services.detection.fingerprint_service import analyze_fingerprint_payload

        fp_dict = body.fingerprint.model_dump(exclude_none=True)
        if fp_dict.get("screen") and not fp_dict.get("screen_resolution"):
            fp_dict["screen_resolution"] = fp_dict["screen"]
        if not fp_dict.get("user_agent"):
            fp_dict["user_agent"] = request.headers.get("user-agent", "")[:512]
        fp_result = await analyze_fingerprint_payload(
            db,
            fp_dict,
            tenant_id=stream.tenant_id,
            server_ip=client_ip,
            persist=True,
            stream_id=stream.id,
        )
        fp_hash = fp_result.fingerprint_hash
        fp_risk = fp_result.risk_score
        trust_score = fp_result.trust_score
        device_hash = fp_result.device_hash
        session_key = fp_result.session_key
        automation_flags = list(fp_result.automation_flags)

    meta = dict(body.metadata)
    meta["fingerprint_risk"] = fp_risk
    meta["trust_score"] = trust_score
    meta["device_hash"] = device_hash
    meta["session_key"] = session_key
    meta["automation_flags"] = automation_flags
    meta["ip_analysis"] = {
        "risk_score": ip_analysis.get("risk_score"),
        "flags": ip_analysis.get("flags", []),
        "asn": ip_analysis.get("asn"),
        "is_proxy": ip_analysis.get("is_proxy"),
        "is_vpn": ip_analysis.get("is_vpn"),
    }
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
        f'  data-interval="60"></script>\n'
        f'<!-- Carga automática de streamshield-fp.js (fingerprint avanzado) desde el mismo origen -->'
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
