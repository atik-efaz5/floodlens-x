"""Tests for city metadata models and validation."""

import pytest
import numpy as np

from floodlens.application.geospatial import (
    CityMetadata,
    GeographicBounds,
    GridReference,
    ScenarioMetadataV2,
    DEFAULT_VISUALIZATION_LAYERS,
)


class TestGeographicBounds:
    """Tests for GeographicBounds model."""

    def test_valid_bounds(self):
        """Test creation of valid geographic bounds."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        assert bounds.west == 91.20
        assert bounds.south == 24.80
        assert bounds.east == 91.50
        assert bounds.north == 25.10

    def test_bounds_to_dict(self):
        """Test conversion of bounds to dictionary."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        result = bounds.to_dict()
        assert result == {
            "west": 91.20,
            "south": 24.80,
            "east": 91.50,
            "north": 25.10,
        }


class TestGridReference:
    """Tests for GridReference model."""

    def test_valid_grid_reference(self):
        """Test creation of valid grid reference."""
        grid = GridReference(
            nx=50, ny=50, dx=240.0, dy=240.0, origin_x=91.20, origin_y=24.80
        )
        assert grid.nx == 50
        assert grid.ny == 50
        assert grid.dx == 240.0
        assert grid.dy == 240.0

    def test_grid_reference_to_dict(self):
        """Test conversion to dictionary."""
        grid = GridReference(
            nx=50, ny=50, dx=240.0, dy=240.0, origin_x=91.20, origin_y=24.80
        )
        result = grid.to_dict()
        assert result["nx"] == 50
        assert result["ny"] == 50
        assert result["dx"] == 240.0
        assert result["dy"] == 240.0
        assert result["crs"] == "EPSG:4326"

    def test_grid_nx_must_be_positive(self):
        """Test that nx must be positive."""
        with pytest.raises(ValueError, match="positive"):
            GridReference(
                nx=0, ny=50, dx=240.0, dy=240.0, origin_x=91.20, origin_y=24.80
            )

    def test_grid_ny_must_be_positive(self):
        """Test that ny must be positive."""
        with pytest.raises(ValueError, match="positive"):
            GridReference(
                nx=50, ny=-1, dx=240.0, dy=240.0, origin_x=91.20, origin_y=24.80
            )

    def test_grid_dx_must_be_positive(self):
        """Test that dx must be positive."""
        with pytest.raises(ValueError, match="positive"):
            GridReference(
                nx=50, ny=50, dx=-240.0, dy=240.0, origin_x=91.20, origin_y=24.80
            )

    def test_grid_dy_must_be_positive(self):
        """Test that dy must be positive."""
        with pytest.raises(ValueError, match="positive"):
            GridReference(
                nx=50, ny=50, dx=240.0, dy=0.0, origin_x=91.20, origin_y=24.80
            )

    def test_grid_crs_must_not_be_empty(self):
        """Test that CRS must not be empty."""
        with pytest.raises(ValueError, match="CRS"):
            GridReference(
                nx=50, ny=50, dx=240.0, dy=240.0, origin_x=91.20, origin_y=24.80, crs=""
            )


