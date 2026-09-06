"""Population exposure. No fabricated counts. A real raster can plug in later."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import numpy as np


class PopulationDataProvider(ABC):
    @abstractmethod
    def expose(self, city_id: str, wet_mask: Optional[np.ndarray] = None) -> dict:
        raise NotImplementedError


class NullPopulationProvider(PopulationDataProvider):
    def expose(self, city_id: str, wet_mask: Optional[np.ndarray] = None) -> dict:
        return {
            "city_id": city_id,
            "population_exposed": None,
            "available": False,
            "reason": "Population raster not ingested; count withheld.",
        }


class DemoPopulationProvider(PopulationDataProvider):
    def expose(self, city_id: str, wet_mask: Optional[np.ndarray] = None) -> dict:
        from floodlens.application.demo_fixtures import demo_population_expose

        return demo_population_expose(city_id, wet_mask)


def get_population_provider() -> PopulationDataProvider:
    from floodlens.application.demo_fixtures import demo_fixtures_enabled

    if demo_fixtures_enabled():
        return DemoPopulationProvider()
    return NullPopulationProvider()
