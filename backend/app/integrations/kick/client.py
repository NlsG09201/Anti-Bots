import asyncio
from typing import Any, Dict, Optional

import httpx

class KickAPIClient:
    PUBLIC_API_BASE = "https://api.kick.com/public/v1"

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token
        self.headers = {"Accept": "application/json"}
        if access_token:
            self.headers["Authorization"] = f"Bearer {access_token}"

    async def get_user_livestream(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Read a broadcaster's live status through Kick's supported public API."""
        if not self.access_token:
            raise RuntimeError("Reconnecta Kick para consultar el estado del canal.")
        async with httpx.AsyncClient(timeout=8.0) as client:
            for attempt in range(2):
                try:
                    response = await client.get(
                        f"{self.PUBLIC_API_BASE}/users/livestreams",
                        headers={
                            "Authorization": f"Bearer {self.access_token}",
                            "Accept": "application/json",
                        },
                        params={"user_id": user_id},
                    )
                except (httpx.TimeoutException, httpx.NetworkError):
                    if attempt == 1:
                        raise
                    await asyncio.sleep(0.4)
                    continue

                if (response.status_code == 429 or response.status_code >= 500) and attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                response.raise_for_status()
                payload = response.json()
                entries = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(entries, list):
                    raise RuntimeError("Kick devolvió una respuesta de directos no válida.")
                if not entries:
                    return None
                live = entries[0]
                if not isinstance(live, dict):
                    raise RuntimeError("Kick devolvió datos de directo no válidos.")
                return {
                    "id": live.get("id"),
                    "viewer_count": live.get("viewer_count", 0),
                    "title": live.get("title"),
                }
        raise RuntimeError("No fue posible consultar el estado del canal Kick.")

    async def get_broadcaster_id_by_slug(self, slug: str) -> Optional[str]:
        if not self.access_token:
            return None
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self.PUBLIC_API_BASE}/channels",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Accept": "application/json",
                },
                params={"slug": slug.strip().lower().lstrip("@")},
            )
            response.raise_for_status()
            channels = response.json().get("data") or []
            if not channels:
                return None
            user_id = channels[0].get("broadcaster_user_id")
            return str(user_id) if user_id else None

    async def send_chat_message(self, broadcaster_id: str, content: str) -> Dict[str, Any]:
        if not self.access_token:
            raise RuntimeError("Conecta Kick antes de enviar mensajes.")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.PUBLIC_API_BASE}/chat",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json={
                    "broadcaster_user_id": int(broadcaster_id),
                    "content": content,
                    "type": "user",
                },
            )
            response.raise_for_status()
            return response.json() if response.content else {}

    async def moderate_user(
        self,
        broadcaster_id: str,
        user_id: str,
        *,
        reason: str,
        duration_minutes: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not self.access_token:
            raise RuntimeError("Conecta Kick antes de moderar usuarios.")
        payload: Dict[str, Any] = {
            "broadcaster_user_id": int(broadcaster_id),
            "user_id": int(user_id),
            "reason": reason[:100],
        }
        if duration_minutes is not None:
            payload["duration"] = duration_minutes
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.PUBLIC_API_BASE}/moderation/bans",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            return response.json() if response.content else {}

    def parse_viewer_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event_type": event_data.get("type", "viewer_join"),
            "platform_user_id": str(event_data.get("user_id", "")),
            "platform_username": event_data.get("username"),
            "metadata": event_data,
        }
