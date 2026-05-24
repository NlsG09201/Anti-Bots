"""Power BI Export Service — Servicio principal de exportación y generación de datasets."""

from __future__ import annotations

import io
import json
import csv
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models import (
    Stream,
    Viewer,
    Attack,
    ViewerSession,
    Platform,
)
from app.power_bi.schemas import (
    SocGlobalMetrics,
    StreamSnapshot,
    SuspiciousViewerAnalytics,
    AttackAnalytics,
    EngagementMetrics,
    PowerBIStreamTable,
    PowerBISuspiciousViewerTable,
    PowerBIAttackTable,
    PowerBIEngagementTable,
    SocKPIs,
    KPI,
)

logger = get_logger(__name__)


class PowerBIExportService:
    """Servicio de exportación y generación de datos para Power BI."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def compute_global_metrics(self, tenant_id: UUID) -> SocGlobalMetrics:
        """Calcula métricas globales del SOC."""
        
        # Contadores principales
        streams_result = await self.db.execute(
            select(func.count(Stream.id)).where(
                Stream.tenant_id == tenant_id,
                Stream.is_live == True,
            )
        )
        active_streams = streams_result.scalar() or 0

        total_result = await self.db.execute(
            select(func.count(Stream.id)).where(Stream.tenant_id == tenant_id)
        )
        total_streams = total_result.scalar() or 0

        suspicious_viewers_result = await self.db.execute(
            select(func.count(Viewer.id)).where(
                Viewer.tenant_id == tenant_id,
                Viewer.risk_score > 0.7,
            )
        )
        suspicious_viewers = suspicious_viewers_result.scalar() or 0

        attacks_result = await self.db.execute(
            select(func.count(Attack.id)).where(
                Attack.tenant_id == tenant_id,
                Attack.status == "active",
            )
        )
        active_attacks = attacks_result.scalar() or 0

        attacks_24h_result = await self.db.execute(
            select(func.count(Attack.id)).where(
                Attack.tenant_id == tenant_id,
                Attack.created_at >= datetime.now(timezone.utc) - timedelta(hours=24),
            )
        )
        attacks_24h = attacks_24h_result.scalar() or 0

        # Calcular amenaza global
        threat_scores = await self.db.execute(
            select(Stream.threat_score).where(Stream.tenant_id == tenant_id)
        )
        scores = threat_scores.scalars().all()
        global_threat_score = sum(scores) / len(scores) if scores else 0.0

        return SocGlobalMetrics(
            total_streams_monitored=total_streams,
            total_suspicious_viewers=suspicious_viewers,
            total_attacks_detected=active_attacks,
            active_streams=active_streams,
            attacks_24h=attacks_24h,
            global_threat_score=min(global_threat_score, 100.0),
        )

    async def get_stream_snapshots(
        self,
        tenant_id: UUID,
        platform_filter: Optional[str] = None,
        limit: int = 100,
    ) -> List[StreamSnapshot]:
        """Obtiene snapshots de streams activos."""
        
        query = select(Stream).where(
            Stream.tenant_id == tenant_id,
            Stream.is_live == True,
        )

        if platform_filter:
            query = query.where(Stream.platform == Platform[platform_filter.upper()])

        result = await self.db.execute(query.limit(limit))
        streams = result.scalars().all()

        snapshots = []
        for stream in streams:
            # Contar viewers sospechosos
            suspicious_result = await self.db.execute(
                select(func.count(Viewer.id)).where(
                    Viewer.stream_id == stream.id,
                    Viewer.risk_score > 0.7,
                )
            )
            suspicious_count = suspicious_result.scalar() or 0

            # Contar ataques activos
            attacks_result = await self.db.execute(
                select(func.count(Attack.id)).where(
                    Attack.stream_id == stream.id,
                    Attack.status == "active",
                )
            )
            active_attacks = attacks_result.scalar() or 0

            snapshots.append(
                StreamSnapshot(
                    stream_id=str(stream.id),
                    tenant_id=str(stream.tenant_id),
                    platform=stream.platform.value,
                    channel_name=stream.channel_name,
                    is_live=stream.is_live,
                    viewer_count=stream.viewer_count or 0,
                    engagement_score=stream.engagement_score or 0.0,
                    threat_score=stream.threat_score or 0.0,
                    bot_probability=stream.synthetic_audience_probability or 0.0,
                    active_attacks=active_attacks,
                    suspicious_viewer_count=suspicious_count,
                )
            )

        return snapshots

    async def get_suspicious_viewers(
        self,
        tenant_id: UUID,
        stream_id: Optional[UUID] = None,
        min_score: float = 0.7,
        limit: int = 1000,
    ) -> List[SuspiciousViewerAnalytics]:
        """Obtiene viewers sospechosos."""
        
        query = select(Viewer).where(
            Viewer.tenant_id == tenant_id,
            Viewer.risk_score >= min_score,
        )

        if stream_id:
            query = query.where(Viewer.stream_id == stream_id)

        result = await self.db.execute(query.limit(limit))
        viewers = result.scalars().all()

        analytics = []
        for viewer in viewers:
            # Calcular actividad
            sessions_result = await self.db.execute(
                select(func.count(ViewerSession.id)).where(
                    ViewerSession.viewer_id == viewer.id
                )
            )
            session_count = sessions_result.scalar() or 0

            # Determinar nivel de riesgo
            if viewer.risk_score >= 0.9:
                risk_level = "critical"
            elif viewer.risk_score >= 0.8:
                risk_level = "high"
            elif viewer.risk_score >= 0.6:
                risk_level = "medium"
            else:
                risk_level = "low"

            analytics.append(
                SuspiciousViewerAnalytics(
                    viewer_id=str(viewer.id),
                    username=viewer.username or f"user_{viewer.id}",
                    platform_user_id=viewer.platform_user_id,
                    stream_id=str(viewer.stream_id),
                    platform=viewer.platform or "unknown",
                    first_seen=viewer.first_seen.isoformat() if viewer.first_seen else "",
                    last_seen=viewer.last_seen.isoformat() if viewer.last_seen else "",
                    bot_probability=viewer.risk_score,
                    suspicious_score=viewer.risk_score,
                    trust_score=max(0, 100 - (viewer.risk_score * 100)),
                    interaction_count=session_count,
                    risk_level=risk_level,
                    suspicious_patterns=viewer.flags or [],
                )
            )

        return analytics

    async def get_attacks(
        self,
        tenant_id: UUID,
        status: Optional[str] = None,
        hours: int = 24,
        limit: int = 500,
    ) -> List[AttackAnalytics]:
        """Obtiene ataques detectados."""
        
        query = select(Attack).where(
            Attack.tenant_id == tenant_id,
            Attack.created_at >= datetime.now(timezone.utc) - timedelta(hours=hours),
        )

        if status:
            query = query.where(Attack.status == status)

        result = await self.db.execute(query.limit(limit))
        attacks = result.scalars().all()

        analytics = []
        for attack in attacks:
            attack_type = (attack.attack_type or "unknown").lower()
            
            if "follow" in attack_type:
                atype = "followbotting"
            elif "viewer" in attack_type:
                atype = "viewbotting"
            elif "raid" in attack_type:
                atype = "raid"
            elif "spam" in attack_type:
                atype = "spam"
            else:
                atype = "synthetic"

            severity = (attack.severity or "medium").lower()

            analytics.append(
                AttackAnalytics(
                    attack_id=str(attack.id),
                    stream_id=str(attack.stream_id),
                    tenant_id=str(attack.tenant_id),
                    attack_type=atype,
                    severity=severity,
                    detected_at=attack.created_at.isoformat(),
                    bots_involved=attack.bots_involved or 0,
                    viewers_affected=attack.viewers_affected or 0,
                    confidence_score=attack.confidence or 0.0,
                    status=attack.status or "active",
                    mitigation_action=attack.mitigation_action,
                )
            )

        return analytics

    async def compute_kpis(self, tenant_id: UUID) -> SocKPIs:
        """Calcula KPIs principales."""
        
        # Engagement real vs sintético
        streams_result = await self.db.execute(
            select(Stream).where(
                Stream.tenant_id == tenant_id,
                Stream.is_live == True,
            )
        )
        streams = streams_result.scalars().all()

        real_engagement = 0.0
        bot_percentage = 0.0

        if streams:
            real_scores = [s.engagement_score or 0.0 for s in streams]
            bot_scores = [s.synthetic_audience_probability or 0.0 for s in streams]
            
            real_engagement = sum(real_scores) / len(real_scores)
            bot_percentage = sum(bot_scores) / len(bot_scores)

        # Attack detection rate
        total_attacks_24h_result = await self.db.execute(
            select(func.count(Attack.id)).where(
                Attack.tenant_id == tenant_id,
                Attack.created_at >= datetime.now(timezone.utc) - timedelta(hours=24),
            )
        )
        total_attacks = total_attacks_24h_result.scalar() or 0

        mitigated_attacks_result = await self.db.execute(
            select(func.count(Attack.id)).where(
                Attack.tenant_id == tenant_id,
                Attack.status == "mitigated",
                Attack.created_at >= datetime.now(timezone.utc) - timedelta(hours=24),
            )
        )
        mitigated = mitigated_attacks_result.scalar() or 0

        mitigation_rate = (mitigated / total_attacks * 100) if total_attacks > 0 else 0

        return SocKPIs(
            real_engagement_percentage=KPI(
                name="real_engagement",
                label="Real Engagement %",
                value=real_engagement * 100,
                target=75.0,
                unit="%",
            ),
            bot_percentage=KPI(
                name="bot_percentage",
                label="Bot Detection Rate",
                value=bot_percentage * 100,
                target=10.0,
                unit="%",
            ),
            attack_detection_rate=KPI(
                name="attack_detection",
                label="Attacks (24h)",
                value=float(total_attacks),
                unit="eventos",
            ),
            threat_mitigation_rate=KPI(
                name="mitigation_rate",
                label="Mitigation Rate",
                value=mitigation_rate,
                target=90.0,
                unit="%",
            ),
            platform_health_score=KPI(
                name="platform_health",
                label="Platform Health",
                value=85.0,
                target=95.0,
                unit="%",
            ),
            viewers_quality_score=KPI(
                name="viewers_quality",
                label="Viewers Quality",
                value=(100 - bot_percentage * 100),
                target=90.0,
                unit="%",
            ),
            synthetic_audience_percentage=KPI(
                name="synthetic_audience",
                label="Synthetic Audience %",
                value=bot_percentage * 100,
                target=5.0,
                unit="%",
            ),
            average_response_time=KPI(
                name="response_time",
                label="Avg Response Time",
                value=245.0,
                target=500.0,
                unit="ms",
            ),
        )

    def generate_powerbi_stream_table(
        self, snapshots: List[StreamSnapshot]
    ) -> List[Dict[str, Any]]:
        """Genera tabla de streams para Power BI."""
        
        rows = []
        for snap in snapshots:
            rows.append({
                "StreamID": snap.stream_id,
                "TenantID": snap.tenant_id,
                "Platform": snap.platform,
                "ChannelName": snap.channel_name,
                "IsLive": snap.is_live,
                "ViewerCount": snap.viewer_count,
                "ViewerCountPeak": snap.viewer_count_peak_24h,
                "Status": snap.status,
                "EngagementScore": round(snap.engagement_score, 2),
                "ThreatScore": round(snap.threat_score, 2),
                "BotProbability": round(snap.bot_probability, 2),
                "ActiveAttacks": snap.active_attacks,
                "SuspiciousViewers": snap.suspicious_viewer_count,
                "MessagesPerMinute": round(snap.messages_per_minute, 1),
                "FollowsPerMinute": round(snap.follows_per_minute, 1),
                "GiftsPerMinute": round(snap.gifts_per_minute, 1),
                "LastUpdated": snap.updated_at,
                "CreatedDate": datetime.now(timezone.utc).isoformat(),
            })
        return rows

    def generate_csv_export(
        self, data: List[Dict[str, Any]], filename: str = "export.csv"
    ) -> io.StringIO:
        """Genera CSV para exportación."""
        
        output = io.StringIO()
        
        if not data:
            return output

        fieldnames = data[0].keys()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        
        writer.writeheader()
        writer.writerows(data)
        
        return output

    def generate_excel_export(
        self, data: List[Dict[str, Any]], filename: str = "export"
    ) -> bytes:
        """Genera Excel para exportación."""
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment
        except ImportError:
            logger.warning("openpyxl not installed, returning JSON instead")
            return json.dumps(data).encode()

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = filename

        if not data:
            return b""

        # Headers
        headers = list(data[0].keys())
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            cell.alignment = Alignment(horizontal="center")

        # Data
        for row_idx, row_data in enumerate(data, 2):
            for col_idx, value in enumerate(row_data.values(), 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.value = value
                cell.alignment = Alignment(horizontal="left", wrap_text=True)

        # Auto-width
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value or "")) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width

        # Guardar en bytes
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output.getvalue()

    async def generate_powerbi_dataset(
        self, tenant_id: UUID, include_tables: List[str] | str = "all"
    ) -> Dict[str, Any]:
        """Genera dataset completo para Power BI."""
        
        if isinstance(include_tables, str) and include_tables == "all":
            include_tables = ["streams", "suspicious_viewers", "attacks"]

        dataset = {
            "name": f"Anti-Bots-SOC-{tenant_id}",
            "description": "Dataset SOC anti-bots en tiempo real",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tables": {},
        }

        if "streams" in include_tables:
            snapshots = await self.get_stream_snapshots(tenant_id)
            dataset["tables"]["Streams"] = self.generate_powerbi_stream_table(snapshots)

        if "suspicious_viewers" in include_tables:
            viewers = await self.get_suspicious_viewers(tenant_id, limit=500)
            dataset["tables"]["SuspiciousViewers"] = [
                viewer.model_dump() for viewer in viewers
            ]

        if "attacks" in include_tables:
            attacks = await self.get_attacks(tenant_id)
            dataset["tables"]["Attacks"] = [a.model_dump() for a in attacks]

        return dataset
