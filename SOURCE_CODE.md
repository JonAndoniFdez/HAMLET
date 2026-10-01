# Source code and rebuilding HAMLET

This is a local release candidate. Original HAMLET code is licensed under
GPL-3.0-only by its authors, identified in NOTICE.txt, following the project
owner's confirmation on 2026-09-30. LICENSE.txt contains the unchanged GPLv3 text.
Public distribution of the included OpenPose models remains unresolved.
Third-party components retain their own licenses and rights independently.

## Official source repository

Repository: https://github.com/JonAndoniFdez/HAMLET

This checkout starts a new history from the validated 1.0 source archive.
`release/SOURCE_SNAPSHOT.json` identifies that archive and the unchanged
application/build inputs. The final release tag and public dependency-source
download locations must still be recorded here when published. Do not use a
moving development branch as the only reference for a distributed binary.

## Source companion

The Zenodo record may contain HAMLET.zip alone if it clearly links to the exact
matching application source release and the required dependency sources hosted
elsewhere. The prepared source ZIPs may be used for those downloads; they need
not be attached to the same Zenodo record. Source downloads must be accessible
without additional payment or access restrictions and kept available as required
by the applicable licenses. A project's home page alone is not an exact source
download. Final public source locations remain to be established before release.

The dependency companion contains exact upstream archives for Qt 6.10.2
(including Chromium and its FFmpeg), Qt for Python 6.10.2, Blender 4.3.2,
CPython 3.11.9, VTK 9.5.1 and the selected Python distributions. `SOURCES.json`
records origin URLs, versions, byte counts and SHA-256 digests. `native/SOURCES.json`
records Blender's dependency archives and verifies them against the hashes in
Blender 4.3.2's `build_files/build_environment/cmake/versions.cmake`.

Blender's source archive includes the dependency build scripts and patches.
Qt's source archive includes module build files and Chromium sources. The
PySide source archive includes the Qt for Python build system. No HAMLET patches
are applied to these upstream runtimes. Sources for unused platforms/build
components can also be present; inclusion is not a statement that all are shipped.

The application source companion includes the readable Blender scripts, worker
modules, GUI, assets, build specification and release tools. The compressed
payload in the executable is packaging, not encryption, and does not replace
the source-code download or remove third-party source obligations.

## Building the application

Use Windows x64 and CPython 3.11.9. Create an isolated Python environment and
install `requirements-release.lock.txt`. This file captures the actual selected
environment; `requirements.txt` forwards to this lock. The historical development
list is retained in `docs/requirements-development-legacy.txt`.
Place the unmodified Blender 4.3.2 Windows x64 distribution under `blender/`.
Provide the two OpenPose hand model files under `openpose/models/hand/`, together
with their upstream `LICENSE` and `Version.txt`. Obtain these files only under
the applicable permissions.

Run the license/source preparation described in `docs/RELEASE_BUILD.md`, then
run `build_release.ps1` with that environment's Python. Qt DLL discovery is
restricted to the build interpreter and Windows directories. The build fails
if it selects a binary from an unrelated tool installation.

Rebuilding upstream runtimes is separate from rebuilding HAMLET. Follow the
build instructions included in each source archive. For Blender, use the
4.3.2 source tree's CMake scripts and `build_files/build_environment`; its source
cache URLs and hashes are recorded in the native manifest. For Qt use the
`configure`/CMake instructions in the Qt 6.10.2 archive; Qt for Python's source
tree contains the binding build scripts. These packages are not a claim that
every upstream binary has been independently rebuilt bit for bit.

## Replacing or debugging LGPL libraries

Qt/PySide6 and other shared libraries remain ordinary dynamically loaded files
in the onedir distribution. HAMLET applies no signature or hash enforcement
to replacement libraries. Close HAMLET, make a backup, and replace a library
with an ABI-compatible Windows x64 build. Keep a consistent Qt/PySide6/shiboken
set and its plugins, resources and runtime dependencies. If a changed interface
requires it, rebuild the application using the provided source and build tools.
Re-run the release self-test and your normal project workflow afterwards.

The LGPL's rights concerning modification, library replacement and reverse
engineering to debug those modifications are not restricted by HAMLET's
application-layer terms. The complete GPL/LGPL texts are in
`third_party_licenses/common/`; they govern the relevant components.

Microsoft system/runtime libraries retain Microsoft's separate terms and are
not relicensed under GPL/LGPL. The project owner confirmed a valid Visual Studio
2022 license on 2026-09-28. The original runtime terms, Visual Studio terms and
redistribution list are supplied in `third_party_licenses/Microsoft/`.

## Publication record

Before publication, record the final approved license, authors, exact version,
source tag/commit and persistent download URLs in the release record. The
source version is 1.0.0.0 for the first public release, named 1.0. The reserved
software DOI is 10.5281/zenodo.23056922; it becomes active upon publication.
The final build's version and hashes are recorded in release-manifest.json.
The original application code is GPLv3; do not describe the entire bundled
package, including OpenPose models, as uniformly GPL-licensed or unrestricted.
