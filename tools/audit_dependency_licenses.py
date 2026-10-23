"""Inventory release dependencies and stage original notices for review.

Run with the build environment's Python. Does not modify dist or certify compliance.
"""
from __future__ import annotations

import ast
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "HAMLET"
OUT = ROOT / "build" / "dependency_audit"
LEGAL_NAME = re.compile(r"(?:^|[._-])(licen[cs]e(?:ref)?|copying|copyright|notice|authors|third[-_ ]party)(?:[._-]|$)", re.I)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    collect = ast.literal_eval((ROOT / "build/HAMLET/COLLECT-00.toc").read_text())[0]
    pure = ast.literal_eval((ROOT / "build/HAMLET/PYZ-00.toc").read_text())[1]
    origins = defaultdict(list)
    for dest, source, kind in [*collect, *pure]:
        origins[str(Path(source).resolve()).casefold()].append({"destination": dest, "kind": kind})

    legal_files = sorted(p for p in DIST.rglob("*") if p.is_file() and LEGAL_NAME.search(p.name))
    legal_hashes = defaultdict(list)
    for path in legal_files:
        legal_hashes[digest(path)].append(path.relative_to(DIST).as_posix())
    records = []
    for package in sorted(metadata.distributions(), key=lambda p: p.metadata.get("Name", "").lower()):
        name = package.metadata.get("Name", "unknown")
        package_files = list(package.files or [])
        evidence = []
        for file in package_files:
            source = Path(package.locate_file(file)).resolve()
            if str(source).casefold() in origins:
                evidence.extend(origins[str(source).casefold()])
        is_build_tool = name.casefold() == "pyinstaller"
        if not evidence and not is_build_tool:
            continue
        folder = OUT / "collected-notices" / f"{name}-{package.version}"
        folder.mkdir(parents=True, exist_ok=True)
        raw_metadata = package.read_text("METADATA") or package.read_text("PKG-INFO") or ""
        (folder / "PACKAGE-METADATA.txt").write_text(raw_metadata, encoding="utf-8")
        notices = []
        for file in package_files:
            if not LEGAL_NAME.search(Path(str(file)).name):
                continue
            source = Path(package.locate_file(file)).resolve()
            if not source.is_file():
                continue
            # RECORD paths may contain '..'; never use them as output paths.
            target = folder / f"{len(notices)+1:03d}-{source.name}"
            shutil.copyfile(source, target)
            file_hash = digest(source)
            notices.append({"original_path": str(file), "sha256": file_hash,
                            "staged_path": target.relative_to(OUT).as_posix(),
                            "identical_notice_in_dist": legal_hashes.get(file_hash, [])})
        license_value = package.metadata.get("License-Expression") or package.metadata.get("License")
        records.append({"name": name, "version_in_build_environment": package.version,
                        "role": "build tool / bootloader" if is_build_tool else "release dependency",
                        "license_metadata": license_value,
                        "license_classifiers": [v for v in package.metadata.get_all("Classifier", []) if v.startswith("License")],
                        "evidence_count": len(evidence), "build_evidence_sample": evidence[:5],
                        "notices": notices})

    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        target = OUT / "collected-notices" / "Python" / "LICENSE.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(python_license, target)

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "method": "Build TOC source paths intersect installed distribution RECORDs. Versions come from current build environment metadata, not requirements.txt. Full binary/version identity is not established by this intersection.",
        "limitations": "Candidate notice collection, not a complete SBOM or compliance certificate. Native/transitive dependencies, Qt module notices, Chromium and Blender source obligations require separate review. Missing hash means no identical standalone notice found under conventional legal filenames; text may exist inside other files.",
        "executable_sha256": digest(DIST / "HAMLET.exe"),
        "build_executable_matches_release": digest(ROOT / "build/HAMLET/HAMLET.exe") == digest(DIST / "HAMLET.exe"),
        "release_legal_files": [p.relative_to(DIST).as_posix() for p in legal_files],
        "qt_dlls": sorted(p.name for p in (DIST / "PySide6").glob("Qt6*.dll")),
        "models": [{"path": p.relative_to(DIST).as_posix(), "bytes": p.stat().st_size, "sha256": digest(p)} for p in sorted((DIST / "openpose/models/hand").glob("*")) if p.is_file()],
        "packages": records,
    }
    report["zip_executable_matches_release"] = None
    if (ROOT / "dist/HAMLET.zip").is_file():
        with zipfile.ZipFile(ROOT / "dist/HAMLET.zip") as archive:
            names = {n.replace("\\", "/"): n for n in archive.namelist()}
            exe = next(n for n in names if n.endswith("HAMLET.exe"))
            report["zip_executable_matches_release"] = hashlib.sha256(archive.read(names[exe])).hexdigest() == report["executable_sha256"]
            report["zip_legal_files"] = sorted(n for n in names if LEGAL_NAME.search(Path(n).name))

    (OUT / "inventory.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Inventario de paquetes y avisos candidatos", "", report["method"], "", report["limitations"], "",
             "| Paquete | Versión del entorno | Evidencias en build | Avisos recogidos | Avisos idénticos encontrados en dist |",
             "| --- | --- | ---: | ---: | ---: |"]
    for item in records:
        lines.append(f"| {item['name']} | {item['version_in_build_environment']} | {item['evidence_count']} | {len(item['notices'])} | {sum(bool(n['identical_notice_in_dist']) for n in item['notices'])} |")
    (OUT / "PACKAGES.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(f"Packages: {len(records)}; staged original notices: {sum(len(p['notices']) for p in records)}")
    print(f"Qt DLLs: {len(report['qt_dlls'])}; build EXE matches: {report['build_executable_matches_release']}; ZIP EXE matches: {report['zip_executable_matches_release']}")
    print(f"Report: {OUT / 'inventory.json'}")


if __name__ == "__main__":
    main()
