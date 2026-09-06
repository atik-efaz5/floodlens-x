"""Phase-2 data layer: envelopes, adapters, repository, API, assistant tools."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from floodlens.application.canonical import InfrastructureRecord
from floodlens.application.data_contracts import DataEnvelope, classify_window, envelope
from floodlens.application.forecast import AIModelForecastProvider, PhysicsForecastProvider
from floodlens.application.meteo import parse_open_meteo
from floodlens.application.osm_ingest import normalize_osm_element
from floodlens.application.rate_limit import INGEST_BUCKET, OVERPASS_BUCKET
from floodlens.application.repository import InMemoryRepository, reset_repository
from floodlens.application.web_server import app
from floodlens.ml.registry import public_status


def _refill_buckets():
    INGEST_BUCKET.tokens = INGEST_BUCKET.capacity
    OVERPASS_BUCKET.tokens = OVERPASS_BUCKET.capacity


def _client():
    reset_repository()
    _refill_buckets()
    return TestClient(app)


def _auth(role: str = "admin") -> dict:
    return {"Authorization": f"Bearer demo.{role}"}


def test_envelope_forbids_live_and_real_simulated():
    with pytest.raises(ValueError):
        DataEnvelope(
            data_status="LIVE",
            provider="x",
            dataset="y",
            retrieved_at="t",
            freshness="RECENT",
        ).to_dict()
    with pytest.raises(ValueError):
        DataEnvelope(
            data_status="REAL",
            provider="x",
            dataset="y",
            retrieved_at="t",
            freshness="RECENT",
            simulated=True,
        ).to_dict()
    payload = envelope(
        data_status="DEMO",
        provider="fixture",
        dataset="osm",
        freshness="SNAPSHOT",
        simulated=True,
        fallback_used=True,
    )
    assert payload["data_status"] != "LIVE"
    assert "live" not in str(payload["freshness"]).lower() or payload["simulated"] is False


def test_freshness_windows_never_live():
    now = datetime.now(timezone.utc)
    assert classify_window(now - timedelta(minutes=5), "open-meteo", now) == "RECENT"
    assert classify_window(now - timedelta(hours=2), "open-meteo", now) == "STALE"
    assert classify_window(now - timedelta(hours=12), "open-meteo", now) == "EXPIRED"
    assert classify_window(now - timedelta(days=3), "open-meteo", now) == "UNAVAILABLE"
    assert classify_window(now, "openstreetmap", now) == "SNAPSHOT"
    assert classify_window(now, "dem", now) == "STATIC"
    assert "LIVE" not in {
        classify_window(now - timedelta(seconds=1), "open-meteo", now),
        classify_window(now, "openstreetmap", now),
    }


def test_osm_normalize_skips_bad_geometry_and_does_not_invent_names():
    retrieved = "2026-01-01T00:00:00+00:00"
    skipped = normalize_osm_element({"id": 1, "tags": {"amenity": "hospital"}}, "dhaka", "REAL", retrieved)
    assert skipped is None
    bad = normalize_osm_element(
        {"id": 2, "lat": 91.0, "lon": 200.0, "tags": {"amenity": "hospital"}},
        "dhaka",
        "REAL",
        retrieved,
    )
    assert bad is None
    ok = normalize_osm_element(
        {"id": 3, "lat": 23.7, "lon": 90.4, "tags": {"amenity": "hospital"}},
        "dhaka",
        "REAL",
        retrieved,
    )
    assert ok is not None
    assert ok.name is None
    assert ok.source_osm_id == "3"


def test_rainfall_split_observed_vs_forecast():
    now = datetime.now(timezone.utc)
    past = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
    future = (now + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M")
    rows = parse_open_meteo(
        {"hourly": {"time": [past, future], "precipitation": [1.2, 4.0]}},
        "dhaka",
        90.4,
        23.8,
    )
    kinds = {row.kind for row in rows}
    assert "OBSERVED" in kinds
    assert "FORECAST" in kinds
    assert all(row.value_mm >= 0 for row in rows)


def test_repository_contract_in_memory():
    reset_repository()
    repo = InMemoryRepository()
    rec = InfrastructureRecord(
        id="a1",
        city_id="dhaka",
        asset_type="hospital",
        name="Test",
        lon=90.41,
        lat=23.81,
        data_status="DEMO",
    )
    repo.put_infrastructure(rec)
    found = repo.list_infrastructure(city_id="dhaka", bbox=(90.0, 23.0, 91.0, 24.0), limit=10)
    assert found[0].id == "a1"
    page = repo.list_infrastructure(city_id="dhaka", limit=1, offset=1)
    assert page == []


def test_infrastructure_geojson_bbox_and_data_sources(monkeypatch):
    client = _client()

    def _fail(self, city_id):
        raise RuntimeError("offline")

    monkeypatch.setattr("floodlens.application.osm_ingest.OsmOverpassAdapter.fetch", _fail)
    ingested = client.post("/api/v1/ingest/osm", params={"city_id": "dhaka"}, headers=_auth())
    assert ingested.status_code == 200
    assert ingested.json()["fallback_used"] is True
    assert ingested.json()["provenance"]["data_status"] == "DEMO"
    geo = client.get(
        "/api/v1/infrastructure",
        params={"city_id": "dhaka", "bbox": "90.0,23.5,90.8,24.1", "limit": 50},
        headers=_auth("general"),
    )
    assert geo.status_code == 200
    body = geo.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"]
    for feature in body["features"]:
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] in {"Point", "LineString"}
        assert feature["geometry"]["coordinates"]
    catalog = client.get("/api/v1/data-sources", params={"city_id": "dhaka"}).json()
    ids = {s["id"] for s in catalog["sources"]}
    assert ids == {"osm", "dem", "open-meteo", "river-gauge", "simulation-engine"}
    assert catalog["provenance"]["data_status"] != "LIVE"
    regions = client.get("/api/v1/regions").json()
    assert regions["features"]
    terrain = client.get("/api/v1/terrain", params={"city_id": "dhaka"}).json()
    assert terrain["provenance"]["freshness"] == "STATIC"
    assert terrain["available"] is False or terrain["dataset"]["data_status"] == "REAL"


def test_open_meteo_mock_and_explicit_demo_fallback(monkeypatch):
    client = _client()
    payload = {
        "hourly": {
            "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
            "precipitation": [0.5, 1.0],
        }
    }

    class _Resp:
        def read(self):
            import json

            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("floodlens.application.meteo.urlopen", lambda *a, **k: _Resp())
    rain = client.post("/api/v1/ingest/rainfall", params={"city_id": "dhaka"}, headers=_auth())
    assert rain.status_code == 200
    body = rain.json()
    assert body["fallback_used"] is False
    assert body["provenance"]["simulated"] is False
    assert "live" not in str(body["provenance"]["freshness"]).lower() or body["provenance"]["simulated"] is False
    obs = client.get(
        "/api/v1/observations",
        params={"city_id": "dhaka", "variable": "precipitation_mm"},
        headers=_auth("general"),
    ).json()
    assert obs["data"]
    assert obs["fallback_used"] is False

    def _boom(*_a, **_k):
        raise TimeoutError("down")

    monkeypatch.setattr("floodlens.application.meteo.urlopen", _boom)
    _refill_buckets()
    failed = client.post("/api/v1/ingest/rainfall", params={"city_id": "sylhet"}, headers=_auth())
    assert failed.json()["fallback_used"] is True
    assert failed.json()["provenance"]["data_status"] == "DEMO"


def test_forecast_timestamps_and_unavailable_providers():
    client = _client()
    data = client.get("/api/v1/forecast", params={"city_id": "dhaka"}).json()
    for point in data["horizons"]:
        assert point["timestamp"]
        assert point["valid_at"]
        assert point["generated_at"]
        assert point["expected_depth"] is None
        assert point["confidence_kind"] == "heuristic"
        assert point["model_id"]
    assert data["model_kind"] == "HEURISTIC"
    physics = PhysicsForecastProvider().forecast("dhaka")
    assert physics["data_status"] == "UNAVAILABLE"
    ai = AIModelForecastProvider().forecast("dhaka")
    if public_status() != "VALIDATED":
        assert ai["data_status"] == "UNAVAILABLE"
    else:
        assert ai["overlay"] is None
        assert ai.get("expected_depth") is None


def test_impact_line_metric_or_not_computed():
    client = _client()
    headers = _auth("emergency")
    job = client.post(
        "/api/v1/jobs",
        json={
            "kind": "simulation",
            "city_id": "dhaka",
            "nx": 10,
            "ny": 10,
            "duration_seconds": 0.2,
            "steps": 1,
        },
        headers=headers,
    )
    assert job.json()["result"]["scenario_id"]
    assert job.json()["result"]["artifact_uri"]
    assert "depth" not in job.json()["result"]
    impact = client.post(
        "/api/v1/impact/assess",
        json={"city_id": "dhaka", "job_id": job.json()["id"]},
        headers=headers,
    ).json()
    assert impact["population_exposed"] is None
    assert impact["accessibility"]["reason"] == "NOT_COMPUTED"
    roads = impact["roads_affected"]
    assert "computed" in roads
    if not roads["computed"]:
        assert "NOT_COMPUTED" in roads["reason"]


def test_assistant_freshness_and_real_or_simulated_use_tools_only():
    client = _client()
    real = client.post(
        "/api/v1/assistant/chat",
        json={"message": "Is this real or simulated?", "city_id": "dhaka"},
        headers=_auth("general"),
    ).json()
    assert "get_data_source" in real["tools_called"]
    sources = real["tool_results"]["get_data_source"]["sources"]
    assert sources
    for row in sources:
        assert row["data_status"] != "LIVE"
    assert "1.2 million" not in real["reply"]
    fresh = client.post(
        "/api/v1/assistant/chat",
        json={"message": "How fresh is rainfall?", "city_id": "dhaka"},
        headers=_auth("general"),
    ).json()
    assert "get_data_freshness" in fresh["tools_called"]
    assert "run_scenario" not in fresh["tools_called"]
    tool = fresh["tool_results"]["get_data_freshness"]
    assert "rainfall_freshness" in tool
    assert str(tool["rainfall_freshness"]) in fresh["reply"] or str(tool["rainfall_data_status"]) in fresh["reply"]


@pytest.mark.postgis
def test_postgis_repository_optional():
    import os

    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    reset_repository()
    from floodlens.application.repository import get_repository

    os.environ["DATABASE_URL"] = os.environ["DATABASE_URL"]
    # Force rebuild
    from floodlens.application import repository as repo_mod

    repo_mod._REPO = None
    repo = get_repository()
    rec = InfrastructureRecord(
        id="pg1",
        city_id="dhaka",
        asset_type="school",
        name="Pg",
        lon=90.4,
        lat=23.8,
        data_status="REAL",
        source="test",
        source_osm_id="99",
    )
    repo.put_infrastructure(rec)
    assert repo.get_infrastructure("pg1") is not None
