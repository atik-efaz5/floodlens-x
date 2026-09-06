"""Feature-cube channel catalog. A channel is spatial only if neighbors can differ."""

from __future__ import annotations

from typing import Dict, Optional

from floodlens.ml.spatial.channel_audit import CONSTANT, MISSING, SPATIAL, TEMPORAL_ONLY

FEATURE_SPECS: Dict[str, dict] = {
    "precip_24h": {
        "units": "mm",
        "source": "open-meteo-archive / ERA5-Land lattice IDW",
        "spatial_resolution": "~11 km lattice onto working grid",
        "temporal_resolution": "24 h accumulation ending at t0",
        "valid_range": [0, None],
        "missing_policy": "drop sample if cube completeness < 0.5; else IDW",
    },
    "precip_72h": {
        "units": "mm",
        "source": "open-meteo-archive / ERA5-Land lattice IDW",
        "spatial_resolution": "~11 km lattice onto working grid",
        "temporal_resolution": "72 h accumulation ending at t0",
        "valid_range": [0, None],
        "missing_policy": "same as precip_24h",
    },
    "precip_intensity_24h": {
        "units": "mm/h",
        "source": "max hourly lattice in 24 h lookback, IDW",
        "spatial_resolution": "~11 km lattice onto working grid",
        "temporal_resolution": "hourly max over 24 h",
        "valid_range": [0, None],
        "missing_policy": "NaN hours ignored",
    },
    "dem": {
        "units": "m",
        "source": "FLOODLENS_DEM_PATH GLO-30 window or Open-Meteo elevation lattice",
        "spatial_resolution": "GLO-30 ~30 m or elevation lattice ~AOI/17",
        "temporal_resolution": "static",
        "valid_range": None,
        "missing_policy": "UNAVAILABLE; dem_present=false; not synthetic",
    },
    "slope": {
        "units": "m / cell",
        "source": "gradient of elevation",
        "spatial_resolution": "same as dem",
        "temporal_resolution": "static",
        "valid_range": [0, None],
        "missing_policy": "UNAVAILABLE if dem missing",
    },
    "river_distance": {
        "units": "degrees",
        "source": "HydroRIVERS or OSM waterways",
        "spatial_resolution": "working grid",
        "temporal_resolution": "static",
        "valid_range": [0, None],
        "missing_policy": "UNAVAILABLE if no vertices",
    },
    "height_above_river": {
        "units": "m",
        "source": "elevation minus min elevation on river-mask cells",
        "spatial_resolution": "working grid",
        "temporal_resolution": "static",
        "valid_range": None,
        "missing_policy": "UNAVAILABLE if dem or river missing",
    },
    "persistence": {
        "units": "class 0/1",
        "source": "previous completed GFM scene",
        "spatial_resolution": "working grid",
        "temporal_resolution": "previous scene before t0",
        "valid_range": [0, 1],
        "missing_policy": "NaN where previous unknown",
    },
    "log1p_q": {
        "units": "log1p m3/s",
        "source": "GloFAS via Open-Meteo",
        "spatial_resolution": "tile scalar (TEMPORAL-ONLY)",
        "temporal_resolution": "daily t-7..t-1",
        "valid_range": [0, None],
        "missing_policy": "drop if last Q missing",
    },
}


def catalog_from_audit(audit: dict) -> list:
    rows = []
    channels = audit.get("channels") or {}
    for name, spec in FEATURE_SPECS.items():
        row = dict(spec)
        row["feature_name"] = name
        info = channels.get(name) or {}
        row["class"] = info.get("class") or MISSING
        row["spatial_variance"] = info.get("spatial_variance")
        row["provenance"] = {
            "class": row["class"],
            "source": spec["source"],
            "missingness": info.get("missingness"),
        }
        rows.append(row)
    return rows


def classify_summary(audit: Optional[dict] = None) -> dict:
    audit = audit or {}
    channels = audit.get("channels") or {}
    counts = {SPATIAL: 0, TEMPORAL_ONLY: 0, CONSTANT: 0, MISSING: 0}
    for row in channels.values():
        klass = row.get("class") or MISSING
        counts[klass] = counts.get(klass, 0) + 1
    return {
        "n_spatial": int(audit.get("n_spatial") or counts[SPATIAL]),
        "n_temporal_only": counts[TEMPORAL_ONLY],
        "n_constant": counts[CONSTANT],
        "n_missing": counts[MISSING],
        "n_channels": len(channels),
    }
