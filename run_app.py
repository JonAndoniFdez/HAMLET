import sys
import importlib
from pathlib import Path


from src.core.worker_commands import WORKER_MODULES

_LEGACY_SCRIPT_WORKERS = {
    "detect_map_worker.py": "detect-map",
    "interactive_label_editor.py": "label-editor",
}


def _run_internal_worker(worker_name: str, args: list[str]) -> bool:
    module_name = WORKER_MODULES.get(worker_name)
    if not module_name:
        raise SystemExit(f"Unknown internal worker: {worker_name}")

    sys.argv = [worker_name] + args
    module = importlib.import_module(module_name)
    result = module.main()
    if isinstance(result, int):
        raise SystemExit(result)
    return True


def _maybe_run_internal_worker() -> bool:
    """
    En modo PyInstaller, sys.executable apunta al propio .exe.
    Algunos workers se lanzan como:
    [sys.executable, "--internal-worker", worker_name, args...].
    Se conserva también la ruta antigua basada en script.py por compatibilidad.
    """
    if len(sys.argv) < 2:
        return False

    if sys.argv[1] == "--self-test-release":
        if len(sys.argv) != 3:
            raise SystemExit("Usage: HAMLET --self-test-release <output-directory>")
        sys.argv = ["release-selftest", sys.argv[2]]
        from src.internal_workers.release_selftest import main
        raise SystemExit(main())

    if sys.argv[1] == "--internal-worker":
        if len(sys.argv) < 3:
            raise SystemExit("Missing internal worker name.")
        return _run_internal_worker(sys.argv[2], sys.argv[3:])

    script_arg = Path(sys.argv[1])
    legacy_worker = _LEGACY_SCRIPT_WORKERS.get(script_arg.name)
    if not legacy_worker:
        return False

    return _run_internal_worker(legacy_worker, sys.argv[2:])


if __name__ == "__main__":
    if not _maybe_run_internal_worker():
        from src.main import main
        main()
