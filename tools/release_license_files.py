"""Collect original notices for distributions actually selected by PyInstaller.

This preserves documents; it does not certify license compatibility or fulfill
corresponding-source obligations by itself. Returns PyInstaller TOC entries.
"""
from __future__ import annotations

import hashlib
import html
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import re
import sys


LEGAL_NAME = re.compile(r"(?:^|[._-])(licen[cs]e(?:ref)?|copying|copyright|notice|authors|third[-_ ]party)(?:[._-]|$)", re.I)


def _key(path) -> str:
    return os.path.normcase(os.path.abspath(path))


def collect_license_files(entries, generated_dir: Path, common_dir: Path):
    selected = {_key(source) for _, source, _ in entries if source}
    result = []
    packages = []
    for package in sorted(metadata.distributions(), key=lambda p: p.metadata.get("Name", "").lower()):
        name = package.metadata.get("Name", "unknown")
        files = list(package.files or [])
        if name.lower() != "pyinstaller" and not any(
            _key(package.locate_file(f)) in selected for f in files
        ):
            continue
        component = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{name}-{package.version}")
        notices = []
        for file in files:
            relative = Path(str(file))
            if not LEGAL_NAME.search(relative.name):
                continue
            source = Path(package.locate_file(file))
            if not source.is_file():
                raise FileNotFoundError(f"Recorded notice is missing for {name}: {source}")
            # Keep output independent of RECORD paths, which can contain '..'.
            destination = f"third_party_licenses/{component}/{len(notices)+1:03d}-{relative.name}"
            result.append((destination, str(source.resolve()), "DATA"))
            notices.append({"file": destination, "original_package_path": str(file),
                            "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
        packages.append({"name": name, "version": package.version,
                         "role": "build tool and bootloader" if name.lower() == "pyinstaller" else "bundled package",
                         "declared_license": package.metadata.get("License-Expression") or package.metadata.get("License"),
                         "license_classifiers": [v for v in package.metadata.get_all("Classifier", []) if v.startswith("License")],
                         "notices": notices,
                         "review_required": not notices or name.lower() in {"pyside6", "pyside6_addons", "pyside6_essentials", "shiboken6"}})

    python_notice = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_notice.is_file():
        raise FileNotFoundError(f"Python runtime notice is missing: {python_notice}")
    result.append(("third_party_licenses/Python/LICENSE.txt", str(python_notice), "DATA"))
    for source in sorted(common_dir.rglob("*")):
        if source.is_file():
            result.append(("third_party_licenses/" + source.relative_to(common_dir).as_posix(), str(source.resolve()), "DATA"))

    manifest = {
        "scope": "Notices from installed packages whose files are selected by this build, plus Python and reference license texts. Blender retains its own license directory.",
        "limitations": "Not a compliance certificate or complete native dependency SBOM. Qt/Chromium module attributions, corresponding source and third-party redistribution permissions require separate review. A packaged commercial-license reference does not establish entitlement to a commercial license.",
        "python_version": sys.version.split()[0],
        "packages": packages,
    }
    generated_dir.mkdir(parents=True, exist_ok=True)
    path = generated_dir / "dependency-licenses.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result.append(("third_party_licenses/dependency-licenses.json", str(path.resolve()), "DATA"))
    sections = {}
    for destination, source, _ in result:
        if destination.endswith(('.json', '.html')):
            continue
        relative = destination.removeprefix('third_party_licenses/')
        parts = relative.split('/')
        group = '/'.join(parts[:2]) if parts[0] == 'upstream-sources' else parts[0]
        sections.setdefault(group, []).append(relative)
    content = ['<!doctype html><html lang="en"><meta charset="utf-8"><title>HAMLET licenses and source code</title>',
               '<style>body{font:16px/1.5 system-ui;max-width:1000px;margin:40px auto;padding:0 20px}a{overflow-wrap:anywhere}details{margin:12px 0}summary{font-weight:bold}</style>',
               '<h1>HAMLET third-party licenses and source code</h1>',
               '<p>Original HAMLET code: <a href="../LICENSE.txt">GNU GPLv3</a> (GPL-3.0-only). <a href="../NOTICE.txt">Authors and copyright</a> · <a href="../CITATION.cff">Citation metadata</a>.</p>',
               '<p>Third-party components retain their own licenses. OpenPose hand models retain CMU academic/noncommercial research terms.</p>',
               '<p><a href="../THIRD_PARTY_LICENSES.txt">Software licenses: readable component summary</a> · <a href="../SOURCE_CODE.md">Source code, rebuilding and replacing libraries</a> · <a href="dependency-licenses.json">Exact Python package inventory</a></p>',
               '<p><a href="../docs/DEPENDENCY_SOURCES.md">Exact dependency-source downloads and instructions</a> · <a href="SOURCE_DOWNLOADS.json">Pinned source archive catalog and SHA-256 digests</a> · <a href="source-availability/urls.json">Dated source URL checks</a> · <a href="source-availability/integrity.json">Full local source archive verification</a></p>',
               '<p><a href="../blender/license/license.md">Blender original notices</a> · <a href="../openpose/LICENSE">OpenPose terms</a> · <a href="../OPENPOSE_MODELS_NOTICE.txt">OpenPose model provenance and status</a> · <a href="QtWebEngine-credits.html">Qt WebEngine and Chromium notices from the exact Qt source archive</a></p>',
               '<p>Upstream source notices include unused and build-only components; their presence does not mean that every component is included in HAMLET.</p>']
    for group, paths in sorted(sections.items()):
        content.append('<details><summary>' + html.escape(group) + '</summary><ul>')
        for relative in paths:
            content.append('<li><a href="' + html.escape(relative, quote=True) + '">' + html.escape(relative) + '</a></li>')
        content.append('</ul></details>')
    content.append('</html>')
    index = generated_dir / 'license-index.html'
    index.write_text('\n'.join(content), encoding='utf-8')
    result.append(('third_party_licenses/index.html', str(index.resolve()), 'DATA'))
    return result
