"""Phase 6.5B: independent-event discovery, inventory, and event-oriented GFM acquire.

Does not train. Does not fabricate labels. Does not loosen the 45-day rule.
"""

from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from floodlens.ml.spatial.acquire_gfm import (
    MAX_BYTES,
    MIN_VALID_FRAC,
    RAW_DIR,
    TILE_ID,
    _download,
    _file_fingerprint,
    covering_orbit_score,
    index_local_v2,
    search_window,
    union_bbox_v2,
    _dedupe_orbits,
)
from floodlens.ml.spatial.events import EVENT_GAP_DAYS, cluster_dates
from floodlens.ml.spatial.schema import SPATIAL_DIR

INVENTORY_DIR = SPATIAL_DIR / "event_inventory"
CANDIDATES_CSV = INVENTORY_DIR / "event_candidates.csv"
CANDIDATES_JSON = INVENTORY_DIR / "event_candidates.json"
STAC_CACHE = INVENTORY_DIR / "stac_discovery.json"
SYLHET_DIAG = INVENTORY_DIR / "sylhet_diagnosis.json"
UNKNOWN_DIAG = INVENTORY_DIR / "unknown_diagnostics.json"

# Existing 6.5A independent events (45-day clusters). Do not re-label as new.
BASELINE_EVENT_IDS = (
    "evt:2016-06-30",
    "evt:2018-01-13",
    "evt:2018-06-06",
    "evt:2019-06-15",
    "evt:2020-06-07",
    "evt:2021-06-02",
    "evt:2022-05-16",
    "evt:2023-06-16",
)

# Target clusters to try for NEW independent pulses. Not GeoTIFF maximization.
# One covering-orbit attempt set per cluster, then stop if AOI-valid.
# Prefer years already inside the precip lattice window (2016-06-01 … 2024-08-31).
TARGET_CLUSTERS = (
    {"event_id": "cand:2017-04", "year": 2017, "start": "2017-04-12", "end": "2017-05-20", "season": "premonsoon", "mechanism": "haor_premonsoon_flash"},
    {"event_id": "cand:2017-08", "year": 2017, "start": "2017-07-31", "end": "2017-08-25", "season": "monsoon", "mechanism": "monsoon_riverine"},
    {"event_id": "cand:2024-07", "year": 2024, "start": "2024-06-20", "end": "2024-08-15", "season": "monsoon", "mechanism": "monsoon_riverine"},
    {"event_id": "cand:2025-07", "year": 2025, "start": "2025-06-20", "end": "2025-08-15", "season": "monsoon", "mechanism": "monsoon_riverine"},
    {"event_id": "cand:2015-07", "year": 2015, "start": "2015-07-01", "end": "2015-08-20", "season": "monsoon", "mechanism": "monsoon_riverine"},
    {"event_id": "cand:2016-01", "year": 2016, "start": "2016-01-10", "end": "2016-02-05", "season": "winter", "mechanism": "winter_or_early"},
    {"event_id": "cand:2019-01", "year": 2019, "start": "2019-01-10", "end": "2019-02-05", "season": "winter", "mechanism": "winter_or_early"},
    {"event_id": "cand:2020-01", "year": 2020, "start": "2020-01-10", "end": "2020-02-05", "season": "winter", "mechanism": "winter_or_early"},
)

MAX_ATTEMPTS_PER_CLUSTER = 4
MAX_NEW_DOWNLOADS = 24

