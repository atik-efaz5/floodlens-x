"""Integration tests for city API endpoints."""

import pytest
from fastapi.testclient import TestClient

from floodlens.application.web_server import app, set_session, get_session
from floodlens.application.geospatial import ScenarioSession


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def session_setup():
    """Set up a default session for tests."""
    session = ScenarioSession.default_sunamganj()
    set_session(session)
    yield
    set_session(None)


class TestCitiesAPI:
    """Tests for the /api/cities endpoints."""

    def test_get_cities_returns_list(self, client):
        """Test GET /api/cities returns list of cities."""
        response = client.get("/api/cities")
        assert response.status_code == 200

        data = response.json()
        assert "cities" in data
        assert "count" in data
        assert isinstance(data["cities"], list)
        assert len(data["cities"]) == 3

    def test_get_cities_contains_sunamganj(self, client):
        """Test that Sunamganj is in the cities list."""
        response = client.get("/api/cities")
        data = response.json()
        city_ids = [city["city_id"] for city in data["cities"]]
        assert "sunamganj" in city_ids

    def test_get_cities_contains_dhaka(self, client):
        """Test that Dhaka is in the cities list."""
        response = client.get("/api/cities")
        data = response.json()
        city_ids = [city["city_id"] for city in data["cities"]]
        assert "dhaka" in city_ids

    def test_get_cities_contains_sylhet(self, client):
        """Test that Sylhet is in the cities list."""
        response = client.get("/api/cities")
        data = response.json()
        city_ids = [city["city_id"] for city in data["cities"]]
        assert "sylhet" in city_ids

    def test_get_city_returns_full_metadata(self, client):
        """Test GET /api/cities/{city_id} returns full metadata."""
        response = client.get("/api/cities/sunamganj")
        assert response.status_code == 200

        data = response.json()
        assert "city" in data
        assert "scenarios" in data
        assert "scenario_count" in data

    def test_get_city_contains_expected_fields(self, client):
        """Test that city metadata contains expected fields."""
        response = client.get("/api/cities/sunamganj")
        data = response.json()
        city = data["city"]

        assert city["city_id"] == "sunamganj"
        assert city["name"] == "Sunamganj"
        assert city["country"] == "Bangladesh"
        assert city["region"] == "Sunamganj District"
        assert "bounds" in city
        assert "center_lat" in city
        assert "center_lon" in city
        assert "grid_metadata" in city

    def test_get_city_dhaka_metadata(self, client):
        """Test Dhaka city metadata."""
        response = client.get("/api/cities/dhaka")
        assert response.status_code == 200

        data = response.json()
        city = data["city"]
        assert city["city_id"] == "dhaka"
        assert city["name"] == "Dhaka"
        assert city["center_lat"] == 23.8103
        assert city["center_lon"] == 90.4125

    def test_get_city_sylhet_metadata(self, client):
        """Test Sylhet city metadata."""
        response = client.get("/api/cities/sylhet")
        assert response.status_code == 200

        data = response.json()
        city = data["city"]
        assert city["city_id"] == "sylhet"
        assert city["name"] == "Sylhet"
        assert city["center_lat"] == 24.8
        assert city["center_lon"] == 91.9

    def test_get_nonexistent_city_returns_404(self, client):
        """Test that requesting nonexistent city returns 404."""
        response = client.get("/api/cities/nonexistent")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data

    def test_city_bounds_are_valid(self, client):
        """Test that city bounds are valid."""
        response = client.get("/api/cities/sunamganj")
        data = response.json()
        city = data["city"]
        bounds = city["bounds"]

        assert bounds["west"] < bounds["east"]
        assert bounds["south"] < bounds["north"]
        assert -180 <= bounds["west"] <= 180
        assert -180 <= bounds["east"] <= 180
        assert -90 <= bounds["south"] <= 90
        assert -90 <= bounds["north"] <= 90

    def test_grid_metadata_is_present(self, client):
        """Test that grid metadata is present for all cities."""
        response = client.get("/api/cities")
        data = response.json()

        for city in data["cities"]:
            assert city["grid_metadata"] is not None
            grid = city["grid_metadata"]
            assert grid["nx"] > 0
            assert grid["ny"] > 0
            assert grid["dx"] > 0
            assert grid["dy"] > 0
            assert "crs" in grid

    def test_sunamganj_is_default_city(self, client):
        """Test that Sunamganj is marked as default."""
        response = client.get("/api/cities/sunamganj")
        data = response.json()
        city = data["city"]
        assert city["is_default_city"] is True

    def test_backward_compatibility_scenario_metadata_endpoint(
        self, client, session_setup
    ):
        """Test that existing /api/scenario/metadata endpoint still works."""
        response = client.get("/api/scenario/metadata")
        assert response.status_code == 200

        data = response.json()
        assert "bounds" in data
        assert "center" in data
        assert "crs" in data
        assert "time_range" in data
        assert "visualization_layers" in data

    def test_backward_compatibility_scenario_run_endpoint(
        self, client, session_setup
    ):
        """Test that scenario run endpoint still works."""
        payload = {
            "nx": 30,
            "ny": 30,
            "rainfall_rate": 1.0e-5,
            "duration_seconds": 5.0,
            "scenario": "sunamganj",
        }
        response = client.post("/api/scenario/run", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "success" in data

    def test_all_visualization_layers_present(self, client):
        """Test that all visualization layers are present."""
        response = client.get("/api/cities/sunamganj")
        data = response.json()
        city = data["city"]

        expected_layers = ["depth", "velocity", "max_depth", "flood_extent"]
        assert set(city["supported_layers"]) == set(expected_layers)
