"""Model registry — load/save sklearn models with versioning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

MODEL_FILES = {
    "anomaly": "anomaly_iforest.joblib",
    "bot_classifier": "bot_classifier.joblib",
    "raid_predictor": "raid_predictor.joblib",
    "viewbot_predictor": "viewbot_predictor.joblib",
    "automation_detector": "automation_detector.joblib",
}


class ModelRegistry:
    _instance: Optional["ModelRegistry"] = None
    _models: Dict[str, Any]

    def __init__(self) -> None:
        self._models = {}
        self._path = Path(settings.ai_model_path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._version = self._load_version()

    @classmethod
    def get(cls) -> "ModelRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_version(self) -> str:
        meta = self._path / "metadata.json"
        if meta.exists():
            try:
                return json.loads(meta.read_text()).get("version", "1.0.0")
            except Exception:
                pass
        return "1.0.0"

    def get_model(self, name: str) -> Optional[Any]:
        if name in self._models:
            return self._models[name]
        fname = MODEL_FILES.get(name)
        if not fname:
            return None
        fpath = self._path / fname
        if not fpath.exists():
            return None
        try:
            import joblib

            model = joblib.load(fpath)
            self._models[name] = model
            return model
        except Exception as exc:
            logger.warning("model_load_failed", name=name, error=str(exc))
            return None

    def save_model(self, name: str, model: Any, version: Optional[str] = None) -> None:
        import joblib

        fname = MODEL_FILES.get(name)
        if not fname:
            return
        joblib.dump(model, self._path / fname)
        self._models[name] = model
        if version:
            self._version = version
            (self._path / "metadata.json").write_text(
                json.dumps({"version": version, "models": list(MODEL_FILES.keys())})
            )

    @property
    def version(self) -> str:
        return self._version
