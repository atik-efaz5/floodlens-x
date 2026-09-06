"""Process health. Values come from the running store, not decorative gauges."""

from __future__ import annotations

from floodlens.application.platform_store import get_platform_store
from floodlens.application.provenance import isoformat, PHYSICS_MODEL_VERSION, FORECAST_MODEL_VERSION
from floodlens.ml.registry import load_registry, public_status
from floodlens.ml.spatial.registry_spatial import load_spatial_registry, public_spatial_status


def health() -> dict:
    """Liveness. `status` is process health, not rainfall/OSM/DEM availability."""
    store = get_platform_store()
    jobs = list(store.jobs.values())
    failed = [j for j in jobs if j.get("status") == "failed"]
    try:
        artifact_ok = isinstance(store.artifacts, dict)
        artifact_status = "ok" if artifact_ok else "degraded"
    except Exception:
        artifact_status = "degraded"
    from floodlens.application.catalog import data_source_catalog

    sources = data_source_catalog("dhaka").get("sources") or []
    data_statuses = [str(row.get("data_status") or "UNAVAILABLE") for row in sources]
    data_ok = any(status not in {"UNAVAILABLE", "NOT_COMPUTED"} for status in data_statuses)
    return {
        "status": "ok",
        "timestamp": isoformat(),
        "note": "SYSTEM HEALTH is not DATA AVAILABILITY. Missing rainfall does not make the process unhealthy.",
        "system": {
            "status": "ok",
            "queue": "in-process",
            "redis": "not_configured",
            "celery": "optional_not_required",
            "artifact_store": artifact_status,
            "identity": "demo-idp",
        },
        "data": {
            "status": "PARTIAL" if data_ok else "UNAVAILABLE",
            "sources": [
                {"id": row.get("id"), "data_status": row.get("data_status"), "title": row.get("title")}
                for row in sources
            ],
        },
        "jobs": {
            "total": len(jobs),
            "failed": len(failed),
            "queued": len([j for j in jobs if j.get("status") == "queued"]),
            "running": len([j for j in jobs if j.get("status") == "running"]),
            "completed": len([j for j in jobs if j.get("status") == "completed"]),
        },
        "ingest_runs": len(store.ingest_runs),
        "assets": len(store.assets),
        "models": {
            "physics": PHYSICS_MODEL_VERSION,
            "forecast": FORECAST_MODEL_VERSION,
            "ai_flood": None,
            "spatial_ai": "NOT_VALIDATED",
        },
        "queue": "in-process",
        "redis": "not_configured",
        "celery": "optional_not_required",
    }


def readiness() -> dict:
    payload = health()
    payload["ready"] = payload.get("system", {}).get("status") == "ok"
    return payload


def model_performance_center() -> dict:
    from floodlens.application.historical_workspace import model_performance_payload

    return model_performance_payload()


def model_catalog() -> dict:
    ai = load_registry()
    ai_status = public_status(ai)
    spatial = load_spatial_registry()
    spatial_status = public_spatial_status(spatial)
    return {
        "models": [
            {
                "id": "PHYSICS-BASELINE-v0.1",
                "title": "Physics Baseline",
                "status": "IMPLEMENTED",
                "kind": "PHYSICS_BASELINE",
                "accuracy_claim": None,
            },
            {
                "id": FORECAST_MODEL_VERSION,
                "title": "Heuristic Forecast",
                "status": "IMPLEMENTED",
                "kind": "HEURISTIC",
                "accuracy_claim": None,
            },
            {
                "id": "ai-forecast",
                "title": "AI Forecast",
                "status": ai_status,
                "kind": "AI",
                "accuracy_claim": None,
                "registry_status": ai.get("status"),
                "label_kind": ai.get("label_kind"),
                "note": ai.get("note"),
            },
            {
                "id": spatial.get("id") or "ai-spatial-forecast",
                "title": spatial.get("title") or "AI Spatial Flood Occurrence",
                "status": spatial_status,
                "kind": "AI_SPATIAL",
                "accuracy_claim": None,
                "registry_status": spatial.get("status"),
                "display_status": (
                    "VALIDATED"
                    if spatial_status == "VALIDATED"
                    else (
                        "TRAINED — NOT VALIDATED"
                        if spatial.get("status") == "TRAINED"
                        else "NOT_TRAINED"
                    )
                ),
                "label_kind": spatial.get("label_kind"),
                "model_id": spatial.get("model_id"),
                "comparable_to_physics": False,
                "formulation_gate": "Phase 6 Gate 2 not passed; spatial API UNAVAILABLE until VALIDATED.",
                "note": spatial.get("note"),
            },
            {
                "id": "hybrid-ai-physics",
                "title": "Hybrid AI/Physics",
                "status": "NOT_IMPLEMENTED",
                "kind": "HYBRID",
                "accuracy_claim": None,
            },
        ]
    }
