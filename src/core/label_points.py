from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from ..core.settings import load_settings
from .blender_scripts import blender_script_path
from .paths import asset_path, resolve_blender_exe
from .output_cleanup import detections_labeled_csv, hand_rigged_labeled_blend
from .subprocess_utils import run_hidden


@dataclass
class LabelPointsResult:
    ok: bool
    message: str = ""
    out_csv: Path | None = None
    out_blend: Path | None = None
    stdout: str = ""
    stderr: str = ""


def label_points_from_template(
    settings: dict,
    blend_path: Path,
    out_dir: Path,
    marker_prefix: str = "Sphere_",
    max_dist: float | None = None,
    template_csv: Path | None = None,
    save_blend: bool = True,
    log=print,
) -> LabelPointsResult:
    blend_path = Path(blend_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not blend_path.exists():
        return LabelPointsResult(False, f"The .blend does not exist: {blend_path}")


    persisted = load_settings() or {}
    merged_settings = dict(persisted)
    if isinstance(settings, dict):
        merged_settings.update(settings)

    blender_exe = resolve_blender_exe(merged_settings)
    if blender_exe is None:
        return LabelPointsResult(
            False,
            "Blender executable not found. Expected bundled path: <app>/blender/blender.exe",
        )

    script_path = blender_script_path("label_points_from_template.py")
    if not script_path.exists():
        return LabelPointsResult(False, f"Script does not exist: {script_path}")

    if template_csv is None:
        template_csv = asset_path("data", "markers_template.csv")

    if not template_csv.exists():
        return LabelPointsResult(False, f"Template CSV does not exist: {template_csv}")

    out_csv = detections_labeled_csv(out_dir)
    out_blend = hand_rigged_labeled_blend(out_dir) if save_blend else None

    cmd = [
        str(blender_exe),
        "--background",
        str(blend_path),
        "--python", str(script_path),
        "--",
        "--template", str(template_csv),
        "--out", str(out_csv),
        "--marker_prefix", marker_prefix,
    ]

    if max_dist is not None:
        cmd += ["--max_dist", str(float(max_dist))]

    if out_blend is not None:
        cmd += ["--save_blend", str(out_blend)]

    log("[Label] Launching Blender to label...")
    log(" ".join(cmd))

    r = run_hidden(cmd, capture_output=True, text=True, cwd=str(blender_exe.parent))

    stdout = r.stdout or ""
    stderr = r.stderr or ""
    if stdout.strip():
        log(stdout)
    if stderr.strip():
        log(stderr)

    if r.returncode != 0:
        return LabelPointsResult(
            ok=False,
            message=f"Blender exited with code {r.returncode}",
            stdout=stdout,
            stderr=stderr,
        )

    if not out_csv.exists():
        return LabelPointsResult(False, f"Blender exited OK but did not generate: {out_csv}", stdout=stdout, stderr=stderr)

    return LabelPointsResult(
        ok=True,
        message="Labeling completed",
        out_csv=out_csv,
        out_blend=out_blend if out_blend and out_blend.exists() else None,
        stdout=stdout,
        stderr=stderr,
    )
