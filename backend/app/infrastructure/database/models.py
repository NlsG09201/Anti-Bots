import enum
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.infrastructure.database.types import JsonType, StringArrayType
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin, UUIDMixin


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    ANALYST = "analyst"
    STREAMER = "streamer"
    VIEWER = "viewer"


class Platform(str, enum.Enum):
    TWITCH = "twitch"
    KICK = "kick"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"


class AttackType(str, enum.Enum):
    VIEWBOT = "viewbot"
    FOLLOWBOT = "followbot"
    CHAT_RAID = "chat_raid"
    SPAM = "spam"
    FAKE_ENGAGEMENT = "fake_engagement"
    COORDINATED = "coordinated"
    DISTRIBUTED = "distributed"


class MitigationAction(str, enum.Enum):
    NONE = "none"
    QUARANTINE = "quarantine"
    SHADOW_BAN = "shadow_ban"
    TIMEOUT = "timeout"
    BAN = "ban"
    MUTE = "mute"
    RATE_LIMIT = "rate_limit"
    CAPTCHA = "captcha"
    JS_CHALLENGE = "js_challenge"


class AlertSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Tenant(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    settings: Mapped[dict] = mapped_column(JsonType, default=dict)

    users: Mapped[List["User"]] = relationship(back_populates="tenant")
    streams: Mapped[List["Stream"]] = relationship(back_populates="tenant")


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),
        Index("ix_users_tenant_role", "tenant_id", "role"),
    )

    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.STREAMER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    mfa_secret: Mapped[Optional[str]] = mapped_column(String(255))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    tenant: Mapped["Tenant"] = relationship(back_populates="users")
    streams: Mapped[List["Stream"]] = relationship(back_populates="owner")
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(back_populates="user")


class RefreshToken(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(512))

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")


class TokenBlacklist(UUIDMixin, Base):
    __tablename__ = "token_blacklist"

    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255))


class Stream(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "streams"
    __table_args__ = (
        Index("ix_streams_platform_external", "platform", "external_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    owner_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    platform: Mapped[Platform] = mapped_column(Enum(Platform), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    viewer_count: Mapped[int] = mapped_column(Integer, default=0)
    oauth_token_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    settings: Mapped[dict] = mapped_column(JsonType, default=dict)

    tenant: Mapped["Tenant"] = relationship(back_populates="streams")
    owner: Mapped["User"] = relationship(back_populates="streams")
    events: Mapped[List["StreamEvent"]] = relationship(back_populates="stream")
    attacks: Mapped[List["Attack"]] = relationship(back_populates="stream")


class StreamEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "stream_events"
    __table_args__ = (
        Index("ix_stream_events_stream_type", "stream_id", "event_type"),
        Index("ix_stream_events_correlation", "correlation_id"),
        Index("ix_stream_events_created", "created_at"),
    )

    stream_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("streams.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    platform_user_id: Mapped[Optional[str]] = mapped_column(String(255))
    platform_username: Mapped[Optional[str]] = mapped_column(String(255))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), index=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512))
    fingerprint_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    asn: Mapped[Optional[int]] = mapped_column(Integer)
    country_code: Mapped[Optional[str]] = mapped_column(String(2))
    is_proxy: Mapped[bool] = mapped_column(Boolean, default=False)
    is_vpn: Mapped[bool] = mapped_column(Boolean, default=False)
    is_tor: Mapped[bool] = mapped_column(Boolean, default=False)
    is_datacenter: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    event_metadata: Mapped[dict] = mapped_column("metadata", JsonType, default=dict)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64))
    raw_payload: Mapped[Optional[dict]] = mapped_column(JsonType)

    stream: Mapped["Stream"] = relationship(back_populates="events")


