"""Weka J48 bot classifier — sklearn fallback tests (no Java required)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.ml.weka_j48.engine import J48Engine
from app.ml.weka_j48.features import ViewerMLRow


def _synthetic_rows(n: int = 60) -> list[ViewerMLRow]:
    rows: list[ViewerMLRow] = []
    for i in range(n):
        is_bot = i % 2 == 0
        if is_bot:
            feats = [0.0, 600.0, 85.0, 0.0, 2.0, 0.8, 0.5, 0.3, 12.0, 0.0, 0.95]
            label = "yes"
        else:
            feats = [15.0, 1200.0, 20.0, 1.0, 40.0, 0.0, 0.0, 0.0, 8.0, 0.8, 0.1]
            label = "no"
        rows.append(ViewerMLRow(features=feats, label=label, session_id=str(i)))
    return rows


def test_sklearn_j48_train_and_predict():
    with tempfile.TemporaryDirectory() as tmp:
        engine = J48Engine(Path(tmp))
        meta = engine.train(_synthetic_rows(), prefer_weka=False)
        assert meta["backend"] == "sklearn_j48_compat"
        assert meta["samples"] == 60

        engine2 = J48Engine(Path(tmp))
        assert engine2.load()
        pred = engine2.predict(_synthetic_rows()[0].features)
        assert pred["backend"] == "sklearn_j48_compat"
        assert pred["is_bot"] is True
        assert pred["probability"] is not None
        assert 0.0 <= pred["probability"] <= 1.0


def test_insufficient_samples_raises():
    with tempfile.TemporaryDirectory() as tmp:
        engine = J48Engine(Path(tmp))
        with pytest.raises(ValueError, match="at least 10"):
            engine.train(_synthetic_rows(8), prefer_weka=False)
