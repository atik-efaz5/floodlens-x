"""Tests for city registry service."""

import pytest

from floodlens.application.city_registry import CityRegistry
from floodlens.application.geospatial import (
    CityMetadata,
    GeographicBounds,
    GridReference,
    ScenarioMetadataV2,
    DEFAULT_VISUALIZATION_LAYERS,
)


@pytest.fixture
def sample_city():
    """Create a sample city for testing."""
    bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
    return CityMetadata(
        city_id="sunamganj",
        name="Sunamganj",
        country="Bangladesh",
        region="Sunamganj District",
        center_lat=24.95,
        center_lon=91.35,
        bounds=bounds,
        is_default_city=True,
    )


@pytest.fixture
def sample_city_2():
    """Create a second sample city for testing."""
    bounds = GeographicBounds(west=90.0, south=23.5, east=90.8, north=24.1)
    return CityMetadata(
        city_id="dhaka",
        name="Dhaka",
        country="Bangladesh",
        region="Dhaka Division",
        center_lat=23.8103,
        center_lon=90.4125,
        bounds=bounds,
        is_default_city=False,
    )


@pytest.fixture
def registry():
    """Create a fresh registry for each test."""
    return CityRegistry()


class TestCityRegistry:
    """Tests for CityRegistry."""

    def test_register_city(self, registry, sample_city):
        """Test registering a city."""
        registry.register_city(sample_city)
        assert registry.has_city("sunamganj")

    def test_get_city(self, registry, sample_city):
        """Test retrieving a city."""
        registry.register_city(sample_city)
        retrieved = registry.get_city("sunamganj")
        assert retrieved.city_id == "sunamganj"
        assert retrieved.name == "Sunamganj"

    def test_get_nonexistent_city_raises_error(self, registry):
        """Test that getting a nonexistent city raises KeyError."""
        with pytest.raises(KeyError, match="not found"):
            registry.get_city("nonexistent")

    def test_list_cities_empty(self, registry):
        """Test listing cities from empty registry."""
        cities = registry.list_cities()
        assert cities == []

    def test_list_cities(self, registry, sample_city, sample_city_2):
        """Test listing all registered cities."""
        registry.register_city(sample_city)
        registry.register_city(sample_city_2)
        cities = registry.list_cities()
        assert len(cities) == 2
        city_ids = [city.city_id for city in cities]
        assert "sunamganj" in city_ids
        assert "dhaka" in city_ids

    def test_get_default_city(self, registry, sample_city):
        """Test retrieving the default city."""
        registry.register_city(sample_city)
        default = registry.get_default_city()
        assert default.city_id == "sunamganj"
        assert default.is_default_city is True

    def test_get_default_city_no_default_raises_error(self, registry, sample_city_2):
        """Test that getting default when none is set raises ValueError."""
        registry.register_city(sample_city_2)
        with pytest.raises(ValueError, match="No default city"):
            registry.get_default_city()

    def test_cannot_register_duplicate_city(self, registry, sample_city):
        """Test that registering duplicate city raises error."""
        registry.register_city(sample_city)
        with pytest.raises(ValueError, match="already registered"):
            registry.register_city(sample_city)

    def test_cannot_set_multiple_default_cities(self, registry, sample_city, sample_city_2):
        """Test that only one city can be default."""
        registry.register_city(sample_city)

        default_dhaka = CityMetadata(
            city_id="dhaka",
            name="Dhaka",
            country="Bangladesh",
            region="Dhaka Division",
            center_lat=23.8103,
            center_lon=90.4125,
            bounds=sample_city_2.bounds,
            is_default_city=True,
        )
        with pytest.raises(ValueError, match="Default city already set"):
            registry.register_city(default_dhaka)

    def test_register_scenario(self, registry, sample_city):
        """Test registering a scenario for a city."""
        registry.register_city(sample_city)
        scenario = ScenarioMetadataV2(
            scenario_id="baseline",
            city_id="sunamganj",
            name="Baseline Scenario",
            modeled_status=True,
        )
        registry.register_scenario(scenario)

    def test_get_scenarios_for_city(self, registry, sample_city):
        """Test retrieving scenarios for a city."""
        registry.register_city(sample_city)
        scenario1 = ScenarioMetadataV2(
            scenario_id="baseline",
            city_id="sunamganj",
            name="Baseline Scenario",
        )
        scenario2 = ScenarioMetadataV2(
            scenario_id="flood_2023",
            city_id="sunamganj",
            name="2023 Flood Event",
        )
        registry.register_scenario(scenario1)
        registry.register_scenario(scenario2)

        scenarios = registry.get_scenarios_for_city("sunamganj")
        assert len(scenarios) == 2
        scenario_ids = [s.scenario_id for s in scenarios]
        assert "baseline" in scenario_ids
        assert "flood_2023" in scenario_ids

    def test_get_scenarios_for_nonexistent_city(self, registry):
        """Test that getting scenarios for nonexistent city raises KeyError."""
        with pytest.raises(KeyError, match="not found"):
            registry.get_scenarios_for_city("nonexistent")

    def test_register_scenario_for_nonexistent_city_raises_error(self, registry):
        """Test that registering scenario for nonexistent city raises KeyError."""
        scenario = ScenarioMetadataV2(
            scenario_id="baseline",
            city_id="nonexistent",
            name="Baseline Scenario",
        )
        with pytest.raises(KeyError, match="not found"):
            registry.register_scenario(scenario)

    def test_cannot_register_duplicate_scenario(self, registry, sample_city):
        """Test that duplicate scenarios for same city are rejected."""
        registry.register_city(sample_city)
        scenario = ScenarioMetadataV2(
            scenario_id="baseline",
            city_id="sunamganj",
            name="Baseline Scenario",
        )
        registry.register_scenario(scenario)

        with pytest.raises(ValueError, match="already exists"):
            registry.register_scenario(scenario)

    def test_has_city(self, registry, sample_city):
        """Test has_city method."""
        assert not registry.has_city("sunamganj")
        registry.register_city(sample_city)
        assert registry.has_city("sunamganj")
        assert not registry.has_city("nonexistent")


