"""Phase 5 spatial flood-occurrence dataset and models.

AOI tabular GBDT lives in ``floodlens.ml`` and is not replaced here.
A spatial model starts NOT_TRAINED and must not inherit VALIDATED status.
"""

from floodlens.ml.spatial.schema import (
    GRID_SIZE,
    HORIZON_HOURS,
    LABEL_DERIVED,
    LABEL_OBSERVED,
    SPATIAL_DATASET_VERSION,
    SpatialForecastSample,
    raster_metadata,
)

__all__ = [
    "GRID_SIZE",
    "HORIZON_HOURS",
    "LABEL_DERIVED",
    "LABEL_OBSERVED",
    "SPATIAL_DATASET_VERSION",
    "SpatialForecastSample",
    "raster_metadata",
]
