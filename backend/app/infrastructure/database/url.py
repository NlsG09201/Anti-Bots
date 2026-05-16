import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def prepare_asyncpg_url(database_url: str) -> tuple[str, dict[str, Any]]:
    """Neon usa sslmode=require; asyncpg necesita ssl=True en connect_args."""
    if not database_url.startswith("postgresql"):
        return database_url, {}

    parsed = urlparse(database_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    connect_args: dict[str, Any] = {}

    sslmode = query.pop("sslmode", None)
    if sslmode in ("require", "verify-full", "verify-ca"):
        connect_args["ssl"] = True
    channel_binding = query.pop("channel_binding", None)
    if channel_binding:
        pass  # asyncpg no usa este parámetro en la URL

    clean_query = urlencode(query)
    clean_url = urlunparse(parsed._replace(query=clean_query))
    clean_url = re.sub(r"\?$", "", clean_url)

    return clean_url, connect_args
