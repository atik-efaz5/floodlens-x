"""Frontend temporal playback contract tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_frontend_uses_backend_available_times():
    hook = (ROOT / "frontend/src/hooks/useTimeAnimation.js").read_text()
    assert "availableTimes" in hook
    assert "duration / stepCount" not in hook

    api_js = (ROOT / "frontend/src/api.js").read_text()
    assert "fetchScenarioTimeline" in api_js
    assert "fetchScenarioSnapshot" in api_js
    assert "/api/scenario/" in api_js

    app = (ROOT / "frontend/src/App.jsx").read_text()
    assert "available_times" in app
    assert "fetchScenarioSnapshot" in app
    assert "currentTime" in app
    bar = (ROOT / "frontend/src/components/TimePlaybackBar.jsx").read_text()
    assert "availableTimes" in bar
    assert "snapshots" in bar
