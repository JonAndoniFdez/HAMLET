"""Explicit, isolated integration checks run inside the frozen executable."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
import traceback


def main():
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ["APPDATA"] = str(out / "settings")
    os.environ.setdefault("QT_QPA_PLATFORM", "windows")
    results = []

    def record(name, detail=""):
        results.append({"test": name, "status": "passed", "detail": detail})
        (out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    try:
        import numpy as np
        import pandas as pd
        import cv2
        from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
        from PySide6.QtCore import QUrl
        from PySide6.QtWebEngineCore import QWebEnginePage
        from src.core.paths import app_root
        assert getattr(sys, "frozen", False), "This test must run in the packaged EXE"
        app = QApplication([])
        def unexpected_dialog(*args, **kwargs):
            raise RuntimeError("Unexpected message box: " + str(args[1:]))
        QMessageBox.warning = unexpected_dialog
        QMessageBox.critical = unexpected_dialog
        from src.gui.appWindow import AppWindow
        window = AppWindow()
        record("application startup and pages")

        from PySide6.QtWidgets import QLabel
        from src.gui.pages.welcome_page import AboutDialog, _get_app_version
        version = _get_app_version()
        assert version == 'v1.0.0', version
        about = AboutDialog(version=version)
        about.show()
        app.processEvents()
        about_text = '\n'.join(label.text() for label in about.findChildren(QLabel))
        assert all(name in about_text for name in ('Fernández-Moyano', 'Gracia-Ibáñez', 'Roda-Sales', 'Gonell-Cruz', 'GPL-3.0-only'))
        about.grab().save(str(out / 'about.png'))
        assert (app_root() / 'LICENSE.txt').read_bytes() == (app_root() / 'third_party_licenses/common/GPL-3.0.txt').read_bytes()
        assert (app_root() / 'CITATION.cff').is_file()
        readme = (app_root() / 'README.txt').read_text(encoding='utf-8')
        assert 'https://github.com/JonAndoniFdez/HAMLET' in readme
        assert (app_root() / 'THIRD_PARTY_LICENSES.txt').is_file()
        about.close()
        record('Release version, author credits and GPL notice', version)

        texture = out / "texture.png"
        cv2.imwrite(str(texture), np.full((64, 64, 3), (220, 130, 30), dtype=np.uint8))
        obj = out / "sample.obj"
        obj.write_text("mtllib sample.mtl\no Sample\nv -1 -1 0\nv 1 -1 0\nv 1 1 0\nv -1 1 0\nvt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\nusemtl TestMaterial\nf 1/1 2/2 3/3 4/4\n")
        (out / "sample.mtl").write_text("newmtl TestMaterial\nKd 1 1 1\nmap_Kd texture.png\n")
        points = out / "points.csv"
        pd.DataFrame({"x3d": [0.0], "y3d": [0.0], "z3d": [0.0]}).to_csv(points, index=False)

        from src.gui.pages.threshold_page import BlenderPreviewDialog
        class InlinePool:
            def start(self, worker):
                worker.run()
        for mode in ("manual", "smartuv"):
            dialog = BlenderPreviewDialog(obj, texture, out / mode, size=64, margin=2)
            dialog.threadpool = InlinePool()
            dialog.start()
            (out / (mode + ".log")).write_text(dialog.log_box.toPlainText(), encoding="utf-8")
            assert not dialog._failed, dialog.status.text()
            assert dialog.result() == QDialog.Accepted
            assert dialog.preview_obj_path.is_file()
            baked = cv2.imread(str(dialog.preview_texture_path))
            assert baked is not None and baked.shape[:2] == (64, 64)
            assert np.any(baked[:, :, 0].astype(int) > baked[:, :, 2].astype(int) + 50)
            record("Blender preview " + mode)

        from src.core.openpose_hand import run_openpose_hand_2d
        detection = run_openpose_hand_2d(texture, out / "openpose", in_height=64)
        assert detection.ok, detection.message
        assert detection.n_points == 21 and detection.keypoints_csv.is_file()
        record("OpenCV DNN model loading and inference", "Synthetic image; validates execution, not anatomical accuracy")

        from src.core.openpose_render import render_hand_topview_for_openpose
        rendered = render_hand_topview_for_openpose(obj, out / "render", resolution=64)
        (out / "render.log").write_text(rendered.stdout + rendered.stderr, encoding="utf-8")
        assert rendered.ok, rendered.message
        record("Blender top-view render")

        import vtkmodules.vtkRenderingOpenGL2
        from vtkmodules.vtkFiltersSources import vtkSphereSource
        from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, vtkRenderer, vtkRenderWindow
        sphere = vtkSphereSource()
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(sphere.GetOutputPort())
        actor = vtkActor(); actor.SetMapper(mapper)
        renderer = vtkRenderer(); renderer.AddActor(actor)
        render_window = vtkRenderWindow(); render_window.SetOffScreenRendering(1)
        render_window.AddRenderer(renderer); render_window.SetSize(64, 64)
        render_window.Render(); render_window.Finalize()
        record("VTK offscreen rendering")

        frame = pd.DataFrame({"measurement": ["test"], "value": [3.5]})
        excel = out / "export.xlsx"
        frame.to_excel(excel, index=False, engine="openpyxl")
        assert pd.read_excel(excel).iloc[0]["value"] == 3.5
        from scipy.spatial import cKDTree
        assert cKDTree([[0, 0, 0], [1, 0, 0]]).query([0, 0, 0])[0] == 0
        record("Excel export/readback and spatial calculations")

        def wait_for(predicate, timeout=45):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                app.processEvents()
                if predicate():
                    return
                time.sleep(0.02)
            raise TimeoutError("Qt event/JavaScript check timed out")

        from src.gui.pages.view3d_dialog import View3DDialog
        viewer = View3DDialog(obj, texture, points)
        viewer.show()
        state = {}
        query = "JSON.stringify({ready:typeof renderer!=='undefined'&&!!renderer&&handMeshes.length>0, error:document.getElementById('errorbox')?.textContent, points:document.getElementById('point_count')?.textContent})"
        def update(value):
            if value:
                state.update(json.loads(value))
        def ready():
            viewer.web.page().runJavaScript(query, update)
            if state.get("error"):
                raise RuntimeError(state["error"])
            return state.get("ready") and state.get("points") == "1"
        wait_for(ready)
        pixels = []
        viewer.web.page().runJavaScript("""(() => {
            renderer.render(scene, camera);
            const gl = renderer.getContext(), w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
            const p = new Uint8Array(w*h*4); gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,p);
            let blue=0; for(let i=0;i<p.length;i+=4) if(p[i+2]>p[i]+40) blue++;
            return blue;
        })()""", pixels.append)
        wait_for(lambda: bool(pixels))
        assert pixels[0] > 100, f"Texture not rendered: blue pixels={pixels[0]}"
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.02)
        viewer.grab().save(str(out / "viewer.png"))
        record("Three.js WebGL viewer loads textured OBJ and landmarks", str(state) + f"; rendered blue pixels={pixels[0]}")

        from src.gui.pages.view3d_dialog import Edit3DDialog
        csv2d = out / 'points2d.csv'
        pd.DataFrame({'cx': [32.0], 'cy': [32.0]}).to_csv(csv2d, index=False)
        editor = Edit3DDialog(obj, texture, csv2d, points, snap_to_vertices=False)
        editor.show()
        bridge_ready = []
        def has_bridge():
            editor.web.page().runJavaScript("typeof bridge !== 'undefined' && !!bridge && handMeshes.length > 0", bridge_ready.append)
            return any(bridge_ready)
        wait_for(has_bridge)
        editor.web.page().runJavaScript('bridge.add_point(0.5, 0.5, 0.0)')
        wait_for(lambda: len(pd.read_csv(points)) == 2)
        editor.web.page().runJavaScript('bridge.remove_point(1)')
        wait_for(lambda: len(pd.read_csv(points)) == 1)
        assert csv2d.is_file()
        record('Editable viewer WebChannel add/remove and CSV persistence')
        editor.close()

        credits = QWebEnginePage()
        loaded = []
        credits.loadFinished.connect(lambda ok: loaded.append(ok))
        credits.load(QUrl.fromLocalFile(str(app_root() / 'third_party_licenses/QtWebEngine-credits.html')))
        wait_for(lambda: bool(loaded))
        html = []
        credits.toHtml(html.append)
        wait_for(lambda: bool(html))
        assert loaded[0] and len(html[0]) > 100000 and 'Redistribution' in html[0], "Local Chromium license texts unavailable"
        record("Qt WebEngine opens complete offline source notices")
        viewer.close(); window.close()
        return 0
    except Exception:
        results.append({"test": "failure", "status": "failed", "detail": traceback.format_exc()})
        (out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
