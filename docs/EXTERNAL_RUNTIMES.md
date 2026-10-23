# External runtimes for running and building HAMLET 1.0 from source

The ready-to-run `HAMLET.zip` already includes these runtime files. This page is
for developers starting from the GitHub source checkout. Download external
components from their official projects; do not add the installations or model
weights to Git. Preserve each component's original license and notices.

## Windows x64 / CPython 3.11.9

[Official Python 3.11.9 release](https://www.python.org/downloads/release/python-3119/)
provides the Windows 64-bit installer. Create an isolated environment and install
the exact packages selected for this release:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-release.lock.txt
```

PySide6/shiboken6 6.10.2, OpenCV 4.10.0.84, VTK 9.5.1, Vedo 2025.5.4,
Trimesh 4.11.4, PyInstaller and the selected Python dependencies are installed
from their official PyPI distributions through this lock file. Qt WebEngine is
included by PySide6_Addons. Do not mix Qt DLLs from other applications into the
build. [Official PyPI](https://pypi.org/) and the projects linked in the source
catalog identify the publishers.

## Blender 4.3.2

Download the unmodified
[official Blender 4.3.2 Windows x64 ZIP](https://download.blender.org/release/Blender4.3/blender-4.3.2-windows-x64.zip)
from [Blender's 4.3 release directory](https://download.blender.org/release/Blender4.3/).
Extract it, then place the contents of its `blender-4.3.2-windows-x64` directory
under the checkout's `blender/` directory, so `blender/blender.exe` exists.
Keep the complete runtime tree and its license files. HAMLET's own scripts under
`src/assets/blender/` are separate from this Blender installation.

## OpenPose 1.7.0 hand model files

HAMLET performs hand inference through OpenCV DNN. It needs the following
OpenPose data files, not an OpenPose executable, CUDA or cuDNN installation:

| Local path | Official origin |
| --- | --- |
| `openpose/models/hand/pose_deploy.prototxt` | [OpenPose v1.7.0 hand network definition](https://raw.githubusercontent.com/CMU-Perceptual-Computing-Lab/openpose/v1.7.0/models/hand/pose_deploy.prototxt) |
| `openpose/models/hand/pose_iter_102000.caffemodel` | [CMU model download](http://posefs1.perception.cs.cmu.edu/OpenPose/models/hand/pose_iter_102000.caffemodel), as specified in the [official v1.7.0 model download script](https://github.com/CMU-Perceptual-Computing-Lab/openpose/blob/v1.7.0/models/getModels.bat) |
| `openpose/LICENSE` | [Original OpenPose v1.7.0 license](https://raw.githubusercontent.com/CMU-Perceptual-Computing-Lab/openpose/v1.7.0/LICENSE) |

Use the official [OpenPose repository and installation documentation](https://github.com/CMU-Perceptual-Computing-Lab/openpose/tree/v1.7.0)
for model access and applicable terms. The model server is operated by CMU;
its availability is separate from HAMLET's dependency-source URL checks. If CMU
changes model hosting, follow its official instructions and verify the exact
files below. A newer or different network is not a drop-in substitute.

The release records local version provenance as `openpose/Version.txt`. Preserve
the original version file when obtaining an upstream distribution, or record
the official tag `v1.7.0` in this file when acquiring its files separately.

Expected SHA-256 digests of the hand model files used by HAMLET 1.0:

```text
d722796d87f251aadf8eb1af9dca03b3732e8a1d1bb524961a29c8e5073a8251  pose_deploy.prototxt
f313aa5ef031ac91606e1a0383daa14be241a6e1a91c1155283dd28503c79c2d  pose_iter_102000.caffemodel
```

These identify the release's files; they do not certify upstream availability
or extend CMU's license. Read [OPENPOSE_MODELS_NOTICE.txt](../OPENPOSE_MODELS_NOTICE.txt)
and keep the upstream terms when packaging the model files.

## Other runtime components and source archives

The offline Three.js r128 viewer assets already reside under
`src/assets/viewer3d/vendor/`, with their MIT notice. Official origin:
[Three.js r128](https://github.com/mrdoob/three.js/tree/r128).
The Visual C++ runtime files required by the release are collected from the
installed Python/Qt/Blender distributions under their original redistribution
terms; see `third_party_licenses/Microsoft/`. Avoid copying unrelated DLLs into
the checkout or adding development tools to HAMLET's runtime search path.

[DEPENDENCY_SOURCES.md](DEPENDENCY_SOURCES.md) and
[SOURCE_DOWNLOADS.json](../third_party_licenses/SOURCE_DOWNLOADS.json) provide the
exact corresponding dependency source archives, official URLs and integrity
digests. Those archives are downloaded only for build/notices preparation and
source verification; they are not committed to Git or necessary to run HAMLET.

Once the runtimes are in place, follow [RELEASE_BUILD.md](RELEASE_BUILD.md).
