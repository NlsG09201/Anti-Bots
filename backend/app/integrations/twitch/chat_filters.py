"""Filtros para listar solo usuarios humanos reales en el chat de Twitch."""

import re

# Bots de moderacion / alertas habituales en canales (no son viewers a vigilar)
TWITCH_CHAT_BOTS = frozenset(
    {
        "jtv",
        "tmi",
        "nightbot",
        "moobot",
        "streamelements",
        "streamlabs",
        "fossabot",
        "wizebot",
        "botrix",
        "stay_hydrated_bot",
        "pretzelrocks",
        "soundalerts",
        "streampilot",
        "coebot",
        "phantombot",
        "vivbot",
        "deepbot",
        "ankhbot",
        "xanbot",
        "scorpbot",
        "revlobot",
        "pohbot",
        "moobotalpha",
        "commanderroot",
        "marbles",
    }
)

CHAT_PRESENCE_SOURCES = frozenset({"irc", "helix", "helix+irc"})
TWITCH_LOGIN_RE = re.compile(r"^[a-zA-Z0-9_]{2,25}$")


def is_valid_chatter_username(username: str) -> bool:
    if not username or not isinstance(username, str):
        return False
    name = username.strip().lstrip("@")
    if not name:
        return False
    lower = name.lower()
    if lower in TWITCH_CHAT_BOTS:
        return False
    if lower.startswith("justinfan"):
        return False
    if not TWITCH_LOGIN_RE.match(name):
        return False
    return True
