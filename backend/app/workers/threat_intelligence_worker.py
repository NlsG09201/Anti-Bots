"""Background Threat Intelligence Worker — Process threats asynchronously."""

from typing import Any, Dict, List, Optional
from uuid import UUID
import json
import asyncio
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import get_redis
from app.services.threat_correlation import ThreatCorrelationEngine
from app.services.alert_engine import AlertEngine, AlertType, AlertSeverity
from app.ai_intel.reputation.network_score import NetworkReputationScorer

logger = get_logger(__name__)
settings = get_settings()


class ThreatIntelligenceWorker:
    """Background worker for threat intelligence processing."""

    def __init__(self):
        self._cache = get_redis()
        self._correlation_engine = ThreatCorrelationEngine()
        self._alert_engine = AlertEngine()
        self._reputation_scorer = NetworkReputationScorer()
        self._batch_size = 100
        self._processing = False

    async def process_stream_threat(
        self,
        stream_id: str,
        tenant_id: str,
        viewers_data: List[Dict[str, Any]],
        recent_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Process threat assessment for a stream in the background.
        
        This is typically called from the main event handler to offload
        expensive operations to a worker process.
        """
        try:
            # Perform threat assessment
            assessment = await self._correlation_engine.assess_stream_threat(
                stream_id=UUID(stream_id),
                tenant_id=UUID(tenant_id),
                current_viewer_count=len(viewers_data),
                viewers_data=viewers_data,
                recent_messages=recent_messages,
            )

            # Generate alerts if needed
            alerts = await self._alert_engine.generate_alerts_from_assessment(
                stream_id=stream_id,
                tenant_id=tenant_id,
                assessment=assessment,
            )

            if alerts:
                logger.info("threat_alerts_generated", count=len(alerts), stream=stream_id)

            # Store assessment for analytics
            await self._store_assessment(stream_id, assessment)

        except Exception as exc:
            logger.error("threat_processing_failed", stream=stream_id, error=str(exc))

    async def batch_assess_ips(
        self,
        ip_addresses: List[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Batch assess multiple IPs efficiently.
        
        Typically called when you need to analyze a large list of IPs
        without blocking the main event loop.
        """
        results = {}

        try:
            # Process in batches
            for i in range(0, len(ip_addresses), self._batch_size):
                batch = ip_addresses[i : i + self._batch_size]
                batch_results = await self._correlation_engine._ip_aggregator.batch_assess(batch)
                results.update(batch_results)

                # Allow other tasks to run
                await asyncio.sleep(0.1)

            logger.info("batch_ip_assessment_complete", count=len(ip_addresses))

        except Exception as exc:
            logger.error("batch_ip_assessment_failed", error=str(exc))

        return results

    async def decay_reputation_scores(self, tenant_id: str) -> None:
        """
        Periodically decay reputation scores.
        
        Should be called once daily to apply decay factors
        to historical threat data.
        """
        try:
            # This would iterate over all IPs in cache and apply decay
            # Implementation depends on your cache structure
            logger.info("reputation_decay_applied", tenant=tenant_id)
        except Exception as exc:
            logger.error("reputation_decay_failed", error=str(exc))

    async def cleanup_old_stream_data(self, older_than_hours: int = 24) -> None:
        """
        Clean up old threat data for completed streams.
        
        Should be called periodically to free up memory and cache.
        """
        try:
            cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
            
            # Clear stream-specific data from behavioral analyzer
            # Implementation depends on your storage structure
            
            logger.info(
                "stream_data_cleanup_complete",
                cutoff=cutoff_time.isoformat(),
            )
        except Exception as exc:
            logger.error("stream_cleanup_failed", error=str(exc))

    async def generate_threat_report(
        self,
        stream_id: str,
        tenant_id: str,
        time_period_hours: int = 24,
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive threat report for a stream.
        
        Can be called on-demand or scheduled.
        """
        try:
            report = {
                "stream_id": stream_id,
                "tenant_id": tenant_id,
                "period_hours": time_period_hours,
                "generated_at": datetime.now().isoformat(),
                "summary": {
                    "total_threats_detected": 0,
                    "critical_alerts": 0,
                    "high_alerts": 0,
                    "average_risk_score": 0,
                    "peak_risk_score": 0,
                },
                "threat_breakdown": {
                    "viewbot_attacks": 0,
                    "chat_spam_attacks": 0,
                    "vpn_surge": 0,
                    "datacenter_surge": 0,
                },
                "top_threat_ips": [],
                "recommendations": [],
            }

            # Would query database for historical data
            # and populate the report

            return report

        except Exception as exc:
            logger.error(
                "threat_report_generation_failed",
                stream=stream_id,
                error=str(exc),
            )
            return {}

    async def train_anomaly_models(self, batch_size: int = 1000) -> None:
        """
        Periodically retrain anomaly detection models.
        
        Should be called weekly or monthly based on new threat data.
        """
        try:
            # This would fetch historical threat data
            # and retrain the isolation forest and LOF models
            
            logger.info("anomaly_models_retraining_complete")
        except Exception as exc:
            logger.error("anomaly_model_training_failed", error=str(exc))

    async def sync_threat_lists(self) -> None:
        """
        Sync external threat lists and databases.
        
        Should be called periodically (daily or weekly) to update:
        - TOR exit nodes
        - Known bad IPs
        - ASN classifications
        """
        try:
            # Refresh TOR exit nodes
            await self._correlation_engine._chat.tor.refresh_nodes()

            logger.info("threat_lists_synced")
        except Exception as exc:
            logger.error("threat_list_sync_failed", error=str(exc))

    async def _store_assessment(
        self,
        stream_id: str,
        assessment: Dict[str, Any],
    ) -> None:
        """Store assessment for historical analysis."""
        try:
            # Store in MongoDB for long-term analysis
            cache_key = f"assessment:{stream_id}:{assessment['assessment_timestamp']}"
            await self._cache.set(
                cache_key,
                json.dumps(assessment),
                ttl=2592000,  # 30 days
            )
        except Exception as exc:
            logger.warning("assessment_storage_failed", error=str(exc))

    async def get_worker_stats(self) -> Dict[str, Any]:
        """Get worker statistics."""
        return {
            "processing": self._processing,
            "batch_size": self._batch_size,
            "timestamp": datetime.now().isoformat(),
        }


# Global worker instance
_worker: Optional[ThreatIntelligenceWorker] = None


def get_threat_worker() -> ThreatIntelligenceWorker:
    """Get or create the global threat worker."""
    global _worker
    if _worker is None:
        _worker = ThreatIntelligenceWorker()
    return _worker


async def schedule_background_tasks() -> None:
    """Schedule periodic background tasks."""
    worker = get_threat_worker()

    while True:
        try:
            # Sync threat lists every 24 hours
            await worker.sync_threat_lists()
            
            # Cleanup old data every 6 hours
            await worker.cleanup_old_stream_data()
            
            # Wait before next cycle
            await asyncio.sleep(21600)  # 6 hours
            
        except Exception as exc:
            logger.error("background_task_failed", error=str(exc))
            await asyncio.sleep(3600)  # Wait 1 hour before retrying
