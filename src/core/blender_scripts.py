from __future__ import annotations

import atexit
import base64
import importlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import zlib

from .paths import asset_path


_EXTRACTED_ASSETS_DIR: Path | None = None


def blender_script_path(script_name: str) -> Path:
    """Return a Blender script path usable by blender.exe."""
    normalized_name = script_name.replace("\\", "/").split("/")[-1]

    if not getattr(sys, "frozen", False):
        return asset_path("blender", normalized_name)

    assets_dir = _ensure_extracted_assets_dir()
    return assets_dir / "blender" / normalized_name


def _ensure_extracted_assets_dir() -> Path:
    global _EXTRACTED_ASSETS_DIR

    if _EXTRACTED_ASSETS_DIR is not None and _EXTRACTED_ASSETS_DIR.exists():
        return _EXTRACTED_ASSETS_DIR

    payload_module = importlib.import_module("hamlet_blender_payload")
    scripts = getattr(payload_module, "SCRIPTS")

    root = Path(tempfile.gettempdir()) / "HAMLET" / f"blender_scripts_{os.getpid()}"
    assets_dir = root / "assets"

    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    for rel_path, encoded in scripts.items():
        out_path = assets_dir / Path(rel_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        data = zlib.decompress(base64.b64decode(encoded.encode("ascii")))
        out_path.write_bytes(data)

    _EXTRACTED_ASSETS_DIR = assets_dir
    atexit.register(lambda: shutil.rmtree(root, ignore_errors=True))
    return assets_dir
