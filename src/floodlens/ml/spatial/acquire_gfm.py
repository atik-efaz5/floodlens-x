"""Acquire Copernicus GFM ensemble flood extent, AOI-clipped, size-capped.

Public STAC + data.eodc.eu asset URLs (probe 5.0). No portal token.
Drops scenes with nodata over the AOI (unknown, never dry).
Raw GeoTIFFs stay gitignored; processed 32×32 maps may be committed.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen

import numpy as np

from floodlens.ml.spatial.equi7 import TILE_CATALOG, TILE_ID, city_window
from floodlens.ml.spatial.labels import GFM_NODATA, encode_binary
from floodlens.ml.spatial.aois_v2 import AOI_IDS_V2, aoi_bounds
from floodlens.ml.spatial.schema import (
    FLOOD_FRACTION_TAU,
    GRID_SIZE,
    GRID_SIZE_V2,
    LABEL_OBSERVED,
    SPATIAL_DATASET_VERSION,
    SPATIAL_DATASET_VERSION_V2,
    SPATIAL_DIR,
)
from floodlens.ml.spatial.tiles import CITIES, cell_size_m, city_bounds, grid_spec

STAC_SEARCH = "https://stac.eodc.eu/api/v1/search"
UA = "floodlens-x-phase5/0.1"
MAX_BYTES = 200 * 1024 * 1024  # 200 MB raw (plan ceiling 8 GB)
MAX_SCENES = 80
MIN_VALID_FRAC = 0.05
# Independent seasons / pulses — not extra 2-day orbit twins of the same event.
WINDOWS = (
    ("2016-06-15", "2016-08-20"),
    ("2017-06-15", "2017-08-20"),
    ("2018-01-10", "2018-01-25"),
    ("2018-06-01", "2018-08-20"),
    ("2019-06-15", "2019-08-20"),
    ("2020-06-01", "2020-08-15"),
    ("2021-06-01", "2021-08-15"),
    ("2022-05-09", "2022-08-15"),
    ("2023-06-01", "2023-08-15"),
    ("2024-06-01", "2024-08-15"),
)
CLUSTER_KEEP_DAYS = 21
RAW_DIR = SPATIAL_DIR / "gfm" / "raw"
PROCESSED_DIR = SPATIAL_DIR / "gfm" / "processed"
PROCESSED_DIR_V2 = SPATIAL_DIR / "gfm" / "processed_v2"


def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _file_fingerprint(path: Path) -> dict:
    size = path.stat().st_size
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        digest.update(handle.read(65536))
        if size > 65536:
            handle.seek(max(0, size - 65536))
            digest.update(handle.read(65536))
    return {"bytes": size, "sha256_ends": digest.hexdigest()}


def _http_json(method: str, url: str, body: Optional[bytes] = None, timeout: int = 60) -> Optional[dict]:
    headers = {"User-Agent": UA}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        cmd = ["curl", "-sS", "-A", UA, "--max-time", str(timeout)]
        if method != "GET":
            cmd.extend(["-X", method])
        if body is not None:
            cmd.extend(["-H", "Content-Type: application/json", "-d", body.decode()])
        cmd.append(url)
        try:
            raw = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
            return json.loads(raw.decode())
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError, ValueError):
            return None


def _download(url: str, dest: Path, timeout: int = 120, retries: int = 3) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        return dest.stat().st_size
    last_err: Optional[Exception] = None
    for _ in range(retries):
        try:
            subprocess.check_call(
                ["curl", "-sS", "-A", UA, "--max-time", str(timeout), "-L", "--retry", "2", "-o", str(dest), url]
            )
            if dest.exists() and dest.stat().st_size > 1000:
                return dest.stat().st_size
        except (OSError, subprocess.CalledProcessError) as exc:
            last_err = exc
            dest.unlink(missing_ok=True)
    raise RuntimeError(f"download failed {url}: {last_err}")


def search_window(start: str, end: str, bbox: List[float], limit: int = 80, retries: int = 4) -> List[dict]:
    """STAC search with retry. Empty results are retried (provider rate-limits to [])."""
    import time

    payload = {
        "collections": ["GFM"],
        "bbox": bbox,
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "limit": limit,
    }
    last: List[dict] = []
    for attempt in range(max(1, retries)):
        out = _http_json("POST", STAC_SEARCH, json.dumps(payload).encode(), timeout=60) or {}
        last = list(out.get("features") or [])
        if last:
            return last
        time.sleep(min(8, 1.5 * (attempt + 1)))
    return last


def _scene_on_allowed_tile(feat: dict, href: str, tiles=None) -> bool:
    tiles = tuple(tiles or TILE_CATALOG.keys())
    blob = f"{feat.get('id') or ''} {href}"
    return any(tid in blob for tid in tiles)


def _dedupe_one_per_day(features: Iterable[dict], tiles=None) -> List[dict]:
    seen: Dict[str, dict] = {}
    tiles = tuple(tiles or (TILE_ID,))
    for feat in features:
        href = ((feat.get("assets") or {}).get("ensemble_flood_extent") or {}).get("href")
        dt = (feat.get("properties") or {}).get("datetime") or ""
        day = dt[:10]
        if not href or not day:
            continue
        if not _scene_on_allowed_tile(feat, href, tiles):
            continue
        tile = next((tid for tid in TILE_CATALOG if tid in f"{feat.get('id') or ''} {href}"), TILE_ID)
        key = f"{day}:{tile}"
        if key not in seen:
            seen[key] = {
                "id": feat.get("id"),
                "datetime": dt,
                "href": href,
                "tile": tile,
            }
    return [seen[k] for k in sorted(seen)]


def covering_orbit_score(datetime_iso: str) -> int:
    """Lower is more likely AOI-valid on E039N021T3 (empirical from local clips).

    Covering: ~12:04 and ~23:55. Empty swaths: ~11:56 and ~23:47.
    """
    hhmm = (datetime_iso or "")[11:16]
    if hhmm.startswith("12:0"):
        return 0
    if hhmm >= "23:54":
        return 1
    if hhmm.startswith("00:"):
        return 2
    return 9


def _dedupe_orbits(features: Iterable[dict], tiles=None) -> List[dict]:
    """Keep distinct (day, tile, orbit-score bucket), preferring covering clocks."""
    tiles = tuple(tiles or (TILE_ID,))
    seen: Dict[str, dict] = {}
    for feat in features:
        href = ((feat.get("assets") or {}).get("ensemble_flood_extent") or {}).get("href")
        dt = (feat.get("properties") or {}).get("datetime") or ""
        day = dt[:10]
        if not href or not day:
            continue
        if not _scene_on_allowed_tile(feat, href, tiles):
            continue
        tile = next((tid for tid in TILE_CATALOG if tid in f"{feat.get('id') or ''} {href}"), TILE_ID)
        bucket = "cover" if covering_orbit_score(dt) <= 2 else "other"
        key = f"{day}:{tile}:{bucket}"
        row = {"id": feat.get("id"), "datetime": dt, "href": href, "tile": tile}
        prev = seen.get(key)
        if prev is None or covering_orbit_score(dt) < covering_orbit_score(prev.get("datetime") or ""):
            seen[key] = row
    return [seen[k] for k in sorted(seen)]


def _keep_independent_days(rows: List[dict], gap_days: int = CLUSTER_KEEP_DAYS) -> List[dict]:
    """Keep at most one scene per gap_days cluster so orbit twins are not extra events."""
    if not rows:
        return []
    rows = sorted(rows, key=lambda r: r.get("datetime") or "")
    kept = [rows[0]]
    last = datetime.fromisoformat(str(rows[0]["datetime"]).replace("Z", "+00:00"))
    for row in rows[1:]:
        stamp = datetime.fromisoformat(str(row["datetime"]).replace("Z", "+00:00"))
        if (stamp - last).days >= gap_days:
            kept.append(row)
            last = stamp
    return kept


def list_candidate_scenes_v2() -> List[dict]:
    """STAC candidates on every AOI-valid Equi7 tile. One scene per day per tile.

    Does not drop neighbor-tile scenes of the same meteorological pulse — those
    add geographic coverage, not extra events. Event clustering happens later.
    """
    feats: List[dict] = []
    bbox = union_bbox_v2()
    print(f"STAC v2 search {len(WINDOWS)} windows bbox={bbox}", flush=True)
    for start, end in WINDOWS:
        hits = search_window(start, end, bbox, limit=100)
        print(f"  v2 {start}..{end}: {len(hits)} features", flush=True)
        feats.extend(hits)
    daily = _dedupe_one_per_day(feats, tiles=tuple(TILE_CATALOG.keys()))
    print(f"v2 candidates daily_by_tile={len(daily)}", flush=True)
    return daily[:MAX_SCENES]


def union_bbox() -> List[float]:
    """One STAC bbox covering all product AOIs (shared Equi7 tile)."""
    west = south = 180.0
    east = north = -180.0
    for city_id in CITIES:
        w, s, e, n = city_bounds(city_id)
        west, south = min(west, w), min(south, s)
        east, north = max(east, e), max(north, n)
    return [west, south, east, north]


def union_bbox_v2() -> List[float]:
    west = south = 180.0
    east = north = -180.0
    for aoi_id in AOI_IDS_V2:
        w, s, e, n = aoi_bounds(aoi_id)
        west, south = min(west, w), min(south, s)
        east, north = max(east, e), max(north, n)
    return [west, south, east, north]


def list_candidate_scenes() -> List[dict]:
    feats: List[dict] = []
    bbox = union_bbox()
    print(f"STAC search {len(WINDOWS)} windows bbox={bbox}", flush=True)
    for start, end in WINDOWS:
        hits = search_window(start, end, bbox, limit=100)
        print(f"  {start}..{end}: {len(hits)} features", flush=True)
        feats.extend(hits)
    daily = _dedupe_one_per_day(feats, tiles=(TILE_ID,))
    kept = _keep_independent_days(daily)[:MAX_SCENES]
    print(f"candidates daily={len(daily)} independent={len(kept)}", flush=True)
    return kept


def _read_gfm(path: Path) -> np.ndarray:
    import tifffile

    return np.asarray(tifffile.imread(str(path)))


def clip_resample(
    arr: np.ndarray,
    city_id: str,
    size: int = GRID_SIZE,
    tile_id: str = TILE_ID,
) -> Tuple[np.ndarray, np.ndarray, float]:
    from floodlens.ml.spatial.equi7 import block_reduce_mode

    try:
        r0, r1, c0, c1 = city_window(aoi_bounds(city_id), tile_id=tile_id)
    except ValueError:
        empty = np.full((size, size), GFM_NODATA, dtype=np.uint8)
        return encode_binary(np.zeros((size, size)), np.zeros((size, size), dtype=bool)), np.zeros((size, size), dtype=np.float32), 0.0
    win = arr[r0:r1, c0:c1]
    if win.size == 0:
        return encode_binary(np.zeros((size, size)), np.zeros((size, size), dtype=bool)), np.zeros((size, size), dtype=np.float32), 0.0
    valid_frac = float(np.mean(win != GFM_NODATA))
    cls, frac = block_reduce_mode(win, size, size, nodata=GFM_NODATA)
    cls = encode_binary(frac, cls != GFM_NODATA, tau=FLOOD_FRACTION_TAU)
    return cls, frac, valid_frac


_SCENE_STAMP = re.compile(r"ENSEMBLE_FLOOD_(\d{8}T\d{6})_")


_TILE_IN_NAME = re.compile(r"(E039N0\d{2}T3)")


def scene_from_raw_path(path: Path) -> Optional[dict]:
    match_tile = _TILE_IN_NAME.search(path.name)
    if not match_tile:
        return None
    tile = match_tile.group(1)
    if tile not in TILE_CATALOG:
        return None
    match = _SCENE_STAMP.search(path.name)
    if not match:
        return None
    raw = match.group(1)
    dt = datetime.strptime(raw, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    return {
        "id": path.stem,
        "datetime": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "href": str(path),
        "tile": tile,
    }


def _clip_cities(arr: np.ndarray, scene_id: str) -> dict:
    city_rows = {}
    for city_id in CITIES:
        cls, frac, vfrac = clip_resample(arr, city_id)
        if vfrac < MIN_VALID_FRAC:
            continue
        out = PROCESSED_DIR / city_id
        out.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            out / f"{scene_id}.npz",
            y_flood=cls,
            y_flood_frac=frac,
        )
        city_rows[city_id] = {
            "valid_frac": vfrac,
            "n_flood": int(np.sum(cls == 1)),
            "n_dry": int(np.sum(cls == 0)),
            "n_unknown": int(np.sum(cls == 255)),
            "grid": grid_spec(city_id),
        }
    return city_rows


def index_local_raw() -> dict:
    """Index every local product-tile GeoTIFF with AOI coverage.

    Independence is measured later by event clustering, not by dropping valid maps.
    Nodata swaths stay unknown, never dry.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    kept = []
    skipped_empty = []
    paths = sorted(RAW_DIR.glob(f"*{TILE_ID}.tif"))
    print(f"index local {len(paths)} {TILE_ID} GeoTIFFs", flush=True)
    for path in paths:
        scene = scene_from_raw_path(path)
        if scene is None:
            skipped_empty.append({"id": path.name, "reason": "unparseable or wrong tile"})
            continue
        try:
            arr = _read_gfm(path)
        except Exception as exc:
            skipped_empty.append({"id": scene["id"], "reason": f"decode: {exc}"})
            continue
        city_rows = _clip_cities(arr, scene["id"])
        del arr
        if not city_rows:
            skipped_empty.append({"id": scene["id"], "reason": "AOI nodata (unknown, not dry)"})
            continue
        kept.append(
            {
                **scene,
                "sha256": _sha256_bytes(path.read_bytes()),
                "bytes": path.stat().st_size,
                "cities": city_rows,
                "label_kind": LABEL_OBSERVED,
            }
        )
        print(f"  local kept {scene['id']} cities={list(city_rows)}", flush=True)
    kept.sort(key=lambda r: r.get("datetime") or "")
    used = sum(p.stat().st_size for p in RAW_DIR.glob("*.tif"))
    index = {
        "dataset_version": SPATIAL_DATASET_VERSION,
        "label_kind": LABEL_OBSERVED,
        "source": "copernicus-gfm-ensemble-flood-extent",
        "tile": TILE_ID,
        "acquired_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "raw_bytes": used,
        "max_bytes": MAX_BYTES,
        "n_candidates": len(paths),
        "n_kept": len(kept),
        "scenes": kept,
        "skipped_empty": skipped_empty,
        "skipped_cap": [],
        "attribution": "Copernicus Emergency Management Service — Global Flood Monitoring (GFM).",
        "license_stac": "proprietary",
        "index_source": "local_product_tile_geotiffs",
    }
    (PROCESSED_DIR / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index


def _grid_spec_aoi(aoi_id: str, size: int) -> dict:
    bounds = aoi_bounds(aoi_id)
    dx_m, dy_m = cell_size_m(bounds, size, size)
    return {
        "city_id": aoi_id,
        "nx": size,
        "ny": size,
        "bounds": list(bounds),
        "crs": "EPSG:4326",
        "dx_m": dx_m,
        "dy_m": dy_m,
        "target_resolution_m": 500.0,
        "note": f"Working tensor is {size}×{size} on AOI geographic bounds. Native GFM is 20 m Equi7.",
    }


def snapshot_processed_v2_index(label: str = "phase65a") -> Optional[Path]:
    """Copy current index.json once so a later version never overwrites the prior dataset record."""
    src = PROCESSED_DIR_V2 / "index.json"
    dest = PROCESSED_DIR_V2 / f"index_{label}.json"
    if src.exists() and not dest.exists():
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        manifest = PROCESSED_DIR_V2 / "scene_manifest.json"
        man_dest = PROCESSED_DIR_V2 / f"scene_manifest_{label}.json"
        if manifest.exists() and not man_dest.exists():
            man_dest.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")
        return dest
    return dest if dest.exists() else None


def stamp_processed_v2_version(dataset_version: str) -> dict:
    path = PROCESSED_DIR_V2 / "index.json"
    if not path.exists():
        return {}
    index = json.loads(path.read_text(encoding="utf-8"))
    index["dataset_version"] = dataset_version
    path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index


def index_local_v2(*, dataset_version: Optional[str] = None) -> dict:
    """64×64 clips for Phase 6 AOIs. Indexes every local Equi7 tile in TILE_CATALOG.

    Neighbor tiles are kept only when an AOI has ≥ MIN_VALID_FRAC valid pixels
    (AOI-valid, not STAC-hit). Duplicate filenames are skipped (resumable).
    """

    snapshot_processed_v2_index("phase65a")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR_V2.mkdir(parents=True, exist_ok=True)
    kept = []
    skipped_empty = []
    failed = []
    version = dataset_version or SPATIAL_DATASET_VERSION_V2
    paths = sorted(p for p in RAW_DIR.glob("*.tif") if _TILE_IN_NAME.search(p.name) and _TILE_IN_NAME.search(p.name).group(1) in TILE_CATALOG)
    print(f"index v2 local {len(paths)} tiles={list(TILE_CATALOG)} → {GRID_SIZE_V2}×{GRID_SIZE_V2}", flush=True)
    for path in paths:
        scene = scene_from_raw_path(path)
        if scene is None:
            continue
        try:
            arr = _read_gfm(path)
        except Exception as exc:
            failed.append({"id": scene["id"], "reason": f"decode: {exc}", "path": str(path)})
            continue
        tile_id = scene.get("tile") or TILE_ID
        city_rows = {}
        for aoi_id in AOI_IDS_V2:
            out = PROCESSED_DIR_V2 / aoi_id
            out.mkdir(parents=True, exist_ok=True)
            npz_path = out / f"{scene['id']}.npz"
            if npz_path.exists():
                blob = np.load(npz_path)
                cls = np.asarray(blob["y_flood"])
                frac = np.asarray(blob["y_flood_frac"])
                if "valid_frac" in blob.files:
                    vfrac = float(np.asarray(blob["valid_frac"]))
                else:
                    vfrac = float(np.mean(cls != GFM_NODATA))
            else:
                cls, frac, vfrac = clip_resample(arr, aoi_id, size=GRID_SIZE_V2, tile_id=tile_id)
                if vfrac < MIN_VALID_FRAC:
                    continue
                np.savez_compressed(npz_path, y_flood=cls, y_flood_frac=frac, valid_frac=np.asarray(vfrac))
            if vfrac < MIN_VALID_FRAC:
                continue
            valid = int(np.sum(cls == 0) + np.sum(cls == 1))
            city_rows[aoi_id] = {
                "valid_frac": vfrac,
                "n_flood": int(np.sum(cls == 1)),
                "n_dry": int(np.sum(cls == 0)),
                "n_unknown": int(np.sum(cls == 255)),
                "flood_among_valid": (int(np.sum(cls == 1)) / valid) if valid else None,
                "quality_status": "poor_valid_fraction" if vfrac < 0.10 else "ok",
                "grid": _grid_spec_aoi(aoi_id, GRID_SIZE_V2),
                "tile_id": tile_id,
                "crs": "EPSG:4326",
                "resampling": "block_reduce_mode then encode_binary tau=0.25; nodata stays 255",
            }
        del arr
        if not city_rows:
            skipped_empty.append({"id": scene["id"], "reason": "AOI nodata (unknown, not dry)", "tile": tile_id})
            continue
        kept.append(
            {
                **scene,
                "cities": city_rows,
                "label_kind": LABEL_OBSERVED,
                "bytes": path.stat().st_size,
                "checksum": _file_fingerprint(path),
                "license": "proprietary",
                "attribution": "Copernicus Emergency Management Service — Global Flood Monitoring (GFM).",
            }
        )
        print(f"  v2 kept {scene['id']} tile={tile_id} aois={list(city_rows)}", flush=True)
    kept.sort(key=lambda r: r.get("datetime") or "")
    index = {
        "dataset_version": version,
        "label_kind": LABEL_OBSERVED,
        "source": "copernicus-gfm-ensemble-flood-extent",
        "tiles": sorted({s.get("tile") for s in kept}),
        "grid": GRID_SIZE_V2,
        "acquired_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "n_candidates": len(paths),
        "n_kept": len(kept),
        "scenes": kept,
        "skipped_empty": skipped_empty,
        "failed_downloads": failed,
        "aois": list(AOI_IDS_V2),
        "attribution": "Copernicus Emergency Management Service — Global Flood Monitoring (GFM).",
        "license_stac": "proprietary",
        "unknown_policy": "255 remains unknown; never recoded as dry",
        "alignment": {
            "label_crs_native": "Equi7 AS020M",
            "working_crs": "EPSG:4326",
            "working_grid": GRID_SIZE_V2,
            "resampling": "AOI window on Equi7 tile, block-reduce, tau=0.25",
        },
    }
    (PROCESSED_DIR_V2 / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    (PROCESSED_DIR_V2 / "scene_manifest.json").write_text(
        json.dumps(
            {
                "n_kept": len(kept),
                "scenes": [
                    {
                        "scene_id": s["id"],
                        "datetime": s.get("datetime"),
                        "tile_id": s.get("tile"),
                        "checksum": s.get("checksum"),
                        "aois": list((s.get("cities") or {}).keys()),
                        "label_kind": LABEL_OBSERVED,
                    }
                    for s in kept
                ],
                "failed": failed,
                "skipped_empty": skipped_empty,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return index


def acquire(max_bytes: int = MAX_BYTES, download: bool = True) -> dict:
    """Download STAC candidates (optional), then index all local product-tile files."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    if download:
        candidates = list_candidate_scenes()
        used = sum(p.stat().st_size for p in RAW_DIR.glob("*.tif"))
        print(f"acquire {len(candidates)} scenes cap={max_bytes}", flush=True)
        for i, scene in enumerate(candidates, start=1):
            if TILE_ID not in str(scene.get("id") or "") and TILE_ID not in str(scene.get("href") or ""):
                continue
            if used > max_bytes:
                break
            dest = RAW_DIR / f"{scene['id']}.tif"
            try:
                _download(scene["href"], dest)
            except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
                print(f"  skip {scene['id']}: {exc}", flush=True)
                continue
            used = sum(p.stat().st_size for p in RAW_DIR.glob("*.tif"))
            print(f"  downloaded {i}/{len(candidates)} {scene['id']}", flush=True)
    print("indexing all local product-tile GeoTIFFs (valid AOI only)", flush=True)
    return index_local_raw()


def acquire_v2(max_bytes: int = MAX_BYTES, download: bool = False) -> dict:
    """Optional STAC download (skip existing), then 64×64 AOI index of every catalog tile."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR_V2.mkdir(parents=True, exist_ok=True)
    failed_downloads = []
    skipped_existing = []
    if download:
        candidates = list_candidate_scenes_v2()
        used = sum(p.stat().st_size for p in RAW_DIR.glob("*.tif"))
        print(f"acquire v2 {len(candidates)} scenes cap={max_bytes}", flush=True)
        for i, scene in enumerate(candidates, start=1):
            dest = RAW_DIR / f"{scene['id']}.tif"
            if dest.exists() and dest.stat().st_size > 1000:
                skipped_existing.append(scene["id"])
                continue
            if used > max_bytes:
                failed_downloads.append({"id": scene.get("id"), "reason": "byte_cap", "href": scene.get("href")})
                continue
            try:
                _download(scene["href"], dest)
            except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
                failed_downloads.append({"id": scene.get("id"), "reason": str(exc), "href": scene.get("href")})
                print(f"  failed {scene['id']}: {exc}", flush=True)
                continue
            used = sum(p.stat().st_size for p in RAW_DIR.glob("*.tif"))
            print(f"  downloaded {i}/{len(candidates)} {scene['id']}", flush=True)
    index = index_local_v2()
    index["failed_downloads"] = list(index.get("failed_downloads") or []) + failed_downloads
    index["skipped_existing"] = skipped_existing
    (PROCESSED_DIR_V2 / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index


def snapshot_available() -> bool:
    idx = PROCESSED_DIR / "index.json"
    if not idx.exists():
        return False
    payload = json.loads(idx.read_text(encoding="utf-8"))
    return int(payload.get("n_kept") or 0) > 0
