"""Alert repository for database operations."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.alert import Alert, AlertHistory, AlertRule, AlertSeverityEnum, AlertTypeEnum
from app.core.logging import get_logger

logger = get_logger(__name__)


class AlertRepository:
    """Repository for alert operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_alert(
        self,
        alert_id: UUID,
        stream_id: str,
        tenant_id: UUID,
        alert_type: str,
        severity: str,
        title: str,
        description: str,
        data: Optional[dict] = None,
        source: Optional[str] = None,
        tags: Optional[dict] = None,
    ) -> Alert:
        """Create a new alert."""
        alert = Alert(
            id=alert_id,
            stream_id=stream_id,
            tenant_id=tenant_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            description=description,
            data=data or {},
            source=source,
            tags=tags or {},
        )
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def get_alert_by_id(self, alert_id: UUID) -> Optional[Alert]:
        """Get alert by ID."""
        stmt = select(Alert).where(Alert.id == alert_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_stream_alerts(
        self,
        stream_id: str,
        limit: int = 50,
        offset: int = 0,
        dismissed: Optional[bool] = None,
        severity: Optional[str] = None,
        alert_type: Optional[str] = None,
    ) -> tuple[List[Alert], int]:
        """Get alerts for a stream with filtering."""
        # Build filter conditions
        conditions = [Alert.stream_id == stream_id]

        if dismissed is not None:
            conditions.append(Alert.dismissed == dismissed)

        if severity:
            conditions.append(Alert.severity == severity)

        if alert_type:
            conditions.append(Alert.alert_type == alert_type)

        # Count query
        count_stmt = select(func.count(Alert.id)).where(and_(*conditions))
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Data query
        stmt = (
            select(Alert)
            .where(and_(*conditions))
            .order_by(Alert.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        alerts = result.scalars().all()

        return alerts, total

    async def get_tenant_alerts(
        self,
        tenant_id: UUID,
        limit: int = 100,
        offset: int = 0,
        dismissed: Optional[bool] = None,
    ) -> tuple[List[Alert], int]:
        """Get all alerts for a tenant."""
        conditions = [Alert.tenant_id == tenant_id]

        if dismissed is not None:
            conditions.append(Alert.dismissed == dismissed)

        # Count query
        count_stmt = select(func.count(Alert.id)).where(and_(*conditions))
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Data query
        stmt = (
            select(Alert)
            .where(and_(*conditions))
            .order_by(Alert.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        alerts = result.scalars().all()

        return alerts, total

    async def dismiss_alert(
        self,
        alert_id: UUID,
        reason: Optional[str] = None,
        dismissed_by: Optional[str] = None,
    ) -> Optional[Alert]:
        """Dismiss an alert."""
        alert = await self.get_alert_by_id(alert_id)
        if not alert:
            return None

        alert.dismissed = True
        alert.dismissed_at = datetime.utcnow()

        # Log history
        await self._log_alert_history(
            alert_id=alert_id,
            action="dismissed",
            changed_by=dismissed_by,
            reason=reason,
        )

        await self.session.flush()
        return alert

    async def acknowledge_alert(
        self,
        alert_id: UUID,
        acked_by: Optional[str] = None,
    ) -> Optional[Alert]:
        """Acknowledge an alert."""
        alert = await self.get_alert_by_id(alert_id)
        if not alert:
            return None

        alert.acknowledged = True
        alert.acknowledged_at = datetime.utcnow()

        # Log history
        await self._log_alert_history(
            alert_id=alert_id,
            action="acknowledged",
            changed_by=acked_by,
        )

        await self.session.flush()
        return alert

    async def get_recent_alerts_for_stream(
        self,
        stream_id: str,
        minutes: int = 60,
    ) -> List[Alert]:
        """Get recent alerts for a stream."""
        from datetime import timedelta

        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)

        stmt = (
            select(Alert)
            .where(
                and_(
                    Alert.stream_id == stream_id,
                    Alert.created_at >= cutoff_time,
                    Alert.dismissed == False,
                )
            )
            .order_by(Alert.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_alert_history(self, alert_id: UUID) -> List[AlertHistory]:
        """Get audit history for an alert."""
        stmt = (
            select(AlertHistory)
            .where(AlertHistory.alert_id == alert_id)
            .order_by(AlertHistory.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def _log_alert_history(
        self,
        alert_id: UUID,
        action: str,
        changed_by: Optional[str] = None,
        reason: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> AlertHistory:
        """Log alert status change."""
        history = AlertHistory(
            id=UUID(int=0),  # Will be generated
            alert_id=alert_id,
            action=action,
            changed_by=changed_by,
            reason=reason,
            metadata=metadata or {},
        )
        self.session.add(history)
        await self.session.flush()
        return history


class AlertRuleRepository:
    """Repository for alert rule operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_rule(
        self,
        rule_id: UUID,
        tenant_id: UUID,
        name: str,
        alert_type: str,
        severity: str,
        conditions: dict,
        actions: dict,
        description: Optional[str] = None,
        cooldown_minutes: int = 5,
        max_alerts_per_hour: Optional[int] = None,
    ) -> AlertRule:
        """Create a new alert rule."""
        rule = AlertRule(
            id=rule_id,
            tenant_id=tenant_id,
            name=name,
            description=description,
            alert_type=alert_type,
            severity=severity,
            conditions=conditions,
            actions=actions,
            cooldown_minutes=cooldown_minutes,
            max_alerts_per_hour=max_alerts_per_hour,
        )
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def get_enabled_rules_for_tenant(self, tenant_id: UUID) -> List[AlertRule]:
        """Get all enabled rules for a tenant."""
        stmt = (
            select(AlertRule)
            .where(
                and_(
                    AlertRule.tenant_id == tenant_id,
                    AlertRule.enabled == True,
                )
            )
            .order_by(AlertRule.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_rule_by_id(self, rule_id: UUID) -> Optional[AlertRule]:
        """Get rule by ID."""
        stmt = select(AlertRule).where(AlertRule.id == rule_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def update_rule(
        self,
        rule_id: UUID,
        **updates,
    ) -> Optional[AlertRule]:
        """Update a rule."""
        rule = await self.get_rule_by_id(rule_id)
        if not rule:
            return None

        for key, value in updates.items():
            if hasattr(rule, key):
                setattr(rule, key, value)

        rule.updated_at = datetime.utcnow()
        await self.session.flush()
        return rule

    async def delete_rule(self, rule_id: UUID) -> bool:
        """Delete a rule."""
        rule = await self.get_rule_by_id(rule_id)
        if not rule:
            return False

        await self.session.delete(rule)
        await self.session.flush()
        return True
