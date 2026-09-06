"""Immutable region reports and share snapshots."""

from __future__ import annotations

import csv
import io
import json
from typing import Optional

from floodlens.application.forecast import forecast_for_city
from floodlens.application.impact_workspace import (
    evacuation_assessment,
    region_impact,
    resource_priorities,
    shelter_assessments,
)
from floodlens.application.platform_store import get_platform_store
from floodlens.application.provenance import (
    DATA_VERSION,
    FORECAST_MODEL_VERSION,
    PHYSICS_MODEL_VERSION,
    isoformat,
)
from floodlens.application.rate_limit import check_rate
from floodlens.application.risk import risk_for_city


def generate_region_report(
    city_id: str,
    baseline_job_id: str | None = None,
    scenario_job_id: str | None = None,
    created_by: str | None = None,
    map_state: dict | None = None,
    event_id: str | None = None,
) -> dict:
    if created_by:
        check_rate(created_by, "report.generate")
    if event_id:
        from floodlens.application.historical_workspace import generate_historical_report

        report = generate_historical_report(event_id, city_id=city_id)
        return _finalize_snapshot(report, created_by=created_by, kind="historical", map_state=map_state)
    store = get_platform_store()
    risk = risk_for_city(city_id)
    forecast = forecast_for_city(city_id)
    impact = region_impact(city_id, job_id=scenario_job_id or baseline_job_id)
    shelters = shelter_assessments(city_id, job_id=scenario_job_id or baseline_job_id)
    evacuation = evacuation_assessment(city_id, job_id=scenario_job_id or baseline_job_id)
    resources = resource_priorities(city_id, job_id=scenario_job_id or baseline_job_id)
    from floodlens.application.population import get_population_provider

    pop_provider = get_population_provider().expose(city_id)
    from floodlens.application.scenario_workspace import compare_scenario_jobs, scenario_baseline, scenario_history

    baseline = scenario_baseline(city_id)
    history = scenario_history(city_id)
    jobs = history.get("scenarios") or []
    baseline_id = baseline_job_id or baseline.get("job_id") or (jobs[-1]["job_id"] if jobs else None)
    scenario_id = scenario_job_id
    if scenario_id is None:
        named = [row for row in jobs if row.get("rainfall_multiplier") not in (None, 1.0)]
        scenario_id = (named[0]["job_id"] if named else None) or (jobs[0]["job_id"] if jobs else None)
    compare = compare_scenario_jobs([baseline_id, scenario_id]) if baseline_id and scenario_id else None
    baseline_row = ((compare or {}).get("comparisons") or [None])[0] if compare else None
    scenario_row = ((compare or {}).get("comparisons") or [None, None])[1] if compare else None
    scenario_section = {
        "description": (scenario_row or {}).get("name") or "No named scenario attached.",
        "baseline": {
            "job_id": baseline_id,
            "forcing": baseline.get("forcing"),
            "model": baseline.get("model"),
            "assumptions": baseline.get("assumptions"),
        },
        "modified_variables": {
            "rainfall_multiplier": (scenario_row or {}).get("rainfall_multiplier"),
            "rainfall_rate_base_mps": (scenario_row or {}).get("rainfall_rate_base_mps"),
            "rainfall_rate_applied_mps": (scenario_row or {}).get("rainfall_rate_applied_mps"),
            "river_level_applied_to_solver": False,
        },
        "results": scenario_row,
        "differences": (compare or {}).get("difference"),
        "impact": {
            "scenario": impact.get("scenario"),
            "categories": impact.get("categories"),
        },
        "limitations": [
            "Rainfall multiplier is applied only when rainfall_rate_applied_mps equals base × multiplier.",
            "river_level_delta_m is stored and is not applied to the SWE solver.",
            "Population exposure remains UNAVAILABLE.",
        ],
        "provenance": baseline.get("provenance"),
        "model_version": (scenario_row or {}).get("model_version") or PHYSICS_MODEL_VERSION,
        "job_id": scenario_id,
        "baseline_job_id": baseline_id,
    }
    body = {
        "region_overview": {"city_id": city_id},
        "scenario": scenario_section,
        "current_conditions": risk,
        "forecast": forecast,
        "flood_probability": forecast["horizons"],
        "confidence": [h.get("confidence") for h in forecast.get("horizons") or []],
        "flood_state": {
            "scenario": impact["scenario"],
            "note": "Flood-state impact uses an attached physics/scenario raster when present.",
        },
        "population_impact": {
            "available": bool(pop_provider.get("available")),
            "population_exposed": pop_provider.get("population_exposed"),
            "data_status": pop_provider.get("data_status") or "UNAVAILABLE",
            "reason": pop_provider.get("reason") or "Population grid not ingested.",
        },
        "infrastructure_impact": {
            "asset_count": len(store.assets_for_city(city_id)),
            "source": "osm-or-fixture",
            "categories": impact["categories"],
        },
        "shelter_analysis": {
            "count": shelters["count"],
            "capacity_status": shelters["capacity_status"],
            "occupancy_status": shelters["occupancy_status"],
            "accessibility_status": shelters["accessibility_status"],
            "shelters": shelters["shelters"],
        },
        "evacuation_planning": {
            "kind": evacuation["kind"],
            "official_evacuation_order": False,
            "routes": evacuation["routes"],
            "road_accessibility": evacuation["road_accessibility"],
            "safety": evacuation["safety"],
        },
        "resource_priorities": resources["priorities"],
        "data_availability": {
            "population": pop_provider.get("data_status") or "UNAVAILABLE",
            "shelter_capacity": "UNAVAILABLE",
            "road_accessibility": evacuation.get("road_accessibility", {}).get("status") or "NOT_COMPUTED",
            "observed_resource_inventory": "DEMO"
            if (resources.get("inventory") or {}).get("rescue_boats", {}).get("status") == "DEMO"
            else "UNAVAILABLE",
        },
        "assumptions": impact["assumptions"],
        "river_conditions": "see /api/v1/rivers/{id}",
        "recommended_planning_actions": [
            "Review heuristic forecast horizons; they are not SWE seconds.",
            "Inspect OSM assets after a physics job completes.",
            "Treat impact output as planning support, not an official evacuation order.",
        ],
        "data_sources": [run for run in store.ingest_runs if run.get("city_id") == city_id],
        "model_information": {
            "physics": PHYSICS_MODEL_VERSION,
            "forecast": FORECAST_MODEL_VERSION,
            "ai_flood_model": None,
        },
        "provenance": impact["provenance"],
        "limitations": [
            "No trained AI flood model is deployed.",
            "Missing layers are omitted rather than invented.",
            "Population, shelter capacity, occupancy, routes, and inventories remain unavailable unless labeled DEMO.",
            "river_level_delta_m is a stored scenario parameter and is not applied to the SWE solver.",
        ],
        "safety": impact["safety"],
        "kind": "scenario" if scenario_id and scenario_id != baseline_id else "region",
        "snapshot": True,
    }
    if not (forecast.get("horizons") or []):
        body.pop("forecast", None)
        body.pop("flood_probability", None)
    pop = body["population_impact"]
    if pop.get("available") is False:
        pop["population_exposed"] = None
        pop["value"] = None
    body["river_conditions"] = {
        "water_level_status": "UNAVAILABLE",
        "discharge_status": "UNAVAILABLE",
        "current_water_level_m": None,
        "current_discharge_m3s": None,
        "note": "Gauge water level and discharge are not invented. See /api/v1/rivers/{id}.",
    }
    body["executive_summary"] = {
        "location": city_id,
        "risk_category": risk.get("category"),
        "flood_probability_24h": next(
            (h.get("flood_probability") for h in (forecast.get("horizons") or []) if h.get("horizon_hours") == 24),
            None,
        ),
        "population": pop_provider.get("population_exposed")
        if pop_provider.get("available")
        else "UNAVAILABLE",
        "official_evacuation_order": False,
        "kind": body["kind"],
    }
    body["evidence"] = {
        "risk_formula": risk.get("formula_id"),
        "impact_scenario": impact.get("scenario"),
        "job_ids": [baseline_id, scenario_id],
    }
    body["map_state"] = map_state
    report = store.put_report(
        {
            "city_id": city_id,
            "created_by": created_by,
            "model_version": FORECAST_MODEL_VERSION,
            "physics_model_version": PHYSICS_MODEL_VERSION,
            "body": body,
            "formats": ["json", "csv", "pdf"],
            "scenario_id": scenario_id,
            "baseline_id": baseline_id,
            "job_id": scenario_id or baseline_id,
            "kind": body["kind"],
            "source_versions": {
                "data_version": DATA_VERSION,
                "forecast": FORECAST_MODEL_VERSION,
                "physics": PHYSICS_MODEL_VERSION,
            },
            "model_versions": {
                "forecast": FORECAST_MODEL_VERSION,
                "physics": PHYSICS_MODEL_VERSION,
            },
            "map_state": map_state,
        }
    )
    store.audit("report.generate", actor=created_by, detail={"report_id": report["id"], "city_id": city_id})
    return _finalize_snapshot(report, created_by=created_by, kind=body["kind"], map_state=map_state)


