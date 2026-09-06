"""Provider-independent location search for FloodLens-X geocoding."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class LocationSearchResult:
    """Structured geographic search result."""

    query: str
    display_name: str
    latitude: float
    longitude: float
    place_type: Optional[str] = None
    administrative: Optional[Dict[str, str]] = None

    def to_dict(self) -> dict:
        payload = {
            "display_name": self.display_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }
        if self.place_type is not None:
            payload["place_type"] = self.place_type
        if self.administrative is not None:
            payload["administrative"] = self.administrative
        region_id = None
        if self.administrative:
            region_id = self.administrative.get("region_id")
        if region_id:
            payload["region_id"] = region_id
        return payload


class GeocodingProvider(ABC):
    """Provider-independent geocoding contract."""

    @abstractmethod
    def search(self, query: str) -> List[LocationSearchResult]:
        """Return zero or more geographic matches for the query."""


class DemoGeocodingProvider(GeocodingProvider):
    """Deterministic demo geocoder for development and offline testing.

    This provider is explicitly labeled as demo-only. It is not a substitute
    for a production geocoder but enables local development without external APIs.
    """

    provider_name = "demo"

    _CATALOG: Tuple[Tuple[str, str, float, float, str, Dict[str, str]], ...] = (
        (
            "dhaka",
            "Dhaka, Bangladesh",
            23.8103,
            90.4125,
            "city",
            {"country": "Bangladesh", "region": "Dhaka Division", "region_id": "dhaka"},
        ),
        (
            "mirpur 10",
            "Mirpur 10, Dhaka, Bangladesh",
            23.8067,
            90.3686,
            "neighbourhood",
            {"country": "Bangladesh", "city": "Dhaka", "area": "Mirpur"},
        ),
        (
            "mirpur",
            "Mirpur, Dhaka, Bangladesh",
            23.8223,
            90.3654,
            "suburb",
            {"country": "Bangladesh", "city": "Dhaka", "area": "Mirpur"},
        ),
        (
            "sunamganj",
            "Sunamganj, Bangladesh",
            25.0658,
            91.3953,
            "city",
            {"country": "Bangladesh", "region": "Sunamganj District", "region_id": "sunamganj"},
        ),
        (
            "sylhet",
            "Sylhet, Bangladesh",
            24.8949,
            91.8687,
            "city",
            {"country": "Bangladesh", "region": "Sylhet Division", "region_id": "sylhet"},
        ),
        (
            "buriganga",
            "Buriganga River, Dhaka, Bangladesh",
            23.702,
            90.408,
            "river",
            {"country": "Bangladesh", "region_id": "dhaka", "river_id": "buriganga"},
        ),
        (
            "bangladesh",
            "Bangladesh",
            23.685,
            90.3563,
            "country",
            {"country": "Bangladesh"},
        ),
        (
            "tanguar haor",
            "Tanguar Haor, Sunamganj, Bangladesh",
            25.128,
            91.102,
            "landmark",
            {"country": "Bangladesh", "region": "Sunamganj District"},
        ),
        (
            "derai",
            "Derai Upazila, Sunamganj, Bangladesh",
            24.8842,
            91.3561,
            "upazila",
            {"country": "Bangladesh", "region": "Sunamganj District"},
        ),
        (
            "tahirpur",
            "Tahirpur Upazila, Sunamganj, Bangladesh",
            25.0986,
            91.2104,
            "upazila",
            {"country": "Bangladesh", "region": "Sunamganj District"},
        ),
    )

    def search(self, query: str) -> List[LocationSearchResult]:
        normalized = query.strip().lower()
        if not normalized:
            return []

        matches: List[LocationSearchResult] = []
        exact: List[LocationSearchResult] = []
        for key, display_name, lat, lon, place_type, admin in self._CATALOG:
            haystack = f"{key} {display_name} {' '.join(admin.values())}".lower()
            hit = LocationSearchResult(
                query=query,
                display_name=display_name,
                latitude=lat,
                longitude=lon,
                place_type=place_type,
                administrative=admin,
            )
            if normalized == key or normalized == display_name.lower():
                exact.append(hit)
            elif normalized in haystack or all(token in haystack for token in normalized.split()):
                matches.append(hit)
        ranked = exact + [row for row in matches if row.display_name not in {item.display_name for item in exact}]
        return ranked[:8]


class LocationSearchService:
    """Application service for resolving place queries to coordinates."""

    def __init__(self, provider: Optional[GeocodingProvider] = None):
        self._provider = provider or DemoGeocodingProvider()

    @property
    def provider_name(self) -> str:
        return getattr(self._provider, "provider_name", self._provider.__class__.__name__)

    def search(self, query: str) -> dict:
        """Search for locations and return a structured API payload."""
        normalized = query.strip()
        if not normalized:
            raise ValueError("Search query must not be empty.")

        results = self._provider.search(normalized)
        validated: List[LocationSearchResult] = []
        for result in results:
            self._validate_coordinates(result.latitude, result.longitude)
            validated.append(
                LocationSearchResult(
                    query=normalized,
                    display_name=result.display_name,
                    latitude=float(result.latitude),
                    longitude=float(result.longitude),
                    place_type=result.place_type,
                    administrative=result.administrative,
                )
            )

        return {
            "query": normalized,
            "provider": self.provider_name,
            "results": [result.to_dict() for result in validated],
        }

    @staticmethod
    def _validate_coordinates(latitude: float, longitude: float) -> None:
        if not (-90.0 <= latitude <= 90.0):
            raise ValueError(f"Invalid latitude: {latitude}")
        if not (-180.0 <= longitude <= 180.0):
            raise ValueError(f"Invalid longitude: {longitude}")


def parse_coordinate_query(query: str) -> Optional[LocationSearchResult]:
    """Parse a direct 'lat, lon' query into a search result."""
    import re

    match = re.match(
        r"^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$",
        query.strip(),
    )
    if not match:
        return None

    first = float(match.group(1))
    second = float(match.group(2))

    if -90.0 <= first <= 90.0 and -180.0 <= second <= 180.0:
        latitude, longitude = first, second
    elif -90.0 <= second <= 90.0 and -180.0 <= first <= 180.0:
        latitude, longitude = second, first
    else:
        return None

    label = f"{latitude:.4f}°, {longitude:.4f}°"
    return LocationSearchResult(
        query=query,
        display_name=label,
        latitude=latitude,
        longitude=longitude,
        place_type="coordinates",
    )
