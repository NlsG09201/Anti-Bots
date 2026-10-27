"""Kick chat bot configuration and actions."""

from __future__ import annotations

import time
from typing import List
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import StreamModeratorUser
from app.core.exceptions import NotFoundError, ValidationError
from app.infrastructure.database.models import Platform, Stream
from app.infrastructure.database.session import get_db
from app.integrations.kick.client import KickAPIClient
from app.services.platforms.oauth_tokens import get_stream_access_token

router = APIRouter(prefix="/kick/bot", tags=["Kick Chat Bot"])
_command_cooldowns: dict[str, float] = {}


class KickBotCommand(BaseModel):
    command: str = Field(min_length=2, max_length=32)
    response: str = Field(min_length=1, max_length=500)
    enabled: bool = True

    @field_validator("command")
    @classmethod
    def normalize_command(cls, value: str) -> str:
        value = value.strip().lower()
        if not value.startswith("!") or not value[1:].replace("_", "").isalnum():
            raise ValueError("El comando debe empezar por ! y contener letras, números o _.")
        return value


class KickBotSettings(BaseModel):
    enabled: bool = False
    commands: List[KickBotCommand] = Field(default_factory=list, max_length=50)

    @field_validator("commands")
    @classmethod
    def unique_commands(cls, commands: List[KickBotCommand]) -> List[KickBotCommand]:
        names = [command.command for command in commands]
        if len(names) != len(set(names)):
            raise ValueError("No puede haber comandos duplicados.")
        return commands


class KickBotMessage(BaseModel):
    content: str = Field(min_length=1, max_length=500)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El mensaje no puede estar vacío.")
        if len(value.encode("utf-8")) > 2048:
            raise ValueError("El mensaje supera el límite permitido por Kick.")
        return value


async def _owned_kick_stream(
    stream_id: UUID,
    tenant_id: UUID,
    db: AsyncSession,
) -> Stream:
    result = await db.execute(
        select(Stream).where(
            Stream.id == stream_id,
            Stream.tenant_id == tenant_id,
            Stream.platform == Platform.KICK,
        )
    )
    stream = result.scalar_one_or_none()
    if not stream:
        raise NotFoundError("Kick channel")
    if not stream.oauth_token_encrypted:
        raise ValidationError("Conecta o vuelve a autorizar el canal Kick.")
    return stream


@router.get("/{stream_id}")
async def get_bot_settings(
    stream_id: UUID,
    current_user: StreamModeratorUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await _owned_kick_stream(stream_id, current_user.tenant_id, db)
    saved = (stream.settings or {}).get("kick_bot", {})
    config = KickBotSettings.model_validate(saved)
    return {
        "stream_id": str(stream.id),
        "channel_name": stream.channel_name,
        "is_live": stream.is_live,
        **config.model_dump(),
    }


@router.put("/{stream_id}")
async def update_bot_settings(
    stream_id: UUID,
    body: KickBotSettings,
    current_user: StreamModeratorUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await _owned_kick_stream(stream_id, current_user.tenant_id, db)
    settings = dict(stream.settings or {})
    settings["kick_bot"] = body.model_dump()
    stream.settings = settings
    await db.commit()
    return {"saved": True, "stream_id": str(stream.id), **body.model_dump()}


@router.post("/{stream_id}/message")
async def send_bot_message(
    stream_id: UUID,
    body: KickBotMessage,
    current_user: StreamModeratorUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await _owned_kick_stream(stream_id, current_user.tenant_id, db)
    token = await get_stream_access_token(stream)
    if not token:
        raise ValidationError("El token de Kick expiró. Vuelve a conectar el canal.")
    try:
        await KickAPIClient(token).send_chat_message(stream.external_id, body.content)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise ValidationError(
                "Kick rechazó el mensaje. Vuelve a conectar Kick y acepta el permiso chat:write."
            ) from exc
        raise ValidationError(
            f"Kick no pudo enviar el mensaje (HTTP {exc.response.status_code})."
        ) from exc
    await db.commit()
    return {"sent": True, "channel_name": stream.channel_name}


async def process_chat_command(
    stream: Stream,
    *,
    sender_id: str,
    username: str,
    content: str,
) -> None:
    """Reply to enabled commands with a short per-command cooldown."""
    settings = (stream.settings or {}).get("kick_bot", {})
    if not settings.get("enabled") or sender_id == stream.external_id:
        return
    parts = content.strip().split(maxsplit=1)
    if not parts:
        return
    command_name = parts[0].lower()
    command = next(
        (
            item for item in settings.get("commands", [])
            if item.get("enabled", True) and item.get("command", "").lower() == command_name
        ),
        None,
    )
    if not command:
        return

    cooldown_key = f"{stream.id}:{command_name}"
    now = time.monotonic()
    if _command_cooldowns.get(cooldown_key, 0) > now:
        return
    _command_cooldowns[cooldown_key] = now + 5
    if len(_command_cooldowns) > 500:
        for key, expiry in list(_command_cooldowns.items()):
            if expiry <= now:
                _command_cooldowns.pop(key, None)

    response = str(command.get("response", ""))
    response = response.replace("{user}", username[:64]).replace(
        "{channel}", stream.channel_name[:64]
    )
    response = response.strip()[:500]
    if not response:
        return
    token = await get_stream_access_token(stream)
    if not token:
        return
    try:
        await KickAPIClient(token).send_chat_message(stream.external_id, response)
    except httpx.HTTPError:
        # Chat command failures must not make Kick retry already ingested events.
        return
