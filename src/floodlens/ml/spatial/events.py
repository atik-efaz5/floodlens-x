"""Independent flood-event grouping. Adjacent orbit pairs are not independent events."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Sequence

from floodlens.ml.leakage import parse_ts
from floodlens.ml.spatial.schema import UNKNOWN, SpatialForecastSample

# Scenes within this many days are one meteorological episode (orbit twins and
# intra-monsoon revisits). Adjacent 2-day GFM pairs are never two events.
EVENT_GAP_DAYS = 45
# Below this, do not claim enough events for VALIDATED spatial forecasting.
MIN_EVENTS_FOR_VALIDATION = 20
MIN_FLOOD_POSITIVE_EVENTS_TEST = 3

# Same monsoon pulse across haor vs central floodplain stays one event_id (date cluster).
# basin_id is metadata for coverage, not a second event key.
BASIN_OF = {
    "sunamganj": "haor_meghna",
    "sylhet": "haor_meghna",
    "kishoreganj": "haor_meghna",
    "netrokona": "haor_meghna",
    "dhaka_sw": "central_floodplain",
    "dhaka_se": "central_floodplain",
    "dhaka_nw": "central_floodplain",
    "dhaka_ne": "central_floodplain",
    "dhaka": "central_floodplain",
}


def basin_id(region_id: str) -> str:
    return BASIN_OF.get(region_id, "bangladesh_unspecified")


def _flood_score(sample: SpatialForecastSample) -> float:
    y = sample.y_flood
    flood = float((y == 1).sum())
    dry = float((y == 0).sum())
    valid = flood + dry
    return flood / valid if valid else 0.0


def event_id(city_id: str, stamp: datetime, gap_days: int = EVENT_GAP_DAYS) -> str:
    """Stable episode key: city + cluster start approximated by fortnight bucket is NOT used.

    IDs are assigned after sorting; this helper is only for tests on a single stamp.
    """
    return f"{city_id}:{stamp.date().isoformat()}"


def cluster_dates(dates: Sequence[str], gap_days: int = EVENT_GAP_DAYS) -> List[List[str]]:
    uniq = sorted({str(d)[:10] for d in dates})
    if not uniq:
        return []
    groups: List[List[str]] = [[uniq[0]]]
    for day in uniq[1:]:
        prev = datetime.fromisoformat(groups[-1][-1])
        cur = datetime.fromisoformat(day)
        if (cur - prev).days > gap_days:
            groups.append([day])
        else:
            groups[-1].append(day)
    return groups


def assign_event_ids(
    samples: Sequence[SpatialForecastSample],
    gap_days: int = EVENT_GAP_DAYS,
) -> List[SpatialForecastSample]:
    dates = [s.valid_at[:10] for s in samples]
    groups = cluster_dates(dates, gap_days=gap_days)
    start_of = {}
    end_of = {}
    for g in groups:
        key = f"evt:{g[0]}"
        for d in g:
            start_of[d] = key
            end_of[d] = g[-1]
    by_event: Dict[str, List[SpatialForecastSample]] = {}
    for sample in samples:
        sample.extra = dict(sample.extra or {})
        eid = start_of.get(sample.valid_at[:10], f"evt:{sample.valid_at[:10]}")
        sample.extra["event_id"] = eid
        sample.extra["event_start"] = eid.replace("evt:", "") + "T00:00:00Z"
        sample.extra["event_end"] = (end_of.get(sample.valid_at[:10]) or sample.valid_at[:10]) + "T00:00:00Z"
        sample.extra["basin_id"] = basin_id(sample.city_id)
        sample.extra["city_episode_id"] = f"{sample.city_id}:{eid}"
        sample.extra["region_id"] = sample.city_id
        sample.extra["source_ids"] = ["copernicus-gfm-ensemble-flood-extent"]
        sample.extra["meteorological_signature"] = {
            "cluster_gap_days": EVENT_GAP_DAYS,
            "season_month": int(sample.valid_at[5:7]),
        }
        sample.extra["hydrological_signature"] = {
            "q_lookback_len": 0 if sample.x_glofas_q_lookback is None else int(len(sample.x_glofas_q_lookback)),
            "kind": "MODELLED" if sample.q_is_glofas_cell else "UNAVAILABLE",
        }
        sample.extra["deduplication_key"] = eid
        sample.extra["flood_mechanism"] = (
            "haor_premonsoon_flash"
            if int(sample.valid_at[5:7]) in (4, 5)
            else (
                "winter_or_early"
                if int(sample.valid_at[5:7]) in (1, 2)
                else ( "haor_monsoon_inundation" if basin_id(sample.city_id) == "haor_meghna" else "monsoon_riverine")
            )
        )
        by_event.setdefault(eid, []).append(sample)
    for eid, members in by_event.items():
        peak = max(members, key=_flood_score)
        peak_at = peak.valid_at
        for sample in members:
            sample.extra["event_peak"] = peak_at
            sample.extra["event_peak_scene_id"] = peak.scene_id
            sample.extra["region_ids"] = sorted({s.city_id for s in members})
            sample.extra["quality_status"] = "ok"
    return list(samples)


def inventory(samples: Sequence[SpatialForecastSample]) -> dict:
    n_tiles = len(samples)
    days = sorted({s.valid_at[:10] for s in samples})
    cities = sorted({s.city_id for s in samples})
    assign_event_ids(samples)
    events = sorted({(s.extra or {}).get("event_id") for s in samples if (s.extra or {}).get("event_id")})
    city_eps = sorted({(s.extra or {}).get("city_episode_id") for s in samples if (s.extra or {}).get("city_episode_id")})
    flood = dry = unk = 0
    pos_events = set()
    for sample in samples:
        y = sample.y_flood
        flood += int((y == 1).sum())
        dry += int((y == 0).sum())
        unk += int((y == UNKNOWN).sum())
        if int((y == 1).sum()) > 0:
            pos_events.add((sample.extra or {}).get("event_id"))
    valid = flood + dry
    total = valid + unk
    splits = {name: sum(1 for s in samples if s.split == name) for name in ("train", "val", "test")}
    n_events = len(events)
    sufficient = n_events >= MIN_EVENTS_FOR_VALIDATION and len(pos_events) >= MIN_FLOOD_POSITIVE_EVENTS_TEST
    return {
        "n_tiles": n_tiles,
        "n_days": len(days),
        "n_cities": len(cities),
        "cities": cities,
        "days": days,
        "n_independent_events": n_events,
        "n_city_episodes": len(city_eps),
        "event_ids": events,
        "n_flood_positive_events": len([e for e in events if e in pos_events]),
        "pixels": {
            "flood": flood,
            "dry": dry,
            "unknown": unk,
            "valid": valid,
            "prevalence_flood_among_valid": (flood / valid) if valid else None,
            "unknown_fraction": (unk / total) if total else None,
        },
        "splits": splits,
        "event_gap_days": EVENT_GAP_DAYS,
        "sufficient_for_validation": sufficient,
        "verdict": "SUFFICIENT FOR VALIDATION" if sufficient else "INSUFFICIENT FOR VALIDATION",
        "note": (
            "Independent events = meteorological episodes separated by >45 days. "
            "Two city tiles on the same flood are one event. Orbit pairs two days apart are one event. "
            "Multiple 21-day revisits inside one monsoon are one event."
        ),
    }


def event_records(samples: Sequence[SpatialForecastSample]) -> List[dict]:
    """Canonical FloodEvent rows. One row per independent meteorological episode."""
    assign_event_ids(samples)
    grouped: Dict[str, List[SpatialForecastSample]] = {}
    for sample in samples:
        eid = (sample.extra or {}).get("event_id")
        if eid:
            grouped.setdefault(eid, []).append(sample)
    rows = []
    for eid, members in sorted(grouped.items()):
        extra0 = members[0].extra or {}
        regions = sorted({s.city_id for s in members})
        scenes = sorted({s.scene_id for s in members if s.scene_id})
        tiles = sorted({(s.extra or {}).get("tile_id") or "E039N021T3" for s in members})
        flood = dry = unk = 0
        for sample in members:
            y = sample.y_flood
            flood += int((y == 1).sum())
            dry += int((y == 0).sum())
            unk += int((y == UNKNOWN).sum())
        valid = flood + dry
        quality = "ok"
        if valid / max(valid + unk, 1) < 0.10:
            quality = "poor_valid_fraction"
        elif flood == 0:
            quality = "no_flood_pixels"
        rows.append(
            {
                "event_id": eid,
                "event_start": extra0.get("event_start"),
                "event_peak": extra0.get("event_peak"),
                "event_end": extra0.get("event_end"),
                "geographic_region": regions,
                "basin_ids": sorted({(s.extra or {}).get("basin_id") for s in members}),
                "source": "copernicus-gfm-ensemble-flood-extent",
                "source_version": "GFM ensemble_flood_extent AS020M",
                "label_source": members[0].label_source,
                "label_kind": members[0].label_kind,
                "provenance": {
                    "n_scenes": len(scenes),
                    "n_tiles": len(members),
                    "scene_ids": scenes,
                    "tile_ids": tiles,
                },
                "quality_status": quality,
                "region_ids": regions,
                "source_ids": extra0.get("source_ids") or ["copernicus-gfm-ensemble-flood-extent"],
                "meteorological_signature": extra0.get("meteorological_signature") or {
                    "cluster_gap_days": EVENT_GAP_DAYS,
                    "season_month": int((extra0.get("event_start") or "0000-00")[5:7] or 0) or None,
                },
                "hydrological_signature": extra0.get("hydrological_signature"),
                "deduplication_key": extra0.get("deduplication_key") or eid,
                "flood_mechanism": extra0.get("flood_mechanism"),
                "pixels": {
                    "flood": flood,
                    "dry": dry,
                    "unknown": unk,
                    "valid": valid,
                    "valid_fraction": (valid / (valid + unk)) if (valid + unk) else None,
                    "flood_among_valid": (flood / valid) if valid else None,
                },
            }
        )
    return rows


def coverage_summary(samples: Sequence[SpatialForecastSample]) -> dict:
    assign_event_ids(samples)
    by_region: Dict[str, dict] = {}
    for sample in samples:
        row = by_region.setdefault(
            sample.city_id,
            {
                "region_id": sample.city_id,
                "event_ids": set(),
                "scene_ids": set(),
                "tile_ids": set(),
                "dates": set(),
                "flood": 0,
                "dry": 0,
                "unknown": 0,
            },
        )
        extra = sample.extra or {}
        row["event_ids"].add(extra.get("event_id"))
        if sample.scene_id:
            row["scene_ids"].add(sample.scene_id)
        row["tile_ids"].add(extra.get("tile_id") or "E039N021T3")
        row["dates"].add(sample.valid_at[:10])
        y = sample.y_flood
        row["flood"] += int((y == 1).sum())
        row["dry"] += int((y == 0).sum())
        row["unknown"] += int((y == UNKNOWN).sum())
    out = []
    for region_id, row in sorted(by_region.items()):
        valid = row["flood"] + row["dry"]
        total = valid + row["unknown"]
        out.append(
            {
                "region_id": region_id,
                "n_events": len({e for e in row["event_ids"] if e}),
                "n_scenes": len(row["scene_ids"]),
                "n_tiles": len(row["tile_ids"]),
                "event_ids": sorted(e for e in row["event_ids"] if e),
                "dates_covered": sorted(row["dates"]),
                "valid_flood_pixels": row["flood"],
                "valid_dry_pixels": row["dry"],
                "unknown_pixels": row["unknown"],
                "unknown_fraction": (row["unknown"] / total) if total else None,
            }
        )
    return {"regions": out, "n_regions": len(out)}


def same_event_in_train_and_test(samples: Iterable[SpatialForecastSample]) -> List[str]:
    return same_event_across_splits(samples, "train", "test")


def same_event_across_splits(
    samples: Iterable[SpatialForecastSample],
    left: str,
    right: str,
) -> List[str]:
    a = {(s.extra or {}).get("event_id") for s in samples if s.split == left}
    b = {(s.extra or {}).get("event_id") for s in samples if s.split == right}
    return sorted(e for e in (a & b) if e)
