"""Download an auditable source companion; never label a failed download complete."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time
import urllib.request


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "HAMLET-release-source-audit/1.0"}), timeout=60)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def fetch(item, folder):
    item = dict(item)
    target = folder / item["filename"]
    try:
        if not target.exists():
            for attempt in range(3):
                try:
                    with get(item["url"]) as response, target.with_suffix(target.suffix + ".partial").open("wb") as out:
                        while data := response.read(1024 * 1024):
                            out.write(data)
                    target.with_suffix(target.suffix + ".partial").replace(target)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(2)
        item["sha256"] = sha(target)
        item["bytes"] = target.stat().st_size
        if item.get("expected_sha256") and item["sha256"] != item["expected_sha256"]:
            raise ValueError("SHA-256 differs from upstream metadata")
        item["status"] = "downloaded"
    except Exception as exc:
        item["status"] = "failed"
        item["error"] = str(exc)
    print(item["name"], item["status"], flush=True)
    return item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path("build/dependency_audit/inventory.json"))
    parser.add_argument("--out", type=Path, default=Path("dist/source-companion"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    packages = json.loads(args.inventory.read_text(encoding="utf-8"))["packages"]
    entries = [
        {"name": "Qt", "version": "6.10.2", "filename": "qt-everywhere-src-6.10.2.tar.xz", "url": "https://download.qt.io/archive/qt/6.10/6.10.2/single/qt-everywhere-src-6.10.2.tar.xz"},
        {"name": "QtForPython", "version": "6.10.2", "filename": "pyside-setup-everywhere-src-6.10.2.tar.xz", "url": "https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.10.2-src/pyside-setup-everywhere-src-6.10.2.tar.xz"},
        {"name": "Blender", "version": "4.3.2", "filename": "blender-4.3.2.tar.xz", "url": "https://download.blender.org/source/blender-4.3.2.tar.xz"},
        {"name": "Python", "version": "3.11.9", "filename": "Python-3.11.9.tar.xz", "url": "https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tar.xz"},
        {"name": "VTK", "version": "9.5.1", "filename": "VTK-9.5.1.tar.gz", "url": "https://www.vtk.org/files/release/9.5/VTK-9.5.1.tar.gz"},
        {"name": "pywin32", "version": "311", "filename": "pywin32-b311.tar.gz", "url": "https://github.com/mhammond/pywin32/archive/refs/tags/b311.tar.gz"},
    ]
    failures = []
    skip = {"pyside6", "pyside6-addons", "pyside6-essentials", "shiboken6", "vtk", "pywin32"}
    for package in packages:
        name = package["name"]
        version = package.get("version_in_build_environment", package.get("version"))
        if name.lower().replace("_", "-") in skip:
            continue
        try:
            with get(f"https://pypi.org/pypi/{name}/{version}/json") as response:
                data = json.load(response)
            source = next(f for f in data["urls"] if f["packagetype"] == "sdist")
            entries.append({"name": name, "version": version, "filename": source["filename"], "url": source["url"], "expected_sha256": source["digests"]["sha256"]})
        except Exception as exc:
            failures.append({"name": name, "version": version, "status": "metadata_failed", "error": str(exc)})
    results = failures[:]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(fetch, item, args.out) for item in entries]
        for future in as_completed(futures):
            results.append(future.result())
            (args.out / "SOURCES.json").write_text(json.dumps({"scope": "Upstream sources selected from dependency inventory. Native/transitive build inputs and publication availability require separate verification.", "sources": sorted(results, key=lambda i: i["name"].lower())}, indent=2), encoding="utf-8")
    if any(item["status"] != "downloaded" for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
