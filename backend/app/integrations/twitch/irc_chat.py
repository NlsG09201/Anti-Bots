import asyncio
import random
import re
from dataclasses import dataclass, field
from typing import Dict, List

from app.core.logging import get_logger
from app.integrations.twitch.chat_filters import is_valid_chatter_username

logger = get_logger(__name__)

JOIN_RE = re.compile(
    r":([^!\s]+)!.* JOIN #(\w+)",
    re.IGNORECASE,
)
PART_RE = re.compile(
    r":([^!\s]+)!.* PART #(\w+)",
    re.IGNORECASE,
)
PRIVMSG_RE = re.compile(
    r":([^!\s]+)!.* PRIVMSG #(\w+)",
    re.IGNORECASE,
)
# Solo RPL_NAMREPLY (353), nunca 366 "End of /NAMES list"
NAMES_REPLY_RE = re.compile(
    r"^:[^ ]+ 353 [^ ]+ #(\w+) :(.*)$",
    re.IGNORECASE,
)


@dataclass
class ChatPresenceSnapshot:
    channel: str
    users: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def record_join(self, username: str) -> None:
        if not is_valid_chatter_username(username):
            return
        key = username.lower()
        entry = self.users.setdefault(key, {"joins": 0, "messages": 0, "username": username})
        entry["joins"] += 1

    def record_message(self, username: str) -> None:
        if not is_valid_chatter_username(username):
            return
        key = username.lower()
        entry = self.users.setdefault(key, {"joins": 0, "messages": 0, "username": username})
        entry["messages"] += 1

    def record_names(self, names_blob: str) -> None:
        for name in names_blob.split():
            if name and name[0] != "@":
                self.record_join(name.lstrip("@"))


async def collect_chat_presence(
    channel_login: str,
    duration_seconds: float = 55.0,
) -> ChatPresenceSnapshot:
    """
    Lista usuarios en el chat via IRC (membership + NAMES).
    No incluye viewers que no estan en chat.
    """
    channel = channel_login.lower().lstrip("#")
    snapshot = ChatPresenceSnapshot(channel=channel)
    nick = f"justinfan{random.randint(10000, 99999)}"
    reader = writer = None
    cap_ready = False
    joined = False

    try:
        import ssl

        ctx = ssl.create_default_context()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("irc.chat.twitch.tv", 6697, ssl=ctx),
            timeout=15.0,
        )

        async def send(line: str) -> None:
            writer.write(f"{line}\r\n".encode("utf-8"))
            await writer.drain()

        await send("CAP REQ :twitch.tv/membership twitch.tv/tags")
        await send("PASS SCHMOOPIIE")
        await send(f"NICK {nick}")

        deadline = asyncio.get_event_loop().time() + duration_seconds
        while asyncio.get_event_loop().time() < deadline:
            try:
                raw = await asyncio.wait_for(reader.readline(), timeout=4.0)
            except asyncio.TimeoutError:
                if cap_ready and not joined:
                    await send(f"JOIN #{channel}")
                    joined = True
                continue
            if not raw:
                break
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            if line.startswith("PING"):
                await send("PONG :tmi.twitch.tv")
                continue

            upper = line.upper()
            if "CAP * ACK" in line or ":twitch.tv/membership" in line.lower():
                cap_ready = True
                if not joined:
                    await send(f"JOIN #{channel}")
                    joined = True
                continue

            if " 353 " in f" {line} ":
                names_m = NAMES_REPLY_RE.match(line)
                if names_m and names_m.group(1).lower() == channel:
                    snapshot.record_names(names_m.group(2))
                continue

            join_m = JOIN_RE.search(line)
            if join_m and join_m.group(2).lower() == channel:
                joiner = join_m.group(1)
                if joiner.lower() != nick.lower():
                    snapshot.record_join(joiner)
                continue

            part_m = PART_RE.search(line)
            if part_m and part_m.group(2).lower() == channel:
                snapshot.users.pop(part_m.group(1).lower(), None)
                continue

            msg_m = PRIVMSG_RE.search(line)
            if msg_m and msg_m.group(2).lower() == channel:
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

    logger.info("irc_snapshot_done", channel=channel, users=len(snapshot.users))
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
