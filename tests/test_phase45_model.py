"""Phase 4.5 real-model training, serialization, registry, and inference."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from floodlens.application.ai_forecast import (
    AI_MODEL_ID,
    AIModelForecastProvider,
    _predict_horizons,
    load_checkpoint,
)
from floodlens.ml.baselines import BoostingModel, fit_baselines
from floodlens.ml.evaluate import average_precision
from floodlens.ml.features import matrix
from floodlens.ml.leakage import parse_ts
from floodlens.ml.real_dataset import snapshot_available
from floodlens.ml.registry import (
    load_registry,
    mark_trained,
    mark_validated,
    public_status,
    save_registry,
)
from floodlens.ml.splits import by_split


pytestmark = pytest.mark.skipif(not snapshot_available(), reason="real Open-Meteo snapshot not acquired")

REAL_CHECKPOINT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "floodlens"
    / "application"
    / "data"
    / "ml"
    / "real"
    / "checkpoint.json"
)


def _samples():
    from floodlens.ml.real_dataset import build_real_samples

    samples, meta = build_real_samples()
    return samples, meta


def test_real_baselines_fit_and_serialize_on_subset():
    samples, _ = _samples()
    train_all = by_split(samples, "train")
    val_all = by_split(samples, "val")
    train = train_all[:: max(1, len(train_all) // 90)][:90]
    val = val_all[:: max(1, len(val_all) // 45)][:45]
    tiny = train + val
    fitted = fit_baselines(tiny, track="A")
    blob = fitted.boosting.to_dict()
    restored = BoostingModel.from_dict(blob)
    X_val, y_val, _ = matrix(val, track="A", scaler=fitted.scaler)
    p0 = fitted.boosting.predict_proba(X_val)
    p1 = restored.predict_proba(X_val)
    assert p0.shape == p1.shape
    a0 = average_precision(y_val, p0)
    a1 = average_precision(y_val, p1)
    assert np.allclose(p0, p1)
    assert (np.isnan(a0) and np.isnan(a1)) or a0 == a1
    log_blob = fitted.logistic.to_dict()
    assert log_blob["coef"] is not None


def test_registry_trained_then_validated_tmp(tmp_path: Path):
    path = tmp_path / "registry.json"
    save_registry(
        {
            "id": "ai-forecast",
            "status": "NOT_TRAINED",
            "accuracy_claim": None,
            "note": "tmp",
        },
        path=path,
    )
    with pytest.raises(ValueError):
        mark_validated({"test": "x"}, {"test": {}}, path=path)
    mark_trained("run-tmp", str(tmp_path / "ckpt.json"), "phase4.5-openmeteo-glofas-v1", path=path)
    assert load_registry(path)["status"] == "TRAINED"
    assert public_status(load_registry(path)) == "NOT_TRAINED"
    mark_validated({"test": "2023-2024"}, {"test": {"n": 1}}, path=path)
    assert load_registry(path)["status"] == "VALIDATED"
    assert public_status(load_registry(path)) == "VALIDATED"


def test_checkpoint_inference_no_depth_and_no_subdaily():
    if not REAL_CHECKPOINT.exists():
        pytest.skip("real checkpoint not trained yet")
    samples, _ = _samples()
    test = by_split(samples, "test")
    assert test
    ckpt = load_checkpoint(str(REAL_CHECKPOINT))
    sample = test[0]
    issue = parse_ts(sample.issue_time)
    points = _predict_horizons(sample, ckpt, issue)
    by_h = {int(p["horizon_hours"]): p for p in points}
    assert by_h[6]["data_status"] == "UNAVAILABLE"
    assert by_h[12]["data_status"] == "UNAVAILABLE"
    for hours in (24, 48, 72):
        assert by_h[hours]["available"] is True
        assert by_h[hours]["expected_depth"] is None
        assert by_h[hours]["artifact_id"] is None
        assert 0.0 <= by_h[hours]["probability"] <= 1.0
        assert by_h[hours]["confidence_kind"] == "conformal"
        assert by_h[hours]["model_id"] == AI_MODEL_ID


def test_unvalidated_catalog_stays_unavailable():
    from floodlens.application.repository import reset_repository

    reset_repository()
    payload = AIModelForecastProvider().forecast("dhaka", allow_unvalidated=False)
    record = load_registry()
    if public_status(record) != "VALIDATED":
        assert payload["data_status"] == "UNAVAILABLE"
        assert payload["horizons"] == []
        assert payload["overlay"] is None
    else:
        assert payload["model_kind"] == "AI"
        assert payload["overlay"] is None
        if payload.get("data_status") != "UNAVAILABLE":
            for row in payload.get("horizons") or []:
                assert row.get("expected_depth") is None
