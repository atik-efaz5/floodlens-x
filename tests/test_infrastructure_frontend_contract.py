"""Frontend contract: planning layers follow the selected city."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_infrastructure_is_keyed_by_city():
    data = (ROOT / "frontend/src/data/infrastructure.js").read_text()
    assert "CITY_INFRASTRUCTURE" in data
    assert "getCityInfrastructure" in data
    assert "dhaka:" in data
    assert "sylhet:" in data
    assert "sunamganj:" in data


def test_map_passes_selected_city_to_infrastructure_layers():
    flood_map = (ROOT / "frontend/src/components/FloodMap.jsx").read_text()
    layers = (ROOT / "frontend/src/components/InfrastructureLayers.jsx").read_text()
    app_js = (ROOT / "frontend/src/App.jsx").read_text()
    assert "cityId={cityId}" in flood_map
    assert "getCityInfrastructure" in layers
    assert "cityId={selectedCityId}" in app_js
