"""JSON-safe serialization for live intel API responses."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Dict

from app.live_intel.schemas import LiveIntelOverview


def sanitize_mongo_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Strip Mongo-specific types so Pydantic/JSON can consume the document."""
    out: Dict[str, Any] = {}
    for key, value in doc.items():
        if key == "_id":
            continue
        out[key] = _json_safe_value(value)
    return out


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return 0.0
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if type(value).__name__ == "ObjectId":
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(v) for v in value]
    return str(value)


def overview_to_api_dict(overview: LiveIntelOverview, *, max_snapshots: int = 30) -> Dict[str, Any]:
    """Build a response dict that always JSON-encodes (no NaN/ObjectId)."""
    data = overview.model_dump(mode="json")
    snaps = data.get("snapshots") or []
    if isinstance(snaps, list) and len(snaps) > max_snapshots:
        data["snapshots"] = snaps[:max_snapshots]
    return _json_safe_value(data)
