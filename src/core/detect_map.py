from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Tuple

import cv2
import numpy as np
import pandas as pd

from .output_cleanup import (
    detections_all_csv,
    detections_mapped_3d_csv,
    target_ranges_path,
)


@dataclass
class DetectMapResult:
    ok: bool
    message: str
    csv_2d: Path | None = None
    csv_3d: Path | None = None
    n_2d: int = 0
    n_3d_mapped: int = 0


def load_target_ranges(target_json: Path) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Read target_ranges.json and return a list of (lo, hi) as uint8 arrays."""
    data = json.loads(target_json.read_text(encoding="utf-8"))
    parts = []
    for p in data.get("ranges_parts", []):
        lo = np.array(p["lo"], dtype=np.uint8)
        hi = np.array(p["hi"], dtype=np.uint8)
        if lo.shape == (3,) and hi.shape == (3,):
            parts.append((lo, hi))
    return parts


def clean_mask(mask: np.ndarray, k_open: int = 3, k_close: int = 5) -> np.ndarray:
    if mask is None or mask.size == 0:
        return mask
    m = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_open, k_open)),
    )
    m = cv2.morphologyEx(
        m,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_close, k_close)),
    )
    return m


def detect_points_from_texture(
    texture_path: Path,
    target_json: Path,
    k_open: int = 3,
    k_close: int = 5,
    min_area: float = 10.0,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """
    Returns:
        - df2d with pixel_x, pixel_y, area, contour_id
        - final mask
        - hsv used
    """
    bgr = cv2.imread(str(texture_path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(f"Could not read texture: {texture_path}")
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    parts = load_target_ranges(target_json)
    if not parts:
        # devolvemos df vacío y mask vacía
        mask = np.zeros(hsv.shape[:2], np.uint8)
        return pd.DataFrame(columns=["pixel_x", "pixel_y", "area", "contour_id"]), mask, hsv

    mask = None
    for lo, hi in parts:
        m = cv2.inRange(hsv, lo, hi)
        mask = m if mask is None else cv2.bitwise_or(mask, m)
    if mask is None:
        mask = np.zeros(hsv.shape[:2], np.uint8)
    mask = clean_mask(mask, k_open, k_close)

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rows = []
    for i, c in enumerate(cnts):
        area = float(cv2.contourArea(c))
        if area < min_area:
            continue
        M = cv2.moments(c)
        if M.get("m00", 0) == 0:
            continue
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        rows.append({"pixel_x": cx, "pixel_y": cy, "area": area, "contour_id": i})

    df2d = pd.DataFrame(rows)
    return df2d, mask, hsv


def _parse_obj_uv_tris_strict(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Parse v, vt and triangulate faces. Handles negative indices."""
    V: list[list[float]] = []
    VT: list[list[float]] = []
    Fv: list[list[int]] = []
    Fvt: list[list[int]] = []

    def _norm_idx(i: int, n: int) -> int:
        return i - 1 if i > 0 else n + i

    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("v "):
                _, x, y, z = line.split()[:4]
                V.append([float(x), float(y), float(z)])
            elif line.startswith("vt "):
                parts = line.split()
                u = float(parts[1])
                v = float(parts[2])
                VT.append([u, v])
            elif line.startswith("f "):
                parts = line.split()[1:]
                vidx: list[int] = []
                vtidx: list[int] = []
                for p in parts:
                    comps = p.split("/")
                    if not comps or comps[0] == "":
                        continue
                    vi = _norm_idx(int(comps[0]), len(V))
                    vidx.append(vi)
                    if len(comps) > 1 and comps[1] != "":
                        vti = _norm_idx(int(comps[1]), len(VT))
                        vtidx.append(vti)
                if len(vidx) >= 3 and len(vtidx) >= 3:
                    # fan triangulation
                    for i in range(1, len(vidx) - 1):
                        Fv.append([vidx[0], vidx[i], vidx[i + 1]])
                        Fvt.append([vtidx[0], vtidx[i], vtidx[i + 1]])

    Vn = np.asarray(V, np.float32)
    VTn = np.asarray(VT, np.float32)
    Fvn = np.asarray(Fv, np.int32)
    Fvtn = np.asarray(Fvt, np.int32)

    if Fvn.size and int(Fvn.max()) >= len(Vn):
        raise ValueError(f"OBJ inconsistency: Fv.max={int(Fvn.max())} >= len(V)={len(Vn)}")
    if Fvtn.size and int(Fvtn.max()) >= len(VTn):
        raise ValueError(f"OBJ inconsistency: Fvt.max={int(Fvtn.max())} >= len(VT)={len(VTn)}")

    return Vn, VTn, Fvn, Fvtn


