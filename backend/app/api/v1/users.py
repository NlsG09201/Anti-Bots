from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser, CurrentUser
from app.core.exceptions import NotFoundError, ValidationError
from app.infrastructure.database.models import User, UserRole
from app.infrastructure.database.session import get_db

router = APIRouter(prefix="/users", tags=["User Management"])

ALLOWED_ROLES = [r.value for r in UserRole]


class UserListItem(BaseModel):
    id: UUID
    email: str
    username: str
    role: UserRole
    is_active: bool
    mfa_enabled: bool
    last_login: Optional[str] = None

    model_config = {"from_attributes": True}


class UpdateRoleRequest(BaseModel):
    role: UserRole = Field(..., description="New role for the user")


class UpdateStatusRequest(BaseModel):
    is_active: bool


@router.get("", response_model=List[UserListItem])
async def list_tenant_users(
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User)
        .where(User.tenant_id == current_user.tenant_id)
        .order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return [
        UserListItem(
            id=u.id,
            email=u.email,
            username=u.username,
            role=u.role,
            is_active=u.is_active,
            mfa_enabled=u.mfa_enabled,
            last_login=u.last_login.isoformat() if u.last_login else None,
        )
        for u in users
    ]


@router.patch("/{user_id}/role", response_model=UserListItem)
async def update_user_role(
    user_id: UUID,
    data: UpdateRoleRequest,
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise ValidationError("Cannot change your own role")

    if current_user.role != UserRole.SUPER_ADMIN and data.role in (
        UserRole.SUPER_ADMIN,
        UserRole.ADMIN,
    ):
        raise ValidationError("Only super_admin can assign admin roles")

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == current_user.tenant_id,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User")

    user.role = data.role
    await db.flush()

    return UserListItem(
        id=user.id,
        email=user.email,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        mfa_enabled=user.mfa_enabled,
        last_login=user.last_login.isoformat() if user.last_login else None,
    )


@router.patch("/{user_id}/status", response_model=UserListItem)
async def update_user_status(
    user_id: UUID,
    data: UpdateStatusRequest,
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise ValidationError("Cannot deactivate your own account")

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == current_user.tenant_id,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User")

    user.is_active = data.is_active
    await db.flush()

    return UserListItem(
        id=user.id,
        email=user.email,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        mfa_enabled=user.mfa_enabled,
        last_login=user.last_login.isoformat() if user.last_login else None,
    )
