Third-party license texts and notices

The common/ directory contains unmodified reference license texts. Their
presence does not apply all these licenses to HAMLET or to every dependency.
Each component's original notices and applicable license determine its terms.

At build time, HAMLET.spec adds the original notice files of Python packages
selected by PyInstaller, Python's runtime license, and dependency-licenses.json.
That index records package versions, declared licenses, notice paths and hashes.
Blender keeps its own notices under blender/license/ and blender/copyright.txt.
The Three.js notice is under assets/viewer3d/vendor/LICENSE.txt. OpenPose model
terms are under openpose/LICENSE when the models are included.

This collection is not a declaration that every distribution obligation has
been satisfied. Qt/Chromium module attributions, corresponding source code,
native libraries and the permission to redistribute OpenPose models need their
own review. A commercial-license reference supplied by a dependency does not
mean HAMLET holds a commercial license.

Reference text provenance (collected 2026-09-28):
- GPL-3.0.txt: https://www.gnu.org/licenses/gpl-3.0.txt
- GPL-2.0.txt: unmodified blender/license/spdx/GPL-2.0-or-later.txt from bundled Blender 4.3.2.
- LGPL-2.1.txt: unmodified blender/license/spdx/LGPL-2.1-or-later.txt from bundled Blender 4.3.2.
- LGPL-3.0.txt: https://github.com/qt/qtbase/blob/v6.10.2/LICENSES/LGPL-3.0-only.txt

Whether a component allows later license versions is determined by its own
grant, not by the short filename of the reference text in this directory.
