from __future__ import annotations
from pathlib import Path
from typing import List

from .types import PipelineConfig


def validate_config(cfg: PipelineConfig) -> List[str]:
    errors: List[str] = []

    if not cfg.input_dir.exists():
        errors.append(f"input_dir no existe: {cfg.input_dir}")

    if not cfg.out_dir.exists():
        # No es error: podemos crearlo en io.py
        pass

    if cfg.mesh_path is not None and not cfg.mesh_path.exists():
        errors.append(f"mesh_path no existe: {cfg.mesh_path}")

    if cfg.texture_path is not None and not cfg.texture_path.exists():
        errors.append(f"texture_path no existe: {cfg.texture_path}")

    if cfg.radius_px <= 0:
        errors.append("radius_px debe ser > 0")

    if cfg.radius_3d <= 0:
        errors.append("radius_3d debe ser > 0")

    return errors
