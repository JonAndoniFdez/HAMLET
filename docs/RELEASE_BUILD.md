# Build HAMLET 1.0 for Windows x64

The GitHub source tree contains HAMLET code and build tools. The portable
`HAMLET.zip` contains the required runtimes and is intended for end users.
Runtime installations, OpenPose weights and dependency source archives are not
committed to the source repository.

## 1. Prepare the environment and official runtimes

Use Windows x64 and CPython 3.11.9. Follow
[EXTERNAL_RUNTIMES.md](EXTERNAL_RUNTIMES.md) for the official Python, Blender
4.3.2 and OpenPose hand model downloads and exact local paths. Create an isolated
Python environment and install `requirements-release.lock.txt` without updating
individual packages. The commands below use that environment's Python.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-release.lock.txt
.\.venv\Scripts\python.exe -B tools/check_source.py --check-environment --report build/source-check.json
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

## 2. Obtain the pinned source archives and original notices

These archives remain in the ignored `dist/source-companion/` cache and are
fetched from the official URLs in `third_party_licenses/SOURCE_DOWNLOADS.json`.
No dependency source hosting by the HAMLET team is required by this workflow.
Allow approximately 3.20 GB for the archived sources.

```powershell
.\.venv\Scripts\python.exe -B tools/download_dependency_sources.py --download --report build/source-downloads.json
.\.venv\Scripts\python.exe -B tools/download_dependency_sources.py --verify-local --report build/source-integrity.json
.\.venv\Scripts\python.exe -B tools/download_dependency_sources.py --check-urls --report build/source-availability.json
.\.venv\Scripts\python.exe -B tools/prepare_source_notices.py
.\.venv\Scripts\python.exe -B tools/generate_qt_notices.py
.\.venv\Scripts\python.exe -B tools/fetch_runtime_terms.py
```

`download_dependency_sources.py` creates the legacy cache metadata files
`SOURCES.json` and `native/SOURCES.json` needed by the build/notice tools.
`prepare_source_notices.py` regenerates original upstream notices and Blender
build-recipe excerpts under the ignored `third_party_licenses/upstream-sources/`.
`generate_qt_notices.py` creates the offline Chromium attribution page from the
exact Qt 6.10.2 source archive. Do not run the build while regenerating notices.
Do not replace pinned source digests to make a failed download pass.

## 3. Build, test and package

```powershell
.\build_release.ps1 -PythonExe .\.venv\Scripts\python.exe -Zip
```

The script checks source inputs and dependency versions, runs the regression
suite, invokes PyInstaller, verifies the packaged Blender preview scripts, runs
the frozen executable's integration checks and creates `dist/HAMLET.zip`.
`HAMLET.spec` selects Qt modules and obtains license notices from the actual
build inputs. Blender's runtime remains separate from HAMLET's DLL analysis.
The license index is accessible locally from **About** in the application.

The result includes Python, Blender, OpenPose hand data, Qt/PySide6, OpenCV,
VTK/Vedo and supporting runtime files. It requires no runtime downloads.
The Windows executable uses the UJI icon. The English guide at `docs/README.pdf`
is available from **Getting started**. Keep the complete portable directory
when testing or copying the application.

## 4. Inspect the release evidence

Review `dist/RELEASE_VALIDATION.json`, `dist/SHA256SUMS.txt` and the self-test
results under `build/release-test-*/`. The finalizer verifies runtime selection,
original notices, the exact source catalog, model hashes, executable tests,
build-input hashes and ZIP CRCs. Synthetic tests verify execution, not anatomical
accuracy or an independent clean Windows installation. Test the extracted ZIP
with a real project on the intended Windows machines.

The release README identifies https://github.com/JonAndoniFdez/HAMLET. The
Zenodo identifier is in the GitHub README only; HAMLET's own portable documents
contain no publication identifier. Original third-party scientific references
are preserved. Source ZIPs are optional and are not needed to run HAMLET.

## 5. Publish matching versions

Publish the selected source snapshot as tag `v1.0`, preserving repository
history. Attach the verified `HAMLET.zip` and its SHA-256 file to the GitHub
release for that tag. Deposit the same binary ZIP on Zenodo, put the GitHub link
in its description and retain the Zenodo DOI link in the repository README.
[DEPENDENCY_SOURCES.md](DEPENDENCY_SOURCES.md) supplies the official corresponding
source links and the GPLv3 section 6(d) access-maintenance procedure. Do not
commit the external runtimes, model weights, downloaded archives, private data,
intermediate build directories or credentials.
