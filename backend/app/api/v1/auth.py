import re
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.api.v1.schemas import (
    LoginRequest,
    MFALoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.mfa.service import MFAService
from app.core.config import get_settings
from app.core.cookies import (
    REFRESH_COOKIE,
    clear_auth_cookies,
    generate_csrf_token,
    set_csrf_cookie,
    set_refresh_cookie,
)
from app.core.exceptions import AuthenticationError, ValidationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_token,
)
from app.infrastructure.cache.redis_client import RedisCache
from app.infrastructure.database.models import RefreshToken, Tenant, User, UserRole
from app.infrastructure.database.session import get_db
from app.infrastructure.security.bruteforce import BruteForceProtection

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()
bruteforce = BruteForceProtection()


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:100] or "tenant"


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _auth_response(
    response: Response,
    access_token: str,
    refresh_token: str,
) -> TokenResponse:
    set_refresh_cookie(response, refresh_token)
    csrf = generate_csrf_token()
    set_csrf_cookie(response, csrf)
    return TokenResponse(
        access_token=access_token,
        refresh_token="",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/register", response_model=TokenResponse)
async def register(
    data: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise ValidationError("Email already registered")

    tenant = Tenant(name=data.tenant_name, slug=_slugify(data.tenant_name))
    db.add(tenant)
    await db.flush()

    user = User(
        tenant_id=tenant.id,
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        role=UserRole.ADMIN,
        is_verified=True,
    )
    db.add(user)
    await db.flush()

    access_token = create_access_token(str(user.id), str(tenant.id), user.role.value)
    refresh_token, jti, expires = create_refresh_token(str(user.id), str(tenant.id))
    db.add(RefreshToken(
        user_id=user.id,
        jti=jti,
        expires_at=expires,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.flush()

    return _auth_response(response, access_token, refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    ip = _client_ip(request)
    identifier = f"{data.email}:{ip}"
    await bruteforce.check_and_raise(identifier)

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.hashed_password):
        await bruteforce.record_failure(identifier)
        raise AuthenticationError("Invalid email or password")
    if not user.is_active:
        raise AuthenticationError("Account is disabled")

    await bruteforce.clear_failures(identifier)

    if user.mfa_enabled and user.mfa_secret:
        mfa_token = secrets.token_urlsafe(32)
        cache = RedisCache(prefix="mfa")
        await cache.set(
            f"pending:{mfa_token}",
            {"user_id": str(user.id)},
            ttl=300,
        )
        return TokenResponse(
            mfa_required=True,
            mfa_token=mfa_token,
            expires_in=300,
        )

    user.last_login = datetime.now(timezone.utc)
    access_token = create_access_token(str(user.id), str(user.tenant_id), user.role.value)
    refresh_token, jti, expires = create_refresh_token(str(user.id), str(user.tenant_id))

    db.add(RefreshToken(
        user_id=user.id,
        jti=jti,
        expires_at=expires,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
    ))
    await db.flush()

    return _auth_response(response, access_token, refresh_token)


@router.post("/mfa/verify", response_model=TokenResponse)
async def verify_mfa_login(
    data: MFALoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    cache = RedisCache(prefix="mfa")
    pending = await cache.get(f"pending:{data.mfa_token}")
    if not pending:
        raise AuthenticationError("MFA session expired")

    result = await db.execute(select(User).where(User.id == UUID(pending["user_id"])))
    user = result.scalar_one_or_none()
    if not user or not user.mfa_secret:
        raise AuthenticationError("Invalid MFA session")

    if not MFAService.verify_code(user.mfa_secret, data.code):
        raise AuthenticationError("Invalid MFA code")

    await cache.delete(f"pending:{data.mfa_token}")
    user.last_login = datetime.now(timezone.utc)

    ip = _client_ip(request)
    access_token = create_access_token(str(user.id), str(user.tenant_id), user.role.value)
    refresh_token, jti, expires = create_refresh_token(str(user.id), str(user.tenant_id))
    db.add(RefreshToken(
        user_id=user.id,
        jti=jti,
        expires_at=expires,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
    ))
    await db.flush()

    return _auth_response(response, access_token, refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token_endpoint(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise AuthenticationError("Refresh token missing")

    payload = verify_token(token, "refresh")
    if not payload:
        clear_auth_cookies(response)
        raise AuthenticationError("Invalid refresh token")

    cache = RedisCache()
    if await cache.is_blacklisted(payload.get("jti", "")):
        clear_auth_cookies(response)
        raise AuthenticationError("Token revoked")

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.jti == payload["jti"],
            RefreshToken.is_revoked == False,
        )
    )
    stored = result.scalar_one_or_none()
    if not stored or _as_utc(stored.expires_at) < _utc_now():
        clear_auth_cookies(response)
        raise AuthenticationError("Refresh token expired")

    result = await db.execute(select(User).where(User.id == UUID(payload["sub"])))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        clear_auth_cookies(response)
        raise AuthenticationError("User not found")

    stored.is_revoked = True
    access_token = create_access_token(str(user.id), str(user.tenant_id), user.role.value)
    new_refresh, new_jti, expires = create_refresh_token(str(user.id), str(user.tenant_id))
    db.add(RefreshToken(user_id=user.id, jti=new_jti, expires_at=expires))
    await db.flush()

    return _auth_response(response, access_token, new_refresh)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    token = request.cookies.get(REFRESH_COOKIE)
    cache = RedisCache()

    if token:
        payload = verify_token(token, "refresh")
        if payload and payload.get("jti"):
            jti = payload["jti"]
            exp = payload.get("exp")
            if exp:
                ttl = max(int(exp - datetime.now(timezone.utc).timestamp()), 60)
                await cache.blacklist_token(jti, ttl)
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.jti == jti)
                .values(is_revoked=True)
            )

    clear_auth_cookies(response)
    return {"message": "Logged out successfully"}


@router.get("/csrf")
async def get_csrf_token(response: Response):
    token = generate_csrf_token()
    set_csrf_cookie(response, token)
    return {"csrf_token": token}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser):
    return current_user
