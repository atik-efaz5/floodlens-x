"""ForecastSample schema and dataset versioning."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from floodlens.application.forecast import HORIZONS_H

DATASET_VERSION = "phase4.2-v0"
LOOKBACK_HOURS = 24
ISSUE_STRIDE_HOURS = 6
HORIZONS = tuple(HORIZONS_H)
TRACK_A = "A"
TRACK_B = "B"
LABEL_MODELLED = "MODELLED"
LABEL_OBSERVED = "OBSERVED"


def _dict(obj) -> dict:
    return {k: v for k, v in asdict(obj).items()}


@dataclass
class ForecastSample:
    city_id: str
    issue_time: str
    horizon_hours: int
    valid_at: str
    x_precip_hourly: List[float]
    x_precip_hourly_kind: List[str]
    x_precip_forecast_to_h: Optional[float]
    x_precip_forecast_issued_at: Optional[str]
    x_antecedent_24h: float
    x_antecedent_72h: Optional[float]
    x_dem_stats: Optional[Dict[str, Optional[float]]]
    x_glofas_q_lookback: Optional[List[Optional[float]]]
    y_track_a: Optional[int]
    y_track_b: Optional[int]
    y_track_b_available: bool
    lookback_complete_frac: float
    label_source: str
    label_kind: str
    issue_precip_forecast_id: Optional[str]
    dataset_version: str = DATASET_VERSION
    split: Optional[str] = None
    missing_flags: Dict[str, bool] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return _dict(self)

    @classmethod
    def from_dict(cls, row: dict) -> "ForecastSample":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in row.items() if k in known}
        return cls(**payload)
