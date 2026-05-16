import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Set
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.core.security import verify_token

logger = get_logger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.user_connections: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        tenant_id: str,
        user_id: str,
    ) -> None:
        await websocket.accept()
        async with self._lock:
            if tenant_id not in self.active_connections:
                self.active_connections[tenant_id] = set()
            self.active_connections[tenant_id].add(websocket)
            self.user_connections[user_id] = websocket
        await self.send_personal(websocket, {
            "type": "connected",
            "tenant_id": tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def disconnect(self, websocket: WebSocket, tenant_id: str, user_id: str) -> None:
        async with self._lock:
            if tenant_id in self.active_connections:
                self.active_connections[tenant_id].discard(websocket)
                if not self.active_connections[tenant_id]:
                    del self.active_connections[tenant_id]
            self.user_connections.pop(user_id, None)

    async def send_personal(self, websocket: WebSocket, data: Dict[str, Any]) -> None:
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.warning("websocket_send_failed", error=str(e))

    async def broadcast_to_tenant(self, tenant_id: str, data: Dict[str, Any]) -> None:
        connections = self.active_connections.get(tenant_id, set()).copy()
        dead: List[WebSocket] = []
        for connection in connections:
            try:
                await connection.send_json(data)
            except Exception:
                dead.append(connection)
        for ws in dead:
            async with self._lock:
                if tenant_id in self.active_connections:
                    self.active_connections[tenant_id].discard(ws)

    async def broadcast_attack(self, tenant_id: str, attack_data: Dict[str, Any]) -> None:
        await self.broadcast_to_tenant(tenant_id, {
            "type": "attack_detected",
            "data": attack_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def broadcast_alert(self, tenant_id: str, alert_data: Dict[str, Any]) -> None:
        await self.broadcast_to_tenant(tenant_id, {
            "type": "alert",
            "data": alert_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def broadcast_stats(self, tenant_id: str, stats: Dict[str, Any]) -> None:
        await self.broadcast_to_tenant(tenant_id, {
            "type": "stats_update",
            "data": stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    @property
    def connection_count(self) -> int:
        return sum(len(conns) for conns in self.active_connections.values())


ws_manager = ConnectionManager()
