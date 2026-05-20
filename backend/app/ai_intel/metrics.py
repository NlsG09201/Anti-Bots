"""Prometheus metrics for AI intelligence pipeline."""

from prometheus_client import Counter, Histogram

AI_ASSESSMENTS_TOTAL = Counter(
    "streamshield_ai_assessments_total",
    "AI assessments completed",
    ["threat_level", "classification"],
)
AI_EARLY_WARNINGS_TOTAL = Counter(
    "streamshield_ai_early_warnings_total",
    "Early-warning predictions emitted",
)
AI_INFERENCE_LATENCY = Histogram(
    "streamshield_ai_inference_seconds",
    "Inference latency in seconds",
    buckets=(0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.25),
)
