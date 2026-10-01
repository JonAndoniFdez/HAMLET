from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple
import importlib
import os
import shutil
import glob

try:
    import importlib.metadata as importlib_metadata
except Exception:  # pragma: no cover
    import importlib_metadata  # type: ignore

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from .paths import app_root, project_root, bundled_blender_exe
from .subprocess_utils import run_hidden


@dataclass
class DepStatus:
    name: str
    required: bool
    kind: str  # "python" | "external"
    spec: Optional[str] = None

    installed_version: Optional[str] = None
    ok: bool = False
    message: str = ""

    # para dependencias externas (p.ej. Blender)
    location: Optional[str] = None


# -------------------------
# Python deps
# -------------------------
def _get_installed_version(dist_name: str) -> Optional[str]:
    try:
        return importlib_metadata.version(dist_name)
    except Exception:
        return None


def _can_import(import_name: str) -> bool:
    try:
        importlib.import_module(import_name)
        return True
    except Exception:
        return False


def check_python_dependencies(
    deps: List[Tuple[str, str, bool, Optional[str]]]
) -> List[DepStatus]:
    """
    deps: (dist_name, import_name, required, spec)
    """
    results: List[DepStatus] = []

    for dist_name, import_name, required, spec in deps:
        st = DepStatus(
            name=dist_name,
            required=required,
            kind="python",
            spec=spec,
        )

        ver = _get_installed_version(dist_name)
        st.installed_version = ver

        if ver is None:
            st.ok = False
            st.message = "No instalado"
            results.append(st)
            continue

        if not _can_import(import_name):
            st.ok = False
            st.message = "Instalado pero no se puede importar"
            results.append(st)
            continue

        if spec:
            try:
                ok = Version(ver) in SpecifierSet(spec)
            except Exception:
                ok = True
            if not ok:
                st.ok = False
                st.message = f"Versión {ver} no cumple {spec}"
                results.append(st)
                continue

        st.ok = True
        st.message = "OK"
        results.append(st)

    return results


# -------------------------
# Blender external dep
# -------------------------
def validate_blender_exe(path: Path) -> bool:
    try:
        return path.exists() and path.is_file() and path.name.lower() == "blender.exe"
    except Exception:
        return False


def _blender_version(path: Path) -> Optional[str]:
    """
    Intenta extraer la versión con: blender.exe --version
    Devuelve algo tipo "Blender 4.3.0" (primera línea), o None si falla.
    """
    try:
        proc = run_hidden(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        out = (proc.stdout or "").strip().splitlines()
        if out:
            return out[0].strip()
    except Exception:
        pass
    return None


def auto_find_blender() -> Optional[Path]:
    
    # 0) Blender embebido junto a src/
    bundled = bundled_blender_exe()
    if bundled and validate_blender_exe(bundled):
        return bundled
    
    # 1) env var
    env = os.environ.get("BLENDER_EXE")
    if env:
        p = Path(env)
        if validate_blender_exe(p):
            return p

    # 2) PATH
    w = shutil.which("blender")
    if w:
        p = Path(w)
        if p.suffix.lower() == ".exe":
            return p

    w = shutil.which("blender.exe")
    if w:
        return Path(w)

    # 3) rutas típicas (Windows)
    candidates = []

    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pfx86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA")

    patterns = [
        str(Path(pf) / "Blender Foundation" / "Blender *" / "blender.exe"),
        str(Path(pfx86) / "Blender Foundation" / "Blender *" / "blender.exe"),
    ]
    if local:
        # a veces installs “portables” o variantes
        patterns += [
            str(Path(local) / "Programs" / "Blender Foundation" / "Blender *" / "blender.exe"),
        ]

    for pat in patterns:
        candidates.extend(glob.glob(pat))

    # escoger el “más alto” por nombre (no perfecto, pero práctico)
    paths = [Path(c) for c in candidates if validate_blender_exe(Path(c))]
    if not paths:
        return None

    # preferimos el que tenga nombre de carpeta más reciente
    # (orden lexicográfico suele funcionar con "Blender 4.3", "Blender 4.2", etc.)
    paths.sort(key=lambda p: str(p.parent), reverse=True)
    return paths[0]


def check_blender(blender_path: Optional[Path] = None, required: bool = True) -> DepStatus:
    st = DepStatus(
        name="Blender",
        required=required,
        kind="external",
        spec=None,
    )

    p = blender_path if blender_path else auto_find_blender()
    if not p:
        st.ok = False
        st.message = "No encontrado"
        return st

    if not validate_blender_exe(p):
        st.ok = False
        st.message = "Ruta inválida (debe ser blender.exe)"
        st.location = str(p)
        return st

    st.location = str(p)
    st.installed_version = _blender_version(p)  # puede ser None
    st.ok = True
    st.message = "OK"
    return st


def check_openpose_hand_models(search_root: Optional[Path] = None, required: bool = True) -> DepStatus:
    """Comprueba que existan los modelos de mano de OpenPose.

    Este proyecto usa OpenCV DNN (Caffe) con los ficheros:
      - openpose/models/hand/pose_deploy.prototxt
      - openpose/models/hand/pose_iter_102000.caffemodel

    Por compatibilidad, se busca en:
      1) search_root (si se pasa)
      2) Path.cwd()
      3) app_root() y project_root() (carpeta del ejecutable/proyecto)
      4) project_root().parent (compatibilidad con layouts antiguos)
    """
    st = DepStatus(
        name="OpenPose (modelos mano)",
        required=required,
        kind="files",
        spec=None,
    )

    roots: list[Path] = []
    if search_root is not None:
        roots.append(Path(search_root))
    roots.append(Path.cwd())
    roots.append(app_root())
    roots.append(project_root())
    roots.append(project_root().parent)

    found_base: Optional[Path] = None
    for r in roots:
        cand = (r / "openpose" / "models" / "hand")
        if cand.exists():
            found_base = cand
            break

    if found_base is None:
        st.ok = False
        st.message = "No se encontró carpeta openpose/models/hand"
        st.details = (
            "Crea una carpeta 'openpose/models/hand' junto al proyecto y coloca ahí los modelos de mano. "
            "(Ver README de OpenPose / modelos Caffe)."
        )
        return st

    proto = found_base / "pose_deploy.prototxt"
    model = found_base / "pose_iter_102000.caffemodel"
    missing = [p for p in (proto, model) if not p.exists()]
    st.location = str(found_base)

    if missing:
        st.ok = False
        st.message = "Faltan archivos"
        st.details = "Faltan: " + ", ".join(p.name for p in missing)
        return st

    st.ok = True
    st.message = "OK"
    return st


def has_required_failures(statuses: List[DepStatus]) -> bool:
    return any((s.required and not s.ok) for s in statuses)