class Fingerprint(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "fingerprints"
    __table_args__ = (
        Index("ix_fingerprints_hash", "hash"),
        Index("ix_fingerprints_risk", "risk_score"),
    )

    hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    canvas_hash: Mapped[Optional[str]] = mapped_column(String(64))
    webgl_hash: Mapped[Optional[str]] = mapped_column(String(64))
    audio_hash: Mapped[Optional[str]] = mapped_column(String(64))
    screen_resolution: Mapped[Optional[str]] = mapped_column(String(20))
    timezone: Mapped[Optional[str]] = mapped_column(String(50))
    language: Mapped[Optional[str]] = mapped_column(String(20))
    platform: Mapped[Optional[str]] = mapped_column(String(50))
    plugins: Mapped[Optional[list]] = mapped_column(StringArrayType)
    fonts: Mapped[Optional[list]] = mapped_column(StringArrayType)
    is_headless: Mapped[bool] = mapped_column(Boolean, default=False)
    is_selenium: Mapped[bool] = mapped_column(Boolean, default=False)
    is_puppeteer: Mapped[bool] = mapped_column(Boolean, default=False)
    is_playwright: Mapped[bool] = mapped_column(Boolean, default=False)
    automation_flags: Mapped[list] = mapped_column(StringArrayType, default=list)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    fp_metadata: Mapped[dict] = mapped_column("metadata", JsonType, default=dict)


class IPReputation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "ip_reputations"
    __table_args__ = (
        Index("ix_ip_reputations_address", "ip_address"),
        Index("ix_ip_reputations_score", "reputation_score"),
    )

    ip_address: Mapped[str] = mapped_column(String(45), unique=True, nullable=False)
    reputation_score: Mapped[float] = mapped_column(Float, default=50.0)
    abuse_reports: Mapped[int] = mapped_column(Integer, default=0)
    asn: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    asn_org: Mapped[Optional[str]] = mapped_column(String(255))
    country_code: Mapped[Optional[str]] = mapped_column(String(2))
    is_proxy: Mapped[bool] = mapped_column(Boolean, default=False)
    is_vpn: Mapped[bool] = mapped_column(Boolean, default=False)
    is_tor: Mapped[bool] = mapped_column(Boolean, default=False)
    is_datacenter: Mapped[bool] = mapped_column(Boolean, default=False)
    is_hosting: Mapped[bool] = mapped_column(Boolean, default=False)
    threat_categories: Mapped[list] = mapped_column(StringArrayType, default=list)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_metadata: Mapped[dict] = mapped_column("metadata", JsonType, default=dict)


class Attack(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "attacks"
    __table_args__ = (
        Index("ix_attacks_stream_status", "stream_id", "status"),
        Index("ix_attacks_type_severity", "attack_type", "severity"),
    )

    stream_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("streams.id"), nullable=False)
    attack_type: Mapped[AttackType] = mapped_column(Enum(AttackType), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity), default=AlertSeverity.MEDIUM)
    status: Mapped[str] = mapped_column(String(20), default="active")
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source_ips: Mapped[list] = mapped_column(StringArrayType, default=list)
    fingerprints: Mapped[list] = mapped_column(StringArrayType, default=list)
    affected_users: Mapped[int] = mapped_column(Integer, default=0)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    evidence: Mapped[dict] = mapped_column(JsonType, default=dict)
    mitigation_action: Mapped[MitigationAction] = mapped_column(
        Enum(MitigationAction), default=MitigationAction.NONE
    )
    mitigated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    stream: Mapped["Stream"] = relationship(back_populates="attacks")
    alerts: Mapped[List["Alert"]] = relationship(back_populates="attack")


class Alert(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_tenant_status", "tenant_id", "status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    attack_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("attacks.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open")
    source: Mapped[str] = mapped_column(String(50), default="detection_engine")
    alert_metadata: Mapped[dict] = mapped_column("metadata", JsonType, default=dict)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True))

    attack: Mapped[Optional["Attack"]] = relationship(back_populates="alerts")


class Ban(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "bans"
    __table_args__ = (
        Index("ix_bans_stream_target", "stream_id", "target_type", "target_value"),
    )

    stream_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("streams.id"), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_value: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    ban_type: Mapped[str] = mapped_column(String(20), default="ban")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True))
    is_automated: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence: Mapped[dict] = mapped_column(JsonType, default=dict)


