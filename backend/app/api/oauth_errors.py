"""Safe public messages for OAuth provider failures."""

import httpx


def oauth_exchange_public_message(provider: str, error: httpx.HTTPError) -> str:
    """Describe an OAuth failure without exposing response bodies or request URLs."""
    if isinstance(error, httpx.HTTPStatusError):
        return f"{provider} rechazó el intercambio de autorización (HTTP {error.response.status_code})."
    return f"No se pudo conectar con {provider} para completar la autorización. Intenta de nuevo."
