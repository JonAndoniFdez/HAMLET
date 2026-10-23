# Source code and rebuilding HAMLET

Original HAMLET code is licensed under
GPL-3.0-only by its authors, identified in NOTICE.txt, following the project
owner's confirmation on 2026-09-30. LICENSE.txt contains the unchanged GPLv3 text.
Third-party components retain their own licenses and rights independently.

## Obtaining the corresponding sources

For **dependency sources**, start with
[the download instructions and version-specific links](docs/DEPENDENCY_SOURCES.md).
The maintained [source catalog](third_party_licenses/SOURCE_DOWNLOADS.json)
identifies the exact archive names, versions, HTTPS downloads, byte counts and
SHA-256 digests. It also records Blender's original dependency-recipe hashes.
The dated evidence in `third_party_licenses/source-availability/` distinguishes
full local integrity verification from live HTTP availability checks.

For **HAMLET's own source**, use the [v1.0 source release](https://github.com/JonAndoniFdez/HAMLET/tree/v1.0)
or its [source archive](https://github.com/JonAndoniFdez/HAMLET/archive/refs/tags/v1.0.zip).
The [Windows release](https://github.com/JonAndoniFdez/HAMLET/releases/tag/v1.0)
provides the portable application. The source tree contains no Blender runtime,
OpenPose model weights, Python installation or Qt binaries. Obtain these from
the official sources in [EXTERNAL_RUNTIMES.md](docs/EXTERNAL_RUNTIMES.md).

The Zenodo record may contain HAMLET.zip alone if its download description clearly
links to the matching application source release and these dependency-source
directions. Neither an extra application-source ZIP nor a dependency-source ZIP
with a particular name is required. Equivalent, complete source access is required.
Source access must involve no additional payment, login or permission request.

[GPLv3 section 6(d)](https://www.gnu.org/licenses/gpl-3.0.html#section6)
expressly permits corresponding sources on a different server, including a
third-party server. Clear directions must appear next to the object-code download;
the distributor remains responsible for source availability. See also the
[FSF explanation](https://www.gnu.org/licenses/gpl-faq.en.html#SourceAndBinaryOnDifferentSites).
The instructions document the maintenance and mirror procedure; a successful
check today does not guarantee future availability. Dependency sources are hosted
by their upstream projects; HAMLET does not operate a dependency download server.
The source-access procedure follows the GPLv3 section 6(d) third-party-server
option and retains the distributor's obligation to maintain access. GPL/LGPL
texts, rather than summaries on vendor websites, govern that option.

## Contents and provenance

The local, untracked dependency source cache contains exact upstream archives for Qt 6.10.2
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

The application source release includes the readable HAMLET-authored Blender scripts, worker
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

The release uses GPL-3.0-only for original HAMLET code, the four authors in
NOTICE.txt, the source tag `v1.0` and the GitHub URLs linked above. Record the
actual published source commit and uploaded asset digests in the release evidence.
The Windows version is 1.0.0.0 for the first public release, named 1.0.
The final build's version and hashes are recorded in release-manifest.json.
The original application code is GPLv3; do not describe the entire bundled
package, including OpenPose models, as uniformly GPL-licensed or unrestricted.
