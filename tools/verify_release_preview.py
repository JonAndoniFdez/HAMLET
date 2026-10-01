"""Check the preview code and Blender payload in the actual release executable."""
from __future__ import annotations

import argparse
import base64
from pathlib import Path
import types
import zlib

from PyInstaller.archive.readers import CArchiveReader


def string_constants(code: types.CodeType):
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            yield from string_constants(value)
        elif isinstance(value, str):
            yield value


def verify(executable: Path) -> None:
    archive = CArchiveReader(str(executable)).open_embedded_archive("PYZ.pyz")
    preview = archive.extract("src.gui.pages.threshold_page")
    scripts = {
        value for value in string_constants(preview) if value.endswith(".py")
    }
    if not scripts:
        raise RuntimeError("No Blender preview script reference found in the executable.")

    namespace = {}
    exec(archive.extract("hamlet_blender_payload"), namespace)
    payload = namespace["SCRIPTS"]
    for script in sorted(scripts):
        key = f"blender/{script}"
        if key not in payload:
            raise RuntimeError(f"Release preview references a missing Blender script: {key}")
        source = zlib.decompress(base64.b64decode(payload[key]))
        compile(source, key, "exec")
        print(f"Verified embedded preview script: {key}")

    visible_sources = list((executable.parent / "assets" / "blender").glob("*.py"))
    if visible_sources:
        raise RuntimeError(f"Blender source files exposed in release assets: {visible_sources}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    verify(parser.parse_args().executable)
