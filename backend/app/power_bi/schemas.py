"""Power BI Data Schemas — Modelos optimizados para exportación y visualización."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================================
# MÉTRICAS GLOBALES SOC
# ============================================================================

class SocGlobalMetrics(BaseModel):
    """Métricas globales del SOC en tiempo real."""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Contadores principales
    total_streams_monitored: int = 0
    total_suspicious_viewers: int = 0
    total_attacks_detected: int = 0
    active_streams: int = 0
    detected_bots: int = 0
    suspicious_follows: int = 0
    
    # Scores
    engagement_score: float = 0.0
    global_threat_score: float = 0.0
    platform_health_score: float = 0.0
    
    # Tendencias
    attacks_24h: int = 0
    suspicious_viewers_24h: int = 0
    new_bots_24h: int = 0


class StreamSnapshot(BaseModel):
    """Snapshot de un stream para analytics."""
    stream_id: str
    tenant_id: str
    platform: Literal["twitch", "kick", "youtube", "tiktok"]
    channel_name: str
    
    is_live: bool
    viewer_count: int
    viewer_count_peak_24h: int
    
    messages_per_minute: float = 0.0
    follows_per_minute: float = 0.0
    gifts_per_minute: float = 0.0
    
    engagement_score: float = 0.0
    threat_score: float = 0.0
    bot_probability: float = 0.0
    synthetic_audience_percentage: float = 0.0
    
    active_attacks: int = 0
    suspicious_viewer_count: int = 0
    
    status: str = "online"
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SuspiciousViewerAnalytics(BaseModel):
    """Analytics de viewers sospechosos."""
    viewer_id: str
    username: str
    platform_user_id: Optional[str] = None
    stream_id: str
    platform: str
    
    first_seen: str
    last_seen: str
    account_age_days: int = 0
    
    bot_probability: float = 0.0
    suspicious_score: float = 0.0
    trust_score: float = 50.0
    
    interaction_count: int = 0
    messages_count: int = 0
    follows_count: int = 0
    
    suspicious_patterns: List[str] = Field(default_factory=list)
    cross_platform_hits: int = 0
    
    risk_level: Literal["low", "medium", "high", "critical"] = "low"


class AttackAnalytics(BaseModel):
    """Analytics de ataques detectados."""
    attack_id: str
    stream_id: str
    tenant_id: str
    
    attack_type: Literal["viewbotting", "followbotting", "spam", "raid", "synthetic"]
    severity: Literal["low", "medium", "high", "critical"]
    
    detected_at: str
    duration_seconds: int = 0
    
    bots_involved: int = 0
    viewers_affected: int = 0
    engagement_impact: float = 0.0
    
    confidence_score: float = 0.0
    ai_prediction: Optional[str] = None
    
    status: Literal["active", "mitigated", "resolved"] = "active"
    mitigation_action: Optional[str] = None


class EngagementMetrics(BaseModel):
    """Métricas de engagement por stream."""
    stream_id: str
    platform: str
    
    period: Literal["1h", "24h", "7d", "30d"]
    
    total_viewers: int = 0
    unique_chatters: int = 0
    messages_total: int = 0
    follows_total: int = 0
    gifts_total: int = 0
    
    messages_per_viewer: float = 0.0
    engagement_rate: float = 0.0
    retention_rate: float = 0.0
    
    real_engagement_score: float = 0.0
    synthetic_engagement_score: float = 0.0
    
    growth_velocity: float = 0.0
    viral_coefficient: float = 0.0


class AIPrediction(BaseModel):
    """Predicciones y anomalías detectadas por IA."""
    prediction_id: str
    stream_id: str
    timestamp: str
    
    anomaly_score: float = 0.0
    botnet_probability: float = 0.0
    coordinated_attack_probability: float = 0.0
    
    predicted_threat_level: Literal["safe", "warning", "danger", "critical"]
    confidence: float = 0.0
    
    detected_patterns: List[str] = Field(default_factory=list)
    recommended_action: Optional[str] = None
    
    ai_flags: List[str] = Field(default_factory=list)
    additional_context: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# TABLAS PARA POWER BI
# ============================================================================

class PowerBIStreamTable(BaseModel):
    """Tabla de streams optimizada para Power BI."""
    StreamID: str
    TenantID: str
    Platform: str
    ChannelName: str
    
    IsLive: bool
    ViewerCount: int
    ViewerCountPeak: int
    Status: str
    
    EngagementScore: float
    ThreatScore: float
    BotProbability: float
    
    ActiveAttacks: int
    SuspiciousViewers: int
    
    MessagesPerMinute: float
    FollowsPerMinute: float
    GiftsPerMinute: float
    
    LastUpdated: str
    CreatedDate: str


class PowerBISuspiciousViewerTable(BaseModel):
    """Tabla de viewers sospechosos para Power BI."""
    ViewerID: str
    Username: str
    StreamID: str
    Platform: str
    
    BotProbability: float
    SuspiciousScore: float
    TrustScore: float
    
    FirstSeen: str
    LastSeen: str
    AccountAgeDays: int
    
    InteractionCount: int
    MessageCount: int
    FollowsCount: int
    
    RiskLevel: str
    CrossPlatformHits: int


class PowerBIAttackTable(BaseModel):
    """Tabla de ataques para Power BI."""
    AttackID: str
    StreamID: str
    TenantID: str
    
    AttackType: str
    Severity: str
    Status: str
    
    DetectedAt: str
    Duration: int
    
    BotsInvolved: int
    ViewersAffected: int
    EngagementImpact: float
    ConfidenceScore: float


class PowerBIEngagementTable(BaseModel):
    """Tabla de engagement para Power BI."""
    StreamID: str
    Platform: str
    Period: str
    
    TotalViewers: int
    UniqueChatters: int
    MessagesTotal: int
    FollowsTotal: int
    GiftsTotal: int
    
    EngagementRate: float
    RetentionRate: float
    RealEngagementScore: float
    SyntheticEngagementScore: float


# ============================================================================
# EXPORTACIÓN CSV/EXCEL
# ============================================================================

class ExportRequest(BaseModel):
    """Request para exportar datos."""
    format: Literal["csv", "excel", "json"] = "csv"
    table_type: Literal["streams", "suspicious_viewers", "attacks", "engagement", "ai_predictions", "all"] = "streams"
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    platform_filter: Optional[str] = None
    tenant_id: Optional[str] = None


class ExportResponse(BaseModel):
    """Response de exportación."""
    status: str
    format: str
    file_url: str
    file_size: int
    rows_exported: int
    created_at: str
    expires_at: str


# ============================================================================
# DATASETS POWER BI
# ============================================================================

class PowerBIDataset(BaseModel):
    """Dataset para importar en Power BI."""
    name: str
    description: str
    tables: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PowerBIMeasure(BaseModel):
    """Medida DAX para Power BI."""
    name: str
    expression: str
    format_string: str = "0.00"
    description: Optional[str] = None


# ============================================================================
# KPIs
# ============================================================================

class KPI(BaseModel):
    """KPI estructurado."""
    name: str
    label: str
    value: float
    target: Optional[float] = None
    trend: Optional[Literal["up", "down", "stable"]] = None
    trend_percentage: Optional[float] = None
    unit: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SocKPIs(BaseModel):
    """KPIs principales del SOC."""
    real_engagement_percentage: KPI
    bot_percentage: KPI
    attack_detection_rate: KPI
    threat_mitigation_rate: KPI
    platform_health_score: KPI
    viewers_quality_score: KPI
    synthetic_audience_percentage: KPI
    average_response_time: KPI
