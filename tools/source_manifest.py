"""Select the maintained files included in an application source release."""
from __future__ import annotations

from pathlib import Path


SOURCE_TREES = ("src", "tools", "tests", "third_party_licenses")
SOURCE_FILES = (
    ".gitignore", "README.md", "run_app.py", "HAMLET.spec", "build_release.ps1",
    "version_info.txt", "requirements.txt", "requirements-release.lock.txt",
    "LICENSE.txt", "THIRD_PARTY_LICENSES.txt", "NOTICE.txt", "SOURCE_CODE.md", "THIRD_PARTY_NOTICES.md",
    "RELEASE_LEGAL_CHECKLIST.md", "release-approvals.json", "README_RELEASE.txt",
    "CITATION.cff", "OPENPOSE_MODELS_NOTICE.txt", "docs/README.pdf",
    "docs/RELEASE_BUILD.md", "docs/PROJECT_STRUCTURE.md", "docs/EXTERNAL_RUNTIMES.md",
    "docs/DEPENDENCY_SOURCES.md", "third_party_licenses/SOURCE_DOWNLOADS.json",
)
EXCLUDED_PARTS = {"__pycache__", ".git", ".pytest_cache", ".ruff_cache"}


def application_source_files(root: Path) -> list[Path]:
    """Return sorted paths, failing on missing mandatory release inputs.

    Working datasets, manuscripts, builds and upstream runtime/source trees are
    outside the public source snapshot. Large generated third-party notices are
    recreated from the pinned official archives when building the portable app.
    """
    root = Path(root).resolve()
    paths = {root / name for name in SOURCE_FILES}
    missing = sorted(str(p.relative_to(root)) for p in paths if not p.is_file())
    for directory in SOURCE_TREES:
        tree = root / directory
        if not tree.is_dir():
            missing.append(directory + "/")
        paths.update(
            p for p in tree.rglob("*")
            if p.is_file()
            and not EXCLUDED_PARTS.intersection(p.relative_to(root).parts)
            and not p.relative_to(root).as_posix().startswith("third_party_licenses/upstream-sources/")
            and p.relative_to(root).as_posix() != "third_party_licenses/QtWebEngine-credits.html"
            and p.suffix.lower() not in {".pyc", ".pyo", ".tmp"}
            and not p.name.startswith("~$")
        )
    if missing:
        raise FileNotFoundError("Missing application source inputs: " + ", ".join(missing))
    for path in paths:
        if not path.resolve().is_relative_to(root):
            raise ValueError(f"Source input points outside the project: {path}")
    return sorted(paths, key=lambda p: p.relative_to(root).as_posix())
