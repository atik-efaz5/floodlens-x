"""Frontend contract for platform shell, demo banners, and dual clocks."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_frontend_role_shell_and_demo_banner():
    shell = (ROOT / "frontend/src/platform/RoleShell.jsx").read_text()
    app = (ROOT / "frontend/src/App.jsx").read_text()
    assert "DEMO / SIMULATED DATA" in shell
    assert "RoleShell" in app
    assert "StatusPanel" in app
    assert "ForecastPanel" in app
    assert "DataSourcesPanel" in app
    assert "AssistantDock" in app
    badge = (ROOT / "frontend/src/platform/ProvenanceBadge.jsx").read_text()
    assert "REAL" in badge and "SIMULATED" in badge and "UNAVAILABLE" in badge
    osm_layer = (ROOT / "frontend/src/components/OsmInfrastructureLayer.jsx").read_text()
    assert "fetchInfrastructure" in osm_layer
    assert "bbox" in osm_layer
    assert "NOT_COMPUTED" in osm_layer
    assert "Regional maximum depth" in osm_layer
    assert "Per-feature depth" in osm_layer
    flood_map = (ROOT / "frontend/src/components/FloodMap.jsx").read_text()
    assert "OsmInfrastructureLayer" in flood_map
    assert "Loading infrastructure" in flood_map
    assert "forecastOverlayUrl" in flood_map
    assert "JobProgressPanel" in app
    assert "RiverForecastPanel" in app
    assert "ForecastTimeline" in app
    assert "AlertsPanel" in app
    assert "ImpactPanel" in app
    assert "CapabilityMatrix" in app
    assert "ReportsPanel" in app
    jobs_panel = (ROOT / "frontend/src/platform/JobProgressPanel.jsx").read_text()
    assert "fetchJob" in jobs_panel
    river_panel = (ROOT / "frontend/src/platform/RiverForecastPanel.jsx").read_text()
    assert "UNAVAILABLE" in river_panel
    assert "Modeled" in app
    assert 'status-active">Live' not in app


def test_frontend_forecast_clock_copy():
    panel = (ROOT / "frontend/src/platform/ForecastPanel.jsx").read_text()
    assert "not SWE" in panel or "meteorological" in panel.lower() or "hours" in panel
    assert "6" in panel and "72" in panel
    assert "artifactOverlayUrl" in panel or "overlay.png" in panel
