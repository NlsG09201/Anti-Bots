from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, AdminUser
from app.core.exceptions import AuthenticationError, ValidationError
from app.infrastructure.database.session import get_db
from app.services.mfa.service import MFAService

router = APIRouter(prefix="/auth/mfa", tags=["MFA"])


class MFASetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    qr_code_base64: str


class MFAVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class MFAStatusResponse(BaseModel):
    enabled: bool
    required_for_role: bool


@router.get("/status", response_model=MFAStatusResponse)
async def mfa_status(current_user: CurrentUser):
    return MFAStatusResponse(
        enabled=current_user.mfa_enabled,
        required_for_role=MFAService.requires_mfa(current_user.role.value),
    )


@router.post("/setup", response_model=MFASetupResponse)
async def setup_mfa(current_user: AdminUser, db: AsyncSession = Depends(get_db)):
    if current_user.mfa_enabled:
        raise ValidationError("MFA is already enabled")

    secret = MFAService.generate_secret()
    uri = MFAService.get_provisioning_uri(secret, current_user.email)
    qr = MFAService.qr_code_base64(uri)

    current_user.mfa_secret = MFAService.encrypt_secret(secret)
    await db.flush()

    return MFASetupResponse(
        secret=secret,
        provisioning_uri=uri,
        qr_code_base64=qr,
    )


@router.post("/enable")
async def enable_mfa(
    data: MFAVerifyRequest,
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
):
    if not current_user.mfa_secret:
        raise ValidationError("Run MFA setup first")

    if not MFAService.verify_code(current_user.mfa_secret, data.code):
        raise AuthenticationError("Invalid MFA code")

    current_user.mfa_enabled = True
    await db.flush()
    return {"enabled": True}


@router.post("/disable")
async def disable_mfa(
    data: MFAVerifyRequest,
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
):
    if not current_user.mfa_enabled:
        return {"enabled": False}

    if not MFAService.verify_code(current_user.mfa_secret or "", data.code):
        raise AuthenticationError("Invalid MFA code")

    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    await db.flush()
    return {"enabled": False}
