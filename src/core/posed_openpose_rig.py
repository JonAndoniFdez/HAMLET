from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
import json
import math
import os
import re
import subprocess

import cv2
import numpy as np
import pandas as pd

from .blender_scripts import blender_script_path
from .paths import asset_path, bundled_openpose_dir, resolve_blender_exe, app_root
from .settings import load_settings
from .output_cleanup import (
    detections_mapped_3d_csv,
    hand_rigged_blend,
    hand_with_points_obj,
    processing_dir,
)
from .hand_with_points import run_make_hand_with_points
from .subprocess_utils import run_hidden


LANDMARK_NAMES = {
    0: "WRIST",
    1: "THUMB_CMC",
    2: "THUMB_MCP",
    3: "THUMB_IP",
    4: "THUMB_TIP",
    5: "INDEX_MCP",
    6: "INDEX_PIP",
    7: "INDEX_DIP",
    8: "INDEX_TIP",
    9: "MIDDLE_MCP",
    10: "MIDDLE_PIP",
    11: "MIDDLE_DIP",
    12: "MIDDLE_TIP",
    13: "RING_MCP",
    14: "RING_PIP",
    15: "RING_DIP",
    16: "RING_TIP",
    17: "PINKY_MCP",
    18: "PINKY_PIP",
    19: "PINKY_DIP",
    20: "PINKY_TIP",
}

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17),
]


@dataclass
class PosedRigBuildResult:
    ok: bool
    out_blend: Path | None = None
    joints_csv: Path | None = None
    keypoints_csv: Path | None = None
    summary_csv: Path | None = None
    overlay_png: Path | None = None
    render_dir: Path | None = None
    triangulated_csv: Path | None = None
    message: str = ""
    stdout: str = ""
    stderr: str = ""


def _log_call(log, message: str):
    if log:
        try:
            log(message)
        except Exception:
            pass


def _settings_texture_path(settings: dict | None) -> Path | None:
    settings = settings or {}
    for key in ("texture_path_work", "work_texture_path", "rebaked_texture_path", "threshold_texture_path", "texture_path"):
        raw = settings.get(key)
        if not raw:
            continue
        try:
            p = Path(raw)
            if p.exists() and p.is_file():
                return p.resolve()
        except Exception:
            continue
    return None


def _run_subprocess(cmd: list[str], *, cwd: Path | None = None, log=None) -> subprocess.CompletedProcess:
    _log_call(log, " ".join(str(x) for x in cmd))
    p = run_hidden(cmd, capture_output=True, text=True, cwd=str(cwd) if cwd else None)
    if p.stdout:
        _log_call(log, p.stdout.strip())
    if p.stderr:
        _log_call(log, p.stderr.strip())
    return p


def _subprocess_error_message(prefix: str, p: subprocess.CompletedProcess, max_lines: int = 20) -> str:
    details = "\n".join(
        line
        for text in (p.stderr or "", p.stdout or "")
        for line in text.splitlines()
        if line.strip()
    )
    if details:
        details = "\n".join(details.splitlines()[-max_lines:])
        return f"{prefix} with code {p.returncode}\n\nBlender output:\n{details}"
    return f"{prefix} with code {p.returncode}"


