# HAMLET

**Hand Anthropometric Measurement and Landmark Extraction Tool** — version 1.0.

HAMLET is a Windows desktop application for scientific research on hand
anthropometry using textured 3D hand models. It supports anatomical landmark
detection, interactive 2D and 3D review, manual adjustment and measurement export.

## Use the application

The ready-to-run Windows package is named `HAMLET.zip`. Extract the complete
archive and launch `HAMLET.exe`; keep its accompanying files together.
Separate Python and Blender installations are not needed for that package.
The source download from GitHub is intended for development and rebuilding.
See the [user guide](docs/README.pdf) for the application workflow.

The first binary release and Zenodo record are being prepared. The reserved DOI
is [10.5281/zenodo.23056922](https://doi.org/10.5281/zenodo.23056922); it becomes
active when the record is published. This repository does not contain the
Windows runtime, Blender binaries or OpenPose model files.

## Run from source and build

Use Windows x64 and CPython 3.11.9. The dependencies are pinned in
`requirements-release.lock.txt`. Follow [the build instructions](docs/RELEASE_BUILD.md)
to set up an isolated environment and obtain the required runtime and model files.
Then run `python run_app.py` with that environment.

The repository includes the application modules, readable Blender scripts,
assets, build specification, release validation tools and original license
notices. [SOURCE_CODE.md](SOURCE_CODE.md) explains corresponding sources and
replacement of LGPL libraries. Versioned upstream source inventories are in
`release/sources/`; those inventories are not the source archives themselves.

## Authors and citation

Jon A. Fernández-Moyano, Verónica Gracia-Ibáñez, Alba Roda-Sales and
Carlos Gonell-Cruz.

Department of Mechanical Engineering and Construction, Universitat Jaume I.
Copyright in original HAMLET code belongs to its authors.
[CITATION.cff](CITATION.cff) contains the citation metadata and authors' ORCIDs.

## Licenses

Original HAMLET code is licensed under **GNU GPL version 3 only**
([LICENSE.txt](LICENSE.txt), [NOTICE.txt](NOTICE.txt)). Third-party software,
assets and models retain their own terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
The scientific research purpose does not add a noncommercial restriction to GPLv3.

OpenPose models are external to this source repository and are not covered by
HAMLET's GPL grant. See [OPENPOSE_MODELS_NOTICE.txt](OPENPOSE_MODELS_NOTICE.txt)
for model provenance and the redistribution clarification still pending for the
binary package. Publishing these application sources does not resolve that item.

## Versions

This repository starts with the current 1.0 source snapshot and has an independent
history. The application code and build tools match the validated source archive
identified in [release/SOURCE_SNAPSHOT.json](release/SOURCE_SNAPSHOT.json).
Repository links and build documentation have been updated for this checkout.
Future releases should retain a stable tag and corresponding source downloads;
never move a published release tag to different code.
