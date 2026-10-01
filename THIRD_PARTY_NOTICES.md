# Third-party notices for HAMLET

Third-party software and data retain their own licenses. HAMLET's application
license does not replace them. This candidate is not approved for public release:
the OpenPose model redistribution response is pending. Original HAMLET code is
GPL-3.0-only, with copyright held by its four authors as listed in NOTICE.txt.

HAMLET is developed for scientific research. This statement of purpose does not
add noncommercial restrictions to GPLv3 or other permissive licenses and does
not waive any conditions imposed by third-party licenses. See
OPENPOSE_MODELS_NOTICE.txt for the exact included hand-model files and status.

Open `third_party_licenses/index.html` (also available from About) for the original
texts, exact Python package versions and upstream notices. The full GPLv2,
GPLv3, LGPLv2.1 and LGPLv3 texts are in `third_party_licenses/common/`.
`SOURCE_CODE.md` explains the companion source downloads and rebuilding.

| Component | Version / scope | Terms and included evidence |
|---|---|---|
| Blender | 4.3.2, separate executable under `blender/` | GPL-3.0-or-later for the distributed combination, with many individual source files GPL-2.0-or-later and other compatible licenses; original `blender/copyright.txt` and `blender/license/`; exact source and dependency archives in the source companion. |
| Qt / PySide6 / shiboken6 | 6.10.2 | Retained Qt modules use the available LGPLv3 route, subject to their third-party licenses. Original source license trees and Qt attribution records are in `third_party_licenses/upstream-sources/Qt-6.10.2/` and `QtForPython-6.10.2/`. No commercial Qt license is asserted. |
| Qt WebEngine / Chromium | Qt WebEngine 6.10.2 | Qt and Chromium have separate obligations. `third_party_licenses/QtWebEngine-credits.html` reproduces the notices from the exact Qt source archive, including Chromium and its FFmpeg sources. It is a source-notice superset, not a list of only compiled components. |
| Python | CPython 3.11.9 | Python and native third-party terms in `third_party_licenses/Python/LICENSE.txt`; source companion includes CPython. |
| PyInstaller | See generated package inventory | GPL with the bootloader exception. This exception does not itself require HAMLET to use GPL. Original terms are included. |
| OpenCV | opencv-python 4.10.0.84 | OpenCV Apache-2.0, wrapper and third-party notices preserved. Its optional FFmpeg video-I/O DLL is excluded because HAMLET uses images and DNN inference. Blender and Chromium retain their own FFmpeg components. |
| VTK / Vedo / NumPy / SciPy / Pandas / Pillow and other Python dependencies | Exact versions in `dependency-licenses.json` | Original package notices, including vendored native libraries and font notices, are copied from this build's selected packages. Source archives accompany the release. GCC runtime exceptions, where used by scientific-library wheels, are preserved. |
| Three.js and OBJLoader / MTLLoader / OrbitControls | r128 | MIT; `assets/viewer3d/vendor/LICENSE.txt`. Loader/control files were compared with upstream r128. |
| OpenPose hand model files | `pose_deploy.prototxt`, `pose_iter_102000.caffemodel` | Upstream `openpose/LICENSE` and version file are preserved. Written redistribution confirmation is pending; presence here is not authorization and does not make the weights open source. |
| Microsoft Visual C++ runtime | Unmodified release DLLs | Microsoft terms and redistribution list in `third_party_licenses/Microsoft/`. Project owner confirmed a valid Visual Studio 2022 license on 2026-09-28. Microsoft components are not relicensed by HAMLET. Use and redistribution remain subject to those terms. |

## Qt selection

The retained native Qt modules are Core, Gui, Widgets, Network, OpenGL,
OpenGLWidgets, PrintSupport, Positioning, Qml, QmlMeta, QmlModels,
QmlWorkerScript, Quick, QuickWidgets, Svg, WebChannel, WebEngineCore and
WebEngineWidgets. Some are native dependencies of the viewer rather than direct
HAMLET imports. The application does not distribute a QML application tree.

Unused Charts, Graphs, DataVisualization, Quick3D, VirtualKeyboard and other
unneeded bindings/plugins are excluded by the build configuration. The QML
debugging, GPS device and PDF image plugins are omitted. Windows TLS uses
Schannel. Qt's optional Mesa software-OpenGL DLL is omitted; the application
uses the Windows rendering stack and Chromium's normal graphics path.

Qt/PySide6 libraries remain replaceable dynamic libraries. HAMLET does not
prohibit modification of LGPL components or reverse engineering to debug those
modifications. See `SOURCE_CODE.md` and the original LGPL terms for details.

## Provenance and scope

The package inventory records original notice paths and SHA-256 digests.
The upstream notice archive intentionally includes unused and build-only source
components; its presence is not evidence that every listed component ships.
The executable's release manifest and validation report describe the actual
files and tests. They are technical evidence, not a substitute for rights-holder
approval or a guarantee of legal compliance in every jurisdiction.

UJI is the authors' affiliation, not the copyright holder of HAMLET's original
code, according to the project owner's correction of 2026-09-30. Institutional
marks and other third-party assets are not relicensed by that confirmation.

## Primary references

- Qt licenses: https://doc.qt.io/qt-6.10/licensing.html
- Qt WebEngine: https://doc.qt.io/qt-6.10/qtwebengine-licensing.html
- Qt LGPL obligations: https://www.qt.io/development/open-source-lgpl-obligations
- Blender source/build recipes: https://download.blender.org/source/blender-4.3.2.tar.xz
- Blender dependencies: https://developer.blender.org/docs/handbook/release_process/build/
- Microsoft redistributable files: https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution
- OpenPose terms: https://github.com/CMU-Perceptual-Computing-Lab/openpose/blob/v1.7.0/LICENSE
- Three.js r128: https://github.com/mrdoob/three.js/blob/r128/LICENSE