def _find_openpose_hand_models(openpose_dir: Path | None = None) -> tuple[Path, Path]:
    candidates: list[Path] = []
    if openpose_dir:
        candidates.append(Path(openpose_dir))
    env_dir = os.environ.get("OPENPOSE_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    bundled = bundled_openpose_dir()
    if bundled:
        candidates.append(bundled)
    candidates.append(app_root() / "openpose")
    candidates.append(Path.cwd() / "openpose")

    checked: list[Path] = []
    for root in candidates:
        try:
            root = root.resolve()
        except Exception:
            continue
        if root in checked:
            continue
        checked.append(root)
        proto = root / "models" / "hand" / "pose_deploy.prototxt"
        model = root / "models" / "hand" / "pose_iter_102000.caffemodel"
        if proto.exists() and model.exists():
            return proto, model

    lines = [
        "No se han encontrado los modelos de mano de OpenPose.",
        "Se esperaba encontrar:",
        "  <OPENPOSE_DIR>/models/hand/pose_deploy.prototxt",
        "  <OPENPOSE_DIR>/models/hand/pose_iter_102000.caffemodel",
        "Rutas comprobadas:",
        *[f"  - {p}" for p in checked],
    ]
    raise FileNotFoundError("\n".join(lines))


def _load_openpose_caffe_network(proto_path: Path, model_path: Path):
    proto_path = Path(proto_path)
    model_path = Path(model_path)
    if not proto_path.exists():
        raise FileNotFoundError(f"OpenPose prototxt not found: {proto_path}")
    if not model_path.exists():
        raise FileNotFoundError(f"OpenPose caffemodel not found: {model_path}")
    if not hasattr(cv2, "dnn"):
        raise RuntimeError("La instalación actual de OpenCV no incluye cv2.dnn.")

    try:
        if hasattr(cv2.dnn, "readNetFromCaffe"):
            return cv2.dnn.readNetFromCaffe(str(proto_path), str(model_path))
    except Exception as exc:
        raise RuntimeError(
            "OpenCV no ha podido cargar el modelo Caffe de OpenPose. "
            "Si estás usando OpenCV 5.x, el importador Caffe puede no estar disponible; "
            "usa una versión 4.x compatible de opencv-python/opencv-contrib-python o una instalación de OpenPose compatible.\n"
            f"Prototxt: {proto_path}\nCaffemodel: {model_path}\nError: {exc}"
        ) from exc

    if hasattr(cv2.dnn, "readNet"):
        last_error = None
        for args in ((str(model_path), str(proto_path), "Caffe"), (str(model_path), str(proto_path)), (str(proto_path), str(model_path))):
            try:
                return cv2.dnn.readNet(*args)
            except Exception as exc:
                last_error = exc
        raise RuntimeError(
            "OpenCV DNN existe, pero no puede cargar el modelo Caffe de OpenPose. "
            "Prueba con OpenCV 4.x compatible."
        ) from last_error

    raise RuntimeError("cv2.dnn no proporciona readNetFromCaffe ni readNet.")


def render_posed_hand_multiview(
    *,
    settings: dict,
    obj_path: Path,
    out_dir: Path,
    resolution: int = 1024,
    num_views: int = 10,
    log=None,
) -> tuple[Path, Path, str, str]:
    persisted = load_settings() or {}
    merged_settings = dict(persisted)
    if isinstance(settings, dict):
        merged_settings.update(settings)

    blender_exe = resolve_blender_exe(merged_settings)
    if blender_exe is None:
        raise RuntimeError("Blender executable not found. Expected bundled path: <app>/blender/blender.exe")

    script = blender_script_path("render_posed_hand_multiview.py")
    if not script.exists():
        raise FileNotFoundError(f"Blender script does not exist: {script}")

    obj_path = Path(obj_path)
    if not obj_path.exists():
        raise FileNotFoundError(f"OBJ does not exist: {obj_path}")

    render_dir = Path(out_dir)
    render_dir.mkdir(parents=True, exist_ok=True)
    texture_path = _settings_texture_path(merged_settings)

    # Keep the posed-hand workflow aligned with the notebook used as reference.
    # These defaults reproduce the capture-axis orbit tested there:
    # orbit around Z, first view from +X, and 10 views from 0 to -180 degrees.
    # They can still be overridden from settings if a future acquisition setup needs it.
    orbit_axis = str(merged_settings.get("posed_rigging_orbit_axis", "Z")).upper().replace("+", "")
    start_view_axis = str(merged_settings.get("posed_rigging_start_view_axis", "X")).upper().replace("+", "")
    if orbit_axis not in {"X", "Y", "Z"}:
        orbit_axis = "Z"
    if start_view_axis not in {"X", "Y", "Z", "-X", "-Y", "-Z"}:
        start_view_axis = "X"

    cmd = [
        str(blender_exe),
        "--background",
        "--python", str(script),
        "--",
        "--obj", str(obj_path),
        "--out_dir", str(render_dir),
        "--resolution", str(int(resolution)),
        "--num_views", str(int(num_views)),
        "--orbit_axis", orbit_axis,
        "--start_view_axis", start_view_axis,
        "--start_angle_deg", "0",
        "--end_angle_deg", "-180",
        "--ortho_scale_factor", "1.25",
    ]
    if texture_path:
        cmd.extend(["--texture", str(texture_path)])

    _log_call(log, "[Posed Rigging] Rendering 10 capture-axis views…")
    p = _run_subprocess(cmd, cwd=blender_exe.parent, log=log)
    if p.returncode != 0:
        raise RuntimeError(_subprocess_error_message("Blender multiview rendering failed", p))

    metadata_path = render_dir / "posed_multiview_camera_metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Blender finished but metadata was not created: {metadata_path}")
    return render_dir, metadata_path, p.stdout or "", p.stderr or ""


def _load_rendered_images_from_metadata(metadata_path: Path) -> Dict[str, Path]:
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    images: Dict[str, Path] = {}
    for view_name, view_data in metadata.items():
        p = Path(view_data["image_path"])
        if p.exists():
            images[view_name] = p
    return images


