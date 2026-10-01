from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

import cv2
import numpy as np
import pandas as pd

from .paths import app_root, bundled_openpose_dir


@dataclass
class OpenPoseHand2DResult:
    ok: bool
    message: str
    render_png: Path | None = None
    keypoints_csv: Path | None = None
    overlay_png: Path | None = None
    n_points: int = 0
    n_valid: int = 0


def _find_openpose_hand_models(openpose_dir: Path | None = None) -> tuple[Path, Path]:
    """Locate OpenPose hand Caffe models.

    Expected layout:
      <OPENPOSE_DIR>/models/hand/pose_deploy.prototxt
      <OPENPOSE_DIR>/models/hand/pose_iter_102000.caffemodel

    If `openpose_dir` is None, we try common locations.
    """

    candidates: list[Path] = []

    if openpose_dir:
        candidates.append(Path(openpose_dir))

    env_dir = os.environ.get("OPENPOSE_DIR")
    if env_dir:
        candidates.append(Path(env_dir))

    bundled = bundled_openpose_dir()
    if bundled:
        candidates.append(bundled)

    # Fallback guesses for development and manually copied release folders.
    candidates.append(app_root() / "openpose")
    candidates.append(Path.cwd() / "openpose")
    try:
        # .../src/core/openpose_hand.py -> parents[0]=core, [1]=src, [2]=<root>
        candidates.append(Path(__file__).resolve().parents[2] / "openpose")
    except Exception:
        pass

    checked: list[Path] = []
    for root in candidates:
        root = root.resolve()
        if root in checked:
            continue
        checked.append(root)
        hand_dir = root / "models" / "hand"
        proto = hand_dir / "pose_deploy.prototxt"
        model = hand_dir / "pose_iter_102000.caffemodel"
        if proto.exists() and model.exists():
            return proto, model

    # build helpful error
    lines = [
        "No se han encontrado los modelos de mano de OpenPose.",
        "Se esperaba encontrar:",
        "  <OPENPOSE_DIR>/models/hand/pose_deploy.prototxt",
        "  <OPENPOSE_DIR>/models/hand/pose_iter_102000.caffemodel",
        "\nRutas comprobadas:",
        *[f"  - {p}" for p in checked],
        "\nSolución:",
        "  • Copia la carpeta 'openpose' junto al proyecto, o",
        "  • Define la variable de entorno OPENPOSE_DIR apuntando a tu instalación de OpenPose.",
    ]
    raise FileNotFoundError("\n".join(lines))


def run_openpose_hand_2d(
    render_png: Path,
    out_dir: Path,
    openpose_dir: Path | None = None,
    in_height: int = 368,
    threshold: float = 0.1,
    n_used: int = 21,
    log=None,
) -> OpenPoseHand2DResult:
    """Run OpenPose hand keypoint model (Caffe) through OpenCV DNN.

    Produces:
      - openpose_hand_keypoints_2d.csv
      - hand_openpose_keypoints_overlay.png

    Returns OpenPoseHand2DResult.
    """

    def _log(msg: str):
        if log:
            try:
                log(msg)
            except Exception:
                pass

    render_png = Path(render_png)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not render_png.exists():
        return OpenPoseHand2DResult(False, f"No existe la imagen para OpenPose: {render_png}")

    try:
        proto, model = _find_openpose_hand_models(openpose_dir)
        _log(f"[OpenPose] Prototxt:  {proto}")
        _log(f"[OpenPose] Caffemodel:{model}")

        img_bgr = cv2.imread(str(render_png), cv2.IMREAD_COLOR)
        if img_bgr is None:
            return OpenPoseHand2DResult(False, f"No se pudo leer la imagen: {render_png}", render_png=render_png)

        h, w = img_bgr.shape[:2]
        in_width = int((in_height / float(h)) * w)

        _log(f"[OpenPose] Imagen: {w}x{h} | input: {in_width}x{in_height}")

        net = cv2.dnn.readNetFromCaffe(str(proto), str(model))

        blob = cv2.dnn.blobFromImage(
            img_bgr,
            scalefactor=1.0 / 255.0,
            size=(in_width, in_height),
            mean=(0, 0, 0),
            swapRB=False,
            crop=False,
        )
        net.setInput(blob)
        output = net.forward()  # (1, nPoints, outH, outW)

        n_points = int(output.shape[1])
        out_h = int(output.shape[2])
        out_w = int(output.shape[3])
        _log(f"[OpenPose] Salida: nPoints={n_points} out={out_w}x{out_h}")

        points = []
        for i in range(n_points):
            heatmap = output[0, i, :, :]
            _, conf, _, pt = cv2.minMaxLoc(heatmap)
            x = (w * pt[0]) / float(out_w)
            y = (h * pt[1]) / float(out_h)
            if conf > threshold:
                points.append((x, y, float(conf)))
            else:
                points.append((np.nan, np.nan, float(conf)))

        pts = np.asarray(points, dtype=np.float32)
        n_used_eff = min(int(n_used), pts.shape[0])
        pts = pts[:n_used_eff, :]

        xy = pts[:, :2]
        conf = pts[:, 2]
        n_valid = int(np.isfinite(xy).all(axis=1).sum())

        csv_path = out_dir / "openpose_hand_keypoints_2d.csv"
        df = pd.DataFrame(xy, columns=["x", "y"])
        df["conf"] = conf
        df.to_csv(csv_path, index=False, encoding="utf-8", na_rep="nan")

        overlay_path = out_dir / "hand_openpose_keypoints_overlay.png"
        overlay = img_bgr.copy()
        for (x, y) in xy:
            if np.isfinite(x) and np.isfinite(y):
                cv2.circle(overlay, (int(x), int(y)), 4, (0, 255, 255), -1)
        cv2.imwrite(str(overlay_path), overlay)

        msg = f"[OK] OpenPose 2D: guardado CSV={csv_path.name} | overlay={overlay_path.name} | valid={n_valid}/{len(df)}"
        _log(msg)
        return OpenPoseHand2DResult(
            ok=True,
            message=msg,
            render_png=render_png,
            keypoints_csv=csv_path,
            overlay_png=overlay_path,
            n_points=n_used_eff,
            n_valid=n_valid,
        )

    except Exception as e:
        return OpenPoseHand2DResult(False, f"Error ejecutando OpenPose: {e}", render_png=render_png)
