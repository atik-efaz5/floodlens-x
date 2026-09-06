"""City registry service for managing multi-city metadata."""

from __future__ import annotations

from typing import Dict, List, Optional

from floodlens.application.geospatial import CityMetadata, ScenarioMetadataV2


class CityRegistry:
    """Data-driven registry for city metadata and associated scenarios."""

    def __init__(self):
        """Initialize the registry with empty storage."""
        self._cities: Dict[str, CityMetadata] = {}
        self._scenarios: Dict[str, List[ScenarioMetadataV2]] = {}
        self._default_city_id: Optional[str] = None

    def register_city(self, metadata: CityMetadata) -> None:
        """Register a city with validation.

        Args:
            metadata: CityMetadata instance.

        Raises:
            ValueError: If city_id already exists or validation fails.
        """
        if metadata.city_id in self._cities:
            raise ValueError(f"City {metadata.city_id} is already registered")

        self._cities[metadata.city_id] = metadata
        if metadata.is_default_city:
            if self._default_city_id is not None:
                raise ValueError(
                    f"Default city already set to {self._default_city_id}. "
                    "Only one city can be marked as default."
                )
            self._default_city_id = metadata.city_id

        if metadata.city_id not in self._scenarios:
            self._scenarios[metadata.city_id] = []

    def get_city(self, city_id: str) -> CityMetadata:
        """Retrieve city metadata by ID.

        Args:
            city_id: The city identifier.

        Returns:
            CityMetadata instance.

        Raises:
            KeyError: If city_id not found.
        """
        if city_id not in self._cities:
            raise KeyError(f"City {city_id} not found in registry")
        return self._cities[city_id]

    def list_cities(self) -> List[CityMetadata]:
        """Return all registered cities.

        Returns:
            List of CityMetadata instances.
        """
        return list(self._cities.values())

    def get_default_city(self) -> CityMetadata:
        """Retrieve the default city.

        Returns:
            CityMetadata instance marked as default.

        Raises:
            ValueError: If no default city is set.
        """
        if self._default_city_id is None:
            raise ValueError("No default city set in registry")
        return self._cities[self._default_city_id]

    def register_scenario(self, scenario: ScenarioMetadataV2) -> None:
        """Register a scenario for a city.

        Args:
            scenario: ScenarioMetadataV2 instance.

        Raises:
            KeyError: If city_id not found.
            ValueError: If scenario_id already exists for this city.
        """
        if scenario.city_id not in self._cities:
            raise KeyError(f"City {scenario.city_id} not found. Register city first.")

        if scenario.city_id not in self._scenarios:
            self._scenarios[scenario.city_id] = []

        # Check for duplicate scenario_id within this city
        for existing in self._scenarios[scenario.city_id]:
            if existing.scenario_id == scenario.scenario_id:
                raise ValueError(
                    f"Scenario {scenario.scenario_id} already exists for city {scenario.city_id}"
                )

        self._scenarios[scenario.city_id].append(scenario)

    def get_scenarios_for_city(self, city_id: str) -> List[ScenarioMetadataV2]:
        """Retrieve all scenarios for a city.

        Args:
            city_id: The city identifier.

        Returns:
            List of ScenarioMetadataV2 instances.

        Raises:
            KeyError: If city_id not found.
        """
        if city_id not in self._cities:
            raise KeyError(f"City {city_id} not found in registry")
        return self._scenarios.get(city_id, [])

    def has_city(self, city_id: str) -> bool:
        """Check if a city is registered.

        Args:
            city_id: The city identifier.

        Returns:
            True if registered, False otherwise.
        """
        return city_id in self._cities
