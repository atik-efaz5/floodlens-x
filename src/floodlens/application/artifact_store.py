"""In-process artifact store. Job JSON holds references, not giant arrays."""

from __future__ import annotations

from io import BytesIO
from typing import Optional

import numpy as np

from floodlens.application.platform_store import get_platform_store

OBJECT_STORE_PREFIX = "artifacts://"


def put_depth_artifact(
    artifact_id: str,
    depth: np.ndarray,
    meta: dict,
) -> dict:
    store = get_platform_store()
    payload = dict(meta)
    payload["id"] = artifact_id
    payload["kind"] = payload.get("kind", "depth_snapshot")
    payload["uri"] = payload.get("uri") or f"{OBJECT_STORE_PREFIX}{artifact_id}/depth.npy"
    payload["nx"] = int(depth.shape[1])
    payload["ny"] = int(depth.shape[0])
    payload["_depth_array"] = np.asarray(depth, dtype=np.float64)
    store.artifacts[artifact_id] = payload
    return {k: v for k, v in payload.items() if k != "_depth_array"}


def get_artifact(artifact_id: str) -> Optional[dict]:
    return get_platform_store().artifacts.get(artifact_id)


def get_depth(artifact_id: str) -> Optional[np.ndarray]:
    art = get_artifact(artifact_id)
    if not art:
        return None
    if "_depth_array" in art:
        return np.asarray(art["_depth_array"], dtype=np.float64)
    raw = art.get("depth")
    if raw is None:
        return None
    return np.asarray(raw, dtype=np.float64)


def overlay_png_bytes(artifact_id: str) -> Optional[bytes]:
    depth = get_depth(artifact_id)
    if depth is None:
        return None
    finite = np.where(np.isfinite(depth), depth, 0.0)
    kind = (get_artifact(artifact_id) or {}).get("kind") or ""
    cmap = "Blues"
    if kind == "depth_difference":
        absmax = float(np.max(np.abs(finite))) or 1.0
        norm = 0.5 + 0.5 * np.clip(finite / absmax, -1.0, 1.0)
        cmap = "RdBu_r"
    elif kind in {"hillshade", "terrain_preview"}:
        vmax = float(np.max(finite)) or 1.0
        norm = np.clip(finite / vmax, 0.0, 1.0)
        cmap = "gray"
    elif kind in {"rainfall_heatmap", "rainfall"}:
        vmax = float(np.max(finite)) or 1.0
        norm = np.clip(finite / vmax, 0.0, 1.0)
        cmap = "YlGnBu"
    elif kind in {"probability_map", "extent_map", "uncertainty_map"}:
        vmax = 1.0
        norm = np.clip(finite / vmax, 0.0, 1.0)
    else:
        vmax = float(np.max(finite)) or 1.0
        norm = np.clip(finite / vmax, 0.0, 1.0)
    try:
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib import pyplot as plt

        fig, ax = plt.subplots(figsize=(4, 4), dpi=64)
        ax.imshow(norm, origin="lower", cmap=cmap)
        ax.set_axis_off()
        buf = BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0)
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        # Minimal uncompressed PNG-like fallback: PGM is not PNG; use raw RGBA via matplotlib-free encoder
        return _png_grayscale(norm)


def _png_grayscale(norm: np.ndarray) -> bytes:
    """Tiny 8-bit grayscale PNG without extra deps."""
    import struct
    import zlib

    height, width = norm.shape
    raw = (np.clip(norm * 255.0, 0, 255).astype(np.uint8))
    rows = b"".join(b"\x00" + raw[i].tobytes() for i in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


def public_summary(artifact_id: str) -> Optional[dict]:
    art = get_artifact(artifact_id)
    if not art:
        return None
    return {k: v for k, v in art.items() if k not in {"_depth_array", "depth"}}
