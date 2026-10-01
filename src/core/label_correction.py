from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from datetime import datetime

from .blender_scripts import blender_script_path
from .paths import asset_path, normalize_blender_exe
from .subprocess_utils import run_hidden
from .worker_commands import internal_worker_command, internal_worker_cwd


@dataclass
class LabelCorrectionResult:
    ok: bool
    message: str = ""
    corrected_csv: Path | None = None
    corrected_blend: Path | None = None
    stdout: str = ""
    stderr: str = ""


def run_interactive_label_editor(
    detections_csv: Path,
    template_csv: Path,
    out_csv: Path,
    mesh_path: Path,
    label_scale_factor: float = 0.75,
    help_scale: float = 0.8,
    no_align_bbox: bool = True,
    log=print,
) -> LabelCorrectionResult:
    cmd = [
        *internal_worker_command("label-editor"),
        "--detections", str(detections_csv),
        "--template", str(template_csv),
        "--out", str(out_csv),
        "--mesh", str(mesh_path),
        "--label_scale_factor", str(label_scale_factor),
        "--help_scale", str(help_scale),
    ]
    if no_align_bbox:
        cmd.append("--no_align_bbox")
    colors_csv = asset_path("scripts", "pointsColor.csv")
    if colors_csv.exists():
        cmd += ["--colors_csv", str(colors_csv)]

    log("[LabelCorrection] Launching interactive editor...")
    log(" ".join(cmd))

    r = run_hidden(cmd, capture_output=True, text=True, cwd=str(internal_worker_cwd()))

    if r.stdout.strip():
        log(r.stdout)
    if r.stderr.strip():
        log(r.stderr)

    if r.returncode == 130:
        return LabelCorrectionResult(False, "Editor cancelled by user.", stdout=r.stdout, stderr=r.stderr)

    if r.returncode != 0:
        return LabelCorrectionResult(False, f"Editor exited with code {r.returncode}", stdout=r.stdout, stderr=r.stderr)

    if not out_csv.exists():
        return LabelCorrectionResult(False, f"Editor exited OK but did not generate: {out_csv}", stdout=r.stdout, stderr=r.stderr)

    return LabelCorrectionResult(True, "Editor completed", corrected_csv=out_csv, stdout=r.stdout, stderr=r.stderr)


def apply_labels_in_blender(
    blender_exe: str,
    labeled_blend: Path,
    corrected_csv: Path,
    out_blend: Path,
    log=print,
) -> LabelCorrectionResult:
    script = blender_script_path("apply_labels_from_csv.py")
    if not script.exists():
        return LabelCorrectionResult(False, f"apply_labels_from_csv.py does not exist at: {script}")

    resolved_blender = normalize_blender_exe(blender_exe)
    if resolved_blender is None:
        return LabelCorrectionResult(
            False,
            f"Invalid Blender executable path: {blender_exe}. Select blender.exe, not a folder.",
        )

    cmd = [
        str(resolved_blender),
        "--background",
        str(labeled_blend),
        "--python", str(script),
        "--",
        "--labels_csv", str(corrected_csv),
        "--save_blend", str(out_blend),
    ]

    log("[LabelCorrection] Launching Blender to apply labels...")
    log(" ".join(cmd))

    r = run_hidden(cmd, capture_output=True, text=True, cwd=str(resolved_blender.parent))

    if r.stdout.strip():
        log(r.stdout)
    if r.stderr.strip():
        log(r.stderr)

    if r.returncode != 0:
        return LabelCorrectionResult(False, f"Blender exited with code {r.returncode}", stdout=r.stdout, stderr=r.stderr)

    if not out_blend.exists():
        return LabelCorrectionResult(False, f"Blender exited OK but did not generate: {out_blend}", stdout=r.stdout, stderr=r.stderr)

    return LabelCorrectionResult(True, "Blender applied", corrected_blend=out_blend, stdout=r.stdout, stderr=r.stderr)


def persist_corrected_csv(
    out_dir: Path,
    base_labeled_csv: Path,
    corrected_csv: Path,
    log=print,
    *,
    create_backup: bool = False,
    backup_dir: Path | None = None,
) -> Path:
    """Persist the edited labels into the canonical detections_labeled.csv file.

    Backups are optional and, when requested, are stored outside the root project
    view so the output folder remains clean.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base_labeled_csv = Path(base_labeled_csv)
    corrected_csv = Path(corrected_csv)

    if create_backup and base_labeled_csv.exists():
        backup_root = Path(backup_dir) if backup_dir else (out_dir / "_processing" / "backups")
        backup_root.mkdir(parents=True, exist_ok=True)
        bak = backup_root / f"{base_labeled_csv.name}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(base_labeled_csv, bak)
        log(f"[LabelCorrection] Backup created: {bak}")

    shutil.copy2(corrected_csv, base_labeled_csv)
    log(f"[LabelCorrection] Overwritten: {base_labeled_csv} ← {corrected_csv}")
    return base_labeled_csv
