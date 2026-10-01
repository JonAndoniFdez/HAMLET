from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import csv
import json
import re

from .output_cleanup import (
    detections_dir,
    detections_labeled_csv,
    hand_with_points_obj,
    processing_dir,
    results_dir as output_results_dir,
    scenes_dir,
    selected_ops_csv,
    threshold_preview_dir,
)


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


@dataclass
class OpenProjectState:
    out_dir: Path
    results_dir: Path | None
    texture_path: Path | None
    obj_path: Path | None
    hand_with_points_obj: Path | None
    target_json: Path | None
    measurement_mode: str
    csv_2d: Path | None
    csv_3d: Path | None
    labeled_csv: Path | None
    labeled_blend: Path | None
    selected_ops_csv: Path | None
    detailed_measures_xlsx: Path | None
    points_xyz_xlsx: Path | None
    missing_required: list[str]
    stage_errors: dict[str, list[str]] = field(default_factory=dict)

    @property
    def can_edit_markers(self) -> bool:
        return not self.stage_errors.get("markers")

    @property
    def can_edit_labels(self) -> bool:
        return not self.stage_errors.get("labels")

    @property
    def can_edit_measures(self) -> bool:
        return not self.stage_errors.get("measures")

    @property
    def is_compatible(self) -> bool:
        """A project is compatible when at least one recoverable workflow stage can be reopened."""
        return self.can_edit_markers or self.can_edit_labels or self.can_edit_measures

    @property
    def available_actions(self) -> list[str]:
        actions: list[str] = []
        if self.can_edit_markers:
            actions.append("markers/detections")
        if self.can_edit_labels:
            actions.append("manual labels")
        if self.can_edit_measures:
            actions.append("measures")
        return actions


def _first_existing(paths: Iterable[Path | None]) -> Path | None:
    for p in paths:
        if p is not None and p.exists() and p.is_file():
            return p.resolve()
    return None


def _search_dirs(out_dir: Path, results_dir: Path | None) -> list[Path]:
    dirs = [
        processing_dir(out_dir, create=False),
        detections_dir(out_dir, create=False),
        scenes_dir(out_dir, create=False),
        threshold_preview_dir(out_dir, create=False),
        out_dir,
    ]
    if results_dir is not None:
        dirs.append(results_dir)
    # Preserve order while removing duplicates.
    unique: list[Path] = []
    for d in dirs:
        d = d.resolve()
        if d not in unique and d.exists() and d.is_dir():
            unique.append(d)
    return unique


def _load_json(path: Path | None) -> dict:
    if path is None or not path.exists() or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _metadata_dicts(out_dir: Path, results_dir: Path | None, names: Iterable[str]) -> list[dict]:
    data: list[dict] = []
    for folder in _search_dirs(out_dir, results_dir):
        for name in names:
            item = _load_json(folder / name)
            if item:
                data.append(item)
    return data


def _find_measurement_mode(out_dir: Path, results_dir: Path | None) -> str:
    return "flat_hand"


def _resolve_candidate(value, base_dirs: Iterable[Path]) -> Path | None:
    """Resolve a path stored in old/new project metadata.

    Supports absolute paths, relative paths and filename-only paths looked up in the
    output/results folders. This keeps old projects openable even if they were moved.
    """
    if not value:
        return None
    try:
        raw = Path(str(value).strip())
    except Exception:
        return None

    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        for base in base_dirs:
            candidates.append(base / raw)

    # When the metadata stores an absolute path that is no longer valid, the file
    # may still exist inside the selected output folder with the same filename.
    if raw.name:
        for base in base_dirs:
            candidates.append(base / raw.name)

    return _first_existing(candidates)


def _candidate_paths_from_metadata(
    out_dir: Path,
    results_dir: Path | None,
    keys: Iterable[str],
    metadata_files: Iterable[str],
) -> list[Path]:
    base_dirs = _search_dirs(out_dir, results_dir)
    candidates: list[Path] = []
    for folder in base_dirs:
        for meta_name in metadata_files:
            data = _load_json(folder / meta_name)
            for key in keys:
                p = _resolve_candidate(data.get(key), base_dirs)
                if p is not None:
                    candidates.append(p)
    return candidates