def _barycentric_uv(P: np.ndarray, A: np.ndarray, B: np.ndarray, C: np.ndarray):
    """Barycentric coordinates of P with respect to triangle ABC in 2D.
    Returns (wA, wB, wC) or None if degenerate/outside.
    """
    v0 = B - A
    v1 = C - A
    v2 = P - A
    dot00 = float(np.dot(v0, v0))
    dot01 = float(np.dot(v0, v1))
    dot11 = float(np.dot(v1, v1))
    dot02 = float(np.dot(v0, v2))
    dot12 = float(np.dot(v1, v2))
    denom = dot00 * dot11 - dot01 * dot01
    if abs(denom) < 1e-12:
        return None
    inv = 1.0 / denom
    u = (dot11 * dot02 - dot01 * dot12) * inv  # weight B-ish
    v = (dot00 * dot12 - dot01 * dot02) * inv  # weight C-ish
    w = 1.0 - u - v
    if u >= -1e-6 and v >= -1e-6 and w >= -1e-6:
        # weights for A,B,C
        return (w, u, v)
    return None


def _px_to_uv(x: int, y: int, W: int, H: int, v_flip: bool = True) -> tuple[float, float]:
    u = (x + 0.5) / float(W)
    v_img = (y + 0.5) / float(H)
    v = 1.0 - v_img if v_flip else v_img
    return u, v


