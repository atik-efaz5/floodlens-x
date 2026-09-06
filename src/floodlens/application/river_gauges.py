"""River gauge provider. Default feed is UNAVAILABLE; never invent discharge."""

from __future__ import annotations

from floodlens.application.canonical import RiverObservation
from floodlens.application.data_contracts import envelope


class RiverGaugeAdapter:
    def fetch(self, river_id: str) -> RiverObservation:
        from floodlens.application.demo_fixtures import demo_fixtures_enabled, demo_river_observations

        if demo_fixtures_enabled():
            return demo_river_observations(river_id)[-1]
        return RiverObservation(
            river_id=river_id,
            segment_id=None,
            observed_at=None,
            water_level_m=None,
            discharge_m3s=None,
            source="no-gauge-feed",
            data_status="UNAVAILABLE",
        )


def unavailable_gauge(river_id: str) -> dict:
    obs = RiverGaugeAdapter().fetch(river_id)
    return {
        "observation": obs.to_dict(),
        "provenance": envelope(
            data_status="UNAVAILABLE",
            provider="river-gauge",
            dataset="water_level",
            freshness="UNAVAILABLE",
        ),
    }
