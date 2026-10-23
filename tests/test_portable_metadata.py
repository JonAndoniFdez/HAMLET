"""Protect the requested repository link and identifier-free application docs."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from check_portable_release import check_metadata_bytes, REPOSITORY


class PortableMetadataTests(unittest.TestCase):
    def test_application_metadata_has_no_publication_identifier(self):
        for name in ("README_RELEASE.txt", "CITATION.cff", "NOTICE.txt", "THIRD_PARTY_LICENSES.txt", "SOURCE_CODE.md", "THIRD_PARTY_NOTICES.md", "OPENPOSE_MODELS_NOTICE.txt"):
            with self.subTest(name=name):
                check_metadata_bytes((ROOT / name).read_bytes(), name)
        self.assertIn(REPOSITORY, (ROOT / "README_RELEASE.txt").read_text(encoding="utf-8"))

    def test_scanner_rejects_identifier_forms(self):
        for value in (b"10.12345/example", b"https://doi.org/10.12345/example"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                check_metadata_bytes(value, "example")


if __name__ == "__main__":
    unittest.main()