def _finalize_snapshot(report: dict, created_by: str | None, kind: str, map_state: dict | None) -> dict:
    report["created_by"] = created_by
    report["kind"] = report.get("kind") or kind
    report["snapshot_time"] = report.get("snapshot_time") or report.get("generated_at")
    report["immutable"] = True
    report["content_version"] = report.get("content_version") or "platform-v1"
    report.setdefault("source_versions", {"data_version": DATA_VERSION})
    report.setdefault("model_versions", {"forecast": report.get("model_version")})
    if map_state:
        report["map_state"] = map_state
        if isinstance(report.get("body"), dict):
            report["body"]["map_state"] = map_state
    report["live"] = False
    report["banner"] = (
        f"SNAPSHOT GENERATED AT: {report.get('snapshot_time')}. "
        "This is a historical snapshot. Current live data may differ."
    )
    return report


def share_report(
    report_id: str,
    owner: str | None = None,
    visibility: str = "private",
    map_state: dict | None = None,
) -> dict:
    store = get_platform_store()
    report = store.reports.get(report_id)
    if not report:
        raise KeyError(report_id)
    if owner:
        check_rate(owner, "share.create")
        if report.get("created_by") and report.get("created_by") != owner:
            raise PermissionError("not owner")
    vis = visibility if visibility in {"private", "organization", "public"} else "private"
    frozen = json.loads(json.dumps(report, default=str))
    if map_state:
        frozen["map_state"] = map_state
    share = store.put_share(
        {
            "report_id": report_id,
            "owner": owner or report.get("created_by"),
            "visibility": vis,
            "model_version": report["model_version"],
            "generated_at": report["generated_at"],
            "snapshot_time": report.get("snapshot_time") or report["generated_at"],
            "dataset_version": (report.get("source_versions") or {}).get("data_version") or DATA_VERSION,
            "artifact_ids": [],
            "scenario_id": report.get("scenario_id") or (report.get("body") or {}).get("scenario", {}).get("job_id"),
            "baseline": report.get("baseline_id"),
            "job_id": report.get("job_id"),
            "city_id": report.get("city_id"),
            "map_state": map_state or report.get("map_state"),
            "snapshot": frozen,
            "live": False,
            "banner": (
                f"Analysis generated at {report.get('snapshot_time') or report['generated_at']}. "
                f"Using: {report.get('model_version')}. "
                f"Dataset: {(report.get('source_versions') or {}).get('data_version') or DATA_VERSION}. "
                "This is a historical snapshot."
            ),
        }
    )
    return share