def _rotate_image_bgr(image_bgr: np.ndarray, angle_deg: int) -> np.ndarray:
    angle_deg = int(angle_deg) % 360
    if angle_deg == 0:
        return image_bgr.copy()
    if angle_deg == 90:
        return cv2.rotate(image_bgr, cv2.ROTATE_90_CLOCKWISE)
    if angle_deg == 180:
        return cv2.rotate(image_bgr, cv2.ROTATE_180)
    if angle_deg == 270:
        return cv2.rotate(image_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError("Only 0, 90, 180 and 270 degree rotations are supported.")


def _map_rotated_point_to_original(x_rot: float, y_rot: float, angle_deg: int, original_width: int, original_height: int) -> tuple[float, float]:
    angle_deg = int(angle_deg) % 360
    if angle_deg == 0:
        return float(x_rot), float(y_rot)
    if angle_deg == 90:
        return float(y_rot), float(original_height - 1 - x_rot)
    if angle_deg == 180:
        return float(original_width - 1 - x_rot), float(original_height - 1 - y_rot)
    if angle_deg == 270:
        return float(original_width - 1 - y_rot), float(x_rot)
    raise ValueError("Only 0, 90, 180 and 270 degree rotations are supported.")


def _run_openpose_hand_on_image_bgr(image_bgr: np.ndarray, net, *, in_height: int, threshold: float, n_used: int = 21) -> pd.DataFrame:
    h, w = image_bgr.shape[:2]
    in_width = int((float(in_height) / float(h)) * float(w))
    blob = cv2.dnn.blobFromImage(
        image_bgr,
        scalefactor=1.0 / 255.0,
        size=(in_width, int(in_height)),
        mean=(0, 0, 0),
        swapRB=False,
        crop=False,
    )
    net.setInput(blob)
    output = net.forward()
    n_points = int(output.shape[1])
    out_h = int(output.shape[2])
    out_w = int(output.shape[3])
    n_used_eff = min(int(n_used), n_points)

    records = []
    for landmark_id in range(n_used_eff):
        heatmap = output[0, landmark_id, :, :]
        _, conf, _, pt = cv2.minMaxLoc(heatmap)
        x_px = (w * pt[0]) / float(out_w)
        y_px = (h * pt[1]) / float(out_h)
        conf = float(conf)
        valid = bool(conf >= threshold)
        records.append({
            "landmark_id": landmark_id,
            "landmark_name": LANDMARK_NAMES.get(landmark_id, f"LANDMARK_{landmark_id}"),
            "x_px_rotated": float(x_px) if valid else np.nan,
            "y_px_rotated": float(y_px) if valid else np.nan,
            "confidence": conf,
            "valid": valid,
        })
    return pd.DataFrame(records)


def _choose_best_openpose_rotation(
    image_bgr: np.ndarray,
    net,
    rotations_deg: Iterable[int],
    *,
    in_height: int,
    threshold: float,
    n_used: int,
) -> tuple[pd.DataFrame, int, dict]:
    original_height, original_width = image_bgr.shape[:2]
    best_df = None
    best_angle = 0
    best_score = (-1, -1.0)
    rotation_trials = []

    for angle in rotations_deg:
        rotated = _rotate_image_bgr(image_bgr, int(angle))
        df = _run_openpose_hand_on_image_bgr(rotated, net, in_height=in_height, threshold=threshold, n_used=n_used)
        num_valid = int(df["valid"].sum())
        mean_conf = float(df["confidence"].mean()) if len(df) else 0.0
        rotation_trials.append({"angle_deg": int(angle), "num_valid": num_valid, "mean_confidence": mean_conf})
        score = (num_valid, mean_conf)
        if score > best_score:
            best_score = score
            best_df = df
            best_angle = int(angle)

    if best_df is None:
        raise RuntimeError("OpenPose did not produce a result for the tested rotations.")

    x_orig_values = []
    y_orig_values = []
    for _, row in best_df.iterrows():
        if not bool(row["valid"]):
            x_orig_values.append(np.nan)
            y_orig_values.append(np.nan)
            continue
        x_orig, y_orig = _map_rotated_point_to_original(
            float(row["x_px_rotated"]),
            float(row["y_px_rotated"]),
            best_angle,
            original_width,
            original_height,
        )
        x_orig_values.append(x_orig)
        y_orig_values.append(y_orig)

    best_df = best_df.copy()
    best_df["x_px"] = x_orig_values
    best_df["y_px"] = y_orig_values
    best_df["best_rotation_deg"] = best_angle
    best_df["image_width"] = int(original_width)
    best_df["image_height"] = int(original_height)
    return best_df, best_angle, {
        "best_rotation_deg": int(best_angle),
        "num_valid": int(best_df["valid"].sum()),
        "mean_confidence": float(best_df["confidence"].mean()) if len(best_df) else 0.0,
        "rotation_trials": rotation_trials,
    }


def _draw_openpose_landmarks(image_bgr: np.ndarray, detections_df: pd.DataFrame, output_path: Path) -> None:
    annotated = image_bgr.copy()
    points = {}
    for _, row in detections_df.iterrows():
        if not bool(row["valid"]):
            continue
        x = float(row["x_px"])
        y = float(row["y_px"])
        if np.isfinite(x) and np.isfinite(y):
            points[int(row["landmark_id"])] = (x, y)

    for a, b in HAND_CONNECTIONS:
        if a in points and b in points:
            pa, pb = points[a], points[b]
            cv2.line(annotated, (int(round(pa[0])), int(round(pa[1]))), (int(round(pb[0])), int(round(pb[1]))), (0, 255, 0), 2)
    for landmark_id, (x, y) in points.items():
        cv2.circle(annotated, (int(round(x)), int(round(y))), 5, (0, 255, 255), -1)
        cv2.putText(annotated, str(landmark_id), (int(round(x)) + 6, int(round(y)) + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), annotated)


def _make_openpose_multiview_grid(
    items: list[dict],
    output_path: Path,
    *,
    columns: int = 5,
    thumb_size: int = 320,
    header_px: int = 34,
) -> Path | None:
    """Create a single preview image containing all posed-hand OpenPose views."""
    valid_items = []
    for item in items:
        p = Path(str(item.get("annotated_path", "")))
        if p.exists():
            valid_items.append(dict(item, annotated_path=str(p)))
    if not valid_items:
        return None

    columns = max(1, int(columns))
    rows = int(math.ceil(len(valid_items) / float(columns)))
    tile_w = int(thumb_size)
    tile_h = int(thumb_size) + int(header_px)
    grid = np.zeros((rows * tile_h, columns * tile_w, 3), dtype=np.uint8)

    for idx, item in enumerate(valid_items):
        image = cv2.imread(str(item["annotated_path"]), cv2.IMREAD_COLOR)
        if image is None:
            continue
        h, w = image.shape[:2]
        if h <= 0 or w <= 0:
            continue
        scale = min(float(tile_w) / float(w), float(thumb_size) / float(h))
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

        r = idx // columns
        c = idx % columns
        x0 = c * tile_w
        y0 = r * tile_h

        title = f"{idx + 1:02d}  {item.get('view_name', '')}"
        detail = f"valid={item.get('num_valid_landmarks', 0)}  rot={item.get('best_rotation_deg', '')}"
        cv2.putText(grid, title[:42], (x0 + 8, y0 + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (230, 230, 230), 1, cv2.LINE_AA)
        cv2.putText(grid, detail[:42], (x0 + 8, y0 + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1, cv2.LINE_AA)

        ix = x0 + (tile_w - new_w) // 2
        iy = y0 + header_px + (thumb_size - new_h) // 2
        grid[iy:iy + new_h, ix:ix + new_w] = resized
        cv2.rectangle(grid, (x0, y0), (x0 + tile_w - 1, y0 + tile_h - 1), (70, 70, 70), 1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(output_path), grid)
    return output_path if ok and output_path.exists() else None


def run_openpose_on_rendered_views(
    *,
    render_dir: Path,
    metadata_path: Path,
    out_dir: Path,
    openpose_dir: Path | None = None,
    in_height: int = 368,
    threshold: float = 0.10,
    n_used: int = 21,
    min_valid_landmarks_per_view: int = 6,
    rotations_deg: Iterable[int] = (0, 90, 180, 270),
    log=None,
) -> tuple[pd.DataFrame, pd.DataFrame, Path | None]:
    out_dir = Path(out_dir)
    annotated_dir = out_dir / "annotated_images"
    out_dir.mkdir(parents=True, exist_ok=True)
    annotated_dir.mkdir(parents=True, exist_ok=True)

    raw_json = out_dir / "openpose_landmarks_raw.json"
    landmarks_csv = out_dir / "openpose_landmarks.csv"
    summary_csv = out_dir / "openpose_detection_summary.csv"

    proto, model = _find_openpose_hand_models(openpose_dir)
    _log_call(log, f"[Posed Rigging] OpenPose prototxt: {proto}")
    _log_call(log, f"[Posed Rigging] OpenPose model:    {model}")
    net = _load_openpose_caffe_network(proto, model)

    rendered_images = _load_rendered_images_from_metadata(metadata_path)
    if not rendered_images:
        raise FileNotFoundError(f"No rendered images found from metadata: {metadata_path}")

    all_records = []
    summary_records = []
    raw_results = {}
    best_preview: tuple[int, Path] | None = None
    grid_items: list[dict] = []

    for view_name, image_path in rendered_images.items():
        _log_call(log, f"[Posed Rigging] Processing OpenPose view: {view_name}")
        image_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image_bgr is None:
            summary_records.append({
                "view_name": view_name,
                "image_path": str(image_path),
                "detected": False,
                "num_landmarks": int(n_used),
                "num_valid_landmarks": 0,
                "mean_confidence": np.nan,
                "best_rotation_deg": None,
                "annotated_path": "",
            })
            continue

        detections_df, best_angle, info = _choose_best_openpose_rotation(
            image_bgr,
            net,
            rotations_deg,
            in_height=int(in_height),
            threshold=float(threshold),
            n_used=int(n_used),
        )
        num_valid = int(detections_df["valid"].sum())
        detected = bool(num_valid >= int(min_valid_landmarks_per_view))
        mean_confidence = float(detections_df["confidence"].mean()) if len(detections_df) else np.nan

        annotated_path = annotated_dir / f"{view_name}_openpose.png"
        _draw_openpose_landmarks(image_bgr, detections_df, annotated_path)
        if best_preview is None or num_valid > best_preview[0]:
            best_preview = (num_valid, annotated_path)
        grid_items.append({
            "view_name": view_name,
            "annotated_path": str(annotated_path),
            "num_valid_landmarks": num_valid,
            "best_rotation_deg": best_angle,
        })

        valid_df = detections_df[detections_df["valid"] == True].copy()
        for _, row in valid_df.iterrows():
            x_px = float(row["x_px"])
            y_px = float(row["y_px"])
            if not np.isfinite(x_px) or not np.isfinite(y_px):
                continue
            all_records.append({
                "view_name": view_name,
                "image_path": str(image_path),
                "landmark_id": int(row["landmark_id"]),
                "landmark_name": row["landmark_name"],
                "x_px": x_px,
                "y_px": y_px,
                "image_width": int(row["image_width"]),
                "image_height": int(row["image_height"]),
                "confidence": float(row["confidence"]),
                "best_rotation_deg": int(row["best_rotation_deg"]),
                "detector": "OpenPose",
            })

        summary_records.append({
            "view_name": view_name,
            "image_path": str(image_path),
            "detected": detected,
            "num_landmarks": int(n_used),
            "num_valid_landmarks": num_valid,
            "mean_confidence": mean_confidence,
            "best_rotation_deg": best_angle,
            "annotated_path": str(annotated_path),
        })
        raw_results[view_name] = {
            "image_path": str(image_path),
            "detected": detected,
            "num_valid_landmarks": num_valid,
            "mean_confidence": mean_confidence,
            "best_rotation_deg": best_angle,
            "rotation_trials": info["rotation_trials"],
            "landmarks": detections_df.replace({np.nan: None}).to_dict(orient="records"),
        }

    landmarks_df = pd.DataFrame(all_records)
    summary_df = pd.DataFrame(summary_records)
    landmarks_df.to_csv(landmarks_csv, index=False, encoding="utf-8")
    summary_df.to_csv(summary_csv, index=False, encoding="utf-8")
    with open(raw_json, "w", encoding="utf-8") as f:
        json.dump(raw_results, f, indent=4)

    grid_png = _make_openpose_multiview_grid(grid_items, out_dir / "openpose_multiview_grid.png")
    overlay_png = grid_png if grid_png is not None else (best_preview[1] if best_preview else None)
    return landmarks_df, summary_df, overlay_png


def _normalize_3d_vector(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise ValueError("Cannot normalize a zero-length vector.")
    return v / n


def _pixel_to_world_ray_orthographic(x_px: float, y_px: float, view_data: dict) -> Tuple[np.ndarray, np.ndarray]:
    camera_matrix_world = np.array(view_data["camera_matrix_world"], dtype=float)
    render_width = int(view_data["render_width"])
    render_height = int(view_data["render_height"])
    camera_type = view_data.get("camera_type", "ORTHO")
    if camera_type != "ORTHO":
        raise ValueError(f"Expected ORTHO camera. Received camera_type={camera_type}")

    ortho_scale = float(view_data["camera_ortho_scale"])
    aspect = render_width / render_height
    ortho_height = ortho_scale
    ortho_width = ortho_scale * aspect

    x_cam = (float(x_px) / render_width - 0.5) * ortho_width
    y_cam = (0.5 - float(y_px) / render_height) * ortho_height
    local_origin = np.array([x_cam, y_cam, 0.0, 1.0], dtype=float)
    world_origin = (camera_matrix_world @ local_origin)[:3]
    rotation_world = camera_matrix_world[:3, :3]
    world_direction = rotation_world @ np.array([0.0, 0.0, -1.0], dtype=float)
    return world_origin, _normalize_3d_vector(world_direction)


def _closest_point_to_lines(origins: np.ndarray, directions: np.ndarray) -> np.ndarray:
    origins = np.asarray(origins, dtype=float)
    directions = np.asarray(directions, dtype=float)
    A = np.zeros((3, 3), dtype=float)
    b = np.zeros(3, dtype=float)
    identity = np.eye(3)
    for origin, direction in zip(origins, directions):
        direction = _normalize_3d_vector(direction)
        projection = identity - np.outer(direction, direction)
        A += projection
        b += projection @ origin
    return np.linalg.pinv(A) @ b


def _point_to_line_distances(point: np.ndarray, origins: np.ndarray, directions: np.ndarray) -> np.ndarray:
    distances = []
    for origin, direction in zip(origins, directions):
        direction = _normalize_3d_vector(direction)
        diff = point - origin
        distances.append(np.linalg.norm(np.cross(diff, direction)))
    return np.array(distances, dtype=float)


def _robust_triangulate_landmark(group: pd.DataFrame):
    origins = group[["ray_origin_x", "ray_origin_y", "ray_origin_z"]].to_numpy(dtype=float)
    directions = group[["ray_dir_x", "ray_dir_y", "ray_dir_z"]].to_numpy(dtype=float)
    num_initial_rays = len(group)
    if num_initial_rays < 2:
        return None, None

    point = _closest_point_to_lines(origins, directions)
    distances = _point_to_line_distances(point, origins, directions)
    keep_mask = np.ones(num_initial_rays, dtype=bool)

    if num_initial_rays >= 3:
        median_distance = float(np.median(distances))
        mad = float(np.median(np.abs(distances - median_distance)))
        threshold = median_distance * 2.5 + 1e-9 if mad < 1e-12 else median_distance + 2.5 * mad
        candidate_keep_mask = distances <= threshold
        if candidate_keep_mask.sum() >= 2 and candidate_keep_mask.sum() < num_initial_rays:
            keep_mask = candidate_keep_mask
            origins_refined = origins[keep_mask]
            directions_refined = directions[keep_mask]
            point = _closest_point_to_lines(origins_refined, directions_refined)
            distances_refined = _point_to_line_distances(point, origins_refined, directions_refined)
        else:
            distances_refined = distances
    else:
        distances_refined = distances

    return point, {
        "num_initial_rays": int(num_initial_rays),
        "num_used_rays": int(keep_mask.sum()),
        "mean_ray_distance": float(np.mean(distances_refined)),
        "max_ray_distance": float(np.max(distances_refined)),
        "used_mask": keep_mask,
    }


def reconstruct_multiview_3d_landmarks(
    *,
    landmarks_df: pd.DataFrame,
    metadata_path: Path,
    out_dir: Path,
    log=None,
) -> tuple[Path, Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rays_csv = out_dir / "landmark_rays.csv"
    triangulated_csv = out_dir / "triangulated_landmarks_3d.csv"
    observations_csv = out_dir / "triangulation_observations.csv"

    with open(metadata_path, "r", encoding="utf-8") as f:
        camera_metadata = json.load(f)

    if len(landmarks_df) == 0:
        raise RuntimeError("OpenPose landmarks file is empty. At least two views are required for triangulation.")

    ray_records = []
    for _, row in landmarks_df.iterrows():
        view_name = str(row["view_name"])
        if view_name not in camera_metadata:
            continue
        ray_origin, ray_direction = _pixel_to_world_ray_orthographic(float(row["x_px"]), float(row["y_px"]), camera_metadata[view_name])
        ray_records.append({
            "view_name": view_name,
            "landmark_id": int(row["landmark_id"]),
            "landmark_name": row["landmark_name"],
            "x_px": float(row["x_px"]),
            "y_px": float(row["y_px"]),
            "ray_origin_x": float(ray_origin[0]),
            "ray_origin_y": float(ray_origin[1]),
            "ray_origin_z": float(ray_origin[2]),
            "ray_dir_x": float(ray_direction[0]),
            "ray_dir_y": float(ray_direction[1]),
            "ray_dir_z": float(ray_direction[2]),
        })

    rays_df = pd.DataFrame(ray_records)
    rays_df.to_csv(rays_csv, index=False, encoding="utf-8")
    if len(rays_df) == 0:
        raise RuntimeError("No valid 3D rays could be created from OpenPose detections.")

    triangulated_records = []
    observation_records = []
    for landmark_id, group in rays_df.groupby("landmark_id", sort=True):
        point, info = _robust_triangulate_landmark(group)
        landmark_name = group["landmark_name"].iloc[0]
        if point is None:
            triangulated_records.append({
                "landmark_id": int(landmark_id),
                "landmark_name": landmark_name,
                "triangulated": False,
                "x": np.nan,
                "y": np.nan,
                "z": np.nan,
                "num_initial_rays": len(group),
                "num_used_rays": 0,
                "mean_ray_distance": np.nan,
                "max_ray_distance": np.nan,
            })
            continue

        triangulated_records.append({
            "landmark_id": int(landmark_id),
            "landmark_name": landmark_name,
            "triangulated": True,
            "x": float(point[0]),
            "y": float(point[1]),
            "z": float(point[2]),
            "num_initial_rays": info["num_initial_rays"],
            "num_used_rays": info["num_used_rays"],
            "mean_ray_distance": info["mean_ray_distance"],
            "max_ray_distance": info["max_ray_distance"],
        })

        used_mask = info["used_mask"]
        for local_idx, (_, row) in enumerate(group.iterrows()):
            origin = np.array([float(row["ray_origin_x"]), float(row["ray_origin_y"]), float(row["ray_origin_z"])])
            direction = np.array([float(row["ray_dir_x"]), float(row["ray_dir_y"]), float(row["ray_dir_z"])])
            distance = _point_to_line_distances(point, origin.reshape(1, 3), direction.reshape(1, 3))[0]
            observation_records.append({
                "landmark_id": int(landmark_id),
                "landmark_name": landmark_name,
                "view_name": row["view_name"],
                "used_for_triangulation": bool(used_mask[local_idx]),
                "ray_distance": float(distance),
                "x_px": float(row["x_px"]),
                "y_px": float(row["y_px"]),
            })

    triangulated_df = pd.DataFrame(triangulated_records)
    observations_df = pd.DataFrame(observation_records)
    triangulated_df.to_csv(triangulated_csv, index=False, encoding="utf-8")
    observations_df.to_csv(observations_csv, index=False, encoding="utf-8")

    n_tri = int(triangulated_df["triangulated"].sum()) if "triangulated" in triangulated_df else 0
    _log_call(log, f"[Posed Rigging] Triangulated OpenPose landmarks: {n_tri}/{len(triangulated_df)}")
    if n_tri < 2:
        raise RuntimeError("Multi-view reconstruction failed: fewer than 2 landmarks could be triangulated.")

    return triangulated_csv, rays_csv, observations_csv


def _find_points3d_csv(out_dir: Path, settings: dict | None = None) -> Path | None:
    settings = settings or {}
    candidates: list[Path] = []
    for key in (
        "csv_3d",
        "points3d_csv",
        "points3d_final_csv",
        "validated_points3d_csv",
    ):
        raw = settings.get(key)
        if raw:
            candidates.append(Path(str(raw)))
    candidates.extend([
        detections_mapped_3d_csv(out_dir, create=False),
        Path(out_dir) / "points3d_final.csv",
        Path(out_dir) / "points3d.csv",
        Path(out_dir) / "detections_mapped_3d.csv",
    ])
    for p in candidates:
        try:
            p = p.resolve()
            if p.exists() and p.is_file():
                return p
        except Exception:
            continue
    return None


def _canonical_sphere_index(value) -> int | None:
    text = str(value or "")
    match = re.search(r"(?i)sphere[^0-9]*0*([0-9]+)", text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _read_validated_points_array(csv_path: Path) -> np.ndarray:
    df = pd.read_csv(csv_path)
    if {"x3d", "y3d", "z3d"}.issubset(df.columns):
        cols = ["x3d", "y3d", "z3d"]
    elif {"X", "Y", "Z"}.issubset(df.columns):
        cols = ["X", "Y", "Z"]
    elif {"x", "y", "z"}.issubset(df.columns):
        cols = ["x", "y", "z"]
    else:
        raise RuntimeError(f"Could not identify 3D coordinate columns in: {csv_path}")
    pts = df[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    return pts


def _find_base_hand_obj(settings: dict | None, fallback_obj: Path | None = None) -> Path | None:
    settings = settings or {}
    for key in ("obj_uvb_path", "work_obj_path", "uv_obj_path", "base_obj", "obj_path"):
        raw = settings.get(key)
        if not raw:
            continue
        try:
            p = Path(str(raw)).resolve()
            if p.exists() and p.is_file() and p.name.lower() != "hand_with_points.obj":
                return p
        except Exception:
            continue
    if fallback_obj is not None:
        try:
            p = Path(fallback_obj).resolve()
            if p.exists() and p.is_file() and p.name.lower() != "hand_with_points.obj":
                return p
        except Exception:
            pass
    return None


def _prepare_posed_hand_with_points_obj(
    *,
    settings: dict | None,
    out_dir: Path,
    current_obj_path: Path,
    log=None,
) -> Path:
    """Regenerate hand_with_points.obj with the same script used by flat-hand.

    This avoids reusing stale OBJ files produced by previous experimental posed-hand
    patches. The detection CSV is the authoritative source for marker locations.
    """
    points_csv = _find_points3d_csv(out_dir, settings)
    base_obj = _find_base_hand_obj(settings, fallback_obj=current_obj_path)
    out_obj = hand_with_points_obj(out_dir)

    if points_csv is None or base_obj is None:
        _log_call(log, "[Posed Rigging] Using existing rigging OBJ; base mesh or 3D CSV was not available for regeneration.")
        return Path(current_obj_path)

    try:
        if out_obj.resolve() == base_obj.resolve():
            return Path(current_obj_path)
    except Exception:
        pass

    _log_call(log, f"[Posed Rigging] Regenerating hand_with_points.obj from validated 3D markers: {points_csv}")
    res = run_make_hand_with_points(
        base_obj=base_obj,
        points_csv=points_csv,
        out_obj=out_obj,
        sphere_radius=0.5,
        log=log,
    )
    if not res.ok or not res.out_obj:
        raise RuntimeError(f"Could not regenerate hand_with_points.obj for posed rigging: {res.message}")
    return Path(res.out_obj)


def align_labeled_csv_to_validated_marker_frame(
    *,
    labeled_csv: Path,
    out_dir: Path,
    settings: dict | None = None,
    log=None,
) -> Path:
    """Rewrite x/y/z in detections_labeled.csv to the validated OBJ marker frame.

    Blender may import the OBJ using its own axis convention, while the interactive
    editor and the measurements use the original OBJ/validated-CSV coordinate frame.
    The flat-hand pipeline already ends up with both frames matching; the posed-hand
    pipeline can differ because the armature is built in Blender from multiview
    OpenPose rays. We therefore use the original Sphere_### index and the validated
    3D CSV to compute the exact affine conversion from Blender-scene coordinates
    back to the marker coordinate frame used by the rest of the application.
    """
    labeled_csv = Path(labeled_csv)
    if not labeled_csv.exists():
        raise FileNotFoundError(labeled_csv)

    points_csv = _find_points3d_csv(Path(out_dir), settings)
    if points_csv is None:
        _log_call(log, "[Posed Rigging] Coordinate-frame alignment skipped: validated 3D CSV not found.")
        return labeled_csv

    df = pd.read_csv(labeled_csv)
    if df.empty or not {"x", "y", "z"}.issubset(df.columns):
        _log_call(log, "[Posed Rigging] Coordinate-frame alignment skipped: labeled CSV has no x/y/z columns.")
        return labeled_csv

    validated_points = _read_validated_points_array(points_csv)
    if validated_points.size == 0:
        _log_call(log, "[Posed Rigging] Coordinate-frame alignment skipped: validated 3D CSV is empty.")
        return labeled_csv

    source_cols = ["x_blender_scene", "y_blender_scene", "z_blender_scene"]
    if set(source_cols).issubset(df.columns):
        source_xyz_all = df[source_cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    else:
        source_xyz_all = df[["x", "y", "z"]].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        df["x_blender_scene"] = source_xyz_all[:, 0]
        df["y_blender_scene"] = source_xyz_all[:, 1]
        df["z_blender_scene"] = source_xyz_all[:, 2]

    src_fit = []
    dst_fit = []

    for row_idx, row in df.iterrows():
        sphere_idx = None
        if "source_sphere_name" in df.columns:
            sphere_idx = _canonical_sphere_index(row.get("source_sphere_name"))
        if sphere_idx is None:
            sphere_idx = _canonical_sphere_index(row.get("sphere_name"))
        if sphere_idx is None and row_idx < len(validated_points):
            sphere_idx = int(row_idx)
        if sphere_idx is None or sphere_idx < 0 or sphere_idx >= len(validated_points):
            continue

        src = source_xyz_all[int(row_idx)]
        dst = validated_points[int(sphere_idx)]
        if np.all(np.isfinite(src)) and np.all(np.isfinite(dst)):
            src_fit.append(src)
            dst_fit.append(dst)

    src_fit = np.asarray(src_fit, dtype=float)
    dst_fit = np.asarray(dst_fit, dtype=float)
    if len(src_fit) < 3:
        _log_call(log, f"[Posed Rigging] Coordinate-frame alignment skipped: not enough matched spheres ({len(src_fit)}).")
        return labeled_csv

    # Fit an affine transform. This is deliberately more general than a pure
    # rotation because OBJ import/export axis conversions can include sign flips.
    X = np.column_stack([src_fit, np.ones(len(src_fit), dtype=float)])
    try:
        affine, *_ = np.linalg.lstsq(X, dst_fit, rcond=None)  # shape: 4 x 3
    except Exception as exc:
        _log_call(log, f"[Posed Rigging] Coordinate-frame alignment skipped: affine fit failed ({exc}).")
        return labeled_csv

    before = float(np.nanmedian(np.linalg.norm(src_fit - dst_fit, axis=1)))
    after_fit = X @ affine
    after = float(np.nanmedian(np.linalg.norm(after_fit - dst_fit, axis=1)))

    # If the frames are already aligned, the fitted transform will be almost identity
    # and applying it is harmless. If the fit does not improve the median error,
    # keep the original values to avoid damaging a valid flat-style output.
    if np.isfinite(before) and np.isfinite(after) and after > max(before * 0.95, before - 1e-9):
        _log_call(log, f"[Posed Rigging] Coordinate-frame alignment not applied; median error did not improve ({before:.6g} -> {after:.6g}).")
        return labeled_csv

    all_src_h = np.column_stack([source_xyz_all, np.ones(len(source_xyz_all), dtype=float)])
    corrected = all_src_h @ affine
    finite_rows = np.all(np.isfinite(corrected), axis=1)
    df.loc[finite_rows, "x"] = corrected[finite_rows, 0]
    df.loc[finite_rows, "y"] = corrected[finite_rows, 1]
    df.loc[finite_rows, "z"] = corrected[finite_rows, 2]
    df["coordinate_frame"] = "validated_3d_marker_csv"

    df.to_csv(labeled_csv, index=False)
    _log_call(log, f"[Posed Rigging] Labeled CSV coordinates aligned to validated marker frame: {before:.6g} -> {after:.6g}")
    return labeled_csv


def create_posed_hand_rig_scene(
    *,
    settings: dict,
    obj_path: Path,
    landmarks_csv: Path,
    out_dir: Path,
    out_blend: Path | None = None,
    log=None,
) -> tuple[Path, Path, str, str]:
    persisted = load_settings() or {}
    merged_settings = dict(persisted)
    if isinstance(settings, dict):
        merged_settings.update(settings)

    blender_exe = resolve_blender_exe(merged_settings)
    if blender_exe is None:
        raise RuntimeError("Blender executable not found. Expected bundled path: <app>/blender/blender.exe")

    script = blender_script_path("create_posed_hand_rig_scene.py")
    if not script.exists():
        raise FileNotFoundError(f"Blender script does not exist: {script}")

    obj_path = Path(obj_path)
    landmarks_csv = Path(landmarks_csv)
    root_out_dir = Path(out_dir)
    root_out_dir.mkdir(parents=True, exist_ok=True)
    if out_blend is None:
        out_blend = hand_rigged_blend(root_out_dir)
    joints_csv = processing_dir(root_out_dir, "posed_rigging") / "hand_joints_3d.csv"
    texture_path = _settings_texture_path(merged_settings)
    points3d_csv = _find_points3d_csv(root_out_dir, merged_settings)

    cmd = [
        str(blender_exe),
        "--background",
        "--python", str(script),
        "--",
        "--obj", str(obj_path),
        "--landmarks_csv", str(landmarks_csv),
        "--out_blend", str(out_blend),
        "--joints_csv", str(joints_csv),
    ]
    if texture_path:
        cmd.extend(["--texture", str(texture_path)])
    if points3d_csv:
        cmd.extend(["--points3d_csv", str(points3d_csv)])

    _log_call(log, "[Posed Rigging] Building posed hand armature scene…")
    p = _run_subprocess(cmd, cwd=blender_exe.parent, log=log)
    if p.returncode != 0:
        raise RuntimeError(_subprocess_error_message("Blender posed rig scene generation failed", p))
    if not Path(out_blend).exists():
        raise FileNotFoundError(f"Blender finished but did not create: {out_blend}")
    return Path(out_blend), joints_csv, p.stdout or "", p.stderr or ""


def build_posed_hand_rig_from_multiview_openpose(
    *,
    settings: dict,
    obj_path: Path,
    out_dir: Path,
    resolution: int = 1024,
    num_views: int = 10,
    log=None,
) -> PosedRigBuildResult:
    try:
        out_dir = Path(out_dir)
        obj_path = Path(obj_path)
        if not obj_path.exists():
            return PosedRigBuildResult(False, message=f"OBJ does not exist: {obj_path}")

        # Always rebuild/refresh hand_with_points.obj for the posed-hand branch
        # using the same flat-hand Blender script and the latest validated 3D CSV.
        # This prevents stale test files from carrying an old axis conversion into
        # the rigging + labeling stage.
        obj_path = _prepare_posed_hand_with_points_obj(
            settings=settings,
            out_dir=out_dir,
            current_obj_path=obj_path,
            log=log,
        )

        posed_dir = processing_dir(out_dir, "posed_rigging")
        render_dir = posed_dir / "capture_axis_orbit_renders"
        openpose_dir = posed_dir / "openpose_landmarks"
        reconstruction_dir = posed_dir / "reconstructed_3d_landmarks_openpose"

        render_dir, metadata_path, render_stdout, render_stderr = render_posed_hand_multiview(
            settings=settings,
            obj_path=obj_path,
            out_dir=render_dir,
            resolution=int(resolution),
            num_views=int(num_views),
            log=log,
        )

        landmarks_df, summary_df, overlay_png = run_openpose_on_rendered_views(
            render_dir=render_dir,
            metadata_path=metadata_path,
            out_dir=openpose_dir,
            in_height=368,
            threshold=0.10,
            n_used=21,
            min_valid_landmarks_per_view=6,
            rotations_deg=(0, 90, 180, 270),
            log=log,
        )
        keypoints_csv = openpose_dir / "openpose_landmarks.csv"
        summary_csv = openpose_dir / "openpose_detection_summary.csv"

        triangulated_csv, _, _ = reconstruct_multiview_3d_landmarks(
            landmarks_df=landmarks_df,
            metadata_path=metadata_path,
            out_dir=reconstruction_dir,
            log=log,
        )

        out_blend, joints_csv, scene_stdout, scene_stderr = create_posed_hand_rig_scene(
            settings=settings,
            obj_path=obj_path,
            landmarks_csv=triangulated_csv,
            out_dir=out_dir,
            out_blend=hand_rigged_blend(out_dir),
            log=log,
        )

        return PosedRigBuildResult(
            ok=True,
            out_blend=out_blend,
            joints_csv=joints_csv,
            keypoints_csv=keypoints_csv,
            summary_csv=summary_csv,
            overlay_png=overlay_png,
            render_dir=render_dir,
            triangulated_csv=triangulated_csv,
            message="OK",
            stdout="\n".join(x for x in (render_stdout, scene_stdout) if x),
            stderr="\n".join(x for x in (render_stderr, scene_stderr) if x),
        )

    except Exception as exc:
        return PosedRigBuildResult(False, message=str(exc))
