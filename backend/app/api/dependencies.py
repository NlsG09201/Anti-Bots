from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.logging import get_logger
from app.core.security import verify_token
from app.infrastructure.cache.redis_client import RedisCache, get_redis
from app.infrastructure.database.models import User, UserRole
from app.infrastructure.database.session import get_db

logger = get_logger(__name__)

ROLE_HIERARCHY = {
    UserRole.SUPER_ADMIN: 5,
    UserRole.ADMIN: 4,
    UserRole.ANALYST: 3,
    UserRole.STREAMER: 2,
    UserRole.VIEWER: 1,
}


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[Optional[str], Header()] = None,
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing or invalid authorization header")

    token = authorization[7:]
    payload = verify_token(token, "access")
    if not payload:
        raise AuthenticationError("Invalid or expired token")

    cache = RedisCache()
    if await cache.is_blacklisted(payload.get("jti", "")):
        raise AuthenticationError("Token has been revoked")

    try:
        user_id = UUID(str(payload.get("sub", "")))
    except (TypeError, ValueError):
        raise AuthenticationError("Invalid or expired token")

    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception("authenticated_user_lookup_failed")
        raise HTTPException(
            status_code=503,
            detail="El servicio de autenticación no está disponible temporalmente.",
        ) from exc
    if not user or not user.is_active:
        raise AuthenticationError("User not found or inactive")

    request.state.user = user
    request.state.tenant_id = payload.get("tenant_id")
    return user


def require_roles(*roles: UserRole):
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in roles:
            min_required = min(ROLE_HIERARCHY[r] for r in roles)
            if ROLE_HIERARCHY.get(current_user.role, 0) < min_required:
                raise AuthorizationError(f"Required role: {[r.value for r in roles]}")
        return current_user
    return role_checker


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN))]
AnalystUser = Annotated[User, Depends(require_roles(UserRole.ANALYST, UserRole.ADMIN, UserRole.SUPER_ADMIN))]