def get_share(share_id: str, requester: str | None = None, authenticated: bool = False) -> dict:
    store = get_platform_store()
    share = store.shares.get(share_id)
    if not share or share.get("revoked_at"):
        return {
            "status": "SHARE UNAVAILABLE",
            "available": False,
            "reason": "Share is unavailable or has been revoked.",
            "live": False,
        }
    vis = share.get("visibility") or "private"
    if vis == "private" and share.get("owner") and requester != share.get("owner"):
        return {
            "status": "SHARE UNAVAILABLE",
            "available": False,
            "reason": "Private share. Owner access required.",
            "live": False,
        }
    if vis == "organization" and not authenticated:
        return {
            "status": "SHARE UNAVAILABLE",
            "available": False,
            "reason": "Organization share requires sign-in.",
            "live": False,
        }
    snapshot = share.get("snapshot") or {}
    return {
        "available": True,
        "status": "SHARED SNAPSHOT",
        "share_id": share["id"],
        "visibility": vis,
        "live": False,
        "banner": share.get("banner"),
        "generated_at": share.get("generated_at") or share.get("snapshot_time"),
        "snapshot_time": share.get("snapshot_time"),
        "model_version": share.get("model_version"),
        "dataset_version": share.get("dataset_version"),
        "stale_notice": "SHARED SNAPSHOT. Current live data may differ. The historical snapshot is not rewritten.",
        "snapshot": snapshot,
        "map_state": share.get("map_state"),
        "city_id": share.get("city_id"),
        "scenario_id": share.get("scenario_id"),
        "job_id": share.get("job_id"),
        "provenance": (snapshot.get("body") or {}).get("provenance") or snapshot.get("provenance"),
    }


