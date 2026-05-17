import asyncio
import random
import re
from dataclasses import dataclass, field
from typing import Dict, List, Set

from app.core.logging import get_logger

logger = get_logger(__name__)

JOIN_RE = re.compile(
    r":([^!]+)!([^@]+)@.* JOIN #(\w+)",
    re.IGNORECASE,
)
PART_RE = re.compile(
    r":([^!]+)!([^@]+)@.* PART #(\w+)",
    re.IGNORECASE,
)
PRIVMSG_RE = re.compile(
    r":([^!]+)!([^@]+)@.* PRIVMSG #(\w+)",
    re.IGNORECASE,
)


@dataclass
class ChatPresenceSnapshot:
    channel: str
    users: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def record_join(self, username: str) -> None:
        key = username.lower()
        entry = self.users.setdefault(key, {"joins": 0, "messages": 0, "username": username})
        entry["joins"] += 1

    def record_message(self, username: str) -> None:
        key = username.lower()
        entry = self.users.setdefault(key, {"joins": 0, "messages": 0, "username": username})
        entry["messages"] += 1

    def active_usernames(self) -> List[str]:
        return [v["username"] for v in self.users.values()]


async def collect_chat_presence(
    channel_login: str,
    duration_seconds: float = 35.0,
) -> ChatPresenceSnapshot:
    """
    Lee presencia en chat publico de Twitch (IRC anonimo).
    No lista todos los viewers de la stream — solo quienes estan o pasan por el chat.
    """
    channel = channel_login.lower().lstrip("#")
    snapshot = ChatPresenceSnapshot(channel=channel)
    nick = f"justinfan{random.randint(10000, 99999)}"
    reader = writer = None

    try:
        import ssl

        ctx = ssl.create_default_context()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("irc.chat.twitch.tv", 6697, ssl=ctx),
            timeout=12.0,
        )

        async def send(line: str) -> None:
            writer.write(f"{line}\r\n".encode("utf-8"))
            await writer.drain()

        await send("CAP REQ :twitch.tv/membership")
        await send(f"PASS SCHMOOPIIE")
        await send(f"NICK {nick}")
        await send(f"JOIN #{channel}")

        deadline = asyncio.get_event_loop().time() + duration_seconds
        while asyncio.get_event_loop().time() < deadline:
            try:
                raw = await asyncio.wait_for(reader.readline(), timeout=3.0)
            except asyncio.TimeoutError:
                continue
            if not raw:
                break
            line = raw.decode("utf-8", errors="ignore").strip()
            if line.startswith("PING"):
                await send("PONG :tmi.twitch.tv")
                continue

            join_m = JOIN_RE.match(line)
            if join_m:
                snapshot.record_join(join_m.group(1))
                continue

            part_m = PART_RE.match(line)
            if part_m:
                snapshot.users.pop(part_m.group(1).lower(), None)
                continue

            msg_m = PRIVMSG_RE.match(line)
            if msg_m:
                snapshot.record_message(msg_m.group(1))

    except Exception as exc:
        logger.warning("irc_snapshot_failed", channel=channel, error=str(exc))
    finally:
        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    return snapshot


def score_username_risk(username: str, joins: int, messages: int) -> float:
    """Heuristica para cuentas sospechosas en chat."""
    score = 0.0
    name = username.lower()
    if len(name) >= 8 and name.isalnum() and any(c.isdigit() for c in name):
        score += 25
    if re.match(r"^[a-z]{2,4}\d{4,8}$", name):
        score += 30
    if joins >= 3:
        score += min(joins * 8, 40)
    if messages == 0 and joins >= 1:
        score += 15
    if name.count("_") >= 3:
        score += 10
    return min(score, 100.0)
