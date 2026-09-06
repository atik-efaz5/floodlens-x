"""SpatialForecastSample and raster metadata contract.

Do not stretch AOI ``ForecastSample`` to rasters. Arrays stay in npy/GeoTIFF;
JSON holds metadata only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

SPATIAL_DATASET_VERSION = "phase55-gfm-aoi-v0.2"
SPATIAL_DATASET_VERSION_V2 = "phase6.5-gfm-spatial-v2"
SPATIAL_DATASET_VERSION_V21 = "phase6.5-gfm-spatial-v2.1"
SPATIAL_MODEL_ID = "AI-SPATIAL-OCCURRENCE-v0.1"
SPATIAL_MODEL_ID_V2 = "AI-SPATIAL-OCCURRENCE-v2"
GRID_SIZE = 32
GRID_SIZE_V2 = 64
HORIZON_HOURS = 192  # 8-day GFM scene slot; not 6/12/24 h
FLOOD_FRACTION_TAU = 0.25
LABEL_OBSERVED = "OBSERVED"
LABEL_DERIVED = "DERIVED"
LABEL_MODELLED = "MODELLED"
LABEL_SIMULATED = "SIMULATED"
UNKNOWN = 255
CRS = "EPSG:4326"
TARGET_RESOLUTION_M = 500.0
MAX_CELLS = 32  # working tensor; Sunamganj ~500 m, larger AOIs coarsened

SPATIAL_DIR = (
    Path(__file__).resolve().parents[2] / "application" / "data" / "ml" / "spatial"
)


def _dict(obj) -> dict:
    return {k: v for k, v in asdict(obj).items()}


def raster_metadata(
    *,
    dataset_id: str,
    variable: str,
    timestamp: str,
    valid_at: str,
    crs: str,
    resolution: float,
    bounds: Sequence[float],
    width: int,
    height: int,
    nodata: float,
    units: str,
    source: str,
    data_status: str,
    label_kind: str,
    artifact_uri: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> dict:
    """JSON-only raster contract. No ndarray in this dict."""
    payload = {
        "dataset_id": dataset_id,
        "variable": variable,
        "timestamp": timestamp,
        "valid_at": valid_at,
        "crs": crs,
        "resolution": resolution,
        "bounds": list(bounds),
        "width": int(width),
        "height": int(height),
        "nodata": nodata,
        "units": units,
        "source": source,
        "data_status": data_status,
        "label_kind": label_kind,
        "artifact_uri": artifact_uri,
    }
    if extra:
        payload["extra"] = extra
    return payload


@dataclass
class SpatialForecastSample:
    """One city AOI tile: features known at issue time, map label at valid_at."""

    city_id: str
    issue_time: str
    valid_at: str
    horizon_hours: int
    # (H, W) uint8: 1 flood, 0 dry, 255 unknown. Never code unknown as dry.
    y_flood: np.ndarray
    y_flood_frac: np.ndarray
    x_precip_hourly: List[float]
    x_precip_hourly_kind: List[str]
    x_antecedent_24h: float
    x_antecedent_72h: Optional[float]
    x_glofas_q_lookback: Optional[List[Optional[float]]]
    x_persistence: Optional[np.ndarray]
    x_dem: Optional[np.ndarray]
    precip_is_aoi_point: bool
    q_is_glofas_cell: bool
    dem_present: bool
    label_kind: str
    label_source: str
    lookback_complete_frac: float
    crs: str = CRS
    bounds: List[float] = field(default_factory=list)
    resolution_m: float = TARGET_RESOLUTION_M
    dataset_version: str = SPATIAL_DATASET_VERSION
    split: Optional[str] = None
    scene_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_meta(self) -> dict:
        meta = _dict(self)
        meta.pop("y_flood", None)
        meta.pop("y_flood_frac", None)
        meta.pop("x_persistence", None)
        meta.pop("x_dem", None)
        extra_maps = dict(meta.get("extra") or {})
        for key in (
            "precip_24h_map",
            "precip_72h_map",
            "precip_intensity_24h_map",
            "precip_cube_lattice",
            "slope",
            "river_distance",
            "river_mask",
            "height_above_river",
        ):
            extra_maps.pop(key, None)
        meta["extra"] = extra_maps
        h, w = np.asarray(self.y_flood).shape
        meta["raster"] = raster_metadata(
            dataset_id=self.dataset_version,
            variable="flood_occurrence",
            timestamp=self.issue_time,
            valid_at=self.valid_at,
            crs=self.crs,
            resolution=self.resolution_m,
            bounds=self.bounds,
            width=w,
            height=h,
            nodata=UNKNOWN,
            units="class",
            source=self.label_source,
            data_status="REAL" if self.label_kind == LABEL_OBSERVED else self.label_kind,
            label_kind=self.label_kind,
            extra={"scene_id": self.scene_id, "tau": FLOOD_FRACTION_TAU},
        )
        return meta

    def valid_mask(self) -> np.ndarray:
        return np.asarray(self.y_flood) != UNKNOWN

    def y_binary(self) -> np.ndarray:
        y = np.asarray(self.y_flood)
        out = np.full(y.shape, np.nan, dtype=np.float64)
        out[y == 0] = 0.0
        out[y == 1] = 1.0
        return out
