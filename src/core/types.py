from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class PipelineConfig:
    input_dir: Path
    out_dir: Path
    radius_px: float = 12.0
    radius_3d: float = 3.0
    mesh_path: Optional[Path] = None
    texture_path: Optional[Path] = None


@dataclass
class PipelineResult:
    ok: bool
    message: str = ""
    csv_2d: Optional[Path] = None
    csv_3d: Optional[Path] = None
