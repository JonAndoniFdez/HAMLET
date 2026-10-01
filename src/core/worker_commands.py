from __future__ import annotations

from pathlib import Path
import sys

from .paths import app_root


WORKER_MODULES = {
    "detect-map": "src.internal_workers.detect_map_worker",
    "label-editor": "src.internal_workers.interactive_label_editor",
}


def internal_worker_command(worker_name: str) -> list[str]:
    if worker_name not in WORKER_MODULES:
        raise ValueError(f"Unknown internal worker: {worker_name}")

    if getattr(sys, "frozen", False):
        return [sys.executable, "--internal-worker", worker_name]

    return [sys.executable, "-m", WORKER_MODULES[worker_name]]


def internal_worker_cwd() -> Path:
    return app_root()
