from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .blender_scripts import blender_script_path
from .paths import resolve_blender_exe
from .settings import load_settings
from .subprocess_utils import run_hidden


@dataclass
class RenderOpenPoseResult:
    ok: bool
    png_path: Path | None
    message: str
    stdout: str = ""
    stderr: str = ""


def render_hand_topview_for_openpose(
    obj_path: Path,
    out_dir: Path,
    resolution: int = 1024,
    out_name: str = "hand_openpose.png",
    log=None,
) -> RenderOpenPoseResult:
    """
    Launch Blender in background to render a top-view PNG of the OBJ.
    Uses the Blender executable configured in settings (blender_exe).
    """
    def _log(s: str):
        if log:
            log(s)

    obj_path = Path(obj_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not obj_path.exists():
        return RenderOpenPoseResult(False, None, f"OBJ does not exist: {obj_path}")

    # VERY IMPORTANT: it must be the UVB obj (and its .mtl and NewHandTexture.png must be accessible)
    out_png = out_dir / out_name

    # Locate Blender script inside assets
    blender_script = blender_script_path("render_hand_for_openpose.py")
    if not blender_script.exists():
        return RenderOpenPoseResult(False, None, f"Blender script not found: {blender_script}")

    # Read blender.exe from settings / bundled resources safely.
    # Do not use Path(""), because it resolves to the current directory.
    s = load_settings() or {}
    blender_exe = resolve_blender_exe(s)

    if blender_exe is None:
        return RenderOpenPoseResult(
            False,
            None,
            "Blender executable not found. Expected bundled path: <app>/blender/blender.exe",
        )

    cmd = [
        str(blender_exe),
        "-b",
        "--background",
        "--python",
        str(blender_script),
        "--",
        "--obj",
        str(obj_path),
        "--out",
        str(out_png),
        "--resolution",
        str(int(resolution)),
    ]

    _log("[INFO] Rendering TopView for OpenPose...")
    _log(" ".join(cmd))

    try:
        p = run_hidden(cmd, capture_output=True, text=True, cwd=str(blender_exe.parent))
        stdout = p.stdout or ""
        stderr = p.stderr or ""

        if stdout.strip():
            _log("=== BLENDER STDOUT ===")
            _log(stdout.strip())
        if stderr.strip():
            _log("=== BLENDER STDERR ===")
            _log(stderr.strip())

        if p.returncode != 0:
            return RenderOpenPoseResult(False, None, f"Blender exited with code {p.returncode}", stdout, stderr)

        if not out_png.exists():
            return RenderOpenPoseResult(False, None, f"Blender finished OK but did not create: {out_png}", stdout, stderr)

        _log(f"[OK] PNG generated: {out_png}")
        return RenderOpenPoseResult(True, out_png, "OK", stdout, stderr)

    except Exception as e:
        return RenderOpenPoseResult(False, None, str(e))
