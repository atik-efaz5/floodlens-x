"""Spatial labels: OBSERVED GFM class maps. Unknown is never dry."""

from __future__ import annotations

from typing import Tuple

import numpy as np

from floodlens.ml.spatial.schema import FLOOD_FRACTION_TAU, UNKNOWN

# GFM ensemble_flood_extent (uint8): 0 dry, 1 flood, 255 nodata/exclusion.
GFM_DRY = 0
GFM_FLOOD = 1
GFM_NODATA = 255


def encode_binary(flood_frac: np.ndarray, valid: np.ndarray, tau: float = FLOOD_FRACTION_TAU) -> np.ndarray:
    """uint8 class map: 1 if frac>=tau, 0 if valid below tau, 255 unknown."""
    out = np.full(flood_frac.shape, UNKNOWN, dtype=np.uint8)
    ok = np.asarray(valid, dtype=bool)
    wet = np.asarray(flood_frac, dtype=np.float64) >= float(tau)
    out[ok & ~wet] = 0
    out[ok & wet] = 1
    return out


def mix_kinds_error(kinds) -> str | None:
    uniq = {k for k in kinds if k}
    if len(uniq) > 1:
        return f"do not mix label kinds in one metric table: {sorted(uniq)}"
    return None


def scene_quality_table(index: dict) -> list:
    """Per-scene / per-city label quality. Nodata is unknown, never dry."""
    rows = []
    for scene in index.get("scenes") or []:
        for city_id, stats in (scene.get("cities") or {}).items():
            n_flood = int(stats.get("n_flood") or 0)
            n_dry = int(stats.get("n_dry") or 0)
            n_unknown = int(stats.get("n_unknown") or 0)
            valid = n_flood + n_dry
            total = valid + n_unknown
            rows.append(
                {
                    "scene_id": scene.get("id"),
                    "datetime": scene.get("datetime"),
                    "city_id": city_id,
                    "valid_pixels": valid,
                    "nodata_or_unknown": n_unknown,
                    "positive_flood_pixels": n_flood,
                    "negative_pixels": n_dry,
                    "unknown_pixels": n_unknown,
                    "valid_frac": stats.get("valid_frac"),
                    "unknown_fraction": (n_unknown / total) if total else None,
                    "nodata_coded_as_dry": False,
                }
            )
    return rows


def valid_prevalence(y: np.ndarray) -> Tuple[int, float]:
    arr = np.asarray(y)
    mask = arr != UNKNOWN
    n = int(np.sum(mask))
    if n == 0:
        return 0, float("nan")
    return n, float(np.mean(arr[mask] == 1))
