"""Classical baselines must beat persistence on Track A and sparse Track B separately."""

from __future__ import annotations

from pathlib import Path

from floodlens.ml.dataset_builder import (
    as_synthetic_track_b,
    build_synthetic_samples,
    samples_from_openmeteo_sample,
    write_jsonl,
)
from floodlens.ml.schema import DATASET_VERSION
from floodlens.ml.sources import emsr_catalog, glofas_cells, licenses, openmeteo_sample
from floodlens.ml.train import maybe_train_lstm, run_experiment


def test_phase41_data_cards_and_extracts():
    sample = openmeteo_sample()
    assert sample["data_status"] == "REAL"
    assert sample["license"].startswith("CC BY")
    assert set(sample["cities"]) == {"sunamganj", "dhaka", "sylhet"}
    assert sample["cities"]["sunamganj"]["n_hours"] == 168
    cells = glofas_cells()
    assert cells["label_kind"] == "MODELLED"
    assert cells["data_status"] == "UNAVAILABLE"
    assert len(cells["cells"]) == 3
    catalog = emsr_catalog()
    assert catalog["polygons_downloaded"] is False
    assert catalog["harvest"]["n_bangladesh_in_public_list"] == 0
    codes = {row["code"] for row in catalog["cited_public_activations"]}
    assert "EMSR097" in codes and "EMSR439" in codes
    log = licenses()
    nc = [d for d in log["datasets"] if d["id"] == "worldfloods-v2"][0]
    assert nc["commercial_ok"] is False
    assert "not downloaded" in nc["acquired"]


def test_openmeteo_sample_has_no_labels():
    samples = samples_from_openmeteo_sample()
    assert samples
    assert all(s.y_track_a is None for s in samples)
    assert all(s.y_track_b_available is False for s in samples)


def test_jsonl_roundtrip(tmp_path: Path):
    samples = build_synthetic_samples(
        start="2021-01-01T00:00:00Z",
        end="2021-03-01T00:00:00Z",
        cities=("dhaka",),
        stride_hours=24,
    )
    path = write_jsonl(samples, tmp_path / "samples.jsonl")
    assert path.exists()
    meta = path.with_suffix(".meta.json")
    assert DATASET_VERSION in meta.read_text()


def test_xgboost_beats_persistence_track_a_and_b(tmp_path: Path):
    samples = build_synthetic_samples(stride_hours=24, seed=7)
    result_a = run_experiment(samples, track="A", experiment_dir=tmp_path, seed=7)
    assert result_a["val"]["n"] > 30
    assert result_a["val"]["beats_persistence"]["xgboost_class"] is True
    assert result_a["test"]["beats_persistence"]["xgboost_class"] is True
    assert result_a["val"]["models"]["xgboost_class"]["accuracy_claim"] is None
    assert "6" in result_a["val"]["by_horizon"]
    assert "72" in result_a["val"]["by_horizon"]
    assert result_a["conformal_coverage_val"] >= 0.5

    samples_b = as_synthetic_track_b(samples, keep_frac=0.35, seed=11)
    result_b = run_experiment(samples_b, track="B", experiment_dir=tmp_path, seed=11)
    assert result_b["val"]["label_kind"] == "OBSERVED"
    assert result_b["val"]["n"] > 20
    assert result_b["val"]["beats_persistence"]["xgboost_class"] is True
    # Tracks must not share a metric table.
    assert result_a["val"]["track"] != result_b["val"]["track"]

    lstm = maybe_train_lstm(samples, result_a, epochs=3)
    assert lstm["trained"] is True
    assert lstm["justified"] is False or (
        lstm["val_auprc"] > result_a["val"]["models"]["xgboost_class"]["auprc"]
    )
    if not lstm["justified"]:
        assert "not promoted" in lstm["reason"].lower() or "sufficient" in lstm["reason"].lower()
    assert result_a["run"]["validated"] is False
