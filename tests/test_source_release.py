"""Check source packaging failures that would break a clean rebuild."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from source_manifest import SOURCE_FILES, SOURCE_TREES, application_source_files
from check_source import check_source


class SourceReleaseTests(unittest.TestCase):
    def fixture(self, root):
        for directory in SOURCE_TREES:
            (root / directory).mkdir(parents=True, exist_ok=True)
        for name in SOURCE_FILES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")

    def test_sources_include_blender_scripts_but_exclude_local_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            names = ("src/assets/blender/render_hand_for_openpose.py", "src/__pycache__/main.pyc", "src/assets/~$locked.docx", "output/data.sav", ".local/Papers/draft.docx", "dist/HAMLET.exe")
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"example")
            selected = {p.relative_to(root).as_posix() for p in application_source_files(root)}
            self.assertIn(names[0], selected)
            self.assertFalse(set(names[1:]).intersection(selected))

    def test_missing_mandatory_source_fails_before_archiving(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / "CITATION.cff").unlink()
            with self.assertRaisesRegex(FileNotFoundError, "CITATION.cff"):
                application_source_files(root)

    def test_active_source_imports_and_assets_are_complete(self):
        result = check_source(ROOT)
        self.assertEqual(result["source_check"], "passed")
        self.assertIn("src/assets/data/pointsColor.csv", result["asset_references"])


if __name__ == "__main__":
    unittest.main()
