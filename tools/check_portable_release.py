"""Verify portable runtime inputs and publication-free HAMLET metadata."""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import re
import types
import zlib


IDENTIFIER = re.compile(rb"(?:https?://(?:dx\.)?doi\.org/[^\s<>\"\x00]+|10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.I)
REPOSITORY = "https://github.com/JonAndoniFdez/HAMLET"
DOCUMENTS = (
    "README.txt", "LICENSE.txt", "THIRD_PARTY_LICENSES.txt", "NOTICE.txt", "CITATION.cff",
    "THIRD_PARTY_NOTICES.md", "SOURCE_CODE.md", "OPENPOSE_MODELS_NOTICE.txt",
    "build-inputs.json",
)
RUNTIME_FILES = (
    "HAMLET.exe", "python311.dll", "blender/blender.exe",
    "openpose/LICENSE", "openpose/Version.txt",
    "openpose/models/hand/pose_deploy.prototxt",
    "openpose/models/hand/pose_iter_102000.caffemodel",
    "PySide6/Qt6Core.dll", "PySide6/Qt6WebEngineCore.dll",
    "PySide6/QtWebEngineProcess.exe", "PySide6/plugins/platforms/qwindows.dll",
    "assets/data/markers_template.csv", "assets/data/pointsColor.csv",
    "assets/data/LandmarksOperations_data.csv", "assets/viewer3d/vendor/three.min.js",
    "docs/README.pdf", "third_party_licenses/index.html",
    "third_party_licenses/dependency-licenses.json", "third_party_licenses/QtWebEngine-credits.html",
)


def check_metadata_bytes(data: bytes, label: str) -> None:
    if IDENTIFIER.search(data):
        raise ValueError("Publication identifier found in HAMLET content: " + label)


def code_strings(code):
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            yield from code_strings(value)
        elif isinstance(value, str):
            yield value


def verify(directory: Path, *, inspect_executable: bool = True) -> dict:
    directory = Path(directory).resolve()
    for name in (*DOCUMENTS, *RUNTIME_FILES):
        if not (directory / name).is_file():
            raise FileNotFoundError("Missing portable release file: " + name)
    if REPOSITORY not in (directory / "README.txt").read_text(encoding="utf-8"):
        raise ValueError("README.txt is missing the repository link")
    for name in DOCUMENTS:
        check_metadata_bytes((directory / name).read_bytes(), name)
    manifest = directory / "release-manifest.json"
    if manifest.is_file():
        check_metadata_bytes(manifest.read_bytes(), manifest.name)
    source_modules = 0
    payload_files = 0
    if inspect_executable:
        from PyInstaller.archive.readers import CArchiveReader
        archive = CArchiveReader(str(directory / "HAMLET.exe")).open_embedded_archive("PYZ.pyz")
        for name in sorted(archive.toc):
            if name == "src" or name.startswith("src."):
                for string in code_strings(archive.extract(name)):
                    check_metadata_bytes(string.encode("utf-8"), name)
                source_modules += 1
        namespace = {}
        exec(archive.extract("hamlet_blender_payload"), namespace)
        for name, data in namespace["SCRIPTS"].items():
            check_metadata_bytes(zlib.decompress(base64.b64decode(data)), name)
            payload_files += 1
    return {
        "portable_content": "passed", "repository_link": REPOSITORY,
        "hamlet_publication_identifiers": "absent",
        "third_party_dependencies": "original scientific references retained by project owner instruction",
        "checked_runtime_files": len(RUNTIME_FILES), "checked_hamlet_documents": len(DOCUMENTS),
        "checked_hamlet_modules": source_modules, "checked_blender_payload_files": payload_files,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = verify(args.directory)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