def map_pixels_to_3d(
    df_pixels: pd.DataFrame,
    obj_path: Path,
    tex_w: int,
    tex_h: int,
    v_flip: bool = True,
    snap_to_vertices: bool = True,
    progress: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    """Map UV->XYZ (OBJ coordinates) with optional snap to nearest vertex."""
    if progress:
        progress("Reading OBJ (v/vt/f)...")

    V, VT, Fv, Fvt = _parse_obj_uv_tris_strict(obj_path)
    tri_uv = VT[Fvt]  # (n_tris, 3, 2)

    if df_pixels.empty:
        df3d = df_pixels.copy()
        df3d["u"] = []
        df3d["v"] = []
        df3d["x3d_raw"] = []
        df3d["y3d_raw"] = []
        df3d["z3d_raw"] = []
        df3d["x3d"] = []
        df3d["y3d"] = []
        df3d["z3d"] = []
        df3d["status"] = []
        return df3d

    # pixel -> uv
    uvs = [
        _px_to_uv(int(x), int(y), tex_w, tex_h, v_flip=v_flip)
        for x, y in df_pixels[["pixel_x", "pixel_y"]].itertuples(index=False, name=None)
    ]

    df3d = df_pixels.copy()
    df3d["u"] = [u for u, _ in uvs]
    df3d["v"] = [v for _, v in uvs]

    xyz_raw = np.full((len(df3d), 3), np.nan, np.float32)

    if progress:
        progress(f"Mapping {len(df3d)} UV->XYZ points (barycentric)...")

    # Simple search: iterate triangles until the container is found
    for idx, (u, v) in enumerate(zip(df3d["u"].to_numpy(), df3d["v"].to_numpy())):
        P = np.array([u, v], np.float32)
        found = False
        for i in range(tri_uv.shape[0]):
            Auv, Buv, Cuv = tri_uv[i]
            wA_wB_wC = _barycentric_uv(P, Auv, Buv, Cuv)
            if wA_wB_wC is not None:
                wA, wB, wC = wA_wB_wC
                A, B, C = V[Fv[i]][0], V[Fv[i]][1], V[Fv[i]][2]
                xyz_raw[idx] = (wA * A + wB * B + wC * C).astype(np.float32)
                found = True
                break
        if progress and (idx % 50 == 0) and idx > 0:
            progress(f"…{idx}/{len(df3d)}")
        if not found:
            # remains NaN
            pass

    df3d["x3d_raw"], df3d["y3d_raw"], df3d["z3d_raw"] = xyz_raw[:, 0], xyz_raw[:, 1], xyz_raw[:, 2]

    valid = np.all(np.isfinite(xyz_raw), axis=1)
    xyz_final = xyz_raw.copy()

    if snap_to_vertices and np.any(valid):
        if progress:
            progress("Snapping points to the surface (nearest vertex)...")
        V_all = V
        for idx in range(len(df3d)):
            if not valid[idx]:
                continue
            p = xyz_raw[idx]
            d2 = np.sum((V_all - p[None, :]) ** 2, axis=1)
            j = int(np.argmin(d2))
            xyz_final[idx] = V_all[j]

    df3d["x3d"], df3d["y3d"], df3d["z3d"] = xyz_final[:, 0], xyz_final[:, 1], xyz_final[:, 2]
    df3d["X"], df3d["Y"], df3d["Z"] = df3d["x3d"], df3d["y3d"], df3d["z3d"]
    df3d["status"] = np.where(valid, "mapped_snapped" if snap_to_vertices else "mapped_raw", "unmapped")

    return df3d



def build_2d_from_3d(df3d: pd.DataFrame) -> pd.DataFrame:
    """Rebuild the 2D detections table from the current 3D table.

    The 3D table is the authoritative source. Each surviving 3D row yields exactly
    one 2D row, even if several texture pixels originally mapped to the same 3D point.
    """
    if df3d is None or df3d.empty:
        return pd.DataFrame(columns=["pixel_x", "pixel_y", "area", "contour_id"])

    df2d = pd.DataFrame(index=df3d.index)
    df2d["pixel_x"] = pd.to_numeric(df3d.get("pixel_x"), errors="coerce").fillna(0).astype(int) if "pixel_x" in df3d.columns else 0
    df2d["pixel_y"] = pd.to_numeric(df3d.get("pixel_y"), errors="coerce").fillna(0).astype(int) if "pixel_y" in df3d.columns else 0
    df2d["area"] = pd.to_numeric(df3d.get("area"), errors="coerce").fillna(0.0) if "area" in df3d.columns else 0.0
    df2d["contour_id"] = pd.to_numeric(df3d.get("contour_id"), errors="coerce").fillna(-1).astype(int) if "contour_id" in df3d.columns else -1
    return df2d.reset_index(drop=True)


def reconcile_points_with_3d_priority(
    df3d: pd.DataFrame,
    obj_path: Path | None = None,
    distance_threshold: float | None = None,
    keep_only_mapped: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, int, float]:
    """Make the 3D list authoritative and derive the 2D list from it.

    Workflow:
    1) Start from the current 3D rows.
    2) Optionally discard unmapped/invalid 3D rows because they cannot rule the set.
    3) Remove near-duplicates by comparing only 3D coordinates.
    4) Rebuild the 2D table from the surviving 3D rows.

    This is the rule used across the app after initial detection and after every
    user edition in 2D or 3D.
    """
    if df3d is None or df3d.empty:
        empty3d = pd.DataFrame(columns=df3d.columns if df3d is not None else None)
        empty2d = build_2d_from_3d(empty3d)
        return empty3d, empty2d, 0, float(distance_threshold or 0.0)

    df = df3d.copy().reset_index(drop=True)

    if keep_only_mapped:
        valid_mask = pd.Series(True, index=df.index)
        if "status" in df.columns:
            valid_mask &= df["status"].astype(str).str.lower() != "unmapped"

        coord_candidates = [("x3d", "y3d", "z3d"), ("X", "Y", "Z"), ("x3d_raw", "y3d_raw", "z3d_raw")]
        coord_cols = next((cols for cols in coord_candidates if set(cols).issubset(df.columns)), None)
        if coord_cols is not None:
            valid_mask &= df[list(coord_cols)].apply(pd.to_numeric, errors="coerce").notna().all(axis=1)

        df = df.loc[valid_mask].reset_index(drop=True)

    df3d_clean, removed_close, dedupe_threshold = remove_close_points_3d(
        df,
        obj_path=obj_path,
        distance_threshold=distance_threshold,
    )
    df2d_clean = build_2d_from_3d(df3d_clean)
    return df3d_clean, df2d_clean, removed_close, dedupe_threshold

def _estimate_3d_duplicate_distance(obj_path: Path | None = None, ratio: float = 0.015, min_abs: float = 1e-6) -> float:
    """Estimate a reasonable 3D deduplication distance from the mesh scale."""
    try:
        if obj_path is not None and Path(obj_path).exists():
            V, _, _, _ = _parse_obj_uv_tris_strict(Path(obj_path))
            if V.size:
                diag = float(np.linalg.norm(V.max(axis=0) - V.min(axis=0)))
                if np.isfinite(diag) and diag > 0:
                    return max(min_abs, diag * ratio)
    except Exception:
        pass
    return float(max(min_abs, ratio))


def remove_close_points_3d(
    df3d: pd.DataFrame,
    obj_path: Path | None = None,
    distance_threshold: float | None = None,
) -> tuple[pd.DataFrame, int, float]:
    """Remove near-duplicate rows by comparing their 3D positions.

    The first point in each proximity group is kept to preserve the user-visible order.
    Unmapped rows are preserved because they cannot be compared in 3D space.
    """
    if df3d is None or df3d.empty:
        return pd.DataFrame(columns=df3d.columns if df3d is not None else None), 0, float(distance_threshold or 0.0)

    df = df3d.reset_index(drop=True).copy()
    threshold = float(distance_threshold) if distance_threshold is not None else _estimate_3d_duplicate_distance(obj_path)

    coord_candidates = [("x3d", "y3d", "z3d"), ("X", "Y", "Z"), ("x3d_raw", "y3d_raw", "z3d_raw")]
    coord_cols = next((cols for cols in coord_candidates if set(cols).issubset(df.columns)), None)
    if coord_cols is None:
        return df, 0, threshold

    coords = df.loc[:, list(coord_cols)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(coords).all(axis=1)

    keep = np.ones(len(df), dtype=bool)
    valid_idx = np.flatnonzero(valid)
    for pos, idx in enumerate(valid_idx):
        if not keep[idx]:
            continue
        if pos + 1 >= len(valid_idx):
            break
        rest = valid_idx[pos + 1:]
        if len(rest) == 0:
            continue
        deltas = coords[rest] - coords[idx]
        dists = np.linalg.norm(deltas, axis=1)
        close_mask = dists <= threshold
        if np.any(close_mask):
            keep[rest[close_mask]] = False

    removed = int((~keep).sum())
    return df.loc[keep].reset_index(drop=True), removed, threshold


def run_detect_and_map(
    texture_path: Path,
    obj_path: Path,
    out_dir: Path,
    target_json: Path | None = None,
    v_flip: bool = True,
    snap_to_vertices: bool = True,
    log: Callable[[str], None] | None = None,
    k_open: int = 3,
    k_close: int = 5,
    min_area: float = 10.0,
) -> DetectMapResult:
    """Run 2D detection + UV->XYZ mapping and save CSVs into out_dir."""
    try:
        out_dir.mkdir(parents=True, exist_ok=True)

        if target_json is None:
            target_json = target_ranges_path(out_dir)
        if not target_json.exists():
            return DetectMapResult(ok=False, message=f"Not found: {target_json}")
        if not texture_path.exists():
            return DetectMapResult(ok=False, message=f"Texture does not exist: {texture_path}")
        if not obj_path.exists():
            return DetectMapResult(ok=False, message=f"OBJ does not exist: {obj_path}")

        if log:
            log(f"Texture: {texture_path}")
            log(f"OBJ: {obj_path}")
            log(f"Target ranges: {target_json}")

        df2d, _mask, hsv = detect_points_from_texture(
            texture_path=texture_path,
            target_json=target_json,
            k_open=k_open,
            k_close=k_close,
            min_area=min_area,
        )

        if log:
            log(f"[OK] Initial 2D detections: {len(df2d)} points")

        df3d = map_pixels_to_3d(
            df_pixels=df2d,
            obj_path=obj_path,
            tex_w=int(hsv.shape[1]),
            tex_h=int(hsv.shape[0]),
            v_flip=v_flip,
            snap_to_vertices=snap_to_vertices,
            progress=log,
        )

        df3d, df2d, removed_close, dedupe_threshold = reconcile_points_with_3d_priority(
            df3d,
            obj_path=obj_path,
        )

        csv_2d = detections_all_csv(out_dir)
        csv_3d = detections_mapped_3d_csv(out_dir)
        df2d.to_csv(csv_2d, index=False, encoding="utf-8")
        df3d.to_csv(csv_3d, index=False, encoding="utf-8")

        n_mapped = int((df3d["status"].astype(str).str.lower() != "unmapped").sum()) if (not df3d.empty and "status" in df3d.columns) else int(len(df3d))
        if log:
            if removed_close > 0:
                log(f"[OK] 3D post-process removed {removed_close} near-duplicate point(s) (distance <= {dedupe_threshold:.6g}).")
            else:
                log(f"[OK] 3D post-process found no near-duplicate points (distance <= {dedupe_threshold:.6g}).")
            log(f"[OK] 2D CSV saved: {csv_2d} ({len(df2d)} points)")
            log(f"[OK] 3D CSV saved: {csv_3d} ({len(df3d)} points; mapped={n_mapped})")

        return DetectMapResult(
            ok=True,
            message="Detection and mapping completed.",
            csv_2d=csv_2d,
            csv_3d=csv_3d,
            n_2d=len(df2d),
            n_3d_mapped=n_mapped,
        )

    except Exception as e:
        return DetectMapResult(ok=False, message=str(e))
