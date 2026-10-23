"""Obtain pinned upstream sources, verify cached archives, or probe source URLs.

Uses only the Python standard library. URL probes are availability evidence at
one instant; only full downloads/local verification establish archive hashes.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "third_party_licenses/SOURCE_DOWNLOADS.json"


def digest(path: Path, algorithm: str = "sha256") -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def load_sources(path: Path) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or not document.get("sources"):
        raise ValueError("Unsupported or empty source manifest")
    seen = set()
    for item in document["sources"]:
        relative = PurePosixPath(item["path"])
        if (relative.is_absolute() or ".." in relative.parts or "\\" in item["path"]
                or ":" in item["path"] or str(relative) != item["path"]
                or relative.name != item["filename"]):
            raise ValueError("Unsafe archive path: " + item["path"])
        if item["path"].casefold() in seen:
            raise ValueError("Duplicate archive path: " + item["path"])
        seen.add(item["path"].casefold())
        if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) or item["bytes"] <= 0:
            raise ValueError("Invalid archive digest/size: " + item["path"])
        if not item["url"].startswith("https://"):
            raise ValueError("Source URLs must use HTTPS")
    return document["sources"]


def verify_archive(path: Path, item: dict) -> None:
    if path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
        raise ValueError("Archive size or SHA-256 mismatch: " + item["path"])
    if item.get("recipe_hash"):
        if digest(path, item["recipe_hash_type"]) != item["recipe_hash"]:
            raise ValueError("Blender build-recipe hash mismatch: " + item["path"])


def request(url: str, timeout: float, *, probe: bool = False):
    headers = {"User-Agent": "HAMLET-source-access/1.0", "Accept-Encoding": "identity"}
    if probe:
        headers["Range"] = "bytes=0-31"
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout)


def probe_url(item: dict, url: str, timeout: float) -> dict:
    with request(url, timeout, probe=True) as response:
        prefix = response.read(32)
        content_type = response.headers.get("Content-Type", "").lower()
        if not prefix or "text/html" in content_type or prefix.lstrip().lower().startswith((b"<!doctype html", b"<html")):
            raise ValueError("URL returned an empty response or an HTML page instead of an archive")
        content_range = response.headers.get("Content-Range", "")
        length = response.headers.get("Content-Length")
        if response.status == 206:
            if not re.fullmatch(r"bytes 0-\d+/" + str(item["bytes"]), content_range):
                raise ValueError("Unexpected partial-response range/total size: " + content_range)
        elif response.status != 200:
            raise ValueError("Unexpected HTTP status: " + str(response.status))
        elif length is not None and int(length) != item["bytes"]:
            raise ValueError("Remote archive size differs from pinned size")
        expected_magic = None
        name = item["filename"].lower()
        for endings, magic in ((('.xz',), b'\xfd7zXZ\x00'), (('.gz', '.tgz'), b'\x1f\x8b'),
                               (('.bz2',), b'BZh'), (('.zip',), b'PK')):
            if name.endswith(endings):
                expected_magic = magic
                break
        if expected_magic and not prefix.startswith(expected_magic):
            raise ValueError("Response does not have the expected archive format")
        return {"status": "available", "http_status": response.status,
                "resolved_url": response.geturl(), "content_range": content_range,
                "verification": "HTTP response, archive signature and advertised size; not a full remote hash"}


def process(item: dict, mode: str, folder: Path, timeout: float, mirror_base: str | None) -> dict:
    url = mirror_base.rstrip("/") + "/" + item["path"] if mirror_base else item["url"]
    result = {"name": item["name"], "version": item["version"], "path": item["path"], "url": url}
    temporary = None
    try:
        target = folder / item["path"]
        if mode == "check-urls":
            result.update(probe_url(item, url, timeout))
        else:
            # Resolve symlinks too: the output directory cannot redirect writes outside itself.
            if not target.resolve().is_relative_to(folder.resolve()):
                raise ValueError("Archive target escapes output directory")
            if mode == "download" and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + ".partial")
                with request(url, timeout) as response, temporary.open("wb") as output:
                    count = 0
                    while data := response.read(1024 * 1024):
                        count += len(data)
                        if count > item["bytes"]:
                            raise ValueError("Download exceeds pinned archive size")
                        output.write(data)
                verify_archive(temporary, item)
                temporary.replace(target)
            verify_archive(target, item)
            result.update(status="verified", sha256=item["sha256"], bytes=item["bytes"])
    except Exception as error:
        result.update(status="failed", error=str(error))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--download", action="store_true")
    modes.add_argument("--verify-local", action="store_true")
    modes.add_argument("--check-urls", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "dist/source-companion")
    parser.add_argument("--component", action="append", help="Exact component name, repeatable; omitted means all")
    parser.add_argument("--mirror-base", help="HTTPS mirror containing the same relative archive paths")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.workers < 1 or args.timeout <= 0:
        parser.error("workers and timeout must be positive")
    if args.mirror_base and not args.mirror_base.startswith("https://"):
        parser.error("mirror-base must use HTTPS")
    entries = load_sources(args.manifest)
    if args.component:
        requested = {name.casefold() for name in args.component}
        known = {item["name"].casefold() for item in entries}
        if requested - known:
            parser.error("Unknown component(s): " + ", ".join(sorted(requested - known)))
        entries = [item for item in entries if item["name"].casefold() in requested]
    mode = "download" if args.download else "verify-local" if args.verify_local else "check-urls"
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda item: process(item, mode, args.out, args.timeout, args.mirror_base), entries))
    failures = [item for item in results if item["status"] == "failed"]
    if mode == "download" and not failures and not args.component:
        # Existing notice/build tools consume these two cache manifests. Keep
        # their content pinned to the public catalog, never to a newer release.
        for native in (False, True):
            folder = args.out / "native" if native else args.out
            folder.mkdir(parents=True, exist_ok=True)
            sources = []
            for entry in entries:
                if entry["path"].startswith("native/") == native:
                    source = {key: value for key, value in entry.items() if key != "path"}
                    source["status"] = "downloaded"
                    sources.append(source)
            (folder / "SOURCES.json").write_text(json.dumps({
                "scope": "Verified upstream source archives pinned by SOURCE_DOWNLOADS.json; source availability is checked separately.",
                "sources": sources}, indent=2) + "\n", encoding="utf-8")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "mode": mode,
              "manifest_sha256": digest(args.manifest), "status": "failed" if failures else "passed",
              "archive_count": len(results), "scope": "selected components" if args.component else "all manifest entries",
              "limitation": "A dated technical check; not a guarantee of future availability or a public-release approval.",
              "sources": results}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{mode}: {len(results) - len(failures)}/{len(results)} passed; report: {args.report}")
    for item in failures:
        print(item["path"] + ": " + item["error"], file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
