# HAMLET 1.0: third-party software notices

The readable component-by-component license document is [THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt).
It covers Blender 4.3.2, the CMU OpenPose hand models, Qt/PySide6/shiboken6 and
Qt WebEngine 6.10.2, OpenCV 4.10, Python 3.11.9, VTK 9.5.1, Vedo 2025.5.4,
Three.js r128, Trimesh 4.11.4, PyInstaller and the Microsoft Visual C++ Runtime.

Original HAMLET code is **GPL-3.0-only**; see [LICENSE.txt](LICENSE.txt) and
[NOTICE.txt](NOTICE.txt). Third-party software and models retain their original
licenses, copyright notices and terms. OpenPose hand models retain CMU's academic
noncommercial research terms. The complete package has multiple licenses.

Open [the offline license index](third_party_licenses/index.html) for original
notices and [the package inventory](third_party_licenses/dependency-licenses.json)
for the exact libraries selected by this build. Supporting libraries such as
NumPy, SciPy, pandas, Pillow and openpyxl are included in that inventory.

Blender's original notices remain under `blender/license/` and
`blender/copyright.txt`. OpenPose's unmodified terms and model provenance are in
`openpose/LICENSE`, `openpose/Version.txt` and `OPENPOSE_MODELS_NOTICE.txt`.
Qt WebEngine's local Chromium credits preserve the separate licenses of its
internal components, including LGPL-2.1 components. Qt and PySide6 libraries
remain dynamically linked and replaceable; see [SOURCE_CODE.md](SOURCE_CODE.md).

Source-notice collections can contain notices for other platforms or build-only
components. The installed-package inventory and release manifest identify the
selected files; a source notice is not a claim that every upstream component
ships. Full original notices govern over this descriptive summary.
