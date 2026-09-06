"""Leakage-resistant temporal and geographic splits."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional, Sequence, Set

from floodlens.ml.leakage import parse_ts
from floodlens.ml.schema import ForecastSample

TRAIN_END = datetime(2022, 1, 1, tzinfo=timezone.utc)
VAL_END = datetime(2023, 1, 1, tzinfo=timezone.utc)
# Named holdout (2022 NE Bangladesh monsoon) is test-only even though the year is val.
NAMED_HOLDOUT = (
    datetime(2022, 5, 9, tzinfo=timezone.utc),
    datetime(2022, 6, 22, tzinfo=timezone.utc),
)
BD_CITIES = frozenset({"dhaka", "sunamganj", "sylhet"})


def in_named_holdout(stamp: datetime) -> bool:
    start, end = NAMED_HOLDOUT
    return start <= stamp < end


def temporal_split(issue_time: str) -> str:
    stamp = parse_ts(issue_time)
    if in_named_holdout(stamp):
        return "test"
    if stamp < TRAIN_END:
        return "train"
    if stamp < VAL_END:
        return "val"
    return "test"


def geographic_split(city_id: str, train_cities: Optional[Set[str]] = None) -> str:
    """Hold BD AOIs out when training on other basins."""
    allowed = train_cities if train_cities is not None else (set() - BD_CITIES)
    if city_id in BD_CITIES and city_id not in allowed:
        return "test"
    return "train"


def assign_temporal(samples: Sequence[ForecastSample]) -> List[ForecastSample]:
    out = []
    for sample in samples:
        sample.split = temporal_split(sample.issue_time)
        out.append(sample)
    return list(out)


def event_straddle_violations(samples: Iterable[ForecastSample]) -> List[str]:
    """Same named holdout window must not appear in train."""
    bad = []
    for sample in samples:
        stamp = parse_ts(sample.issue_time)
        if in_named_holdout(stamp) and sample.split == "train":
            bad.append(f"{sample.city_id} {sample.issue_time}")
    return bad


def by_split(samples: Sequence[ForecastSample], name: str) -> List[ForecastSample]:
    return [s for s in samples if s.split == name]
