# Building HAMLET from a clean source checkout

Use Windows x64 and CPython 3.11.9. Run these PowerShell commands from the
repository root. They install packages into a local environment only.

```powershell
py -3.11 -m venv .venv
$hamletPython = (Resolve-Path .venv/Scripts/python.exe).Path
& $hamletPython -m pip install -r requirements-release.lock.txt
& $hamletPython -m pip check
```

Confirm that the selected interpreter is Python 3.11.9 before building.
Do not update pinned dependencies while reproducing version 1.0.

## Runtime prerequisites

1. Obtain the unmodified Blender 4.3.2 Windows x64 distribution from Blender's
   official archive, and extract its contents so `blender/blender.exe` exists.
2. Obtain the OpenPose v1.7.0 hand files only under their applicable terms:
   `openpose/models/hand/pose_deploy.prototxt` and
   `openpose/models/hand/pose_iter_102000.caffemodel`. Preserve the upstream
   `openpose/LICENSE` and `openpose/Version.txt`. The exact model SHA-256 hashes
   are in `OPENPOSE_MODELS_NOTICE.txt`. The model files are not in this repository.
3. With those prerequisites, run the GUI using `& $hamletPython run_app.py`.

## First build

The repository already preserves the original source notices and Qt credits.
They can be used for the initial build; there is no dependency on an earlier
local build inventory.

```powershell
./build_release.ps1 -PythonExe $hamletPython
& $hamletPython tools/audit_dependency_licenses.py
```

The audit reads the newly generated PyInstaller TOC files and writes
`output/dependency_audit/inventory.json`. Review changes against the portable
reference `release/dependency-inventory.json` if any versions or dependencies
differ from the validated release.

## Corresponding upstream sources

Before creating the release ZIPs, populate `dist/source-companion/` with the
upstream archives and its `SOURCES.json` plus `native/SOURCES.json`.
The exact reference versions, URLs, byte counts and SHA-256 hashes are recorded
in `release/sources/`. These JSON files are inventories, not substitutes for the
archives. The sources can be prepared before an initial build with:

```powershell
& $hamletPython tools/fetch_release_sources.py --inventory release/dependency-inventory.json
& $hamletPython tools/prepare_source_notices.py
& $hamletPython tools/prepare_native_sources.py
& $hamletPython tools/generate_qt_notices.py
```

After building, use the actual audit inventory instead of the reference if the
selected packages differ. Verify all resulting archive hashes against
`release/sources/` for a reproduction of 1.0. `tools/fetch_runtime_terms.py` can
refresh Microsoft's original runtime terms; the prepared terms are already
included in this checkout. Regenerating notices changes build inputs: finish
preparation before rebuilding, and do not regenerate notices during a build.

## Release artifacts and checks

```powershell
./build_release.ps1 -PythonExe $hamletPython -Zip
```

This builds the executable, runs its integration checks and creates binary,
application-source and dependency-source ZIPs with hashes. All source archives
must be present for this step. The finalizer verifies notices, dependency
versions, actual executable version, model hashes and source/build consistency.
`dist/RELEASE_VALIDATION.json` records the outcome and remaining publication
items. Tests use synthetic inputs and do not establish anatomical accuracy.
Also test the extracted binary with a real project on a separate Windows PC.

Before publishing the binary, close the applicable items in
`RELEASE_LEGAL_CHECKLIST.md`, retain the exact source tag and dependency downloads,
and run `tools/finalize_release.py --test-results <results.json> --for-publication`.
The check rejects unresolved publication items; a successful technical build
does not grant third-party redistribution permission.

The optional guide-generation script uses `python-docx`, which is not needed to
run or build HAMLET. The distributed PDF user guide is already included.
