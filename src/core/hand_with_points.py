from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .blender_scripts import blender_script_path
from .paths import resolve_blender_exe
from .settings import load_settings
from .subprocess_utils import run_hidden


@dataclass
class MakePointsResult:
    ok: bool
    out_obj: Path | None = None
    message: str = ""


def run_make_hand_with_points(
    base_obj: Path,
    points_csv: Path,
    out_obj: Path,
    *,
    sphere_radius: float = 0.5,
    log=None,
) -> MakePointsResult:
    """
    Generate hand_with_points.obj using Blender (hand + spheres at the 3D points).
    """
    base_obj = Path(base_obj)
    points_csv = Path(points_csv)
    out_obj = Path(out_obj)

    if not base_obj.exists():
        return MakePointsResult(False, None, f"Base OBJ does not exist: {base_obj}")
    if not points_csv.exists():
        return MakePointsResult(False, None, f"Points CSV does not exist: {points_csv}")

    s = load_settings() or {}
    blender_exe = resolve_blender_exe(s)
    if blender_exe is None:
        return MakePointsResult(
            False,
            None,
            "Blender executable not found. Expected bundled path: <app>/blender/blender.exe",
        )

    script_path = blender_script_path("make_hand_with_points.py")
    if not script_path.exists():
        return MakePointsResult(False, None, f"Script not found: {script_path}")

    cmd = [
        str(blender_exe),
        "--background",
        "--python", str(script_path),
        "--",
        "--obj", str(base_obj),
        "--csv", str(points_csv),
        "--out_obj", str(out_obj),
        "--sphere_radius", str(float(sphere_radius)),
    ]

    if log:
        log("[INFO] Generating hand_with_points.obj with Blender…")
        log(" ".join(cmd))

    try:
        p = run_hidden(cmd, capture_output=True, text=True, cwd=str(blender_exe.parent))
        if log and p.stdout:
            log(p.stdout.strip())
        if log and p.stderr:
            log(p.stderr.strip())

        if p.returncode != 0:
            return MakePointsResult(False, None, f"Blender exited with code {p.returncode}")

        if not out_obj.exists():
            return MakePointsResult(False, None, f"Blender finished but did not produce: {out_obj}")

        return MakePointsResult(True, out_obj, "OK")

    except Exception as e:
        return MakePointsResult(False, None, str(e))
