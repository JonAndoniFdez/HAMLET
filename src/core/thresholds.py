from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple
import numpy as np
import cv2


# Presets (HSV OpenCV: H 0..179, S/V 0..255)
BLUE_RANGES = [
    ((90, 30, 20), (160, 255, 200)),   # azul clásico
    ((125, 25, 25), (155, 210, 180)),  # azul-violeta
]


@dataclass
class Pick:
    hsv_center: List[int]          # [H,S,V]
    px: int
    py: int
    parts_added: int               # 1 o 2 según wrap


def apply_preproc_bgr(img_bgr: np.ndarray) -> np.ndarray:
    """
    Sustituye esto por tu apply_preproc real si quieres.
    Aquí dejo algo suave y estable: ligera corrección + blur.
    """
    # Convertir a LAB y ecualizar L (suave) puede ayudar, pero lo dejamos simple:
    blurred = cv2.GaussianBlur(img_bgr, (3, 3), 0)
    return blurred


def bgr_to_hsv(img_bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)


def hsv_wrap_ranges(center_hsv: np.ndarray, h_tol: int, s_tol: int, v_tol: int):
    """
    Devuelve 1 o 2 rangos (lo, hi) manejando wrap del canal H (0..179).
    """
    Hc, Sc, Vc = int(center_hsv[0]), int(center_hsv[1]), int(center_hsv[2])
    lo = np.array([Hc - h_tol, max(0, Sc - s_tol), max(0, Vc - v_tol)], dtype=np.int32)
    hi = np.array([Hc + h_tol, min(255, Sc + s_tol), min(255, Vc + v_tol)], dtype=np.int32)

    parts = []
    lH, hH = int(lo[0]), int(hi[0])

    if lH < 0:
        parts.append((np.array([0, lo[1], lo[2]]), np.array([hi[0] % 180, hi[1], hi[2]])))
        parts.append((np.array([lH % 180, lo[1], lo[2]]), np.array([179, hi[1], hi[2]])))
    elif hH > 179:
        parts.append((np.array([0, lo[1], lo[2]]), np.array([hH % 180, hi[1], hi[2]])))
        parts.append((np.array([lH % 180, lo[1], lo[2]]), np.array([179, hi[1], hi[2]])))
    else:
        parts.append((lo, hi))

    return parts


def median_hsv_patch(img_hsv: np.ndarray, x: int, y: int, radius: int) -> np.ndarray:
    """
    Mediana HSV en un parche alrededor del click.
    """
    H, W = img_hsv.shape[:2]
    x = int(np.clip(x, 0, W - 1))
    y = int(np.clip(y, 0, H - 1))

    x0 = max(0, x - radius)
    x1 = min(W, x + radius + 1)
    y0 = max(0, y - radius)
    y1 = min(H, y + radius + 1)

    patch = img_hsv[y0:y1, x0:x1].reshape(-1, 3).astype(np.int32)
    center = np.median(patch, axis=0).astype(np.int32)
    return center