def revoke_share(share_id: str, owner: str) -> dict:
    store = get_platform_store()
    share = store.shares.get(share_id)
    if not share:
        raise KeyError(share_id)
    if share.get("owner") and share.get("owner") != owner:
        raise PermissionError("not owner")
    share["revoked_at"] = isoformat()
    share["status"] = "REVOKED"
    return {"id": share_id, "status": "SHARE UNAVAILABLE", "revoked_at": share["revoked_at"]}


def get_report(report_id: str, owner: str | None = None) -> dict:
    store = get_platform_store()
    report = store.reports.get(report_id)
    if not report:
        raise KeyError(report_id)
    if owner and report.get("created_by") and report.get("created_by") != owner:
        raise PermissionError("not owner")
    return report


def list_reports(owner: str, limit: int = 30) -> dict:
    store = get_platform_store()
    rows = [r for r in store.reports.values() if not owner or r.get("created_by") in {owner, None}]
    if owner:
        rows = [r for r in store.reports.values() if r.get("created_by") == owner]
    rows.sort(key=lambda row: str(row.get("generated_at") or ""), reverse=True)
    cap = min(max(int(limit), 1), 50)
    summaries = [
        {
            "id": row["id"],
            "kind": row.get("kind"),
            "city_id": row.get("city_id"),
            "generated_at": row.get("generated_at"),
            "snapshot_time": row.get("snapshot_time"),
            "model_version": row.get("model_version"),
            "immutable": True,
        }
        for row in rows[:cap]
    ]
    return {"reports": summaries, "n": len(summaries)}


def _flatten(prefix: str, value, rows: list) -> None:
    if value is None:
        rows.append((prefix, "", "UNAVAILABLE"))
        return
    if isinstance(value, bool):
        rows.append((prefix, "true" if value else "false", "ok"))
        return
    if isinstance(value, (int, float)):
        rows.append((prefix, str(value), "ok"))
        return
    if isinstance(value, str):
        rows.append((prefix, value, "ok"))
        return
    if isinstance(value, list):
        rows.append((prefix, json.dumps(value, default=str), "ok"))
        return
    if isinstance(value, dict):
        if not value:
            rows.append((prefix, "", "UNAVAILABLE"))
            return
        for key, item in value.items():
            _flatten(f"{prefix}.{key}" if prefix else key, item, rows)


