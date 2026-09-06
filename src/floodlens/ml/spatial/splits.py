"""Event / temporal / geographic splits for spatial tiles. No pixel-i.i.d. split."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Sequence
import json

from floodlens.ml.leakage import parse_ts
from floodlens.ml.spatial.schema import SpatialForecastSample
from floodlens.ml.splits import in_named_holdout

# Plan: train years ≤ 2018; val 2019–2021; test 2022 named holdout + later if labels exist.
TRAIN_END = datetime(2019, 1, 1, tzinfo=timezone.utc)
VAL_END = datetime(2022, 1, 1, tzinfo=timezone.utc)
GEO_TRAIN_CITIES = frozenset({"dhaka"})
GEO_TEST_CITIES = frozenset({"sunamganj", "sylhet"})


def temporal_split(issue_time: str) -> str:
    stamp = parse_ts(issue_time)
    if in_named_holdout(stamp):
        return "test"
    if stamp < TRAIN_END:
        return "train"
    if stamp < VAL_END:
        return "val"
    return "test"


def geographic_split(city_id: str) -> str:
    from floodlens.ml.spatial.aois_v2 import GEO_TEST_AOIS

    if city_id in GEO_TEST_CITIES or city_id in GEO_TEST_AOIS:
        return "test"
    return "train"


def assign_temporal(samples: Sequence[SpatialForecastSample]) -> List[SpatialForecastSample]:
    out = []
    for sample in samples:
        sample.split = temporal_split(sample.issue_time)
        out.append(sample)
    return list(out)


def assign_event_level_splits(samples: Sequence[SpatialForecastSample]) -> List[SpatialForecastSample]:
    """All scenes of one meteorological event share the split of event_start.

    Per-sample year cuts can leak one monsoon across train/val. Forbidden.
    """
    from floodlens.ml.spatial.events import assign_event_ids

    assign_event_ids(samples)
    event_split = {}
    for sample in samples:
        eid = (sample.extra or {}).get("event_id")
        if not eid:
            sample.split = temporal_split(sample.issue_time)
            continue
        if eid not in event_split:
            start = (sample.extra or {}).get("event_start") or sample.issue_time
            event_split[eid] = temporal_split(start)
        sample.split = event_split[eid]
    return list(samples)


def event_straddle_violations(samples: Iterable[SpatialForecastSample]) -> List[str]:
    bad = []
    for sample in samples:
        stamp = parse_ts(sample.issue_time)
        if in_named_holdout(stamp) and sample.split == "train":
            bad.append(f"{sample.city_id} {sample.issue_time} {sample.scene_id}")
    return bad


def by_split(samples: Sequence[SpatialForecastSample], name: str) -> List[SpatialForecastSample]:
    return [s for s in samples if s.split == name]


def forbid_pixel_iid(split_scheme: str) -> None:
    if split_scheme in {"pixel", "i.i.d.", "iid", "random_pixel"}:
        raise ValueError("pixel-level random split is forbidden for spatial flood maps")


def write_split_manifests(samples: Sequence[SpatialForecastSample], out_dir) -> dict:
    """Persist event-level train/val/test and geographic/temporal holdouts. No pixel split."""
    from pathlib import Path

    from floodlens.ml.spatial.events import assign_event_ids, same_event_across_splits, same_event_in_train_and_test

    assign_event_level_splits(samples)
    forbid_pixel_iid("event")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def _ids(name: str) -> list:
        return sorted({(s.extra or {}).get("event_id") for s in samples if s.split == name and (s.extra or {}).get("event_id")})

    train_ids, val_ids, test_ids = _ids("train"), _ids("val"), _ids("test")
    leak_tt = same_event_in_train_and_test(samples)
    leak_tv = same_event_across_splits(samples, "train", "val")
    leak_vt = same_event_across_splits(samples, "val", "test")
    if leak_tt or leak_tv or leak_vt:
        raise ValueError(f"event leak across splits: train/test={leak_tt} train/val={leak_tv} val/test={leak_vt}")

    geo_test = sorted({s.city_id for s in samples if geographic_split(s.city_id) == "test"})
    geo_train = sorted({s.city_id for s in samples if geographic_split(s.city_id) == "train"})
    payload = {
        "scheme": "event_temporal",
        "pixel_iid": False,
        "train_events": train_ids,
        "validation_events": val_ids,
        "test_events": test_ids,
        "geographic_holdout": {"train_regions": geo_train, "test_regions": geo_test},
        "temporal_holdout": {
            "train_end": TRAIN_END.date().isoformat(),
            "val_end": VAL_END.date().isoformat(),
            "named_holdout": "2022-05-09/2022-06-21",
        },
        "leaks": {"train_test": leak_tt, "train_val": leak_tv, "val_test": leak_vt},
    }
    (out_dir / "train_events.json").write_text(json.dumps({"event_ids": train_ids}, indent=2), encoding="utf-8")
    (out_dir / "validation_events.json").write_text(json.dumps({"event_ids": val_ids}, indent=2), encoding="utf-8")
    (out_dir / "test_events.json").write_text(json.dumps({"event_ids": test_ids}, indent=2), encoding="utf-8")
    (out_dir / "geographic_holdout.json").write_text(json.dumps(payload["geographic_holdout"], indent=2), encoding="utf-8")
    (out_dir / "temporal_holdout.json").write_text(json.dumps(payload["temporal_holdout"], indent=2), encoding="utf-8")
    (out_dir / "splits.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
