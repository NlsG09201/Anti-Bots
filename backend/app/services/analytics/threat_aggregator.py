from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models import (
    Attack,
    AttackType,
    Stream,
    ThreatAnalyticsDaily,
)

logger = get_logger(__name__)


class ThreatAnalyticsAggregator:
    """Aggregates threat metrics for historical analytics and trending."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def aggregate_daily(self, tenant_id: UUID, date_str: Optional[str] = None):
        """Aggregate daily threat metrics."""

        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        result = await self.db.execute(
            select(ThreatAnalyticsDaily).where(
                ThreatAnalyticsDaily.tenant_id == tenant_id,
                ThreatAnalyticsDaily.date == date_str,
            )
        )
        daily = result.scalar_one_or_none()

        tenant_stream_ids = (
            await self.db.execute(
                select(Stream.id).where(Stream.tenant_id == tenant_id)
            )
        ).scalars().all()

        if not tenant_stream_ids:
            return None

        from datetime import date as date_class

        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        start_time = datetime.combine(date_obj, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_time = datetime.combine(date_obj, datetime.max.time()).replace(tzinfo=timezone.utc)

        attacks_result = await self.db.execute(
            select(Attack).where(
                Attack.stream_id.in_(tenant_stream_ids),
                Attack.created_at >= start_time,
                Attack.created_at <= end_time,
            )
        )
        attacks = list(attacks_result.scalars().all())

        metrics = self._calculate_metrics(attacks)

        if daily:
            daily.attack_count = metrics["attack_count"]
            daily.blocked_ips = metrics["blocked_ips"]
            daily.blocked_fingerprints = metrics["blocked_fingerprints"]
            daily.top_asns = metrics["top_asns"]
            daily.top_attack_types = metrics["top_attack_types"]
            daily.avg_risk_score = metrics["avg_risk_score"]
            daily.max_risk_score = metrics["max_risk_score"]
            await self.db.flush()
        else:
            daily = ThreatAnalyticsDaily(
                tenant_id=tenant_id,
                date=date_str,
                **metrics,
            )
            self.db.add(daily)
            await self.db.flush()

        return daily

    def _calculate_metrics(self, attacks: List[Attack]) -> Dict:
        """Calculate aggregate metrics from attacks."""

        if not attacks:
            return {
                "attack_count": 0,
                "blocked_ips": 0,
                "blocked_fingerprints": 0,
                "top_asns": [],
                "top_attack_types": [],
                "avg_risk_score": 0.0,
                "max_risk_score": 0.0,
            }

        all_ips = set()
        all_fps = set()
        asn_counts = {}
        attack_type_counts = {}
        risk_scores = []

        for attack in attacks:
            all_ips.update(attack.source_ips or [])
            all_fps.update(attack.fingerprints or [])
            risk_scores.append(attack.risk_score)

            attack_type_str = attack.attack_type.value
            attack_type_counts[attack_type_str] = attack_type_counts.get(attack_type_str, 0) + 1

        top_asns = sorted(
            [(ip, 1) for ip in all_ips],
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        top_attack_types = sorted(
            attack_type_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:5]

        avg_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0.0
        max_risk = max(risk_scores) if risk_scores else 0.0

        return {
            "attack_count": len(attacks),
            "blocked_ips": len(all_ips),
            "blocked_fingerprints": len(all_fps),
            "top_asns": [
                {"asn": ip, "count": count}
                for ip, count in top_asns
            ],
            "top_attack_types": [
                {"type": attack_type, "count": count}
                for attack_type, count in top_attack_types
            ],
            "avg_risk_score": avg_risk,
            "max_risk_score": max_risk,
        }

    async def get_threat_trends(
        self,
        tenant_id: UUID,
        period: str = "30d",
    ) -> Dict:
        """Get threat trends for a period."""

        days = self._parse_period(period)
        date_cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        from datetime import timedelta

        start_date = date_cutoff - timedelta(days=days)

        result = await self.db.execute(
            select(ThreatAnalyticsDaily).where(
                ThreatAnalyticsDaily.tenant_id == tenant_id,
                ThreatAnalyticsDaily.date >= start_date.strftime("%Y-%m-%d"),
            )
        )
        analytics = list(result.scalars().all())

        if not analytics:
            return {
                "period": period,
                "total_attacks": 0,
                "total_blocked_ips": 0,
                "avg_risk_score": 0.0,
                "daily_trend": [],
                "top_attack_types": [],
            }

        total_attacks = sum(a.attack_count for a in analytics)
        total_ips = sum(a.blocked_ips for a in analytics)
        avg_risk = sum(a.avg_risk_score * a.attack_count for a in analytics) / total_attacks if total_attacks > 0 else 0.0

        all_attack_types = {}
        for daily in analytics:
            for attack_type_obj in daily.top_attack_types or []:
                attack_type = attack_type_obj.get("type")
                count = attack_type_obj.get("count", 0)
                all_attack_types[attack_type] = all_attack_types.get(attack_type, 0) + count

        top_types = sorted(
            all_attack_types.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:5]

        return {
            "period": period,
            "total_attacks": total_attacks,
            "total_blocked_ips": total_ips,
            "avg_risk_score": avg_risk,
            "daily_trend": [
                {
                    "date": a.date,
                    "attacks": a.attack_count,
                    "blocked_ips": a.blocked_ips,
                    "avg_risk": a.avg_risk_score,
                }
                for a in sorted(analytics, key=lambda a: a.date)
            ],
            "top_attack_types": [
                {"type": t[0], "count": t[1]}
                for t in top_types
            ],
        }

    def _parse_period(self, period: str) -> int:
        """Parse period string to days."""
        if period.endswith("d"):
            return int(period[:-1])
        elif period.endswith("w"):
            return int(period[:-1]) * 7
        elif period.endswith("m"):
            return int(period[:-1]) * 30
        else:
            return 30
