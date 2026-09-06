"""Phase 5.0 access probe: GFM STAC, CyVerse inundation, DEM. No large download."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from floodlens.application.city_data import create_city_registry
from floodlens.ml.spatial.schema import SPATIAL_DIR

STAC_ROOT = "https://stac.eodc.eu/api/v1"
GFM_COLLECTION = "GFM"
SAMPLE_HREF = (
    "https://data.eodc.eu/collections/GFM_ARCHIVE/flood_extent/AS020M/2022/06/18/"
    "ENSEMBLE_FLOOD_20220618T234833_VV_AS020M_E039N021T3.tif"
)
CYVERSE_ANON = (
    "https://data.cyverse.org/dav-anon/iplant/home/shared/"
    "commons_repo/curated/Giezendanner_BangladeshInundationHistory_2022"
)
MAX_MVP_BYTES = 8 * 1024 * 1024 * 1024
UA = "floodlens-x-phase5/0.1"


def _http(method: str, url: str, body: Optional[bytes] = None, timeout: int = 30) -> tuple[int, dict, bytes]:
    headers = {"User-Agent": UA}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            return int(resp.status), hdrs, raw
    except URLError:
        cmd = ["curl", "-sS", "-A", UA, "--max-time", str(timeout), "-D", "-", "-o", "-"]
        if method != "GET":
            cmd.extend(["-X", method])
        if body is not None:
            cmd.extend(["-H", "Content-Type: application/json", "-d", body.decode()])
        cmd.append(url)
        blob = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        head, _, rest = blob.partition(b"\r\n\r\n")
        status = 0
        hdrs: dict = {}
        for line in head.decode("latin1", errors="replace").splitlines():
            if line.startswith("HTTP/"):
                try:
                    status = int(line.split()[1])
                except (IndexError, ValueError):
                    status = 0
            elif ":" in line:
                k, v = line.split(":", 1)
                hdrs[k.strip().lower()] = v.strip()
        return status, hdrs, rest


def _city_bbox(city_id: str) -> list:
    city = create_city_registry().get_city(city_id)
    b = city.bounds
    return [b.west, b.south, b.east, b.north]


def probe_gfm_stac() -> dict:
    status, _, raw = _http("GET", f"{STAC_ROOT}/collections/{GFM_COLLECTION}", timeout=30)
    collection = {}
    if status == 200 and raw:
        try:
            collection = json.loads(raw.decode())
        except json.JSONDecodeError:
            collection = {}
    license_field = collection.get("license") or "unknown"
    bbox = _city_bbox("sunamganj")
    search = {
        "collections": [GFM_COLLECTION],
        "bbox": bbox,
        "datetime": "2022-06-01T00:00:00Z/2022-06-30T23:59:59Z",
        "limit": 5,
    }
    s_status, _, s_raw = _http("POST", f"{STAC_ROOT}/search", json.dumps(search).encode(), timeout=45)
    features = []
    if s_status == 200 and s_raw:
        try:
            features = (json.loads(s_raw.decode()).get("features") or [])
        except json.JSONDecodeError:
            features = []
    sample_item = features[0] if features else {}
    href = ((sample_item.get("assets") or {}).get("ensemble_flood_extent") or {}).get("href") or SAMPLE_HREF
    h_status, h_hdrs, _ = _http("HEAD", href, timeout=20)
    public = h_status == 200
    size = None
    if h_hdrs.get("content-length"):
        try:
            size = int(h_hdrs["content-length"])
        except ValueError:
            size = None
    return {
        "provider": "CEMS / EODC Copernicus GFM",
        "stac": STAC_ROOT,
        "collection": GFM_COLLECTION,
        "collection_http": status,
        "license_stac": license_field,
        "license_note": (
            "STAC lists 'proprietary'. Use Copernicus / CEMS GFM attribution. "
            "Do not claim CC-BY. REST wiki documents a portal token for some endpoints; "
            "this probe used public STAC + public data.eodc.eu asset URLs."
        ),
        "label_kind": "OBSERVED",
        "search_http": s_status,
        "n_search_hits_june2022_sunamganj_limit5": len(features),
        "sample_item_id": sample_item.get("id"),
        "sample_asset_href": href,
        "sample_head_http": h_status,
        "sample_bytes": size,
        "download_public_no_token": public,
        "shared_equi7_tile": "E039N021T3",
        "credentials_required": not public,
    }


def probe_cyverse() -> dict:
    status, hdrs, _ = _http("HEAD", CYVERSE_ANON, timeout=20)
    loc = hdrs.get("location") or ""
    blocked = status in {301, 302, 303, 307, 308} and "unblockme" in loc.lower()
    return {
        "provider": "CyVerse (Giezendanner Bangladesh Inundation History, DOI 10.25739/2edm-jh03)",
        "url": CYVERSE_ANON,
        "http": status,
        "location": loc or None,
        "blocked": blocked or status >= 400 or status == 0,
        "label_kind": "DERIVED",
        "note": (
            "Fallback only if GFM download is not public. Never call these maps OBSERVED. "
            + (
                "This probe hit a CyVerse interstitial/unblock redirect or error; do not fabricate credentials."
                if (blocked or status >= 400 or status == 0)
                else "Anonymous HEAD succeeded; GFM remains the primary OBSERVED source so this archive was not downloaded."
            )
        ),
    }


def probe_dem() -> dict:
    path = os.environ.get("FLOODLENS_DEM_PATH")
    exists = bool(path) and Path(path).exists()
    return {
        "env": "FLOODLENS_DEM_PATH",
        "path": path,
        "available": exists,
        "data_status": "REAL" if exists else "UNAVAILABLE",
        "note": "DEM window is not invented when unset.",
    }


def run_probe(write: bool = True) -> dict:
    gfm = probe_gfm_stac()
    cyverse = probe_cyverse()
    dem = probe_dem()
    primary = "GFM" if gfm.get("download_public_no_token") else ("CYVERSE" if not cyverse.get("blocked") else "STOP")
    report = {
        "probed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "max_mvp_bytes": MAX_MVP_BYTES,
        "gfm": gfm,
        "cyverse_inundation": cyverse,
        "dem": dem,
        "primary_label_source": primary,
        "stop": primary == "STOP",
        "note": (
            "Probe only. Large archives were not downloaded. "
            "GFM scenes that intersect the Equi7 tile but have nodata over the AOI "
            "must be dropped (unknown, never dry)."
        ),
    }
    if write:
        SPATIAL_DIR.mkdir(parents=True, exist_ok=True)
        path = SPATIAL_DIR / "probe.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["wrote"] = str(path)
    return report
