"""Frontend comparison contract tests."""

from pathlib import Path

from floodlens.application.comparison import COMPARISON_MODES

ROOT = Path(__file__).resolve().parents[1]


def test_frontend_comparison_modes_and_sync_helpers_exist():
    state_js = (ROOT / "frontend/src/comparison/state.js").read_text()
    assert "SIDE_BY_SIDE" in state_js
    assert "SWIPE" in state_js
    assert "DIFFERENCE" in state_js
    assert "canCompareScenarios" in state_js
    assert "syncViewport" in state_js
    assert set(COMPARISON_MODES) == {"SIDE_BY_SIDE", "SWIPE", "DIFFERENCE"}


def test_frontend_comparison_panel_and_swipe_components_exist():
    assert (ROOT / "frontend/src/components/ComparisonPanel.jsx").exists()
    assert (ROOT / "frontend/src/components/SwipeCompareMap.jsx").exists()
    app = (ROOT / "frontend/src/App.jsx").read_text()
    assert "ComparisonPanel" in app
    assert "SwipeCompareMap" in app
    assert "DIFFERENCE" in app