def _read_mtllibs(obj_path: Path) -> list[Path]:
    mtls: list[Path] = []
    try:
        with obj_path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.lower().startswith("mtllib "):
                    rest = line.split(None, 1)[1].strip()
                    if rest:
                        p = (obj_path.parent / rest).resolve()
                        if p.exists() and p.is_file():
                            mtls.append(p)
    except Exception:
        pass
    return mtls


def _textures_from_mtl(mtl_path: Path, base_dirs: Iterable[Path]) -> list[Path]:
    textures: list[Path] = []
    try:
        with mtl_path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Handles: map_Kd texture.png and simple options before the file.
                if line.lower().startswith("map_kd "):
                    rest = line.split(None, 1)[1].strip()
                    if not rest:
                        continue
                    parts = rest.split()
                    # Usually the texture file is the last token.
                    tex_token = parts[-1]
                    candidates = [mtl_path.parent / tex_token]
                    for base in base_dirs:
                        candidates.append(base / tex_token)
                        candidates.append(base / Path(tex_token).name)
                    p = _first_existing(candidates)
                    if p is not None:
                        textures.append(p)
    except Exception:
        pass
    return textures


def _obj_has_geometry_and_uv(path: Path | None) -> bool:
    if path is None or not path.exists() or path.suffix.lower() != ".obj":
        return False
    has_v = has_vt = has_f = False
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("v "):
                    has_v = True
                elif line.startswith("vt "):
                    has_vt = True
                elif line.startswith("f "):
                    has_f = True
                if has_v and has_vt and has_f:
                    return True
    except Exception:
        return False
    return False


def _find_obj(out_dir: Path, results_dir: Path | None) -> Path | None:
    base_dirs = _search_dirs(out_dir, results_dir)
    metadata_candidates = _candidate_paths_from_metadata(
        out_dir,
        results_dir,
        keys=[
            "obj_path",
            "work_obj_path",
            "obj_uvb_path",
            "uv_obj_path",
            "mesh_path",
            "obj",
        ],
        metadata_files=[
            "project_context.json",
            "target_ranges.json",
            "NewHandTexture.meta.json",
        ],
    )

    named_candidates: list[Path] = []
    for d in base_dirs:
        named_candidates.extend(sorted(d.glob("*_UVB.obj")))
        named_candidates.extend([
            d / "hand.obj",
            d / "model.obj",
        ])
        # Prefer any user/source mesh before the generated helper mesh.
        named_candidates.extend(sorted([
            p for p in d.glob("*.obj")
            if p.is_file() and p.name.lower() != "hand_with_points.obj"
        ]))
        named_candidates.append(d / "hand_with_points.obj")

    seen: set[Path] = set()
    for p in [*metadata_candidates, *named_candidates]:
        try:
            p = p.resolve()
        except Exception:
            continue
        if p in seen:
            continue
        seen.add(p)
        if p.exists() and p.is_file() and p.suffix.lower() == ".obj":
            return p
    return None


def _find_hand_with_points_obj(out_dir: Path, results_dir: Path | None) -> Path | None:
    return _first_existing([
        hand_with_points_obj(out_dir, create=False),
        out_dir / "hand_with_points.obj",
        *( [results_dir / "hand_with_points.obj"] if results_dir else [] ),
    ])


def _find_target_json(out_dir: Path, results_dir: Path | None) -> Path | None:
    return _first_existing([
        processing_dir(out_dir, create=False) / "target_ranges.json",
        out_dir / "target_ranges.json",
        *( [results_dir / "target_ranges.json"] if results_dir else [] ),
    ])


