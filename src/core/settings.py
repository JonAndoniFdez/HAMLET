from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from .app_info import APP_SHORT_NAME

APP_NAME = APP_SHORT_NAME


def _config_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_NAME
    # fallback
    return Path.home() / f".{APP_NAME}"


def settings_path() -> Path:
    return _config_dir() / "settings.json"


def load_settings() -> Dict[str, Any]:
    p = settings_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data: Dict[str, Any]) -> None:
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
