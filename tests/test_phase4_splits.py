"""Temporal, geographic, and event-holdout splits."""

from __future__ import annotations

from floodlens.ml.dataset_builder import build_synthetic_samples
from floodlens.ml.splits import (
    BD_CITIES,
    assign_temporal,
    event_straddle_violations,
    geographic_split,
    in_named_holdout,
    temporal_split,
)
from floodlens.ml.leakage import parse_ts


def test_named_holdout_is_test_only():
    samples = build_synthetic_samples(
        start="2022-04-01T00:00:00Z",
        end="2022-08-01T00:00:00Z",
        cities=("sunamganj", "sylhet"),
        stride_hours=24,
    )
    assign_temporal(samples)
    assert event_straddle_violations(samples) == []
    holdout = [s for s in samples if in_named_holdout(parse_ts(s.issue_time))]
    assert holdout
    assert all(s.split == "test" for s in holdout)


def test_year_cuts():
    assert temporal_split("2020-06-01T00:00:00Z") == "train"
    assert temporal_split("2022-02-01T00:00:00Z") == "val"
    assert temporal_split("2024-01-15T00:00:00Z") == "test"


def test_geographic_holdout_sends_bd_aois_to_test():
    for city in BD_CITIES:
        assert geographic_split(city, train_cities={"meghna_holdout"}) == "test"
    assert geographic_split("meghna_holdout", train_cities={"meghna_holdout"}) == "train"


def test_splits_are_assigned_on_builder_output():
    samples = build_synthetic_samples(
        start="2020-01-01T00:00:00Z",
        end="2024-02-01T00:00:00Z",
        cities=("dhaka",),
        stride_hours=48,
    )
    names = {s.split for s in samples}
    assert names == {"train", "val", "test"}