def _find_texture(out_dir: Path, results_dir: Path | None, obj_path: Path | None) -> Path | None:
    base_dirs = _search_dirs(out_dir, results_dir)

    metadata_candidates = _candidate_paths_from_metadata(
        out_dir,
        results_dir,
        keys=[
            "texture_path",
            "texture_path_work",
            "work_texture_path",
            "threshold_texture_path",
            "rebaked_texture_path",
            "source_texture",
            "original_texture",
            "manual_preview_texture",
            "texture",
        ],
        metadata_files=[
            "project_context.json",
            "target_ranges.json",
            "NewHandTexture.meta.json",
        ],
    )

    mtl_candidates: list[Path] = []
    if obj_path is not None and obj_path.exists():
        for mtl in _read_mtllibs(obj_path):
            mtl_candidates.extend(_textures_from_mtl(mtl, base_dirs))

    named_candidates: list[Path] = []
    preferred_names = [
        "NewHandTexture.png",
        "original_texture.png",
        "OriginalTexture.png",
        "texture.png",
        "hand_texture.png",
    ]
    for d in base_dirs:
        for name in preferred_names:
            named_candidates.append(d / name)
        named_candidates.extend(sorted([
            p for p in d.iterdir() if p.is_file()
            and p.suffix.lower() in _IMAGE_SUFFIXES
            and "texture" in p.stem.lower()
            and not re.search(r"overlay|openpose|render|mask|preview", p.stem.lower())
        ]))

    seen: set[Path] = set()
    for p in [*metadata_candidates, *mtl_candidates, *named_candidates]:
        try:
            p = p.resolve()
        except Exception:
            continue
        if p in seen:
            continue
        seen.add(p)
        if p.exists() and p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES:
            return p
    return None


def _find_csv(out_dir: Path, results_dir: Path | None, name: str) -> Path | None:
    candidates: list[Path | None] = []
    if name == "detections_labeled.csv":
        candidates.append(detections_labeled_csv(out_dir, create=False))
    elif name in {"detections_all.csv", "detections_mapped_3d.csv"}:
        candidates.append(detections_dir(out_dir, create=False) / name)
    elif name == "LandmarksOperations_selected.csv":
        candidates.append(selected_ops_csv(out_dir, create=False))

    candidates.extend([
        processing_dir(out_dir, create=False) / name,
        out_dir / name,
        *( [results_dir / name] if results_dir else [] ),
    ])
    return _first_existing(candidates)


def _find_blend(out_dir: Path, results_dir: Path | None) -> Path | None:
    candidates: list[Path] = []
    names = [
        "hand_rigged_labeled_manual.blend",
        "hand_rigged_labeled.blend",
        "hand_rigged.blend",
        "hand_rigged_labeled_final.blend",
    ]
    for d in _search_dirs(out_dir, results_dir):
        candidates.extend([d / name for name in names])
        candidates.extend(sorted(d.glob("*.blend")))
    return _first_existing(candidates)


def _csv_header(path: Path | None) -> list[str]:
    if path is None or not path.exists() or not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            return [str(c).strip() for c in next(reader, [])]
    except Exception:
        try:
            with path.open("r", encoding="latin1", newline="") as f:
                reader = csv.reader(f)
                return [str(c).strip() for c in next(reader, [])]
        except Exception:
            return []


def _has_columns(path: Path | None, columns: Iterable[str]) -> bool:
    hdr = set(_csv_header(path))
    return all(c in hdr for c in columns)


def _has_any_xyz(path: Path | None) -> bool:
    hdr = set(_csv_header(path))
    xyz_sets = [
        {"x3d", "y3d", "z3d"},
        {"X", "Y", "Z"},
        {"x", "y", "z"},
        {"pos_x", "pos_y", "pos_z"},
        {"POS_X", "POS_Y", "POS_Z"},
    ]
    return any(cols.issubset(hdr) for cols in xyz_sets)


def _has_label_column(path: Path | None) -> bool:
    hdr = set(_csv_header(path))
    return any(c in hdr for c in ("label", "Label", "LABEL", "name", "Name"))


def _stage_errors_markers(texture_path: Path | None, obj_path: Path | None, csv_2d: Path | None, csv_3d: Path | None) -> list[str]:
    errors: list[str] = []
    if texture_path is None:
        errors.append("missing a valid texture image")
    if obj_path is None:
        errors.append("missing the project OBJ mesh")
    elif not _obj_has_geometry_and_uv(obj_path):
        errors.append("the OBJ mesh does not contain usable geometry/UV coordinates")
    if csv_2d is None:
        errors.append("missing detections_all.csv")
    elif not _has_columns(csv_2d, ["pixel_x", "pixel_y"]):
        errors.append("detections_all.csv does not contain pixel_x/pixel_y columns")
    if csv_3d is None:
        errors.append("missing detections_mapped_3d.csv")
    elif not _has_any_xyz(csv_3d):
        errors.append("detections_mapped_3d.csv does not contain valid XYZ columns")
    return errors