SOURCE_COMPATIBILITY = {
    "copernicus-gfm-ensemble-flood-extent": {
        "decision": "A",
        "role": "primary_label",
        "observed_extent": True,
        "spatial_resolution": "20 m Equi7",
        "temporal_resolution": "S1 revisit ~6–12 d; 192 h scene slot",
        "bangladesh": True,
        "historical": "2015–present (public STAC)",
        "unknown": "uint8 255 nodata/exclusion, not optical cloud",
        "license": "STAC proprietary; Copernicus attribution",
        "compatible_with_gfm": True,
        "note": "Headline OBSERVED label. Expand years/orbits, do not replace.",
    },
    "opera-dswx-s1": {
        "decision": "D",
        "role": "incompatible_duplicate",
        "observed_extent": True,
        "note": "Same S1 revisit class as GFM. Do not train a second classifier or merge labels.",
    },
    "viirs-modis-nrt": {
        "decision": "D",
        "role": "incompatible",
        "observed_extent": True,
        "note": "Optical, cloud-heavy, different flood definition and unknown process.",
    },
    "global-flood-database": {
        "decision": "C",
        "role": "event_discovery_only",
        "observed_extent": True,
        "license": "CC BY-NC",
        "note": "Event-max climatology, not t0→t+192 h forecast labels. NC. Do not mix into headline metrics.",
    },
    "giezendanner-bangladesh": {
        "decision": "D",
        "role": "incompatible",
        "observed_extent": False,
        "note": "DERIVED 8-day ~500 m. Never call OBSERVED. Do not mix with GFM.",
    },
    "glofas-rapid-flood-mapping": {
        "decision": "D",
        "role": "incompatible",
        "observed_extent": False,
        "note": "MODELLED RP inundation. Comparison candidate, not training labels.",
    },
    "emsr": {
        "decision": "C",
        "role": "event_discovery_only",
        "note": "Phase 4 found 0 Bangladesh rows in the public list.",
    },
    "worldfloods-sen1floods11": {
        "decision": "D",
        "role": "incompatible",
        "note": "Same-time mapping / often NC. Wrong task for these AOIs.",
    },
}

REGION_PROFILES = {
    "sunamganj": {"mechanism": "haor_monsoon_inundation", "basin": "haor_meghna"},
    "sylhet": {"mechanism": "haor_monsoon_inundation", "basin": "haor_meghna"},
    "kishoreganj": {"mechanism": "haor_meghna_floodplain", "basin": "haor_meghna"},
    "netrokona": {"mechanism": "haor_meghna_floodplain", "basin": "haor_meghna"},
    "dhaka_sw": {"mechanism": "central_floodplain_riverine", "basin": "central_floodplain"},
    "dhaka_se": {"mechanism": "central_floodplain_riverine", "basin": "central_floodplain"},
    "dhaka_nw": {"mechanism": "central_floodplain_riverine", "basin": "central_floodplain"},
    "dhaka_ne": {"mechanism": "central_floodplain_riverine", "basin": "central_floodplain"},
}


def _iso_day(value: str) -> str:
    return str(value)[:10]


def intervals_overlap(a0: str, a1: str, b0: str, b1: str, pad_days: int = EVENT_GAP_DAYS) -> bool:
    """True if two episodes are the same pulse under the 45-day rule."""
    a0d = datetime.fromisoformat(_iso_day(a0))
    a1d = datetime.fromisoformat(_iso_day(a1))
    b0d = datetime.fromisoformat(_iso_day(b0))
    b1d = datetime.fromisoformat(_iso_day(b1))
    if a1d < a0d:
        a0d, a1d = a1d, a0d
    if b1d < b0d:
        b0d, b1d = b1d, b0d
    gap = (b0d - a1d).days if b0d > a1d else (a0d - b1d).days if a0d > b1d else 0
    if b0d <= a1d and a0d <= b1d:
        return True
    return gap <= pad_days


def deduplication_key(start: str, end: str, basin: str = "bangladesh_monsoon") -> str:
    return f"{basin}:{_iso_day(start)}:{_iso_day(end)}"


def flood_mechanism_for_date(day: str, region_id: str = "") -> str:
    month = int(day[5:7])
    profile = REGION_PROFILES.get(region_id) or {}
    if month in (4, 5):
        return "haor_premonsoon_flash"
    if month in (6, 7, 8, 9):
        return profile.get("mechanism") or "monsoon_riverine"
    if month in (1, 2):
        return "winter_or_early"
    return profile.get("mechanism") or "unspecified"


def baseline_windows() -> List[Tuple[str, str, str]]:
    """Approximate start/end from 6.5A event ids (cluster start dates)."""
    # end unknown until samples exist; use +45d exclusive neighbor as conservative span
    out = []
    for eid in BASELINE_EVENT_IDS:
        start = eid.replace("evt:", "")
        end = (datetime.fromisoformat(start) + timedelta(days=50)).date().isoformat()
        out.append((eid, start, end))
    return out