class AuditLog(UUIDMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_logs_action", "action"),
    )

    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(512))
    details: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )


class ViewerSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "viewer_sessions"
    __table_args__ = (
        Index("ix_viewer_sessions_stream", "stream_id", "is_active"),
        Index("ix_viewer_sessions_fingerprint", "fingerprint_hash"),
    )

    stream_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("streams.id"), nullable=False)
    platform_user_id: Mapped[Optional[str]] = mapped_column(String(255))
    platform_username: Mapped[Optional[str]] = mapped_column(String(255))
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    fingerprint_hash: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(512))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    watch_duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    chat_messages: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_suspected_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    behavior_metrics: Mapped[dict] = mapped_column(JsonType, default=dict)


class IncidentStatus(str, enum.Enum):
    ACTIVE = "active"
    MITIGATED = "mitigated"
    ESCALATED = "escalated"
    RESOLVED = "resolved"


class Incident(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_stream_status", "stream_id", "status"),
        Index("ix_incidents_correlation", "correlation_id"),
        Index("ix_incidents_threat_actor", "threat_actor_id"),
    )

    stream_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("streams.id"), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[IncidentStatus] = mapped_column(Enum(IncidentStatus), default=IncidentStatus.ACTIVE)
    severity: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    threat_actor_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("threat_actors.id"))
    attack_ids: Mapped[list] = mapped_column(StringArrayType, default=list)
    alert_ids: Mapped[list] = mapped_column(StringArrayType, default=list)
    related_ips: Mapped[list] = mapped_column(StringArrayType, default=list)
    related_fingerprints: Mapped[list] = mapped_column(StringArrayType, default=list)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Playbook(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "playbooks"
    __table_args__ = (
        Index("ix_playbooks_tenant_enabled", "tenant_id", "enabled"),
    )

    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    conditions: Mapped[dict] = mapped_column(JsonType, default=dict)
    actions: Mapped[list] = mapped_column(JsonType, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    execution_count: Mapped[int] = mapped_column(Integer, default=0)
    last_executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    executions: Mapped[List["PlaybookExecution"]] = relationship(back_populates="playbook")


class PlaybookExecution(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "playbook_executions"
    __table_args__ = (
        Index("ix_playbook_executions_playbook_status", "playbook_id", "status"),
        Index("ix_playbook_executions_incident", "incident_id"),
    )

    playbook_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("playbooks.id"), nullable=False)
    incident_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("incidents.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    executed_actions: Mapped[list] = mapped_column(JsonType, default=list)
    failed_actions: Mapped[list] = mapped_column(JsonType, default=list)
    execution_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    playbook: Mapped["Playbook"] = relationship(back_populates="executions")


class ThreatActor(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "threat_actors"
    __table_args__ = (
        Index("ix_threat_actors_tenant_confidence", "tenant_id", "confidence"),
    )

    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tactics: Mapped[list] = mapped_column(StringArrayType, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    incident_count: Mapped[int] = mapped_column(Integer, default=0)
    target_count: Mapped[int] = mapped_column(Integer, default=0)
    common_asns: Mapped[list] = mapped_column(StringArrayType, default=list)
    common_fingerprints: Mapped[list] = mapped_column(StringArrayType, default=list)
    actor_metadata: Mapped[dict] = mapped_column("metadata", JsonType, default=dict)


class ThreatAnalyticsDaily(UUIDMixin, Base):
    __tablename__ = "threat_analytics_daily"
    __table_args__ = (
        Index("ix_threat_analytics_tenant_date", "tenant_id", "date"),
        UniqueConstraint("tenant_id", "date", name="uq_threat_analytics_tenant_date"),
    )

    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    date: Mapped[str] = mapped_column(String(10), nullable=False)
    attack_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_ips: Mapped[int] = mapped_column(Integer, default=0)
    blocked_fingerprints: Mapped[int] = mapped_column(Integer, default=0)
    top_asns: Mapped[list] = mapped_column(JsonType, default=list)
    top_attack_types: Mapped[list] = mapped_column(JsonType, default=list)
    avg_risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    max_risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
