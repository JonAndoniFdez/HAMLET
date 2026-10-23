"""Check source completeness before building; never compile an executable."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

from source_manifest import application_source_files


ROOT = Path(__file__).resolve().parents[1]


def module_exists(root: Path, module: str) -> bool:
    path = root.joinpath(*module.split("."))
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()


def check_source(root: Path) -> dict:
    root = Path(root).resolve()
    files = application_source_files(root)
    included = set(files)
    python_files = [p for p in files if p.suffix == ".py" and p.parts[len(root.parts)] != "third_party_licenses"]
    python_files.append(root / "HAMLET.spec")
    errors = []
    references = set()
    for path in python_files:
        relative = path.relative_to(root)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(relative))
            compile(tree, str(relative), "exec")
        except (SyntaxError, UnicodeError) as error:
            errors.append(f"{relative}: {error}")
            continue
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level and relative.parts[0] == "src":
                    package = list(relative.with_suffix("").parts[:-1])
                    if node.level > len(package):
                        errors.append(f"{relative}:{node.lineno}: invalid relative import")
                        continue
                    base = package[:len(package) - node.level + 1]
                    if node.module:
                        base.extend(node.module.split("."))
                    modules = [".".join(base)]
                    if not node.module:
                        modules += [".".join(base + [alias.name]) for alias in node.names if alias.name != "*"]
                elif not node.level:
                    modules = [node.module or ""]
            for module in modules:
                if (module == "src" or module.startswith("src.")) and not module_exists(root, module):
                    errors.append(f"{relative}:{node.lineno}: missing local module {module}")
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in {"asset_path", "blender_script_path"}:
                continue
            if not node.args or not all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in node.args):
                continue
            parts = [a.value for a in node.args]
            if node.func.id == "blender_script_path":
                parts.insert(0, "blender")
            asset = root / "src" / "assets" / Path(*parts)
            references.add(asset.relative_to(root).as_posix())
            if not asset.exists() or (asset.is_file() and asset not in included):
                errors.append(f"{relative}:{node.lineno}: missing release asset {asset.relative_to(root)}")
    # These files are referenced dynamically by the viewer, Blender and worker launcher.
    required = (
        "src/assets/blender_texture_material_utils.py",
        "src/assets/viewer3d/vendor/three.min.js",
        "src/assets/viewer3d/vendor/OrbitControls.js",
        "src/assets/viewer3d/vendor/OBJLoader.js",
        "src/assets/viewer3d/vendor/MTLLoader.js",
        "src/assets/viewer3d/vendor/LICENSE.txt",
        "src/internal_workers/detect_map_worker.py",
        "src/internal_workers/interactive_label_editor.py",
        "src/internal_workers/release_selftest.py",
    )
    for name in required:
        if root / name not in included:
            errors.append("Missing dynamic release input: " + name)
    if errors:
        raise ValueError("\n".join(errors))
    return {
        "source_check": "passed", "python_files": len(python_files),
        "asset_references": sorted(references),
        "source_files": {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    }


def check_environment(root: Path) -> dict:
    errors = []
    if sys.version_info[:3] != (3, 11, 9) or sys.maxsize <= 2**32 or sys.platform != "win32":
        errors.append("The release requires Windows x64 and CPython 3.11.9")
    pins = 0
    for line in (root / "requirements-release.lock.txt").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s]+)", line.strip())
        if not match:
            continue
        name, expected = match.groups()
        pins += 1
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = "missing"
        if actual != expected:
            errors.append(f"{name}: expected {expected}, found {actual}")
    if not pins:
        errors.append("Empty dependency lock")
    blender = root / "blender" / "blender.exe"
    if not blender.is_file():
        errors.append("Missing blender/blender.exe")
    else:
        version = subprocess.check_output([str(blender), "--version"], text=True, timeout=30).splitlines()[0].strip()
        if version != "Blender 4.3.2":
            errors.append("Expected Blender 4.3.2, found " + version)
    for name in ("LICENSE", "Version.txt", "models/hand/pose_deploy.prototxt", "models/hand/pose_iter_102000.caffemodel"):
        if not (root / "openpose" / name).is_file():
            errors.append("Missing openpose/" + name)
    if errors:
        raise ValueError("\n".join(errors))
    return {"environment_check": "passed", "pinned_packages": pins, "python": platform.python_version()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-environment", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = check_source(ROOT)
        if args.check_environment:
            report.update(check_environment(ROOT))
    except (ValueError, FileNotFoundError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Source check passed: {report['python_files']} Python/spec files, {len(report['source_files'])} source inputs")
    if args.check_environment:
        print(f"Release environment passed: {report['pinned_packages']} pinned packages, Blender 4.3.2 and OpenPose files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
