from __future__ import annotations

from pathlib import Path
import shutil
import sys


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def project_root() -> Path:
    """Backward-compatible alias used by dependency checks."""
    return app_root()


def src_root() -> Path:
    """Dev: .../HAMLET/src | EXE: no existe (pero devolvemos algo coherente)."""
    if getattr(sys, "frozen", False):
        return app_root() / "src"
    return app_root() / "src"


def assets_root() -> Path:
    """
    Dev: .../HAMLET/src/assets
    EXE: .../dist/HAMLET/assets
    """
    if getattr(sys, "frozen", False):
        return app_root() / "assets"
    return app_root() / "src" / "assets"


def asset_path(*parts: str) -> Path:
    return assets_root() / Path(*parts)


def _blender_exe_name() -> str:
    return "blender.exe" if sys.platform.startswith("win") else "blender"


def normalize_blender_exe(value: str | Path | None) -> Path | None:
    """
    Devuelve una ruta válida al ejecutable de Blender o None.

    Acepta:
    - una ruta directa a blender.exe
    - una ruta a la carpeta que contiene blender.exe
    - None / cadena vacía

    Evita explícitamente el bug de Path("") -> Path("."), que en Windows
    puede acabar intentando ejecutar una carpeta y provocar "Acceso denegado".
    """
    if value is None:
        return None

    raw = str(value).strip().strip('"')
    if not raw:
        return None

    p = Path(raw).expanduser()
    exe_name = _blender_exe_name()

    try:
        if p.is_dir():
            candidate = p / exe_name
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
            return None

        if p.exists() and p.is_file() and p.name.lower() == exe_name.lower():
            return p.resolve()
    except OSError:
        return None

    return None


def bundled_blender_exe() -> Path | None:
    exe_name = _blender_exe_name()

    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        # Ruta PRIORITARIA en el ejecutable portable:
        # dist/HAMLET/blender/blender.exe
        candidates.append(Path(sys.executable).resolve().parent / "blender" / exe_name)

    # Ruta de desarrollo:
    # HAMLET/blender/blender.exe
    candidates.append(app_root() / "blender" / exe_name)

    for p in candidates:
        try:
            if p.exists() and p.is_file():
                return p.resolve()
        except OSError:
            continue

    return None


def resolve_blender_exe(settings: dict | None = None) -> Path | None:
    """
    Resuelve Blender de forma segura y centralizada.

    Orden de búsqueda:
    1. settings["blender_exe"]
    2. settings["blender_path"]
    3. variable de entorno BLENDER_EXE
    4. Blender empaquetado junto al ejecutable/proyecto
    5. blender/blender.exe detectable en PATH

    Nunca devuelve Path("") ni Path("."). Si no hay ejecutable válido,
    devuelve None.
    """
    settings = settings or {}

    for key in ("blender_exe", "blender_path"):
        p = normalize_blender_exe(settings.get(key))
        if p:
            return p

    import os

    p = normalize_blender_exe(os.environ.get("BLENDER_EXE"))
    if p:
        return p

    bundled = bundled_blender_exe()
    if bundled:
        return bundled

    for name in ("blender", "blender.exe"):
        found = shutil.which(name)
        p = normalize_blender_exe(found)
        if p:
            return p

    return None


def bundled_openpose_dir() -> Path | None:
    """
    Dev:  .../HAMLET/openpose
    EXE:  .../dist/HAMLET/openpose
    """
    p = app_root() / "openpose"
    return p if p.exists() else None
