"""Protect pinned source access against corrupt archives and misleading URLs."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from download_dependency_sources import load_sources, probe_url, process


class DependencySourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "build").mkdir(exist_ok=True)

    def item(self, data=b"correct source archive"):
        return {"name": "Example", "version": "1.0", "path": "example.tar.gz",
                "filename": "example.tar.gz", "url": "https://example.invalid/example.tar.gz",
                "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}

    def test_corrupt_cached_archive_is_rejected_without_replacing_it(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as directory:
            folder = Path(directory)
            path = folder / "example.tar.gz"
            path.write_bytes(b"incorrect source data!")
            with patch("download_dependency_sources.request") as network:
                result = process(self.item(), "download", folder, 1, None)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(path.read_bytes(), b"incorrect source data!")
            network.assert_not_called()

    def test_bad_download_is_not_promoted_to_verified_archive(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as directory:
            folder = Path(directory)
            with patch("download_dependency_sources.request", return_value=io.BytesIO(b"wrong bytes")):
                result = process(self.item(), "download", folder, 1, None)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(list(folder.iterdir()), [])

    def test_successful_download_is_verified_and_reused_offline(self):
        data = b"correct source archive"
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as directory:
            folder = Path(directory)
            with patch("download_dependency_sources.request", return_value=io.BytesIO(data)):
                self.assertEqual(process(self.item(data), "download", folder, 1, None)["status"], "verified")
            with patch("download_dependency_sources.request") as network:
                self.assertEqual(process(self.item(data), "download", folder, 1, None)["status"], "verified")
                network.assert_not_called()

    def test_html_success_response_is_not_source_availability(self):
        response = io.BytesIO(b"<!doctype html><html>Error</html>")
        response.headers = {"Content-Type": "text/html"}
        response.status = 200
        with patch("download_dependency_sources.request", return_value=response):
            with self.assertRaisesRegex(ValueError, "HTML"):
                probe_url(self.item(), self.item()["url"], 1)

    def test_unsafe_manifest_path_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as directory:
            path = Path(directory) / "catalog.json"
            for value in ("../example.tar.gz", "/example.tar.gz", "native\\example.tar.gz", "C:/example.tar.gz"):
                item = self.item()
                item["path"] = value
                path.write_text(json.dumps({"schema_version": 1, "sources": [item]}))
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Unsafe"):
                    load_sources(path)

    def test_catalog_versions_match_locked_environment(self):
        import re
        versions = {re.sub(r"[-_.]+", "-", item["name"].lower()): item["version"]
                    for item in load_sources(ROOT / "third_party_licenses/SOURCE_DOWNLOADS.json")}
        aliases = dict.fromkeys(("pyside6", "pyside6-addons", "pyside6-essentials", "shiboken6"), "qtforpython")
        locked = {}
        for line in (ROOT / "requirements-release.lock.txt").read_text().splitlines():
            match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s]+)", line.strip())
            if match:
                name = re.sub(r"[-_.]+", "-", match[1].lower())
                locked[aliases.get(name, name)] = match[2]
        for name, version in versions.items():
            if name not in {"blender", "python", "qt"} and not name.startswith("blender-"):
                with self.subTest(package=name):
                    self.assertEqual(locked.get(name), version)
        self.assertEqual(versions["blender"], "4.3.2")
        self.assertEqual(versions["python"], "3.11.9")
        self.assertEqual(versions["qt"], "6.10.2")


if __name__ == "__main__":
    unittest.main()
