"""Weka J48 engine with sklearn entropy-tree fallback when Java/Weka is unavailable."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
from sklearn.tree import DecisionTreeClassifier

from app.core.logging import get_logger
from app.ml.weka_j48.features import (
    ATTRIBUTE_NAMES,
    NOMINAL_CLASS,
    ViewerMLRow,
    sanitize_rows,
)
from app.ml.weka_j48.runtime import (
    is_jvm_started,
    warm_weka_jvm,
    weka_python_installed,
)

logger = get_logger(__name__)


def weka_runtime_available(java_home: str = "") -> bool:
    """Weka Python instalado + Java disponible (JVM puede arrancar bajo demanda)."""
    from app.ml.weka_j48.runtime import java_available

    return weka_python_installed() and java_available(java_home)


def _ensure_jvm(java_home: str = "", max_heap: str = "512m") -> bool:
    if is_jvm_started():
        return True
    result = warm_weka_jvm(java_home=java_home, max_heap=max_heap)
    return bool(result.get("ok"))


def _build_weka_instances(rows: List[ViewerMLRow]):
    from weka.core.dataset import create_instances_from_lists

    data_rows = [r.features + [r.label or "no"] for r in rows if r.label]
    return create_instances_from_lists(
        ATTRIBUTE_NAMES + [NOMINAL_CLASS],
        ["numeric"] * len(ATTRIBUTE_NAMES) + [f"nominal:yes,no"],
        data_rows,
        class_index=len(ATTRIBUTE_NAMES),
    )


class J48ModelBundle:
    """Serialized model + metadata."""

    def __init__(
        self,
        backend: str,
        artifact: Any,
        meta: Dict[str, Any],
    ):
        self.backend = backend
        self.artifact = artifact
        self.meta = meta


class J48Engine:
    def __init__(self, model_dir: Path, java_home: str = "", max_heap: str = "512m"):
        self.model_dir = model_dir.resolve()
        self.java_home = java_home
        self.max_heap = max_heap
        try:
            self.model_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("weka_model_dir_mkdir_failed", path=str(self.model_dir), error=str(exc))
            raise
        self._bundle: Optional[J48ModelBundle] = None

    @property
    def model_path(self) -> Path:
        return self.model_dir / "bot_j48.bundle.joblib"

    @property
    def weka_model_path(self) -> Path:
        return self.model_dir / "bot_j48.weka.model"

    def is_loaded(self) -> bool:
        return self._bundle is not None

    def load(self) -> bool:
        if self.model_path.exists():
            data = joblib.load(self.model_path)
            self._bundle = J48ModelBundle(
                backend=data["backend"],
                artifact=data.get("sklearn_model"),
                meta=data.get("meta", {}),
            )
            if self._bundle.backend == "weka" and self.weka_model_path.exists():
                if _ensure_jvm(self.java_home, self.max_heap):
                    from weka.core.serialization import read as weka_read

                    self._bundle.artifact = weka_read(str(self.weka_model_path))
            return True
        return False

    def train(
        self,
        rows: List[ViewerMLRow],
        *,
        prefer_weka: bool = True,
        confidence: float = 0.25,
        min_instances: int = 2,
    ) -> Dict[str, Any]:
        labeled = sanitize_rows([r for r in rows if r.label in ("yes", "no")])
        if len(labeled) < 10:
            raise ValueError(f"Need at least 10 labeled rows, got {len(labeled)}")

        yes = sum(1 for r in labeled if r.label == "yes")
        no = len(labeled) - yes
        if yes < 2 or no < 2:
            raise ValueError("Need at least 2 examples per class (bot / human)")

        use_weka = (
            prefer_weka
            and weka_runtime_available(self.java_home)
            and _ensure_jvm(self.java_home, self.max_heap)
        )
        if use_weka:
            try:
                return self._train_weka(
                    labeled, confidence=confidence, min_instances=min_instances
                )
            except Exception as exc:
                logger.warning(
                    "weka_j48_native_train_failed_using_sklearn",
                    error=str(exc),
                    samples=len(labeled),
                )
        return self._train_sklearn(labeled)

    def _train_weka(
        self,
        labeled: List[ViewerMLRow],
        *,
        confidence: float,
        min_instances: int,
    ) -> Dict[str, Any]:
        from weka.classifiers.trees import J48
        from weka.core.serialization import write as weka_write

        data = _build_weka_instances(labeled)
        classifier = J48()
        classifier.options = [
            "-C",
            str(confidence),
            "-M",
            str(min_instances),
        ]
        classifier.build_classifier(data)

        meta = {
            "backend": "weka",
            "samples": len(labeled),
            "attributes": ATTRIBUTE_NAMES,
            "class": NOMINAL_CLASS,
            "options": {"confidence": confidence, "min_instances": min_instances},
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            weka_write(str(self.weka_model_path), classifier)
            joblib.dump(
                {"backend": "weka", "sklearn_model": None, "meta": meta},
                self.model_path,
            )
        except OSError as exc:
            raise OSError(
                f"No se pudo guardar el modelo en {self.model_dir}: {exc}"
            ) from exc
        self._bundle = J48ModelBundle("weka", classifier, meta)
        logger.info("weka_j48_trained", samples=len(labeled))
        return meta

    def _train_sklearn(self, labeled: List[ViewerMLRow]) -> Dict[str, Any]:
        x = np.array([r.features for r in labeled], dtype=np.float64)
        y = np.array([1 if r.label == "yes" else 0 for r in labeled])

        clf = DecisionTreeClassifier(
            criterion="entropy",
            max_depth=10,
            min_samples_leaf=5,
            class_weight="balanced",
            random_state=42,
        )
        clf.fit(x, y)
        meta = {
            "backend": "sklearn_j48_compat",
            "samples": len(labeled),
            "attributes": ATTRIBUTE_NAMES,
            "class": NOMINAL_CLASS,
            "note": "J48-compatible entropy tree; install Java + weka-python3 for native Weka J48",
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }
        joblib.dump(
            {"backend": "sklearn_j48_compat", "sklearn_model": clf, "meta": meta},
            self.model_path,
        )
        self._bundle = J48ModelBundle("sklearn_j48_compat", clf, meta)
        logger.info("sklearn_j48_compat_trained", samples=len(labeled))
        return meta

    def predict(self, features: List[float]) -> Dict[str, Any]:
        from app.ml.weka_j48.features import sanitize_feature_vector

        features = sanitize_feature_vector(features)
        if not self._bundle:
            if not self.load():
                return {
                    "is_bot": None,
                    "probability": None,
                    "class_label": None,
                    "backend": None,
                    "error": "model_not_loaded",
                }

        if self._bundle.backend == "weka" and self._bundle.artifact is not None:
            return self._predict_weka(features)
        if self._bundle.backend == "sklearn_j48_compat" and self._bundle.artifact is not None:
            return self._predict_sklearn(features)
        return {
            "is_bot": None,
            "probability": None,
            "class_label": None,
            "backend": self._bundle.backend if self._bundle else None,
            "error": "invalid_bundle",
        }

    def _predict_weka(self, features: List[float]) -> Dict[str, Any]:
        from weka.core.dataset import create_instances_from_lists

        inst = create_instances_from_lists(
            ATTRIBUTE_NAMES + [NOMINAL_CLASS],
            ["numeric"] * len(ATTRIBUTE_NAMES) + [f"nominal:yes,no"],
            [features + ["no"]],
            class_index=len(ATTRIBUTE_NAMES),
        )
        inst.class_is_last()
        inst.class_index = len(ATTRIBUTE_NAMES)
        inst.delete_attribute(len(ATTRIBUTE_NAMES))
        inst = inst.get_instance(0)

        clf = self._bundle.artifact
        pred = clf.classify_instance(inst)
        dist = clf.distribution_for_instance(inst)
        prob_bot = float(dist[0]) if len(dist) > 0 else 0.5
        is_bot = str(pred).lower() == "yes"
        if not is_bot and len(dist) > 1:
            prob_bot = float(dist[1]) if str(clf.class_attribute.value(0)).lower() == "no" else prob_bot

        return {
            "is_bot": is_bot,
            "probability": round(prob_bot, 4),
            "class_label": str(pred),
            "backend": "weka",
        }

    def _predict_sklearn(self, features: List[float]) -> Dict[str, Any]:
        clf: DecisionTreeClassifier = self._bundle.artifact
        x = np.array([features], dtype=np.float64)
        pred = int(clf.predict(x)[0])
        proba = clf.predict_proba(x)[0]
        classes = list(clf.classes_)
        prob_bot = float(proba[classes.index(1)]) if 1 in classes else float(proba[0])
        return {
            "is_bot": pred == 1,
            "probability": round(prob_bot, 4),
            "class_label": "yes" if pred == 1 else "no",
            "backend": "sklearn_j48_compat",
        }

    def health(self) -> Dict[str, Any]:
        trained_at = None
        if self.model_path.exists():
            mtime = datetime.fromtimestamp(
                self.model_path.stat().st_mtime, tz=timezone.utc
            )
            trained_at = mtime.isoformat()
        meta = self._bundle.meta if self._bundle else {}
        from app.ml.weka_j48.runtime import java_available, runtime_status

        rt = runtime_status(self.java_home)
        return {
            **rt,
            "weka_python_available": rt["weka_python_installed"] and rt["java_available"],
            "model_loaded": self.is_loaded(),
            "model_path": str(self.model_path),
            "backend": self._bundle.backend if self._bundle else None,
            "meta": meta,
            "trained_at": meta.get("trained_at") or trained_at,
            "training_samples": meta.get("samples"),
        }