def report_csv(report: dict) -> str:
    rows: list = []
    _flatten("", {k: v for k, v in report.items() if k != "body"}, rows)
    _flatten("body", report.get("body"), rows)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["field", "value", "status"])
    for field, value, status in rows:
        if value in {"0", "0.0"} and status == "UNAVAILABLE":
            value = ""
        writer.writerow([field, value, status])
    return buf.getvalue()


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def report_pdf(report: dict) -> bytes:
    body = report.get("body") or {}
    summary = body.get("executive_summary") or {}
    lines = [
        "FLOODLENS-X REPORT SNAPSHOT",
        f"SNAPSHOT GENERATED AT: {report.get('snapshot_time') or report.get('generated_at')}",
        f"Report: {report.get('id')}",
        f"Location: {report.get('city_id')}",
        f"Kind: {report.get('kind')}",
        f"Model / method: {report.get('model_version')}",
        f"Dataset: {(report.get('source_versions') or {}).get('data_version')}",
        f"Scenario: {report.get('scenario_id')}",
        f"Job: {report.get('job_id')}",
        "This is a historical snapshot. Current live data may differ.",
        "",
        "SUMMARY",
        f"Risk: {summary.get('risk_category')}",
        f"24h flood probability: {summary.get('flood_probability_24h')}",
        f"Population: {summary.get('population') or 'UNAVAILABLE'}",
        f"Official evacuation order: {summary.get('official_evacuation_order')}",
        "",
        "MAP STATE",
        json.dumps(report.get("map_state") or body.get("map_state") or {}, default=str)[:500],
        "",
        "LIMITATIONS",
    ]
    for item in (body.get("limitations") or [])[:12]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("PROVENANCE")
    lines.append(json.dumps(body.get("provenance") or report.get("provenance") or {}, default=str)[:800])
    if body.get("forecast_accuracy_omitted"):
        lines.append("FORECAST VS REALITY: UNAVAILABLE")
    scenario = body.get("scenario") or {}
    modified = scenario.get("modified_variables") or {}
    if modified:
        lines.append("")
        lines.append("SCENARIO")
        lines.append(f"rainfall_multiplier: {modified.get('rainfall_multiplier')}")
        lines.append("river_level_applied_to_solver: STORED ONLY / NOT APPLIED")
    wrapped: list[str] = []
    for line in lines:
        text = str(line)
        while len(text) > 90:
            wrapped.append(text[:90])
            text = text[90:]
        wrapped.append(text)
    pages: list[list[str]] = []
    for i in range(0, len(wrapped), 48):
        pages.append(wrapped[i : i + 48])
    chunks = ["%PDF-1.4"]
    xref = [0]
    objects = []
    page_ids = []
    font_id = 3
    content_ids = []
    obj_id = 4
    for page in pages:
        stream_lines = ["BT", "/F1 10 Tf", "50 780 Td", "12 TL"]
        for line in page:
            stream_lines.append(f"({_pdf_escape(line)}) Tj T*")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", "replace")
        content_ids.append(obj_id)
        objects.append((obj_id, f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"))
        obj_id += 1
        page_ids.append(obj_id)
        objects.append(
            (
                obj_id,
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_ids[-1]} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode(),
            )
        )
        obj_id += 1
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    catalog = b"<< /Type /Catalog /Pages 2 0 R >>"
    pages_obj = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode()
    font_obj = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    ordered = [(1, catalog), (2, pages_obj), (3, font_obj)] + objects
    ordered.sort(key=lambda item: item[0])
    body_out = b"%PDF-1.4\n"
    offsets = {0: 0}
    for oid, payload in ordered:
        offsets[oid] = len(body_out)
        body_out += f"{oid} 0 obj\n".encode() + payload + b"\nendobj\n"
    xref_pos = len(body_out)
    max_id = max(offsets)
    body_out += f"xref\n0 {max_id + 1}\n".encode()
    body_out += b"0000000000 65535 f \n"
    for i in range(1, max_id + 1):
        body_out += f"{offsets.get(i, 0):010d} 00000 n \n".encode()
    body_out += f"trailer << /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    return body_out

