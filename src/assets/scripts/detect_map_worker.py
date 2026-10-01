from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _project_root_from_script() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def _ensure_import_path():
    root = _project_root_from_script()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def parse_args():
    parser = argparse.ArgumentParser(description="Isolated detection + UV mapping worker")
    parser.add_argument("--texture", required=True)
    parser.add_argument("--obj", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--target_json", required=False)
    parser.add_argument("--v_flip", default="1")
    parser.add_argument("--snap_to_vertices", default="1")
    return parser.parse_args()


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def main() -> int:
    _ensure_import_path()
    from src.core.detect_map import run_detect_and_map

    args = parse_args()
    logs: list[str] = []

    res = run_detect_and_map(
        texture_path=Path(args.texture),
        obj_path=Path(args.obj),
        out_dir=Path(args.out_dir),
        target_json=Path(args.target_json) if args.target_json else None,
        v_flip=_as_bool(args.v_flip),
        snap_to_vertices=_as_bool(args.snap_to_vertices),
        log=lambda s: logs.append(str(s)),
    )

    payload = {
        "ok": bool(res.ok),
        "message": res.message,
        "csv_2d": str(res.csv_2d) if res.csv_2d else None,
        "csv_3d": str(res.csv_3d) if res.csv_3d else None,
        "n_2d": int(res.n_2d or 0),
        "n_3d_mapped": int(res.n_3d_mapped or 0),
        "logs": logs,
    }
    print("JSON_RESULT " + json.dumps(payload, ensure_ascii=False))
    return 0 if res.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
