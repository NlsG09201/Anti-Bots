from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.infrastructure.database.models import (
    AlertSeverity,
    AttackType,
    MitigationAction,
    Platform,
    UserRole,
)


class TokenResponse(BaseModel):
    access_token: str = ""
    refresh_token: str = ""
    token_type: str = "bearer"
    expires_in: int = 0
    mfa_required: bool = False
    mfa_token: str = ""


class MFALoginRequest(BaseModel):
    mfa_token: str
    code: str = Field(..., min_length=6, max_length=6)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=12)
    tenant_name: str = Field(..., min_length=2, max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain digit")
        return v


class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    role: UserRole
    is_active: bool
    tenant_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class StreamCreate(BaseModel):
    platform: Platform
    external_id: str
    channel_name: str


class StreamResponse(BaseModel):
    id: UUID
    platform: Platform
    external_id: str
    channel_name: str
    is_live: bool
    viewer_count: int
    created_at: datetime
    monitor_mode: bool = False
    is_owned: bool = True
    login: Optional[str] = None

    model_config = {"from_attributes": True}


class StreamWatchRequest(BaseModel):
    login: str = Field(..., min_length=2, max_length=50)
    platform: Platform = Platform.TWITCH


class TimelinePoint(BaseModel):
    time: str
    attacks: int
    mitigated: int


class HeatmapPoint(BaseModel):
    hour: str
    risk: int
    events: int = 0


class DashboardCharts(BaseModel):
    timeline: List[TimelinePoint]
    heatmap: List[HeatmapPoint]
    updated_at: str


class AIInsightResponse(BaseModel):
    summary: str
    severity_assessment: str
    recommended_action: str
    recommendation: str
    confidence: float
    source: str


class FingerprintSubmit(BaseModel):
    canvas_hash: Optional[str] = None
    webgl_hash: Optional[str] = None
    audio_hash: Optional[str] = None
    screen_resolution: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    platform: Optional[str] = None
    plugins: Optional[List[str]] = None
    fonts: Optional[List[str]] = None
    webdriver: bool = False
    selenium: bool = False
    puppeteer: bool = False
    playwright: bool = False
    user_agent: Optional[str] = None
    languages: Optional[List[str]] = None


class FingerprintResponse(BaseModel):
    hash: str
    risk_score: float
    is_headless: bool
    is_blocked: bool
    automation_flags: List[str]


class EventIngest(BaseModel):
    event_type: str
    platform_user_id: Optional[str] = None
    platform_username: Optional[str] = None
    ip_address: Optional[str] = None
    fingerprint_hash: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AttackResponse(BaseModel):
    id: UUID
    attack_type: AttackType
    severity: AlertSeverity
    status: str
    risk_score: float
    confidence: float
    correlation_id: str
    source_ips: List[str]
    fingerprints: List[str]
    mitigation_action: MitigationAction
    evidence: Dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertResponse(BaseModel):
    id: UUID
    title: str
    message: str
    severity: AlertSeverity
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BanCreate(BaseModel):
    target_type: str = Field(..., pattern="^(user|ip|fingerprint|asn)$")
    target_value: str
    reason: str
    ban_type: str = "ban"
    duration_hours: Optional[int] = None


class BanResponse(BaseModel):
    id: UUID
    target_type: str
    target_value: str
    ban_type: str
    reason: str
    is_active: bool
    expires_at: Optional[datetime]
    is_automated: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DashboardStats(BaseModel):
    active_attacks: int
    total_alerts: int
    blocked_ips: int
    suspected_bots: int
    live_viewers: int
    risk_score_avg: float
    attacks_last_24h: int
    mitigations_applied: int


class ViewerSessionResponse(BaseModel):
    id: UUID
    platform_user_id: Optional[str] = None
    platform_username: Optional[str]
    ip_address: str
    fingerprint_hash: Optional[str]
    risk_score: float
    is_suspected_bot: bool
    is_active: bool
    watch_duration_seconds: int
    chat_messages: int = 0
    behavior_metrics: Dict[str, Any] = Field(default_factory=dict)
    joined_at: datetime

    model_config = {"from_attributes": True}


class BlockViewerRequest(BaseModel):
    reason: str = "Actividad sospechosa detectada por StreamShield"
    duration_hours: Optional[int] = 24
    apply_twitch_ban: bool = True


class MitigationRequest(BaseModel):
    attack_id: UUID
    action: Optional[MitigationAction] = None
    targets: List[Dict[str, str]]
    duration_hours: Optional[int] = None
