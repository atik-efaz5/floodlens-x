"""Phase 6.5C: multi-source event registry and label-compatibility study.

Does not train. Does not merge incompatible pixel labels. Does not loosen
the 45-day independence rule. Observation families stay separate.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from floodlens.ml.spatial.event_expansion import (
    INVENTORY_DIR,
    flood_mechanism_for_date,
    intervals_overlap,
    lattice_covers,
)
from floodlens.ml.spatial.events import EVENT_GAP_DAYS
from floodlens.ml.spatial.schema import SPATIAL_DIR

REGISTRY_VERSION = "phase6.5-multisource-event-v1"
REGISTRY_CSV = INVENTORY_DIR / "multisource_event_registry.csv"
REGISTRY_JSON = INVENTORY_DIR / "multisource_event_registry.json"
COMPAT_JSON = INVENTORY_DIR / "source_compatibility_matrix.json"
COMPAT_CSV = INVENTORY_DIR / "source_compatibility_matrix.csv"
PHASE65C_EVAL = SPATIAL_DIR / "phase65c_eval.json"

FAMILY_GFM = "A"
FAMILY_BD_HIST = "B"
FAMILY_GFD = "C"
FAMILY_DFO = "D"

BD_LON_MIN, BD_LON_MAX = 88.0, 92.8
BD_LAT_MIN, BD_LAT_MAX = 20.5, 26.8

SOURCES = {
    "copernicus-gfm-ensemble-flood-extent": {
        "family": FAMILY_GFM,
        "dataset_name": "Copernicus GFM ensemble_flood_extent",
        "provider": "CEMS / EODC",
        "observation_type": "Sentinel-1 SAR ensemble flood extent",
        "label_kind": "OBSERVED",
        "raw_or_derived": "raw_observed_product",
        "spatial_resolution_m": 20,
        "temporal_resolution": "S1 revisit ~6–12 d; 192 h scene slot",
        "event_definition": "45-day meteorological cluster of GFM scenes",
        "flood_definition": "ensemble class 1 at tau=0.25 on AOI grid; 255 unknown",
        "permanent_water": "not a separate class; may appear as flood or dry",
        "unknown": "uint8 255 nodata/exclusion, never recoded dry",
        "bangladesh": True,
        "temporal_coverage": "2015–present (public STAC)",
        "license": "STAC proprietary; Copernicus attribution",
        "commercial_ok": None,
        "access": "https://stac.eodc.eu/api/v1",
        "accessible": True,
        "reproducible": True,
        "role": "primary_training_label",
    },
    "giezendanner-bangladesh-inundation-history": {
        "family": FAMILY_BD_HIST,
        "dataset_name": "Bangladesh Inundation History",
        "provider": "University of Arizona / CyVerse (Giezendanner et al. 2023)",
        "observation_type": "CNN–LSTM fusion of Sentinel-1 fractional inundation onto MODIS 8-day composites",
        "label_kind": "DERIVED",
        "raw_or_derived": "model_output",
        "spatial_resolution_m": 500,
        "temporal_resolution": "8-day, 985 GeoTIFFs, 2001–2022",
        "event_definition": "none published; continuous fractional inundation, not an event inventory",
        "flood_definition": "fractional inundated area (not binary GFM class)",
        "permanent_water": "absorbed into fractional water; not GFM-compatible",
        "unknown": "optical MODIS gaps imputed by the fusion model; not a 255 mask",
        "bangladesh": True,
        "temporal_coverage": "2001–2022, most of Bangladesh",
        "license": "CyVerse curated download; companion code MIT; training inputs include FABDEM (CC BY-NC-SA)",
        "doi": "10.25739/2edm-jh03",
        "access": "https://datacommons.cyverse.org/browse/iplant/home/shared/commons_repo/curated/Giezendanner_BangladeshInundationHistory_Mai2023",
        "accessible": False,
        "access_blocker": "Anonymous GET redirects to unblockme.cyverse.org (captcha/login). Rasters not downloaded.",
        "reproducible": False,
        "role": "not_acquired",
    },
    "global-flood-database": {
        "family": FAMILY_GFD,
        "dataset_name": "Global Flood Database v1 (MODIS events)",
        "provider": "Cloud to Street / Dartmouth Flood Observatory",
        "observation_type": "MODIS Terra/Aqua water classification, event-maximum extent",
        "label_kind": "OBSERVED",
        "raw_or_derived": "observed_event_max_map",
        "spatial_resolution_m": 250,
        "temporal_resolution": "one map per DFO event (2000–2018); 3-day MODIS composites inside the event",
        "event_definition": "DFO catalog events that passed GFD QC (significant inundation beyond permanent water)",
        "flood_definition": "maximum water during the DFO date range, including permanent water unless jrc_perm_water masked",
        "permanent_water": "JRC GSW band provided; default flooded band includes permanent water",
        "unknown": "cloud via clear_views / clear_perc; optical, not GFM 255",
        "bangladesh": True,
        "temporal_coverage": "2000-02-17 … 2018-12-10; 913 mapped events globally, 28 intersecting Bangladesh",
        "license": "CC BY-NC 4.0",
        "commercial_ok": False,
        "access": "GEE GLOBAL_FLOOD_DB/MODIS_EVENTS/V1; QC CSV on GitHub",
        "accessible": True,
        "accessible_what": "event metadata (this study). Rasters not ingested (NC + incompatible target).",
        "reproducible": True,
        "role": "event_discovery_only",
        "do_not_use": "population exposure metrics are not flood labels",
    },
    "dartmouth-flood-observatory": {
        "family": FAMILY_DFO,
        "dataset_name": "DFO Global Active Archive of Large Flood Events (Bangladesh listing)",
        "provider": "Dartmouth Flood Observatory, University of Colorado",
        "observation_type": "event catalog from news, government, instruments, and remote sensing",
        "label_kind": "INVENTORY",
        "raw_or_derived": "catalog_not_pixels",
        "spatial_resolution_m": None,
        "temporal_resolution": "event start/end dates",
        "event_definition": "DFO discrete flood IDs (may split or merge one monsoon)",
        "flood_definition": "reported flooding; polygon is affected-area estimate, not inundation",
        "permanent_water": "n/a",
        "unknown": "n/a",
        "bangladesh": True,
        "temporal_coverage": "1985–present; 115 BD-listed rows; this study uses 2000+",
        "license": "catalog listing; no restriction specified on the public wiki table",
        "access": "https://floodobservatory.colorado.edu/wiki/Bangladesh",
        "accessible": True,
        "reproducible": True,
        "role": "event_discovery_only",
    },
}

# Pairwise compatibility. Exactly one of A/B/C/D per pair.
COMPATIBILITY_PAIRS = {
    "gfm__giezendanner": {
        "left": "copernicus-gfm-ensemble-flood-extent",
        "right": "giezendanner-bangladesh-inundation-history",
        "decision": "D",
        "reason": (
            "Giezendanner is DERIVED CNN–LSTM fractional inundation at 8-day / 500 m, "
            "trained on S1 fractions fused onto MODIS. GFM is OBSERVED 20 m SAR ensemble "
            "at a 192 h scene slot with 255 unknown. Different flood definition, resolution, "
            "temporal aggregation, permanent-water treatment, and uncertainty. Training "
            "inputs include FABDEM (NC-SA). Do not unify pixels. Rasters were not accessible."
        ),
    },
    "gfm__gfd": {
        "left": "copernicus-gfm-ensemble-flood-extent",
        "right": "global-flood-database",
        "decision": "C",
        "reason": (
            "GFD is observed MODIS event-maximum water at 250 m for DFO date ranges, "
            "optical/cloud-limited, CC BY-NC, and not a t0→t+192 h forecast label. "
            "Useful to discover which DFO events were satellite-mapped. Do not merge "
            "event-max pixels with GFM scene labels or upsample 250 m to 20 m. "
            "Population exposure is not a label. Optional future separate-eval track "
            "would be B, not a unified training set."
        ),
    },
    "giezendanner__gfd": {
        "left": "giezendanner-bangladesh-inundation-history",
        "right": "global-flood-database",
        "decision": "D",
        "reason": (
            "Derived 8-day 500 m fractional inundation vs observed event-max 250 m MODIS. "
            "Incompatible flood definition, timing, and processing. Do not merge."
        ),
    },
    "gfm__dfo": {
        "left": "copernicus-gfm-ensemble-flood-extent",
        "right": "dartmouth-flood-observatory",
        "decision": "C",
        "reason": (
            "DFO is an event catalog without inundation rasters. Match events in time, "
            "never invent DFO pixels. One DFO ID and one GFM cluster can describe the "
            "same real-world flood."
        ),
    },
    "gfd__dfo": {
        "left": "global-flood-database",
        "right": "dartmouth-flood-observatory",
        "decision": "C",
        "reason": (
            "GFD events are a QC subset of DFO IDs (2000–2018). Same real-world event; "
            "GFD adds a mapped extent, DFO adds the catalog. Not two independent floods."
        ),
    },
}

REGISTRY_FIELDS = (
    "event_id",
    "source_event_id",
    "year",
    "region",
    "event_start",
    "event_peak",
    "event_end",
    "flood_mechanism",
    "source",
    "observation_family",
    "label_kind",
    "source_confidence",
    "gfm_available",
    "secondary_label_available",
    "rainfall_available",
    "dem_available",
    "river_data_available",
    "event_eligible",
    "cube_eligible",
    "quality",
    "accepted",
    "rejection_reason",
    "matched_gfm_event_id",
    "independent_from_gfm",
    "spatial_resolution_m",
    "license",
    "provenance",
)


def _iso_day(value: str) -> str:
    return str(value)[:10]


def _month(day: str) -> int:
    return int(_iso_day(day)[5:7])


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_gfm_events() -> List[dict]:
    blob = _load_json(INVENTORY_DIR / "gfm_events_v21.json")
    return list(blob.get("events") or [])


def load_gfd_events() -> List[dict]:
    blob = _load_json(INVENTORY_DIR / "gfd_bangladesh_events.json")
    return list(blob.get("events") or [])


def load_dfo_events() -> List[dict]:
    blob = _load_json(INVENTORY_DIR / "dfo_bangladesh_events.json")
    rows = []
    for raw in blob.get("events") or []:
        rows.append(
            {
                **raw,
                "source_event_id": f"dfo:{raw['dfo_id']}",
                "source": "dartmouth-flood-observatory",
                "observation_family": FAMILY_DFO,
                "label_kind": "INVENTORY",
                "license": "DFO public catalog",
                "spatial_resolution_m": None,
            }
        )
    return rows


def centroid_in_bangladesh(lat: Optional[float], lon: Optional[float]) -> bool:
    if lat is None or lon is None:
        return True
    return BD_LAT_MIN <= lat <= BD_LAT_MAX and BD_LON_MIN <= lon <= BD_LON_MAX


def country_is_bangladesh_useful(country: str) -> bool:
    text = (country or "").lower()
    if "nigeria" in text:
        return False
    return "bangladesh" in text


def _align_overlapping_secondary(rows: List[dict]) -> None:
    """Same real-world flood from DFO and GFD must share event_id."""
    secondary = [
        r
        for r in rows
        if r.get("accepted") and r.get("source") in {"global-flood-database", "dartmouth-flood-observatory"}
    ]
    for i, a in enumerate(secondary):
        for b in secondary[i + 1 :]:
            if match_windows(a["event_start"], a["event_end"], b["event_start"], b["event_end"]):
                keep = a["matched_gfm_event_id"] or b["matched_gfm_event_id"] or min(a["event_id"], b["event_id"])
                a["event_id"] = keep
                b["event_id"] = keep
                if a.get("matched_gfm_event_id") or b.get("matched_gfm_event_id"):
                    a["matched_gfm_event_id"] = a.get("matched_gfm_event_id") or b.get("matched_gfm_event_id")
                    b["matched_gfm_event_id"] = a["matched_gfm_event_id"]
                    a["independent_from_gfm"] = False
                    b["independent_from_gfm"] = False
                    a["gfm_available"] = True
                    b["gfm_available"] = True


def quality_reject_secondary(row: dict) -> Tuple[bool, str, str]:
    """Return (ok, quality, rejection_reason)."""
    start = _iso_day(row.get("event_start") or "")
    end = _iso_day(row.get("event_end") or start)
    if not start:
        return False, "no_dates", "missing_event_dates"
    if not country_is_bangladesh_useful(row.get("country") or ""):
        return False, "not_bangladesh", "country_not_bangladesh_useful"
    area = row.get("area_km2")
    dead = int(row.get("dead") or 0)
    disp = int(row.get("displaced") or 0)
    if not centroid_in_bangladesh(row.get("lat"), row.get("lon")):
        area_val = float(area) if area is not None else 0.0
        if area_val < 100000:
            return False, "outside_aoi", "centroid_outside_bangladesh"
    if area is not None and float(area) < 1000 and dead == 0 and disp < 10000:
        return False, "tiny_extent", "tiny_or_unconfirmed_extent"
    month = _month(start)
    if month in (1, 2) and dead == 0 and disp < 10000:
        return False, "winter_residual", "winter_residual_water_cluster"
    cause = (row.get("main_cause") or "").lower()
    if "tropical" in cause or "cyclone" in cause or "amphan" in cause or "storm surge" in cause:
        quality = "tropical_cyclone_or_compound"
    elif month in (4, 5):
        quality = "haor_premonsoon"
    elif month in (6, 7, 8, 9, 10):
        quality = "monsoon_riverine"
    else:
        quality = "ok"
    return True, quality, ""


def match_windows(a0: str, a1: str, b0: str, b1: str) -> bool:
    return intervals_overlap(a0, a1, b0, b1, pad_days=EVENT_GAP_DAYS)


def cluster_source_rows(rows: Sequence[dict]) -> List[List[dict]]:
    if not rows:
        return []
    ordered = sorted(rows, key=lambda r: (_iso_day(r["event_start"]), _iso_day(r.get("event_end") or r["event_start"])))
    groups: List[List[dict]] = [[ordered[0]]]
    for row in ordered[1:]:
        prev = groups[-1]
        p0 = min(_iso_day(x["event_start"]) for x in prev)
        p1 = max(_iso_day(x.get("event_end") or x["event_start"]) for x in prev)
        if match_windows(p0, p1, row["event_start"], row.get("event_end") or row["event_start"]):
            groups[-1].append(row)
        else:
            groups.append([row])
    return groups


def _dem_river_available() -> Tuple[bool, bool]:
    return (SPATIAL_DIR / "elevation_lattice.json").exists(), (SPATIAL_DIR / "rivers_osm.json").exists()


def _confidence(row: dict) -> str:
    sev = row.get("severity")
    disp = int(row.get("displaced") or 0)
    dead = int(row.get("dead") or 0)
    if sev and float(sev) >= 1.5 and (disp >= 10000 or dead > 0):
        return "high"
    if disp >= 10000 or dead > 0:
        return "medium"
    return "low"


def build_registry() -> dict:
    INVENTORY_DIR.mkdir(parents=True, exist_ok=True)
    dem_ok, river_ok = _dem_river_available()
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    gfm = load_gfm_events()
    gfd_raw = load_gfd_events()
    dfo_raw = load_dfo_events()
    gfd_geo = {int(x["dfo_id"]): x for x in gfd_raw if x.get("dfo_id") is not None}
    for row in dfo_raw:
        g = gfd_geo.get(int(row.get("dfo_id") or 0))
        if g:
            row.setdefault("lat", g.get("lat"))
            row.setdefault("lon", g.get("lon"))

    registry: List[dict] = []

    # GFM family: already clustered. Keep cube vs indexed distinction.
    gfm_windows = []
    for row in gfm:
        start, end = _iso_day(row["event_start"]), _iso_day(row["event_end"])
        flood_px = int(row.get("pixels_flood") or 0)
        unk = row.get("unknown_fraction")
        quality = row.get("quality_status") or "ok"
        rejection = ""
        accepted = True
        if _month(start) in (1, 2) and flood_px < 50:
            quality = "weak_residual_water"
        if unk is not None and float(unk) >= 0.80:
            quality = "high_unknown"
        cube = bool(row.get("cube_eligible", True))
        if not cube:
            rejection = row.get("rejection_from_cube") or "not_cube_eligible"
        rain = lattice_covers(start, end)
        gfm_windows.append((row["event_id"], start, end))
        registry.append(
            {
                "event_id": row["event_id"],
                "source_event_id": row.get("source_event_id") or row["event_id"],
                "year": int(start[:4]),
                "region": ",".join(row.get("region_ids") or []),
                "event_start": start,
                "event_peak": _iso_day(row.get("event_peak") or start),
                "event_end": end,
                "flood_mechanism": row.get("flood_mechanism") or flood_mechanism_for_date(start),
                "source": "copernicus-gfm-ensemble-flood-extent",
                "observation_family": FAMILY_GFM,
                "label_kind": "OBSERVED",
                "source_confidence": "high" if cube else "medium",
                "gfm_available": True,
                "secondary_label_available": False,
                "rainfall_available": rain,
                "dem_available": dem_ok,
                "river_data_available": river_ok,
                "event_eligible": True,
                "cube_eligible": cube,
                "quality": quality,
                "accepted": accepted,
                "rejection_reason": rejection,
                "matched_gfm_event_id": row["event_id"],
                "independent_from_gfm": False,
                "spatial_resolution_m": 20,
                "license": "STAC proprietary; Copernicus attribution",
                "provenance": f"phase6.5-gfm-spatial-v2.1;retrieved={retrieved}",
            }
        )

    def _match_gfm(start: str, end: str) -> Optional[str]:
        for eid, g0, g1 in gfm_windows:
            if match_windows(start, end, g0, g1):
                return eid
        return None

    # GFD observations: same DFO IDs as catalog; attach as second source on matches,
    # and keep unique clusters only if quality-ok and independent.
    gfd_ok = []
    gfd_rejected = []
    for row in gfd_raw:
        ok, quality, why = quality_reject_secondary(row)
        rec = {**row, "quality": quality, "rejection_reason": why}
        if ok:
            gfd_ok.append(rec)
        else:
            gfd_rejected.append(rec)

    for group in cluster_source_rows(gfd_ok):
        start = min(_iso_day(x["event_start"]) for x in group)
        end = max(_iso_day(x.get("event_end") or x["event_start"]) for x in group)
        peak = start
        matched = _match_gfm(start, end)
        ids = ",".join(x["source_event_id"] for x in group)
        primary = max(group, key=lambda x: float(x.get("area_km2") or 0))
        independent = matched is None
        eid = matched or f"evt:{start}"
        registry.append(
            {
                "event_id": eid,
                "source_event_id": ids,
                "year": int(start[:4]),
                "region": "bangladesh",
                "event_start": start,
                "event_peak": peak,
                "event_end": end,
                "flood_mechanism": flood_mechanism_for_date(start),
                "source": "global-flood-database",
                "observation_family": FAMILY_GFD,
                "label_kind": "OBSERVED",
                "source_confidence": _confidence(primary),
                "gfm_available": matched is not None,
                "secondary_label_available": True,
                "rainfall_available": lattice_covers(start, end),
                "dem_available": dem_ok,
                "river_data_available": river_ok,
                "event_eligible": independent or matched is not None,
                "cube_eligible": False,
                "quality": primary.get("quality") or "ok",
                "accepted": True,
                "rejection_reason": "" if independent or matched else "",
                "matched_gfm_event_id": matched or "",
                "independent_from_gfm": independent,
                "spatial_resolution_m": 250,
                "license": "CC BY-NC 4.0",
                "provenance": f"gfd_qcdatabase_2019_08_01;dfo_ids={ids};retrieved={retrieved}",
            }
        )

    for rec in gfd_rejected:
        start = _iso_day(rec.get("event_start") or "")
        registry.append(
            {
                "event_id": f"rej:gfd:{rec.get('dfo_id')}",
                "source_event_id": rec.get("source_event_id"),
                "year": int(start[:4]) if start else None,
                "region": "bangladesh",
                "event_start": start,
                "event_peak": start,
                "event_end": _iso_day(rec.get("event_end") or start),
                "flood_mechanism": flood_mechanism_for_date(start) if start else "",
                "source": "global-flood-database",
                "observation_family": FAMILY_GFD,
                "label_kind": "OBSERVED",
                "source_confidence": "rejected",
                "gfm_available": False,
                "secondary_label_available": True,
                "rainfall_available": bool(start) and lattice_covers(start, rec.get("event_end") or start),
                "dem_available": dem_ok,
                "river_data_available": river_ok,
                "event_eligible": False,
                "cube_eligible": False,
                "quality": rec.get("quality"),
                "accepted": False,
                "rejection_reason": rec.get("rejection_reason"),
                "matched_gfm_event_id": "",
                "independent_from_gfm": False,
                "spatial_resolution_m": 250,
                "license": "CC BY-NC 4.0",
                "provenance": f"gfd_qcdatabase_2019_08_01;rejected;retrieved={retrieved}",
            }
        )

    dfo_ok, dfo_rejected = [], []
    for row in dfo_raw:
        ok, quality, why = quality_reject_secondary(row)
        rec = {**row, "quality": quality, "rejection_reason": why}
        (dfo_ok if ok else dfo_rejected).append(rec)

    gfd_ids = {int(x.get("dfo_id")) for x in gfd_raw if x.get("dfo_id") is not None}

    for group in cluster_source_rows(dfo_ok):
        start = min(_iso_day(x["event_start"]) for x in group)
        end = max(_iso_day(x.get("event_end") or x["event_start"]) for x in group)
        matched = _match_gfm(start, end)
        ids = ",".join(x["source_event_id"] for x in group)
        primary = max(group, key=lambda x: float(x.get("area_km2") or 0))
        independent = matched is None
        eid = matched or f"evt:{start}"
        also_gfd = any(int(x.get("dfo_id") or 0) in gfd_ids for x in group)
        registry.append(
            {
                "event_id": eid,
                "source_event_id": ids,
                "year": int(start[:4]),
                "region": "bangladesh",
                "event_start": start,
                "event_peak": start,
                "event_end": end,
                "flood_mechanism": flood_mechanism_for_date(start),
                "source": "dartmouth-flood-observatory",
                "observation_family": FAMILY_DFO,
                "label_kind": "INVENTORY",
                "source_confidence": _confidence(primary),
                "gfm_available": matched is not None,
                "secondary_label_available": also_gfd,
                "rainfall_available": lattice_covers(start, end),
                "dem_available": dem_ok,
                "river_data_available": river_ok,
                "event_eligible": True,
                "cube_eligible": False,
                "quality": primary.get("quality") or "ok",
                "accepted": True,
                "rejection_reason": "",
                "matched_gfm_event_id": matched or "",
                "independent_from_gfm": independent,
                "spatial_resolution_m": "",
                "license": "DFO public catalog",
                "provenance": f"dfo_wiki_bangladesh;ids={ids};retrieved={retrieved}",
            }
        )

    for rec in dfo_rejected:
        start = _iso_day(rec.get("event_start") or "")
        registry.append(
            {
                "event_id": f"rej:dfo:{rec.get('dfo_id')}",
                "source_event_id": rec.get("source_event_id"),
                "year": int(start[:4]) if start else None,
                "region": rec.get("country"),
                "event_start": start,
                "event_peak": start,
                "event_end": _iso_day(rec.get("event_end") or start),
                "flood_mechanism": flood_mechanism_for_date(start) if start else "",
                "source": "dartmouth-flood-observatory",
                "observation_family": FAMILY_DFO,
                "label_kind": "INVENTORY",
                "source_confidence": "rejected",
                "gfm_available": False,
                "secondary_label_available": False,
                "rainfall_available": bool(start) and lattice_covers(start, rec.get("event_end") or start),
                "dem_available": dem_ok,
                "river_data_available": river_ok,
                "event_eligible": False,
                "cube_eligible": False,
                "quality": rec.get("quality"),
                "accepted": False,
                "rejection_reason": rec.get("rejection_reason"),
                "matched_gfm_event_id": "",
                "independent_from_gfm": False,
                "spatial_resolution_m": "",
                "license": "DFO public catalog",
                "provenance": f"dfo_wiki_bangladesh;rejected;retrieved={retrieved}",
            }
        )

    _align_overlapping_secondary(registry)

    # Giezendanner: no events (rasters inaccessible; not an event inventory).
    registry.append(
        {
            "event_id": "rej:giezendanner:not_acquired",
            "source_event_id": "doi:10.25739/2edm-jh03",
            "year": "",
            "region": "bangladesh",
            "event_start": "2001-01-01",
            "event_peak": "",
            "event_end": "2022-12-31",
            "flood_mechanism": "",
            "source": "giezendanner-bangladesh-inundation-history",
            "observation_family": FAMILY_BD_HIST,
            "label_kind": "DERIVED",
            "source_confidence": "unavailable",
            "gfm_available": False,
            "secondary_label_available": False,
            "rainfall_available": False,
            "dem_available": dem_ok,
            "river_data_available": river_ok,
            "event_eligible": False,
            "cube_eligible": False,
            "quality": "not_acquired",
            "accepted": False,
            "rejection_reason": "cyverse_anonymous_access_blocked",
            "matched_gfm_event_id": "",
            "independent_from_gfm": False,
            "spatial_resolution_m": 500,
            "license": "CyVerse curated; FABDEM NC-SA in training stack",
            "provenance": f"doi:10.25739/2edm-jh03;retrieved={retrieved}",
        }
    )

    INVENTORY_DIR.mkdir(parents=True, exist_ok=True)
    with REGISTRY_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REGISTRY_FIELDS), extrasaction="ignore")
        writer.writeheader()
        for row in registry:
            writer.writerow(row)
    REGISTRY_JSON.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    return {"n": len(registry), "rows": registry, "retrieved_at": retrieved}


def summarize_registry(rows: Sequence[dict]) -> dict:
    gfm_cube = [r for r in rows if r["source"] == "copernicus-gfm-ensemble-flood-extent" and r.get("cube_eligible")]
    gfm_all = [r for r in rows if r["source"] == "copernicus-gfm-ensemble-flood-extent" and r.get("accepted")]
    gfd_acc = [r for r in rows if r["source"] == "global-flood-database" and r.get("accepted")]
    dfo_acc = [r for r in rows if r["source"] == "dartmouth-flood-observatory" and r.get("accepted")]
    unique_ids = set()
    for r in gfm_cube:
        unique_ids.add(r["event_id"])
    unique_secondary = []
    overlap_gfd = overlap_dfo = 0
    for r in gfd_acc:
        if r.get("independent_from_gfm"):
            if r["event_id"] not in unique_ids:
                unique_ids.add(r["event_id"])
                unique_secondary.append(r)
        else:
            overlap_gfd += 1
    for r in dfo_acc:
        if r.get("independent_from_gfm"):
            if r["event_id"] not in unique_ids:
                unique_ids.add(r["event_id"])
                unique_secondary.append(r)
        else:
            overlap_dfo += 1

    # Combined independent real-world events = unique event_id set among accepted
    # GFM cube + independent quality secondary (DFO/GFD). GFM winters remain in official 15.
    combined = sorted(unique_ids)
    by_year: Dict[str, set] = {}
    by_mech: Dict[str, set] = {}
    for eid in combined:
        members = [r for r in rows if r.get("event_id") == eid and r.get("accepted")]
        if not members:
            continue
        year = str(members[0].get("year") or "")[:4]
        by_year.setdefault(year, set()).add(eid)
        mech = members[0].get("flood_mechanism") or "unspecified"
        by_mech.setdefault(mech, set()).add(eid)

    n_gfm = len({r["event_id"] for r in gfm_cube})
    n_unique = len(unique_secondary)
    n_combined = len(combined)
    n_cube = n_gfm  # official cube-eligible stays GFM-only
    if n_combined < 20:
        research = "FAIL"
        research_text = f"FAIL ({n_combined} < 20 independent real-world events in the registry)"
    elif n_combined < 30:
        research = "MINIMUM FLOOR REACHED"
        research_text = f"MINIMUM FLOOR REACHED ({n_combined} independent real-world events; GFM cube still {n_gfm})"
    elif n_combined < 40:
        research = "RESEARCH-USEFUL"
        research_text = f"RESEARCH-USEFUL ({n_combined})"
    else:
        research = "STRONGER"
        research_text = f"STRONGER ({n_combined})"

    official_b = "PASS" if n_gfm >= 20 else "FAIL"

    return {
        "gfm_only": n_gfm,
        "gfm_indexed_including_non_cube": len({r["event_id"] for r in gfm_all}),
        "gfd_accepted_clusters": len(gfd_acc),
        "dfo_accepted_clusters": len(dfo_acc),
        "gfd_overlap_with_gfm": overlap_gfd,
        "dfo_overlap_with_gfm": overlap_dfo,
        "additional_unique_events": n_unique,
        "additional_unique_event_ids": sorted({r["event_id"] for r in unique_secondary}),
        "combined_independent_events": n_combined,
        "combined_event_ids": combined,
        "cube_eligible": n_cube,
        "events_per_year": {k: len(v) for k, v in sorted(by_year.items())},
        "events_per_mechanism": {k: len(v) for k, v in sorted(by_mech.items())},
        "official_gate_b": official_b,
        "research_recommendation": research,
        "research_text": research_text,
        "event_gap_days": EVENT_GAP_DAYS,
    }


def write_compatibility_matrix() -> dict:
    payload = {
        "observation_families": {
            FAMILY_GFM: "GFM OBSERVED 20 m scene labels",
            FAMILY_BD_HIST: "Bangladesh 2001–2022 Giezendanner DERIVED 500 m 8-day",
            FAMILY_GFD: "Global Flood Database OBSERVED event-max 250 m",
            FAMILY_DFO: "DFO event catalog (no pixels)",
        },
        "sources": SOURCES,
        "pairs": COMPATIBILITY_PAIRS,
        "default_state": "SEPARATE OBSERVATION FAMILY",
        "harmonization": {
            "strategy_a": "GFM-only training labels; other sources event discovery only. RECOMMENDED.",
            "strategy_b": "Separate evaluation tracks per family. Optional later; not implemented.",
            "strategy_c": "Harmonized intersection/union/probabilistic target. NOT implemented. Not justified.",
        },
        "resolution": {
            "do_not_upsample": True,
            "gfm_m": 20,
            "giezendanner_m": 500,
            "gfd_m": 250,
            "recommendation": (
                "Keep GFM-only 20 m as the high-resolution benchmark. "
                "If a historical track is ever built, keep it at native 500 m / 250 m as a "
                "coarse-resolution research benchmark. Multi-resolution training labels are "
                "not scientifically justified here."
            ),
        },
    }
    COMPAT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with COMPAT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["pair", "left", "right", "decision", "reason"])
        writer.writeheader()
        for key, row in COMPATIBILITY_PAIRS.items():
            writer.writerow({"pair": key, **row})
    return payload


def evaluate_phase65c() -> dict:
    """Event-registry quality only. No training. Does not overwrite GFM v2.1 tensors."""
    from floodlens.ml.spatial.gates import GATE0_MIN_EVENTS, GATE0_MIN_REGIONS

    built = build_registry()
    summary = summarize_registry(built["rows"])
    compat = write_compatibility_matrix()
    payload = {
        "evaluated_at": built["retrieved_at"],
        "phase": "6.5C",
        "dataset_version": REGISTRY_VERSION,
        "does_not_overwrite": "phase6.5-gfm-spatial-v2.1",
        "cnn_trained": False,
        "gbdt_trained": False,
        "unet_trained": False,
        "catalog_status": "NOT_VALIDATED",
        "spatial_ai": "NOT_VALIDATED",
        "api_ai_spatial": "UNAVAILABLE",
        "solver_modified": False,
        "gate_b_official_floor_unchanged": GATE0_MIN_EVENTS,
        "gate_f_official_floor_unchanged": GATE0_MIN_REGIONS,
        "compatibility": {k: v["decision"] for k, v in COMPATIBILITY_PAIRS.items()},
        "sources": {k: {"accessible": v.get("accessible"), "label_kind": v.get("label_kind"), "license": v.get("license")} for k, v in SOURCES.items()},
        "summary": summary,
        "registry_csv": str(REGISTRY_CSV),
        "note": (
            "Observation families remain separate. No pixel labels were merged. "
            "Official Gate B is GFM cube-eligible independent events only."
        ),
    }
    PHASE65C_EVAL.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