class TestCityData:
    """Tests for pre-configured city data."""

    def test_create_city_registry_has_three_cities(self):
        """Test that city_data creates registry with three cities."""
        from floodlens.application.city_data import create_city_registry

        registry = create_city_registry()
        cities = registry.list_cities()
        assert len(cities) == 3

    def test_sunamganj_is_default(self):
        """Test that Sunamganj is marked as default city."""
        from floodlens.application.city_data import create_city_registry

        registry = create_city_registry()
        default_city = registry.get_default_city()
        assert default_city.city_id == "sunamganj"

    def test_sunamganj_metadata_valid(self):
        """Test Sunamganj metadata is valid."""
        from floodlens.application.city_data import create_city_registry

        registry = create_city_registry()
        sunamganj = registry.get_city("sunamganj")
        assert sunamganj.name == "Sunamganj"
        assert sunamganj.country == "Bangladesh"
        assert sunamganj.center_lat == 24.95
        assert sunamganj.center_lon == 91.35
        assert sunamganj.bounds.west == 91.20
        assert sunamganj.bounds.east == 91.50

    def test_dhaka_metadata_valid(self):
        """Test Dhaka metadata is valid."""
        from floodlens.application.city_data import create_city_registry

        registry = create_city_registry()
        dhaka = registry.get_city("dhaka")
        assert dhaka.name == "Dhaka"
        assert dhaka.country == "Bangladesh"
        assert dhaka.center_lat == 23.8103
        assert dhaka.center_lon == 90.4125

    def test_sylhet_metadata_valid(self):
        """Test Sylhet metadata is valid."""
        from floodlens.application.city_data import create_city_registry

        registry = create_city_registry()
        sylhet = registry.get_city("sylhet")
        assert sylhet.name == "Sylhet"
        assert sylhet.country == "Bangladesh"
        assert sylhet.center_lat == 24.8
        assert sylhet.center_lon == 91.9

    def test_all_cities_have_grid_metadata(self):
        """Test all cities have grid metadata."""
        from floodlens.application.city_data import create_city_registry

        registry = create_city_registry()
        for city in registry.list_cities():
            assert city.grid_metadata is not None
            assert city.grid_metadata.nx > 0
            assert city.grid_metadata.ny > 0
