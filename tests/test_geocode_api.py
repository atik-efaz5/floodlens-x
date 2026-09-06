"""API tests for GET /api/geocode/search."""

import pytest
from fastapi.testclient import TestClient

from floodlens.application.location_search import (
    LocationSearchResult,
    LocationSearchService,
)
from floodlens.application.web_server import (
    app,
    get_location_search_service,
    set_location_search_service,
)


class MockGeocodingProvider:
    provider_name = "mock"

    def __init__(self, results_by_query):
        self._results_by_query = results_by_query

    def search(self, query: str):
        return self._results_by_query.get(query.strip().lower(), [])


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def restore_service():
    original = get_location_search_service()
    yield
    set_location_search_service(original)


def test_geocode_api_valid_query(client):
    set_location_search_service(
        LocationSearchService(
            MockGeocodingProvider(
                {
                    "mirpur 10": [
                        LocationSearchResult(
                            "Mirpur 10",
                            "Mirpur 10, Dhaka",
                            23.8067,
                            90.3686,
                            "neighbourhood",
                            {"city": "Dhaka"},
                        )
                    ]
                }
            )
        )
    )

    response = client.get("/api/geocode/search", params={"q": "Mirpur 10"})
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "Mirpur 10"
    assert data["provider"] == "mock"
    assert len(data["results"]) == 1
    result = data["results"][0]
    assert set(result.keys()) >= {"display_name", "latitude", "longitude"}
    assert result["display_name"] == "Mirpur 10, Dhaka"
    assert result["place_type"] == "neighbourhood"
    assert result["administrative"]["city"] == "Dhaka"


def test_geocode_api_empty_query_rejection(client):
    response = client.get("/api/geocode/search", params={"q": "   "})
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_geocode_api_no_results(client):
    set_location_search_service(
        LocationSearchService(MockGeocodingProvider({}))
    )
    response = client.get("/api/geocode/search", params={"q": "Nowhere"})
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_geocode_api_coordinate_query(client):
    response = client.get("/api/geocode/search", params={"q": "24.95, 91.35"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["place_type"] == "coordinates"
    assert data["results"][0]["latitude"] == pytest.approx(24.95)
    assert data["results"][0]["longitude"] == pytest.approx(91.35)
