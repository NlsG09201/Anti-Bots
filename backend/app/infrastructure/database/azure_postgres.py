"""Azure Database for PostgreSQL connection support."""

import asyncio
from typing import Any

import asyncpg
from sqlalchemy.engine import URL, make_url

from app.infrastructure.database.url import prepare_asyncpg_url

AZURE_POSTGRES_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"


def create_passwordless_url(database_url: str, drivername: str | None = None) -> URL:
    parsed_url = make_url(database_url)
    return URL.create(
        drivername=drivername or parsed_url.drivername,
        username=parsed_url.username,
        host=parsed_url.host,
        port=parsed_url.port,
        database=parsed_url.database,
        query=dict(parsed_url.query),
    )


def create_managed_identity_connector(database_url: str, credential: Any):
    """Create an asyncpg connector that obtains a fresh Entra token per connection."""
    original_url = make_url(database_url)
    if original_url.drivername != "postgresql+asyncpg":
        raise ValueError("Managed identity authentication requires a PostgreSQL asyncpg URL")
    if not original_url.host or not original_url.username or not original_url.database:
        raise ValueError(
            "Managed identity authentication requires a PostgreSQL URL with host, user, and database"
        )

    asyncpg_url, _ = prepare_asyncpg_url(database_url)
    parsed_url = make_url(asyncpg_url)

    # asyncpg accepts a plain PostgreSQL DSN; omit any URL password because the
    # short-lived Entra access token is supplied separately for each connection.
    dsn = create_passwordless_url(
        asyncpg_url,
        drivername="postgresql",
    ).render_as_string(hide_password=False)

    async def connect():
        token = await asyncio.to_thread(credential.get_token, AZURE_POSTGRES_SCOPE)
        return await asyncpg.connect(
            dsn=dsn,
            password=token.token,
            ssl=True,
        )

    return connect
