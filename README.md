# HAMLET 1.0

**Hand Anthropometric Measurement and Landmark Extraction Tool** is a Windows
application developed at Universitat Jaume I for hand anthropometry from
textured 3D **flat-hand** models. It guides anatomical landmark detection,
interactive 2D/3D review, manual adjustment and measurement export.

## Download and citation

- [Windows 64-bit application, release v1.0](https://github.com/JonAndoniFdez/HAMLET/releases/tag/v1.0)
- [Zenodo archival record: 10.5281/zenodo.23056922](https://doi.org/10.5281/zenodo.23056922)
- [Exact v1.0 application source](https://github.com/JonAndoniFdez/HAMLET/tree/v1.0)

Extract the complete `HAMLET.zip` archive and launch `HAMLET.exe`, keeping all
accompanying files and folders together. The portable package includes Python,
Blender, Qt, the OpenPose hand model files and the other required runtime
components. No additional runtime downloads or separate Python/Blender
installations are required. Open **Getting started** for the included user guide.

## Run from source

Use **Windows x64 and CPython 3.11.9**. This repository contains HAMLET source,
assets, tests, build scripts and license/source-access information. External
runtime installations, model weights and dependency source archives are not
stored here. Obtain them from their official projects using
[EXTERNAL_RUNTIMES.md](docs/EXTERNAL_RUNTIMES.md).

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-release.lock.txt
.\.venv\Scripts\python.exe -B run_app.py
```

Before running, place Blender 4.3.2 under `blender/` and the two OpenPose hand
model files under `openpose/models/hand/`, with their original terms and version
information. HAMLET uses OpenCV DNN for inference; the OpenPose executable,
CUDA and cuDNN are not required for this workflow.

## Build the portable application

Follow [the complete build instructions](docs/RELEASE_BUILD.md). Dependency
versions are fixed in `requirements-release.lock.txt`. Build preparation obtains
original notices and dependency sources from official, versioned downloads;
these generated files remain outside Git.

```powershell
.\.venv\Scripts\python.exe -B tools/check_source.py --check-environment --report build/source-check.json
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\build_release.ps1 -PythonExe .\.venv\Scripts\python.exe -Zip
```

The result is `dist/HAMLET.zip`. The build checks and executable self-tests must
pass before distribution. Tests use synthetic data and verify execution;
inspect landmarks and measurements for your own data.

## Corresponding sources and licenses

Original HAMLET code is **GPL-3.0-only**; see [LICENSE.txt](LICENSE.txt) and
[NOTICE.txt](NOTICE.txt). Third-party components retain their respective terms,
described in [THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt).
OpenPose's academic/noncommercial terms apply to its models separately.
The research purpose does not add a noncommercial restriction to HAMLET's GPL.

[SOURCE_CODE.md](SOURCE_CODE.md) covers rebuilding and replacing LGPL libraries.
[DEPENDENCY_SOURCES.md](docs/DEPENDENCY_SOURCES.md) lists exact official source
downloads; [SOURCE_DOWNLOADS.json](third_party_licenses/SOURCE_DOWNLOADS.json)
records versions, sizes and SHA-256 digests. HAMLET does not provide a dependency
hosting service. Sources remain on the official projects' download servers,
using GPLv3 section 6(d)'s third-party-server option with clear directions.
Dated integrity and availability evidence is included under
`third_party_licenses/source-availability/`.

## Authors

- Jon A. Fernández-Moyano: [0000-0002-8242-2834](https://orcid.org/0000-0002-8242-2834)
- Verónica Gracia-Ibáñez: [0000-0003-0681-7356](https://orcid.org/0000-0003-0681-7356)
- Alba Roda-Sales: [0000-0002-4644-1886](https://orcid.org/0000-0002-4644-1886)
- Carlos Gonell-Cruz: [0009-0005-3975-8307](https://orcid.org/0009-0005-3975-8307)

Department of Mechanical Engineering and Construction, Universitat Jaume I.
Copyright in original HAMLET code belongs to its authors.
[CITATION.cff](CITATION.cff) provides machine-readable citation metadata.
[PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) describes the maintained code.