class TestCityMetadata:
    """Tests for CityMetadata model."""

    def test_valid_city_metadata(self):
        """Test creation of valid city metadata."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        city = CityMetadata(
            city_id="sunamganj",
            name="Sunamganj",
            country="Bangladesh",
            region="Sunamganj District",
            center_lat=24.95,
            center_lon=91.35,
            bounds=bounds,
            is_default_city=True,
        )
        assert city.city_id == "sunamganj"
        assert city.name == "Sunamganj"
        assert city.is_default_city is True

    def test_city_to_dict(self):
        """Test conversion to dictionary."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        city = CityMetadata(
            city_id="sunamganj",
            name="Sunamganj",
            country="Bangladesh",
            region="Sunamganj District",
            center_lat=24.95,
            center_lon=91.35,
            bounds=bounds,
        )
        result = city.to_dict()
        assert result["city_id"] == "sunamganj"
        assert result["name"] == "Sunamganj"
        assert result["center_lat"] == 24.95
        assert result["center_lon"] == 91.35
        assert "bounds" in result

    def test_city_id_cannot_be_empty(self):
        """Test that city_id cannot be empty."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        with pytest.raises(ValueError, match="city_id"):
            CityMetadata(
                city_id="",
                name="Sunamganj",
                country="Bangladesh",
                region="Sunamganj District",
                center_lat=24.95,
                center_lon=91.35,
                bounds=bounds,
            )

    def test_name_cannot_be_empty(self):
        """Test that name cannot be empty."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        with pytest.raises(ValueError, match="name"):
            CityMetadata(
                city_id="sunamganj",
                name="",
                country="Bangladesh",
                region="Sunamganj District",
                center_lat=24.95,
                center_lon=91.35,
                bounds=bounds,
            )

    def test_country_cannot_be_empty(self):
        """Test that country cannot be empty."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        with pytest.raises(ValueError, match="country"):
            CityMetadata(
                city_id="sunamganj",
                name="Sunamganj",
                country="",
                region="Sunamganj District",
                center_lat=24.95,
                center_lon=91.35,
                bounds=bounds,
            )

    def test_region_cannot_be_empty(self):
        """Test that region cannot be empty."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        with pytest.raises(ValueError, match="region"):
            CityMetadata(
                city_id="sunamganj",
                name="Sunamganj",
                country="Bangladesh",
                region="",
                center_lat=24.95,
                center_lon=91.35,
                bounds=bounds,
            )

    def test_center_lat_must_be_finite(self):
        """Test that center_lat must be finite."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        with pytest.raises(ValueError, match="finite"):
            CityMetadata(
                city_id="sunamganj",
                name="Sunamganj",
                country="Bangladesh",
                region="Sunamganj District",
                center_lat=np.inf,
                center_lon=91.35,
                bounds=bounds,
            )

    def test_center_lon_must_be_finite(self):
        """Test that center_lon must be finite."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        with pytest.raises(ValueError, match="finite"):
            CityMetadata(
                city_id="sunamganj",
                name="Sunamganj",
                country="Bangladesh",
                region="Sunamganj District",
                center_lat=24.95,
                center_lon=np.nan,
                bounds=bounds,
            )

    def test_center_lat_must_be_in_valid_range(self):
        """Test that center_lat must be in [-90, 90]."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        with pytest.raises(ValueError, match="center_lat"):
            CityMetadata(
                city_id="sunamganj",
                name="Sunamganj",
                country="Bangladesh",
                region="Sunamganj District",
                center_lat=95.0,
                center_lon=91.35,
                bounds=bounds,
            )

    def test_center_lon_must_be_in_valid_range(self):
        """Test that center_lon must be in [-180, 180]."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        with pytest.raises(ValueError, match="center_lon"):
            CityMetadata(
                city_id="sunamganj",
                name="Sunamganj",
                country="Bangladesh",
                region="Sunamganj District",
                center_lat=24.95,
                center_lon=200.0,
                bounds=bounds,
            )

    def test_bounds_west_must_be_less_than_east(self):
        """Test that bounds.west < bounds.east."""
        bounds = GeographicBounds(west=91.50, south=24.80, east=91.20, north=25.10)
        with pytest.raises(ValueError, match="west.*east"):
            CityMetadata(
                city_id="sunamganj",
                name="Sunamganj",
                country="Bangladesh",
                region="Sunamganj District",
                center_lat=24.95,
                center_lon=91.35,
                bounds=bounds,
            )

    def test_bounds_south_must_be_less_than_north(self):
        """Test that bounds.south < bounds.north."""
        bounds = GeographicBounds(west=91.20, south=25.10, east=91.50, north=24.80)
        with pytest.raises(ValueError, match="south.*north"):
            CityMetadata(
                city_id="sunamganj",
                name="Sunamganj",
                country="Bangladesh",
                region="Sunamganj District",
                center_lat=24.95,
                center_lon=91.35,
                bounds=bounds,
            )

    def test_default_zoom_must_be_within_range(self):
        """Test that default_zoom is between min_zoom and max_zoom."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        with pytest.raises(ValueError, match="default_zoom"):
            CityMetadata(
                city_id="sunamganj",
                name="Sunamganj",
                country="Bangladesh",
                region="Sunamganj District",
                center_lat=24.95,
                center_lon=91.35,
                bounds=bounds,
                default_zoom=20,
                min_zoom=8,
                max_zoom=16,
            )

    def test_zoom_levels_must_be_valid(self):
        """Test that zoom levels are in valid range."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        with pytest.raises(ValueError, match="Zoom"):
            CityMetadata(
                city_id="sunamganj",
                name="Sunamganj",
                country="Bangladesh",
                region="Sunamganj District",
                center_lat=24.95,
                center_lon=91.35,
                bounds=bounds,
                min_zoom=-1,
            )

    def test_crs_cannot_be_empty(self):
        """Test that CRS cannot be empty."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        with pytest.raises(ValueError, match="CRS"):
            CityMetadata(
                city_id="sunamganj",
                name="Sunamganj",
                country="Bangladesh",
                region="Sunamganj District",
                center_lat=24.95,
                center_lon=91.35,
                bounds=bounds,
                crs="",
            )

    def test_supported_layers_cannot_be_empty(self):
        """Test that supported_layers cannot be empty."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        with pytest.raises(ValueError, match="supported_layers"):
            CityMetadata(
                city_id="sunamganj",
                name="Sunamganj",
                country="Bangladesh",
                region="Sunamganj District",
                center_lat=24.95,
                center_lon=91.35,
                bounds=bounds,
                supported_layers=(),
            )

    def test_city_with_grid_metadata(self):
        """Test city with grid metadata."""
        bounds = GeographicBounds(west=91.20, south=24.80, east=91.50, north=25.10)
        grid = GridReference(
            nx=50, ny=50, dx=240.0, dy=240.0, origin_x=91.20, origin_y=24.80
        )
        city = CityMetadata(
            city_id="sunamganj",
            name="Sunamganj",
            country="Bangladesh",
            region="Sunamganj District",
            center_lat=24.95,
            center_lon=91.35,
            bounds=bounds,
            grid_metadata=grid,
        )
        result = city.to_dict()
        assert result["grid_metadata"] is not None
        assert result["grid_metadata"]["nx"] == 50