def _stage_errors_labels(obj_path: Path | None, labeled_csv: Path | None, labeled_blend: Path | None) -> list[str]:
    errors: list[str] = []
    if obj_path is None:
        errors.append("missing the project OBJ mesh")
    if labeled_csv is None:
        errors.append("missing detections_labeled.csv")
    else:
        if not _has_label_column(labeled_csv):
            errors.append("detections_labeled.csv does not contain a label column")
        if not _has_any_xyz(labeled_csv):
            errors.append("detections_labeled.csv does not contain valid XYZ columns")
    if labeled_blend is None:
        errors.append("missing a rigged/labeled .blend file")
    return errors


def _stage_errors_measures(labeled_csv: Path | None) -> list[str]:
    errors: list[str] = []
    if labeled_csv is None:
        errors.append("missing detections_labeled.csv")
    else:
        if not _has_label_column(labeled_csv):
            errors.append("detections_labeled.csv does not contain a label column")
        if not _has_any_xyz(labeled_csv):
            errors.append("detections_labeled.csv does not contain valid XYZ columns")
    return errors


def inspect_output_project(out_dir: str | Path) -> OpenProjectState:
    out_dir = Path(out_dir).resolve()

    missing_required: list[str] = []
    if not out_dir.exists():
        missing_required.append("Selected output folder does not exist.")
    elif not out_dir.is_dir():
        missing_required.append("Selected path is not a folder.")

    results_dir = output_results_dir(out_dir, create=False)
    if not results_dir.exists() or not results_dir.is_dir():
        results_dir = None

    obj_path = _find_obj(out_dir, results_dir) if not missing_required else None
    texture_path = _find_texture(out_dir, results_dir, obj_path) if not missing_required else None
    hand_with_points_obj = _find_hand_with_points_obj(out_dir, results_dir) if not missing_required else None
    target_json = _find_target_json(out_dir, results_dir) if not missing_required else None
    measurement_mode = _find_measurement_mode(out_dir, results_dir) if not missing_required else "flat_hand"

    csv_2d = _find_csv(out_dir, results_dir, "detections_all.csv") if not missing_required else None
    csv_3d = _find_csv(out_dir, results_dir, "detections_mapped_3d.csv") if not missing_required else None
    labeled_csv = _find_csv(out_dir, results_dir, "detections_labeled.csv") if not missing_required else None
    selected_ops_csv = _find_csv(out_dir, results_dir, "LandmarksOperations_selected.csv") if not missing_required else None
    detailed_measures_xlsx = _find_csv(out_dir, results_dir, "hand_measures_detailed.xlsx") if not missing_required else None
    points_xyz_xlsx = _find_csv(out_dir, results_dir, "points_xyz.xlsx") if not missing_required else None
    labeled_blend = _find_blend(out_dir, results_dir) if not missing_required else None

    if missing_required:
        stage_errors = {
            "markers": missing_required[:],
            "labels": missing_required[:],
            "measures": missing_required[:],
        }
    else:
        stage_errors = {
            "markers": _stage_errors_markers(texture_path, obj_path, csv_2d, csv_3d),
            "labels": _stage_errors_labels(obj_path, labeled_csv, labeled_blend),
            "measures": _stage_errors_measures(labeled_csv),
        }
        if all(stage_errors.values()):
            missing_required.append(
                "The folder does not contain any complete recoverable workflow stage."
            )

    return OpenProjectState(
        out_dir=out_dir,
        results_dir=results_dir,
        texture_path=texture_path,
        obj_path=obj_path,
        hand_with_points_obj=hand_with_points_obj,
        target_json=target_json,
        measurement_mode=measurement_mode,
        csv_2d=csv_2d,
        csv_3d=csv_3d,
        labeled_csv=labeled_csv,
        labeled_blend=labeled_blend,
        selected_ops_csv=selected_ops_csv,
        detailed_measures_xlsx=detailed_measures_xlsx,
        points_xyz_xlsx=points_xyz_xlsx,
        missing_required=missing_required,
        stage_errors=stage_errors,
    )
