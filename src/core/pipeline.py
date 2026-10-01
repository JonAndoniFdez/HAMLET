from __future__ import annotations

from .types import PipelineConfig, PipelineResult
from .validators import validate_config
from .io import ensure_dir
from .output_cleanup import detections_all_csv, detections_mapped_3d_csv


def run_pipeline(cfg: PipelineConfig) -> PipelineResult:
    """
    Placeholder del pipeline real.
    Aquí conectarás tu flujo del notebook, pero por ahora devolvemos algo válido.
    """
    errors = validate_config(cfg)
    if errors:
        return PipelineResult(ok=False, message="; ".join(errors))

    ensure_dir(cfg.out_dir)

    # TODO: aquí irá tu algoritmo real
    return PipelineResult(
        ok=True,
        message="Pipeline ejecutado (placeholder).",
        csv_2d=detections_all_csv(cfg.out_dir),
        csv_3d=detections_mapped_3d_csv(cfg.out_dir),
    )
