"""Alert domain models."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, JSON, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.domain.base import Base


class AlertSeverityEnum(str, Enum):
    """Alert severity levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AlertTypeEnum(str, Enum):
    """Alert types."""
    VIEWBOT_ATTACK = "VIEWBOT_ATTACK"
    FOLLOWBOT_ATTACK = "FOLLOWBOT_ATTACK"
    CHAT_SPAM = "CHAT_SPAM"
    MASS_JOIN = "MASS_JOIN"
    COORDINATED_ATTACK = "COORDINATED_ATTACK"
    VPN_SURGE = "VPN_SURGE"
    PROXY_SURGE = "PROXY_SURGE"
    DATACENTER_SURGE = "DATACENTER_SURGE"
    SUSPICIOUS_PATTERN = "SUSPICIOUS_PATTERN"
    RAID_ATTACK = "RAID_ATTACK"


class Alert(Base):
    """Alert model for persistent storage."""

    __tablename__ = "alerts"

    # Primary key
    id = Column(PG_UUID(as_uuid=True), primary_key=True)

    # Foreign keys
    stream_id = Column(String(255), nullable=False, index=True)
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Alert details
    alert_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=False)

    # Alert data (JSON)
    data = Column(JSON, nullable=True, default={})

    # Status
    dismissed = Column(Boolean, nullable=False, default=False)
    acknowledged = Column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    dismissed_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)

    # Additional metadata
    source = Column(String(50), nullable=True)  # e.g., "threat_engine", "api"
    tags = Column(JSON, nullable=True, default={})

    # Indexes
    __table_args__ = (
        Index("ix_alerts_stream_id_created_at", "stream_id", "created_at"),
        Index("ix_alerts_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_alerts_severity", "severity"),
        Index("ix_alerts_dismissed", "dismissed"),
        Index("ix_alerts_alert_type", "alert_type"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            "id": str(self.id),
            "stream_id": self.stream_id,
            "tenant_id": str(self.tenant_id),
            "type": self.alert_type,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "data": self.data or {},
            "dismissed": self.dismissed,
            "acknowledged": self.acknowledged,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "dismissed_at": self.dismissed_at.isoformat() if self.dismissed_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "source": self.source,
            "tags": self.tags or {},
        }


class AlertHistory(Base):
    """Audit trail for alert status changes."""

    __tablename__ = "alert_history"

    # Primary key
    id = Column(PG_UUID(as_uuid=True), primary_key=True)

    # Foreign key
    alert_id = Column(PG_UUID(as_uuid=True), ForeignKey("alerts.id"), nullable=False, index=True)

    # Change tracking
    action = Column(String(50), nullable=False)  # created, dismissed, acknowledged, resolved
    changed_by = Column(String(255), nullable=True)  # user_id or system
    reason = Column(String(500), nullable=True)
    metadata = Column(JSON, nullable=True, default={})

    # Timestamp
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("ix_alert_history_alert_id", "alert_id"),
        Index("ix_alert_history_created_at", "created_at"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "alert_id": str(self.alert_id),
            "action": self.action,
            "changed_by": self.changed_by,
            "reason": self.reason,
            "metadata": self.metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AlertRule(Base):
    """Alert rules for automated generation."""

    __tablename__ = "alert_rules"

    # Primary key
    id = Column(PG_UUID(as_uuid=True), primary_key=True)

    # Organization
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Rule details
    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    alert_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)

    # Conditions (JSON)
    conditions = Column(JSON, nullable=False, default={})
    # Example: {"threat_score": {"operator": "gte", "value": 0.7}, "attack_types": ["VIEWBOT_ATTACK"]}

    # Actions (JSON)
    actions = Column(JSON, nullable=False, default={})
    # Example: {"discord": true, "webhook": "https://...", "email": false}

    # Control
    enabled = Column(Boolean, nullable=False, default=True)
    cooldown_minutes = Column(Integer, nullable=False, default=5)
    max_alerts_per_hour = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("ix_alert_rules_tenant_id", "tenant_id"),
        Index("ix_alert_rules_enabled", "enabled"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "name": self.name,
            "description": self.description,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "conditions": self.conditions,
            "actions": self.actions,
            "enabled": self.enabled,
            "cooldown_minutes": self.cooldown_minutes,
            "max_alerts_per_hour": self.max_alerts_per_hour,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
