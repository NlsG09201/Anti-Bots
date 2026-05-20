"""
StreamShield AI Intelligence — modular real-time anti-viewbotting AI.

Layers: features → models → inference → orchestrator → mitigation recommendations.
"""

from app.ai_intel.orchestrator import AIIntelligenceOrchestrator
from app.ai_intel.schemas import AIAssessment, ThreatClassification, ThreatLevel

__all__ = [
    "AIIntelligenceOrchestrator",
    "AIAssessment",
    "ThreatClassification",
    "ThreatLevel",
]
