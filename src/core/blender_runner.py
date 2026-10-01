from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from .subprocess_utils import popen_hidden


@dataclass
class BlenderRebakeResult:
    outdir: Path
    out_obj: Path
    out_png: Path
    returncode: int


def build_blender_cmd(
    blender_exe: Path,
    rebake_script: Path,
    obj_in: Path,
    outdir: Path,
    size: int = 4096,
    margin: int = 16,
    uvb_name: str = "UVMap_2",
) -> list[str]:
    return [
        str(blender_exe),
        "-b",
        "-P",
        str(rebake_script),
        "--",
        "--obj",
        str(obj_in),
        "--outdir",
        str(outdir),
        "--size",
        str(size),
        "--margin",
        str(margin),
        "--uvb",
        uvb_name,
    ]


def build_blender_threshold_preview_cmd(
    blender_exe: Path,
    preview_script: Path,
    obj_in: Path,
    texture_in: Path,
    outdir: Path,
    size: int = 2048,
    margin: int = 8,
    uvb_name: str = "UVMap_2",
) -> list[str]:
    return [
        str(blender_exe),
        "-b",
        "-P",
        str(preview_script),
        "--",
        "--obj",
        str(obj_in),
        "--texture",
        str(texture_in),
        "--outdir",
        str(outdir),
        "--size",
        str(size),
        "--margin",
        str(margin),
        "--uvb",
        uvb_name,
    ]


def expected_threshold_preview_output(outdir: Path) -> Path:
    return outdir / "NewHandTexture.png"


def validate_blender_cmd(cmd: list[str]) -> Path:
    """Validate the executable part of a Blender command before launching it."""
    if not cmd:
        raise RuntimeError("Empty Blender command.")

    blender_exe = Path(cmd[0])

    if not blender_exe.exists():
        raise FileNotFoundError(f"Blender executable does not exist: {blender_exe}")

    if not blender_exe.is_file():
        raise RuntimeError(
            f"Invalid Blender executable path: {blender_exe}\n"
            "The path exists but it is not a file. "
            "Check that the application is pointing to blender.exe, not to a folder."
        )

    return blender_exe.resolve()


def run_blender_rebake_stream(
    cmd: list[str],
):
    """
    Lanza Blender y devuelve un Popen con stdout combinado (stdout+stderr).
    Se consume fuera, línea a línea, para mostrar log en la GUI.
    """
    blender_exe = validate_blender_cmd(cmd)

    return popen_hidden(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        cwd=str(blender_exe.parent),
    )


def expected_outputs(obj_in: Path, outdir: Path) -> tuple[Path, Path]:
    stem = obj_in.stem
    out_obj = outdir / f"{stem}_UVB.obj"
    out_png = outdir / "NewHandTexture.png"
    return out_obj, out_png
