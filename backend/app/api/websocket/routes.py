from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.api.websocket.manager import ws_manager
from app.core.security import verify_token
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.websocket("/ws/live")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
):
    payload = verify_token(token, "access")
    if not payload:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    tenant_id = payload.get("tenant_id", "")
    user_id = payload.get("sub", "")

    await ws_manager.connect(websocket, tenant_id, user_id)
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
                    "data": {"connections": ws_manager.connection_count},
                })
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, tenant_id, user_id)
        logger.info("websocket_disconnected", user_id=user_id)
    except Exception as e:
        logger.error("websocket_error", error=str(e))
        await ws_manager.disconnect(websocket, tenant_id, user_id)
