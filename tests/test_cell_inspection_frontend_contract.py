"""Frontend click-to-inspect contract tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_frontend_inspection_api_parameters():
    api_js = (ROOT / "frontend/src/api.js").read_text()
    assert "inspectCell" in api_js
    assert "city_id" in api_js
    assert "scenario_id" in api_js
    assert "time" in api_js


def test_frontend_inspection_state_and_stale_clearing():
    app_js = (ROOT / "frontend/src/App.jsx").read_text()
    assert "handleInspect" in app_js
    assert "setInspection(null)" in app_js
    assert "inspectionContext" in app_js
    assert "searchMarker" in app_js


def test_frontend_inspection_panel_shows_modeled_values():
    card = (ROOT / "frontend/src/components/InspectionCard.jsx").read_text()
    assert "modeled" in card.lower()
    assert "scenario" in card.lower()
    assert "flood_status" in card or "Flood Status" in card


def test_frontend_map_viewport_uses_city_bounds():
    flood_map = (ROOT / "frontend/src/components/FloodMap.jsx").read_text()
    app_js = (ROOT / "frontend/src/App.jsx").read_text()
    assert "studyBounds" in flood_map
    assert "viewportBounds" in flood_map
    assert "Rectangle" in flood_map
    assert "studyBounds={studyBounds}" in app_js
    assert "cityMetadata?.bounds" in app_js


def test_frontend_samples_city_bounds_not_session_metadata():
    app_js = (ROOT / "frontend/src/App.jsx").read_text()
    assert "sampleRasterGrid" in app_js
    assert "cityMetadata?.bounds || updatedMetadata.bounds" in app_js
    assert "sampleBounds" in app_js


def test_frontend_outside_domain_inspect_names_city():
    app_js = (ROOT / "frontend/src/App.jsx").read_text()
    api_js = (ROOT / "frontend/src/api.js").read_text()
    assert "OUTSIDE_SIMULATION_DOMAIN" in app_js
    assert "Click is outside the" in app_js
    assert "study region" in app_js
    assert "errorCode" in api_js
