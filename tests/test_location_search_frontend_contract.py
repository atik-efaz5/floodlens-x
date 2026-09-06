"""Frontend location search contract tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_frontend_location_search_api_and_state_exist():
    api_js = (ROOT / "frontend/src/api.js").read_text()
    assert "searchLocations" in api_js
    assert "/api/geocode/search" in api_js

    search_bar = (ROOT / "frontend/src/components/LocationSearchBar.jsx").read_text()
    assert "searchLocations" in search_bar
    assert "loading" in search_bar.lower()
    assert "error" in search_bar.lower()

    utils = (ROOT / "frontend/src/utils/locationSearch.js").read_text()
    assert "isWithinCityBounds" in utils
    assert "selectSearchZoom" in utils


def test_frontend_outside_city_notice():
    app_js = (ROOT / "frontend/src/App.jsx").read_text()
    assert "searchNotice" in app_js
    assert "outside the current study region" in app_js


def test_frontend_map_navigation_and_marker_support():
    app_js = (ROOT / "frontend/src/App.jsx").read_text()
    flood_map = (ROOT / "frontend/src/components/FloodMap.jsx").read_text()

    assert "searchMarker" in app_js
    assert "handleSelectLocation" in app_js
    assert "searchMarker" in flood_map
    assert "flyTarget" in flood_map
    assert "RiverNetworkLayer" in flood_map
    assert "Loading infrastructure" in flood_map
    assert "aria-label" in (ROOT / "frontend/src/platform/RoleShell.jsx").read_text()