class TestScenarioMetadataV2:
    """Tests for ScenarioMetadataV2 model."""

    def test_valid_scenario_metadata(self):
        """Test creation of valid scenario metadata."""
        scenario = ScenarioMetadataV2(
            scenario_id="sunamganj_baseline",
            city_id="sunamganj",
            name="Baseline Scenario",
            modeled_status=True,
            simulated_status=False,
        )
        assert scenario.scenario_id == "sunamganj_baseline"
        assert scenario.city_id == "sunamganj"
        assert scenario.name == "Baseline Scenario"

    def test_scenario_to_dict(self):
        """Test conversion to dictionary."""
        scenario = ScenarioMetadataV2(
            scenario_id="sunamganj_baseline",
            city_id="sunamganj",
            name="Baseline Scenario",
        )
        result = scenario.to_dict()
        assert result["scenario_id"] == "sunamganj_baseline"
        assert result["city_id"] == "sunamganj"
        assert result["name"] == "Baseline Scenario"

    def test_scenario_id_cannot_be_empty(self):
        """Test that scenario_id cannot be empty."""
        with pytest.raises(ValueError, match="scenario_id"):
            ScenarioMetadataV2(
                scenario_id="",
                city_id="sunamganj",
                name="Baseline Scenario",
            )

    def test_city_id_cannot_be_empty(self):
        """Test that city_id cannot be empty."""
        with pytest.raises(ValueError, match="city_id"):
            ScenarioMetadataV2(
                scenario_id="sunamganj_baseline",
                city_id="",
                name="Baseline Scenario",
            )

    def test_name_cannot_be_empty(self):
        """Test that name cannot be empty."""
        with pytest.raises(ValueError, match="name"):
            ScenarioMetadataV2(
                scenario_id="sunamganj_baseline",
                city_id="sunamganj",
                name="",
            )
