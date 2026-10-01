from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.settings import load_settings

from .blender_scripts import blender_script_path
from .paths import resolve_blender_exe
from .output_cleanup import hand_rigged_blend
from .subprocess_utils import run_hidden


@dataclass
class RigBuildResult:
    ok: bool
    out_blend: Path | None = None
    joints_csv: Path | None = None
    message: str = ""


def build_armature_from_openpose(
    *,
    settings: dict,
    obj_path: Path,
    csv_2d_path: Path,
    out_dir: Path,
    resolution: int = 1024,
    out_blend: Path | None = None,
    log=print,
    ) -> RigBuildResult:
    try:
            
        persisted = load_settings() or {}
        merged_settings = dict(persisted)
        if isinstance(settings, dict):
            merged_settings.update(settings)

        blender_exe = resolve_blender_exe(merged_settings)
        if blender_exe is None:
            return RigBuildResult(
                False,
                message="Blender executable not found. Expected bundled path: <app>/blender/blender.exe",
            )

        script = blender_script_path("build_hand_armature_from_openpose.py")

        obj_path = Path(obj_path)
        csv_2d_path = Path(csv_2d_path)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if out_blend is None:
            out_blend = hand_rigged_blend(out_dir)

        if not obj_path.exists():
            return RigBuildResult(False, message=f"OBJ does not exist: {obj_path}")
        if not csv_2d_path.exists():
            return RigBuildResult(False, message=f"2D OpenPose CSV does not exist: {csv_2d_path}")
        if not script.exists():
            return RigBuildResult(False, message=f"Blender script does not exist: {script}")

        cmd = [
            str(blender_exe),
            "--background",
            "--python", str(script),
            "--",
            "--obj", str(obj_path),
            "--csv", str(csv_2d_path),
            "--resolution", str(int(resolution)),
            "--out_blend", str(out_blend),
        ]

        log("[Rigging] Launching Blender (armature):")
        log(" ".join(cmd))

        p = run_hidden(cmd, capture_output=True, text=True, cwd=str(blender_exe.parent))
        if p.stdout:
            log(p.stdout)
        if p.stderr:
            log(p.stderr)

        if p.returncode != 0:
            return RigBuildResult(False, message=f"Blender exited with code {p.returncode}")

        # The Blender script saves hand_joints_3d.csv next to the 2D keypoints CSV.
        # This allows OpenPose intermediate files to live in a private processing
        # folder while the final rigged .blend remains in the clean project root.
        joints_csv = csv_2d_path.parent / "hand_joints_3d.csv"
        return RigBuildResult(True, out_blend=out_blend, joints_csv=joints_csv, message="OK")

    except Exception as e:
        return RigBuildResult(False, message=str(e))