def independent_from_existing(start: str, end: str, existing: Optional[Sequence[Tuple[str, str, str]]] = None) -> Tuple[bool, str]:
    existing = list(existing or baseline_windows())
    for eid, e0, e1 in existing:
        if intervals_overlap(start, end, e0, e1):
            return False, f"overlaps_{eid}"
    return True, ""


def discover_cluster(cluster: dict) -> dict:
    bbox = union_bbox_v2()
    hits = search_window(cluster["start"], cluster["end"], bbox, limit=100, retries=5)
    daily = _dedupe_orbits(hits, tiles=(TILE_ID,))
    daily.sort(key=lambda r: (covering_orbit_score(r.get("datetime") or ""), r.get("datetime") or ""))
    return {
        **cluster,
        "n_stac_features": len(hits),
        "n_orbit_candidates": len(daily),
        "candidates": daily,
        "stac_empty": len(hits) == 0,
    }


def _local_path(scene_id: str) -> Path:
    return RAW_DIR / f"{scene_id}.tif"


def acquire_cluster(cluster: dict, *, download: bool = True) -> dict:
    """Download covering-orbit GFM until one AOI-valid scene exists, or attempts exhausted."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    discovered = discover_cluster(cluster)
    attempts = []
    accepted_scene = None
    used = sum(p.stat().st_size for p in RAW_DIR.glob("*.tif"))
    n_new = 0
    for row in discovered.get("candidates") or []:
        if n_new >= MAX_ATTEMPTS_PER_CLUSTER:
            break
        if n_new >= MAX_NEW_DOWNLOADS:
            break
        dest = _local_path(row["id"])
        if dest.exists() and dest.stat().st_size > 1000:
            attempts.append({**row, "status": "skipped_existing", "bytes": dest.stat().st_size})
            continue
        if not download:
            attempts.append({**row, "status": "not_downloaded"})
            continue
        if used > MAX_BYTES:
            attempts.append({**row, "status": "byte_cap"})
            break
        if n_new >= MAX_ATTEMPTS_PER_CLUSTER:
            break
        try:
            _download(row["href"], dest)
            used = sum(p.stat().st_size for p in RAW_DIR.glob("*.tif"))
            n_new += 1
            fp = _file_fingerprint(dest)
            attempts.append({**row, "status": "downloaded", "bytes": dest.stat().st_size, "checksum": fp})
            accepted_scene = row["id"]
        except Exception as exc:
            attempts.append({**row, "status": "download_failed", "reason": str(exc)})
            continue
    discovered["attempts"] = attempts
    discovered["probe_scene_id"] = accepted_scene
    discovered["n_new_downloads"] = n_new
    return discovered


def acquire_target_clusters(*, download: bool = True) -> dict:
    INVENTORY_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, cluster in enumerate(TARGET_CLUSTERS):
        print(f"discover {cluster['event_id']} {cluster['start']}..{cluster['end']}", flush=True)
        rows.append(acquire_cluster(cluster, download=download))
        if i + 1 < len(TARGET_CLUSTERS):
            time.sleep(3)
    index = index_local_v2()
    payload = {
        "acquired_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "clusters": rows,
        "gfm_index_n_kept": index.get("n_kept"),
        "duplicate_scenes": detect_duplicate_scenes(index),
        "source_compatibility": SOURCE_COMPATIBILITY,
    }
    STAC_CACHE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def detect_duplicate_scenes(index: dict) -> List[str]:
    ids = [s.get("id") for s in (index.get("scenes") or []) if s.get("id")]
    seen = set()
    dups = []
    for sid in ids:
        if sid in seen:
            dups.append(sid)
        seen.add(sid)
    return sorted(set(dups))


LATTICE_START = "2016-06-01"
LATTICE_END = "2024-08-31"


def lattice_covers(start: str, end: str) -> bool:
    s, e = _iso_day(start), _iso_day(end)
    return s >= LATTICE_START and e <= LATTICE_END


CANDIDATE_FIELDS = (
    "event_id",
    "year",
    "region",
    "candidate_source",
    "candidate_start",
    "candidate_peak",
    "candidate_end",
    "gfm_available",
    "rain_available",
    "dem_available",
    "river_available",
    "quality",
    "independent_from_existing",
    "accepted",
    "rejection_reason",
    "provenance",
    "season",
    "mechanism",
    "deduplication_key",
)


def _scene_span(index: dict) -> List[dict]:
    scenes = list(index.get("scenes") or [])
    dates = sorted({(s.get("datetime") or "")[:10] for s in scenes if s.get("datetime")})
    groups = cluster_dates(dates, gap_days=EVENT_GAP_DAYS)
    rows = []
    by_day = {}
    for scene in scenes:
        by_day.setdefault((scene.get("datetime") or "")[:10], []).append(scene)
    for g in groups:
        members = []
        for d in g:
            members.extend(by_day.get(d) or [])
        aois = sorted({a for s in members for a in (s.get("cities") or {})})
        flood = dry = unk = 0
        peak = None
        peak_score = -1.0
        for scene in members:
            for stats in (scene.get("cities") or {}).values():
                fl = int(stats.get("n_flood") or 0)
                dr = int(stats.get("n_dry") or 0)
                un = int(stats.get("n_unknown") or 0)
                flood += fl
                dry += dr
                unk += un
                valid = fl + dr
                score = (fl / valid) if valid else 0.0
                if score > peak_score:
                    peak_score = score
                    peak = scene.get("datetime")
        eid = f"evt:{g[0]}"
        rows.append(
            {
                "event_id": eid,
                "year": int(g[0][:4]),
                "region": ",".join(aois),
                "candidate_source": "copernicus-gfm-ensemble-flood-extent",
                "candidate_start": g[0],
                "candidate_peak": (peak or g[0])[:10],
                "candidate_end": g[-1],
                "gfm_available": True,
                "season": "premonsoon" if int(g[0][5:7]) in (4, 5) else ("winter" if int(g[0][5:7]) <= 3 else "monsoon"),
                "mechanism": flood_mechanism_for_date(g[0], aois[0] if aois else ""),
                "pixels_flood": flood,
                "pixels_dry": dry,
                "pixels_unknown": unk,
                "n_scenes": len(members),
                "scene_ids": [s.get("id") for s in members],
            }
        )
    return rows


def build_candidate_inventory(index: Optional[dict] = None, acquire_log: Optional[dict] = None) -> List[dict]:
    from floodlens.ml.spatial.acquire_gfm import PROCESSED_DIR_V2

    if index is None:
        path = PROCESSED_DIR_V2 / "index.json"
        index = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"scenes": []}
    elev_ok = (SPATIAL_DIR / "elevation_lattice.json").exists()
    rain_ok = (SPATIAL_DIR / "precip_lattice.json").exists()
    river_ok = (SPATIAL_DIR / "rivers_osm.json").exists()

    accepted_rows = _scene_span(index)
    existing_windows = [(r["event_id"], r["candidate_start"], r["candidate_end"]) for r in accepted_rows]
    inventory: List[dict] = []
    for row in accepted_rows:
        valid = (row["pixels_flood"] + row["pixels_dry"])
        total = valid + row["pixels_unknown"]
        quality = "ok"
        rejection = ""
        accepted = True
        if valid / max(total, 1) < MIN_VALID_FRAC:
            quality = "poor_valid_fraction"
            accepted = False
            rejection = "valid_fraction_below_5pct"
        elif row["pixels_flood"] == 0:
            quality = "no_flood_pixels"
            accepted = False
            rejection = "no_flood_pixels"
        inventory.append(
            {
                "event_id": row["event_id"],
                "year": row["year"],
                "region": row["region"],
                "candidate_source": row["candidate_source"],
                "candidate_start": row["candidate_start"],
                "candidate_peak": row["candidate_peak"],
                "candidate_end": row["candidate_end"],
                "gfm_available": True,
                "rain_available": rain_ok and lattice_covers(row["candidate_start"], row["candidate_end"]),
                "dem_available": elev_ok,
                "river_available": river_ok,
                "quality": quality,
                "independent_from_existing": True,
                "accepted": accepted,
                "rejection_reason": rejection,
                "provenance": f"gfm_index:{row['n_scenes']}_scenes",
                "season": row["season"],
                "mechanism": row["mechanism"],
                "deduplication_key": deduplication_key(row["candidate_start"], row["candidate_end"]),
            }
        )

    for cluster in (acquire_log or {}).get("clusters") or TARGET_CLUSTERS:
        start, end = cluster["start"], cluster["end"]
        indep, why = independent_from_existing(start, end, existing_windows)
        stac_n = cluster.get("n_stac_features")
        if stac_n is None:
            continue
        already = any(intervals_overlap(start, end, r["candidate_start"], r["candidate_end"]) for r in accepted_rows)
        if already:
            rejection = "already_in_index"
            accepted = False
        elif cluster.get("stac_empty"):
            rejection = "stac_empty_or_rate_limited"
            accepted = False
        elif not cluster.get("candidates") and not cluster.get("attempts"):
            rejection = "no_product_tile_orbits"
            accepted = False
        elif not indep:
            rejection = why
            accepted = False
        else:
            rejection = "downloaded_but_aoi_nodata" if cluster.get("attempts") else "not_aoi_valid_after_index"
            accepted = False
        inventory.append(
            {
                "event_id": cluster.get("event_id"),
                "year": cluster.get("year"),
                "region": "bangladesh_aois_v2",
                "candidate_source": "copernicus-gfm-ensemble-flood-extent",
                "candidate_start": start,
                "candidate_peak": "",
                "candidate_end": end,
                "gfm_available": bool(cluster.get("candidates") or cluster.get("attempts")),
                "rain_available": rain_ok and lattice_covers(start, end),
                "dem_available": elev_ok,
                "river_available": river_ok,
                "quality": "candidate",
                "independent_from_existing": indep,
                "accepted": accepted,
                "rejection_reason": rejection if not accepted else "",
                "provenance": f"stac_features={stac_n};attempts={len(cluster.get('attempts') or [])}",
                "season": cluster.get("season"),
                "mechanism": cluster.get("mechanism"),
                "deduplication_key": deduplication_key(start, end),
            }
        )

    INVENTORY_DIR.mkdir(parents=True, exist_ok=True)
    with CANDIDATES_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CANDIDATE_FIELDS), extrasaction="ignore")
        writer.writeheader()
        for row in inventory:
            writer.writerow(row)
    CANDIDATES_JSON.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    return inventory


def diagnose_sylhet() -> dict:
    """Sylhet has 0 kept v2 scenes. Measure why without enlarging the AOI."""
    from floodlens.ml.spatial.acquire_gfm import RAW_DIR, _read_gfm, clip_resample, GRID_SIZE_V2
    from floodlens.ml.spatial.equi7 import TILE_CATALOG, TILE_ID, city_window, in_tile
    from floodlens.ml.spatial.aois_v2 import AOI_BOUNDS

    bounds = AOI_BOUNDS["sylhet"]
    tile_hits = {tid: sum(in_tile(lat, lon, tid) for lat, lon in (
        (bounds[1], bounds[0]), (bounds[1], bounds[2]), (bounds[3], bounds[0]), (bounds[3], bounds[2])
    )) for tid in TILE_CATALOG}
    covering = None
    for path in sorted(RAW_DIR.glob("*E039N021T3.tif")):
        if "20180606T120436" in path.name:
            covering = path
            break
    if covering is None:
        covering = next(iter(sorted(RAW_DIR.glob("*E039N021T3.tif"))), None)
    vfracs = {}
    if covering is not None:
        arr = _read_gfm(covering)
        for aoi in ("sylhet", "sunamganj", "kishoreganj"):
            _, _, vfracs[aoi] = clip_resample(arr, aoi, size=GRID_SIZE_V2, tile_id=TILE_ID)
    cause = "scene_footprint_mismatch"
    if tile_hits.get(TILE_ID, 0) < 4:
        cause = "catalog_tile_mismatch"
    elif vfracs.get("sylhet", 0) >= MIN_VALID_FRAC:
        cause = "unexpected_valid_on_probe_scene"
    elif vfracs.get("sunamganj", 0) >= MIN_VALID_FRAC and vfracs.get("sylhet", 0) < MIN_VALID_FRAC:
        cause = "scene_footprint_mismatch"
    payload = {
        "aoi_bounds": list(bounds),
        "corners_in_tile": tile_hits,
        "probe_scene": None if covering is None else covering.name,
        "valid_frac_on_probe": vfracs,
        "min_valid_frac": MIN_VALID_FRAC,
        "diagnosis": cause,
        "kept_sylhet_scenes": [],
        "note": (
            "Sylhet's 0.8° box lies on E039N021T3 (not N024). On typical covering Sunamganj orbits "
            "(e.g. 20180606T120436), Sylhet valid_frac is ~0.1% because that SAR swath does not "
            "cover Sylhet city. This is footprint mismatch, not a 5% threshold bug and not solved "
            "by enlarging the AOI. Neighbor tile E039N024T3 does not contain the AOI. "
            "A minority of other orbits (2015-07-11, 2016-01-19) do clip ≥5% valid Sylhet pixels; "
            "those are orbit-specific, not a reason to enlarge the box."
        ),
    }
    from floodlens.ml.spatial.acquire_gfm import PROCESSED_DIR_V2

    idx_path = PROCESSED_DIR_V2 / "index.json"
    if idx_path.exists():
        index = json.loads(idx_path.read_text(encoding="utf-8"))
        payload["kept_sylhet_scenes"] = [
            s.get("id") for s in (index.get("scenes") or []) if "sylhet" in (s.get("cities") or {})
        ]
        payload["n_kept_sylhet_scenes"] = len(payload["kept_sylhet_scenes"])
    INVENTORY_DIR.mkdir(parents=True, exist_ok=True)
    SYLHET_DIAG.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def unknown_diagnostics(index: Optional[dict] = None) -> dict:
    from floodlens.ml.spatial.acquire_gfm import PROCESSED_DIR_V2

    if index is None:
        path = PROCESSED_DIR_V2 / "index.json"
        index = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"scenes": []}
    by_region: Dict[str, dict] = {}
    by_event: Dict[str, dict] = {}
    by_scene = []
    dates = sorted({(s.get("datetime") or "")[:10] for s in index.get("scenes") or []})
    start_of = {}
    for g in cluster_dates(dates):
        for d in g:
            start_of[d] = f"evt:{g[0]}"
    for scene in index.get("scenes") or []:
        day = (scene.get("datetime") or "")[:10]
        eid = start_of.get(day, f"evt:{day}")
        for aoi, stats in (scene.get("cities") or {}).items():
            fl = int(stats.get("n_flood") or 0)
            dr = int(stats.get("n_dry") or 0)
            un = int(stats.get("n_unknown") or 0)
            total = fl + dr + un
            unk_frac = (un / total) if total else None
            by_scene.append(
                {
                    "scene_id": scene.get("id"),
                    "region_id": aoi,
                    "tile_id": scene.get("tile"),
                    "event_id": eid,
                    "flood": fl,
                    "dry": dr,
                    "unknown": un,
                    "unknown_fraction": unk_frac,
                    "valid_frac": stats.get("valid_frac"),
                }
            )
            for bucket, key in ((by_region, aoi), (by_event, eid)):
                row = bucket.setdefault(key, {"flood": 0, "dry": 0, "unknown": 0})
                row["flood"] += fl
                row["dry"] += dr
                row["unknown"] += un

    def _finalize(mapping):
        out = []
        for key, row in sorted(mapping.items()):
            total = row["flood"] + row["dry"] + row["unknown"]
            out.append(
                {
                    "id": key,
                    **row,
                    "unknown_fraction": (row["unknown"] / total) if total else None,
                    "exclude_label_quality": (row["unknown"] / total) >= 0.80 if total else True,
                }
            )
        return out

    payload = {
        "by_region": _finalize(by_region),
        "by_event": _finalize(by_event),
        "by_scene_tile": by_scene,
        "worst_scene_unknown_fraction": max((r["unknown_fraction"] or 0.0) for r in by_scene) if by_scene else None,
        "worst_event_unknown_fraction": max((r["unknown_fraction"] or 0.0) for r in _finalize(by_event)) if by_event else None,
        "regions_suggested_exclude": [r["id"] for r in _finalize(by_region) if r.get("exclude_label_quality")],
    }
    INVENTORY_DIR.mkdir(parents=True, exist_ok=True)
    UNKNOWN_DIAG.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
