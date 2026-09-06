"""Phase 4 ML package: AOI flood-occurrence models.

Does not import ``floodlens.numerical``. Does not claim operational skill
until the registry status is VALIDATED.
"""

from floodlens.ml.schema import DATASET_VERSION, LOOKBACK_HOURS, ForecastSample

__all__ = ["DATASET_VERSION", "LOOKBACK_HOURS", "ForecastSample"]
