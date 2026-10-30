from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.api.websocket.manager import ws_manager
from app.core.logging import get_logger
from app.core.security import verify_token_with_reason
from app.infrastructure.cache.redis_client import RedisCache
from app.infrastructure.database.models import User
from app.infrastructure.database.session import AsyncSessionLocal

logger = get_logger(__name__)
router = APIRouter()


def _token_from_subprotocols(websocket: WebSocket) -> str | None:
    offered = [value.strip() for value in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    if "streamshield" not in offered:
        return None
    tokens = [value.removeprefix("bearer.") for value in offered if value.startswith("bearer.")]
    return tokens[0] if len(tokens) == 1 and tokens[0] else None


async def _authenticated_identity(token: str) -> tuple[str, str] | None:
    payload, _reason = verify_token_with_reason(token, "access")
    if not payload or not payload.get("jti"):
        return None
    try:
        user_id = UUID(str(payload.get("sub", "")))
    except (TypeError, ValueError):
        return None

    tenant_claim = str(payload.get("tenant_id", ""))
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.is_active or str(user.tenant_id) != tenant_claim:
            return None
        identity = str(user.id), str(user.tenant_id)

    if await RedisCache().is_blacklisted(str(payload["jti"])):
        return None
    return identity


@router.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    token = _token_from_subprotocols(websocket)
    try:
        identity = await _authenticated_identity(token) if token else None
    except Exception as exc:
        logger.error("websocket_auth_dependency_failed", error_type=type(exc).__name__)
        await websocket.close(code=1013, reason="Authentication temporarily unavailable")
        return

    if not identity:
        await websocket.close(code=4401, reason="Unauthorized")
        return

    user_id, tenant_id = identity
    await ws_manager.connect(websocket, tenant_id)
    logger.info("websocket_connected", user_id=user_id, tenant_id=tenant_id)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "ping")

            if msg_type == "ping":
                await ws_manager.send_personal(websocket, {"type": "pong"})
            elif msg_type == "subscribe":
                channel = data.get("channel", "all")
                await ws_manager.send_personal(websocket, {
                    "type": "subscribed",
                    "channel": channel,
                })
            elif msg_type == "stats_request":
                await ws_manager.send_personal(websocket, {
                    "type": "stats_update",
                    "data": {
                        "connections": ws_manager.connection_count_for_tenant(tenant_id)
                    },
                })
    except WebSocketDisconnect:
        logger.info("websocket_disconnected", user_id=user_id)
    except Exception as exc:
        logger.warning("websocket_error", error_type=type(exc).__name__)
    finally:
        await ws_manager.disconnect(websocket, tenant_id)
