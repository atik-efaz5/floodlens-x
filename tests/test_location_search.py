"""Unit tests for location search service and providers."""

import pytest

from floodlens.application.location_search import (
    DemoGeocodingProvider,
    LocationSearchResult,
    LocationSearchService,
    parse_coordinate_query,
)


class MockGeocodingProvider:
    provider_name = "mock"

    def __init__(self, results):
        self._results = results
        self.last_query = None

    def search(self, query: str):
        self.last_query = query
        return self._results


def test_valid_search_query():
    service = LocationSearchService(DemoGeocodingProvider())
    payload = service.search("Dhaka")
    assert payload["query"] == "Dhaka"
    assert len(payload["results"]) >= 1
    assert payload["results"][0]["display_name"].startswith("Dhaka")
    assert -90.0 <= payload["results"][0]["latitude"] <= 90.0
    assert -180.0 <= payload["results"][0]["longitude"] <= 180.0


def test_empty_query_rejection():
    service = LocationSearchService(DemoGeocodingProvider())
    with pytest.raises(ValueError, match="must not be empty"):
        service.search("   ")


def test_no_result_response():
    service = LocationSearchService(DemoGeocodingProvider())
    payload = service.search("Atlantis Underwater City")
    assert payload["results"] == []


def test_multiple_search_results():
    provider = MockGeocodingProvider(
        [
            LocationSearchResult("mirpur", "Mirpur 10", 23.8, 90.36, "neighbourhood"),
            LocationSearchResult("mirpur", "Mirpur", 23.82, 90.37, "suburb"),
        ]
    )
    service = LocationSearchService(provider)
    payload = service.search("mirpur")
    assert len(payload["results"]) == 2


def test_valid_latitude_range_enforced():
    provider = MockGeocodingProvider(
        [LocationSearchResult("bad", "Bad Lat", 95.0, 90.0)]
    )
    service = LocationSearchService(provider)
    with pytest.raises(ValueError, match="Invalid latitude"):
        service.search("bad")


def test_valid_longitude_range_enforced():
    provider = MockGeocodingProvider(
        [LocationSearchResult("bad", "Bad Lon", 23.0, 200.0)]
    )
    service = LocationSearchService(provider)
    with pytest.raises(ValueError, match="Invalid longitude"):
        service.search("bad")


def test_parse_coordinate_query():
    result = parse_coordinate_query("24.95, 91.35")
    assert result is not None
    assert result.latitude == pytest.approx(24.95)
    assert result.longitude == pytest.approx(91.35)
    assert result.place_type == "coordinates"
