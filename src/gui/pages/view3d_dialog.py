from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import json
import tempfile
import uuid
from ...core.paths import asset_path

import numpy as np
import pandas as pd
import cv2

from PySide6.QtCore import QObject, Signal, Slot, QUrl, Qt, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QHBoxLayout, QMessageBox, QLabel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebChannel import QWebChannel


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def _viewer_cache_dir() -> Path:
    root = Path(tempfile.gettempdir()) / "amano_view3d_runtime"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _vendor_dir() -> Path:
    return asset_path("viewer3d", "vendor")


def _project_src_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _check_vendor_files() -> list[str]:
    vendor = _vendor_dir()
    required = ["three.min.js", "OBJLoader.js", "MTLLoader.js", "OrbitControls.js"]
    missing = [name for name in required if not (vendor / name).exists()]
    return missing


def _points_payload_from_df(pts_df: pd.DataFrame) -> list[dict]:
    if pts_df is None or pts_df.empty:
        return []

    if {"x3d", "y3d", "z3d"}.issubset(pts_df.columns):
        x_col, y_col, z_col = "x3d", "y3d", "z3d"
    elif {"X", "Y", "Z"}.issubset(pts_df.columns):
        x_col, y_col, z_col = "X", "Y", "Z"
    else:
        return []

    x = pd.to_numeric(pts_df[x_col], errors="coerce")
    y = pd.to_numeric(pts_df[y_col], errors="coerce")
    z = pd.to_numeric(pts_df[z_col], errors="coerce")

    mask = x.notna() & y.notna() & z.notna()

    out = []
    for idx, row in pts_df.loc[mask].iterrows():
        out.append(
            {
                "row_idx": int(idx),
                "x": float(row[x_col]),
                "y": float(row[y_col]),
                "z": float(row[z_col]),
            }
        )
    return out


def _build_three_payload(
    *,
    obj_path: Path,
    texture_path: Path,
    pts_df: pd.DataFrame,
    editable: bool,
) -> dict:
    obj_path = Path(obj_path).resolve()
    texture_path = Path(texture_path).resolve()
    mtl_path = obj_path.with_suffix(".mtl")
    obj_dir = obj_path.parent.resolve()

    return {
        "obj_url": obj_path.as_uri(),
        "obj_name": obj_path.name,
        "obj_dir_url": obj_dir.as_uri().rstrip("/") + "/",
        "mtl_url": mtl_path.as_uri() if mtl_path.exists() else None,
        "mtl_name": mtl_path.name if mtl_path.exists() else None,
        "texture_url": texture_path.as_uri(),
        "texture_name": texture_path.name,
        "editable": bool(editable),
        "points": _points_payload_from_df(pts_df),
        "debug": {
            "obj_path": str(obj_path),
            "texture_path": str(texture_path),
            "mtl_path": str(mtl_path) if mtl_path.exists() else None,
            "is_uvb_obj": obj_path.name.lower().endswith("_uvb.obj"),
            "is_newhandtexture": texture_path.name.lower() == "newhandtexture.png",
        }
    }


def _write_viewer_html(web: QWebEngineView, html: str, prefix: str):
    cache_dir = _viewer_cache_dir()
    html_path = cache_dir / f"{prefix}_{uuid.uuid4().hex}.html"
    html_path.write_text(html, encoding="utf-8")
    web.load(QUrl.fromLocalFile(str(html_path.resolve())))


# --------------------------------------------------------------------------------------
# Debug page
# --------------------------------------------------------------------------------------


class _DebugPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        print(f"[View3D JS][{level}] {message} (line {lineNumber}, source={sourceID})")


# --------------------------------------------------------------------------------------
# Base viewer (read-only)
# --------------------------------------------------------------------------------------


class View3DDialog(QDialog):
    """Read-only dialog for displaying a 3D model with points."""

    def __init__(self, obj_path: Path, texture_path: Path, csv3d_path: Path, v_flip: bool = True, parent=None):
        super().__init__(parent)
        self.resize(1200, 900)

        self.obj_path = Path(obj_path)
        self.texture_path = Path(texture_path)
        self.csv3d_path = Path(csv3d_path)
        self.v_flip = bool(v_flip)

        layout = QVBoxLayout(self)

        self.web = QWebEngineView()
        self.web.setPage(_DebugPage(self.web))
        layout.addWidget(self.web, stretch=1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        bottom.addWidget(btn_close)
        layout.addLayout(bottom)

        self._load_readonly()

    def _load_readonly(self):
        missing_vendor = _check_vendor_files()
        if missing_vendor:
            QMessageBox.warning(
                self,
                "Missing 3D viewer files",
                "The local Three.js viewer files are missing.\n\n"
                f"Folder expected:\n{_vendor_dir()}\n\n"
                "Missing files:\n- " + "\n- ".join(missing_vendor)
            )
            self.close()
            return

        if not self.obj_path.exists():
            QMessageBox.warning(self, "Missing OBJ", f"OBJ file does not exist:\n{self.obj_path}")
            self.close()
            return

        if not self.texture_path.exists():
            QMessageBox.warning(self, "Missing texture", f"Texture file does not exist:\n{self.texture_path}")
            self.close()
            return

        if not self.csv3d_path.exists():
            QMessageBox.warning(self, "Missing 3D CSV", f"3D CSV file does not exist:\n{self.csv3d_path}")
            self.close()
            return

        try:
            pts_df = pd.read_csv(self.csv3d_path)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not read 3D CSV:\n{e}")
            self.close()
            return

        payload = _build_three_payload(
            obj_path=self.obj_path,
            texture_path=self.texture_path,
            pts_df=pts_df,
            editable=False,
        )

        html = _wrap_threejs_viewer(payload, editable=False)
        _write_viewer_html(self.web, html, "view3d_readonly")


# --------------------------------------------------------------------------------------
# Editable dialog
# --------------------------------------------------------------------------------------


@dataclass
class _MeshCache:
    V: np.ndarray
    VT: np.ndarray
    Fv: np.ndarray
    Fvt: np.ndarray
    vertex_uv: np.ndarray
    tri_v: np.ndarray
    tri_uv: np.ndarray
    tri_centroids: np.ndarray


class _Bridge(QObject):
    add_requested = Signal(float, float, float)
    remove_requested = Signal(int)
    move_requested = Signal(int, float, float, float)
    undo_requested = Signal()
    reset_requested = Signal()
    continue_requested = Signal()

    @Slot(float, float, float)
    def add_point(self, x: float, y: float, z: float):
        self.add_requested.emit(float(x), float(y), float(z))

    @Slot(int)
    def remove_point(self, row_idx: int):
        self.remove_requested.emit(int(row_idx))

    @Slot(int, float, float, float)
    def move_point(self, row_idx: int, x: float, y: float, z: float):
        self.move_requested.emit(int(row_idx), float(x), float(y), float(z))

    @Slot()
    def undo(self):
        self.undo_requested.emit()

    @Slot()
    def reset_camera(self):
        self.reset_requested.emit()

    @Slot()
    def reset_points(self):
        self.reset_requested.emit()

    @Slot()
    def continue_editor(self):
        self.continue_requested.emit()


class Edit3DDialog(QDialog):
    """Interactive 3D editor: add/remove points directly on the model."""

    def __init__(
        self,
        obj_path: Path,
        texture_path: Path,
        csv2d_path: Path,
        csv3d_path: Path,
        v_flip: bool = True,
        snap_to_vertices: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("3D View (editable)")
        self.resize(1250, 920)
        self.destroyed.connect(self._mark_dialog_destroyed)

        self.obj_path = Path(obj_path)
        self.texture_path = Path(texture_path)
        self.csv2d_path = Path(csv2d_path)
        self.csv3d_path = Path(csv3d_path)
        self.v_flip = bool(v_flip)
        self.snap_to_vertices = bool(snap_to_vertices)

        self._tex_w: Optional[int] = None
        self._tex_h: Optional[int] = None
        self._mesh: Optional[_MeshCache] = None
        self._page_ready: bool = False
        self._closing: bool = False
        self._web_destroyed: bool = False
        self.undo_stack: list[dict] = []
        self._continue_callback = self.close
        self._cancel_callback = self.reject
        self._reset_callback = None
        self._initial_df2d = self._read_csv_snapshot(self.csv2d_path)
        self._initial_df3d = self._read_csv_snapshot(self.csv3d_path)

        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)

        header_text = QVBoxLayout()
        header_text.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(
            "Tip: Click on an existing visible point to remove it. "
            "Click and drag a point to adjust it on the surface. "
            "Shift + click on the mesh to add a new point."
        )
        hint.setWordWrap(True)
        header_text.addWidget(hint)

        self.count_label = QLabel("Points in 3D view: 0")
        self.count_label.setStyleSheet("font-weight: 600;")
        header_text.addWidget(self.count_label)
        header.addLayout(header_text, 1)

        layout.addLayout(header)

        self.web = QWebEngineView()
        self.web.setPage(_DebugPage(self.web))
        self.web.destroyed.connect(self._mark_web_destroyed)
        layout.addWidget(self.web, stretch=1)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(10)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self._trigger_cancel)
        bottom.addWidget(self.btn_cancel)

        bottom.addStretch(1)
        self.btn_undo = QPushButton("Undo (Z)")
        self.btn_reset = QPushButton("Reset Camera (R)")
        self.btn_continue = QPushButton("Continue (ENTER)")
        self.btn_undo.clicked.connect(self._undo)
        self.btn_reset.clicked.connect(self._trigger_reset)
        self.btn_continue.clicked.connect(self._trigger_continue)
        bottom.addWidget(self.btn_undo)
        bottom.addWidget(self.btn_reset)
        bottom.addWidget(self.btn_continue)
        layout.addLayout(bottom)

        self._bridge = _Bridge()
        self._bridge.add_requested.connect(self._on_add_requested)
        self._bridge.remove_requested.connect(self._on_remove_requested)
        self._bridge.move_requested.connect(self._on_move_requested)
        self._bridge.undo_requested.connect(self._undo)
        self._bridge.reset_requested.connect(self._trigger_reset)
        self._bridge.continue_requested.connect(self._trigger_continue)

        channel = QWebChannel(self.web.page())
        channel.registerObject("bridge", self._bridge)
        self.web.page().setWebChannel(channel)

        self.web.loadFinished.connect(self._on_load_finished)

        self._init_assets_or_close()
        self._render_initial()

    def _mark_web_destroyed(self, *_):
        self._web_destroyed = True
        self._page_ready = False

    def _mark_dialog_destroyed(self, *_):
        self._closing = True
        self._page_ready = False

    def _viewer_is_available(self) -> bool:
        if self._closing or self._web_destroyed or not self._page_ready:
            return False
        try:
            return self.web is not None and self.web.page() is not None
        except RuntimeError:
            self._mark_web_destroyed()
            return False

    def _run_viewer_js(self, js: str) -> bool:
        if not self._viewer_is_available():
            return False
        try:
            self.web.page().runJavaScript(js)
            self.web.update()
            return True
        except RuntimeError:
            self._mark_web_destroyed()
            return False

    @staticmethod
    def _read_csv_snapshot(path: Path) -> pd.DataFrame:
        try:
            path = Path(path)
            if path.exists():
                return pd.read_csv(path).reset_index(drop=True)
        except Exception:
            pass
        return pd.DataFrame()

    def _on_load_finished(self, ok: bool):
        if self._closing or self._web_destroyed:
            return
        self._page_ready = bool(ok)
        if self._page_ready:
            self._push_points_to_js()
            self._update_count_label()

    def _init_assets_or_close(self):
        missing_vendor = _check_vendor_files()
        if missing_vendor:
            QMessageBox.warning(
                self,
                "Missing 3D viewer files",
                "The local Three.js viewer files are missing.\n\n"
                f"Folder expected:\n{_vendor_dir()}\n\n"
                "Missing files:\n- " + "\n- ".join(missing_vendor)
            )
            self.close()
            return

        if not self.obj_path.exists():
            QMessageBox.warning(self, "Missing OBJ", f"OBJ file does not exist:\n{self.obj_path}")
            self.close()
            return

        if not self.texture_path.exists():
            QMessageBox.warning(self, "Missing texture", f"Texture file does not exist:\n{self.texture_path}")
            self.close()
            return

        if not self.csv2d_path.exists():
            QMessageBox.warning(self, "Missing 2D CSV", f"2D CSV file does not exist:\n{self.csv2d_path}")
            self.close()
            return

        if not self.csv3d_path.exists():
            QMessageBox.warning(self, "Missing 3D CSV", f"3D CSV file does not exist:\n{self.csv3d_path}")
            self.close()
            return

        tex = cv2.imread(str(self.texture_path), cv2.IMREAD_COLOR)
        if tex is None:
            QMessageBox.warning(self, "Error", f"Could not read texture:\n{self.texture_path}")
            self.close()
            return

        self._tex_h, self._tex_w = tex.shape[:2]

        V, VT, Fv, Fvt = self._parse_obj(self.obj_path)
        vertex_uv = _compute_vertex_uv(V=V, VT=VT, Fv=Fv, Fvt=Fvt)

        tri_v = V[Fv]

        if VT.size > 0 and Fvt.shape == Fv.shape:
            tri_uv = VT[Fvt]
        else:
            tri_uv = np.full((Fv.shape[0], 3, 2), np.nan, dtype=np.float32)

        tri_centroids = tri_v.mean(axis=1)

        self._mesh = _MeshCache(
            V=V,
            VT=VT,
            Fv=Fv,
            Fvt=Fvt,
            vertex_uv=vertex_uv,
            tri_v=tri_v,
            tri_uv=tri_uv,
            tri_centroids=tri_centroids,
        )

    def _parse_obj(self, path: Path):
        def _norm_idx(idx, n):
            if idx > 0:
                return idx - 1
            return n + idx

        V, VT, Fv, Fvt = [], [], [], []
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("v "):
                    _, x, y, z = line.split()[:4]
                    V.append([float(x), float(y), float(z)])
                elif line.startswith("vt "):
                    p = line.split()
                    VT.append([float(p[1]), float(p[2])])
                elif line.startswith("f "):
                    parts = line.split()[1:]
                    vidx, vtidx = [], []
                    for p in parts:
                        comps = p.split("/")
                        vidx.append(_norm_idx(int(comps[0]), len(V)))
                        if len(comps) > 1 and comps[1] != "":
                            vtidx.append(_norm_idx(int(comps[1]), len(VT)))
                    if len(vidx) >= 3:
                        for i in range(1, len(vidx) - 1):
                            Fv.append([vidx[0], vidx[i], vidx[i + 1]])
                            if len(vtidx) >= 3:
                                Fvt.append([vtidx[0], vtidx[i], vtidx[i + 1]])

        V = np.asarray(V, dtype=np.float32)
        VT = np.asarray(VT, dtype=np.float32) if VT else np.zeros((0, 2), dtype=np.float32)
        Fv = np.asarray(Fv, dtype=np.int32) if Fv else np.zeros((0, 3), dtype=np.int32)
        Fvt = np.asarray(Fvt, dtype=np.int32) if Fvt else np.zeros((0, 3), dtype=np.int32)
        return V, VT, Fv, Fvt

    def _render_initial(self):
        try:
            pts_df = pd.read_csv(self.csv3d_path)
        except Exception:
            pts_df = pd.DataFrame()

        payload = _build_three_payload(
            obj_path=self.obj_path,
            texture_path=self.texture_path,
            pts_df=pts_df,
            editable=True,
        )

        html = _wrap_threejs_viewer(payload, editable=True)
        _write_viewer_html(self.web, html, "view3d_editable")

    def _push_points_to_js(self):
        if not self._page_ready:
            return

        try:
            pts_df = pd.read_csv(self.csv3d_path)
        except Exception:
            pts_df = pd.DataFrame()

        self._push_points_df_to_js(pts_df)

    def _push_points_df_to_js(self, pts_df: pd.DataFrame):
        if not self._viewer_is_available():
            return

        payload = json.dumps(_points_payload_from_df(pts_df))
        js = (
            f"window.updateDetections && window.updateDetections({payload});"
            "window.renderViewerOnce && window.renderViewerOnce();"
        )
        self._run_viewer_js(js)

    def _update_count_label(self):
        try:
            df3d = pd.read_csv(self.csv3d_path)
        except Exception:
            df3d = pd.DataFrame()

        self._update_count_label_from_df(df3d)

    def _update_count_label_from_df(self, df3d: pd.DataFrame):
        n = 0
        if not df3d.empty:
            if {"x3d", "y3d", "z3d"}.issubset(df3d.columns):
                x = pd.to_numeric(df3d["x3d"], errors="coerce")
                y = pd.to_numeric(df3d["y3d"], errors="coerce")
                z = pd.to_numeric(df3d["z3d"], errors="coerce")
                n = int((x.notna() & y.notna() & z.notna()).sum())
            elif {"X", "Y", "Z"}.issubset(df3d.columns):
                x = pd.to_numeric(df3d["X"], errors="coerce")
                y = pd.to_numeric(df3d["Y"], errors="coerce")
                z = pd.to_numeric(df3d["Z"], errors="coerce")
                n = int((x.notna() & y.notna() & z.notna()).sum())
            else:
                n = int(len(df3d))

        self.count_label.setText(f"Points in 3D view: {n}")
        self.count_label.update()

    def refresh_visuals_from_df(self, df3d: pd.DataFrame | None = None):
        """Push points to the web scene and repaint even when reset happens mid-event."""
        if df3d is None:
            try:
                df3d = pd.read_csv(self.csv3d_path)
            except Exception:
                df3d = pd.DataFrame()
        else:
            df3d = df3d.copy().reset_index(drop=True)

        self._update_count_label_from_df(df3d)

        def _refresh():
            if not self._viewer_is_available():
                return
            self._push_points_df_to_js(df3d)
            try:
                self.update()
            except RuntimeError:
                self._mark_dialog_destroyed()

        _refresh()
        QTimer.singleShot(0, _refresh)
        QTimer.singleShot(80, _refresh)

    def set_continue_callback(self, callback, text: str | None = None):
        """Replace the default Continue action.

        Used when the 3D editor is embedded inside the combined 2D/3D
        validation dialog.
        """
        self._continue_callback = callback
        if text is not None:
            self.btn_continue.setText(text)

    def set_cancel_callback(self, callback):
        """Replace the default Cancel action."""
        self._cancel_callback = callback

    def set_reset_callback(self, callback):
        """Replace the default Reset Camera action."""
        self._reset_callback = callback

    def _trigger_continue(self):
        try:
            self._continue_callback()
        except TypeError:
            self.close()

    def _trigger_cancel(self):
        try:
            self._cancel_callback()
        except TypeError:
            self.reject()

    def _trigger_reset(self):
        if self._reset_callback is not None:
            try:
                self._reset_callback()
                return
            except TypeError:
                pass
        self._reset_camera()

    def refresh_from_disk(self):
        """Reload the CSV-backed points and push them to the web viewer."""
        self._sync_from_disk()
        self.refresh_visuals_from_df()

    def _build_2d_from_3d(self, df3d: pd.DataFrame) -> pd.DataFrame:
        if df3d is None or df3d.empty:
            return pd.DataFrame(columns=["pixel_x", "pixel_y", "area", "contour_id"])

        df2d = pd.DataFrame()

        if "pixel_x" in df3d.columns:
            df2d["pixel_x"] = pd.to_numeric(df3d["pixel_x"], errors="coerce").fillna(0).astype(int)
        else:
            df2d["pixel_x"] = 0

        if "pixel_y" in df3d.columns:
            df2d["pixel_y"] = pd.to_numeric(df3d["pixel_y"], errors="coerce").fillna(0).astype(int)
        else:
            df2d["pixel_y"] = 0

        if "area" in df3d.columns:
            df2d["area"] = pd.to_numeric(df3d["area"], errors="coerce").fillna(0.0)
        else:
            df2d["area"] = 0.0

        if "contour_id" in df3d.columns:
            df2d["contour_id"] = pd.to_numeric(df3d["contour_id"], errors="coerce").fillna(-1).astype(int)
        else:
            df2d["contour_id"] = -1

        return df2d.reset_index(drop=True)

    def _persist_current_state(self, df3d: pd.DataFrame):
        df3d = df3d.reset_index(drop=True)
        df2d = self._build_2d_from_3d(df3d)

        df3d.to_csv(self.csv3d_path, index=False)
        df2d.to_csv(self.csv2d_path, index=False)

    def _sync_from_disk(self):
        try:
            if not self.csv3d_path.exists():
                return
            df3d = pd.read_csv(self.csv3d_path)
            self._persist_current_state(df3d)
        except Exception:
            pass

    def _undo(self):
        if not self.undo_stack:
            return

        action = self.undo_stack.pop()

        try:
            df3d = pd.read_csv(self.csv3d_path)
        except Exception:
            return

        if action.get("type") == "add":
            row_idx = int(action.get("row_idx", len(df3d) - 1))
            if row_idx in df3d.index:
                df3d = df3d.drop(index=row_idx).reset_index(drop=True)
            elif not df3d.empty:
                df3d = df3d.iloc[:-1].reset_index(drop=True)
        elif action.get("type") == "remove":
            row_idx = int(action.get("row_idx", len(df3d)))
            row = dict(action.get("row", {}))
            for col in row.keys():
                if col not in df3d.columns:
                    df3d[col] = np.nan
            for col in df3d.columns:
                if col not in row:
                    row[col] = np.nan
            row_df = pd.DataFrame([row], columns=df3d.columns)
            top = df3d.iloc[:row_idx]
            bottom = df3d.iloc[row_idx:]
            df3d = pd.concat([top, row_df, bottom], ignore_index=True)
        elif action.get("type") == "move":
            row_idx = int(action.get("row_idx", -1))
            row = dict(action.get("row_before", {}))
            if row_idx not in df3d.index or not row:
                return
            for col in row.keys():
                if col not in df3d.columns:
                    df3d[col] = np.nan
            for col in df3d.columns:
                df3d.at[row_idx, col] = row.get(col, np.nan)
        else:
            return

        self._persist_current_state(df3d)
        self._push_points_to_js()
        self._update_count_label()

    def _reset_camera(self):
        if not self._viewer_is_available():
            return
        self._run_viewer_js("window.resetCameraView && window.resetCameraView();")

    def _reset_points(self):
        self._initial_df3d.to_csv(self.csv3d_path, index=False)
        self._initial_df2d.to_csv(self.csv2d_path, index=False)
        self.undo_stack.clear()
        self.refresh_visuals_from_df(self._initial_df3d)

    def keyPressEvent(self, event):
        text = (event.text() or "").strip().lower()
        key = int(event.key())

        def _qt_key_value(name, fallback):
            value = getattr(Qt, name, None)
            if value is None:
                value = getattr(getattr(Qt, "Key", object), name, fallback)
            return int(value)

        key_return = _qt_key_value("Key_Return", 16777220)
        key_enter = _qt_key_value("Key_Enter", 16777221)
        key_escape = _qt_key_value("Key_Escape", 16777216)

        if text == "z":
            self._undo()
            event.accept()
            return
        if text == "r":
            self._trigger_reset()
            event.accept()
            return
        if key in (key_return, key_enter, key_escape):
            self._trigger_continue()
            event.accept()
            return
        super().keyPressEvent(event)

    def _surface_row_values(self, x: float, y: float, z: float, *, allow_snap: bool, status: str):
        if self._mesh is None or self._tex_w is None or self._tex_h is None:
            return None

        p = np.array([x, y, z], dtype=np.float32)

        if allow_snap and self.snap_to_vertices:
            V = self._mesh.V
            d2 = np.sum((V - p[None, :]) ** 2, axis=1)
            vi = int(np.argmin(d2))
            xyz = V[vi].astype(float)
            uv = self._mesh.vertex_uv[vi].astype(float)
        else:
            uv, xyz = _uv_from_surface_point(
                p,
                tri_v=self._mesh.tri_v,
                tri_uv=self._mesh.tri_uv,
                tri_centroids=self._mesh.tri_centroids,
                k=80,
            )

        if uv is None or not np.isfinite(uv).all():
            return None

        px, py = _uv_to_px(float(uv[0]), float(uv[1]), int(self._tex_w), int(self._tex_h), v_flip=self.v_flip)
        u, v = float(uv[0]), float(uv[1])
        x3, y3, z3 = float(xyz[0]), float(xyz[1]), float(xyz[2])

        return {
            "pixel_x": int(px),
            "pixel_y": int(py),
            "u": u,
            "v": v,
            "x3d_raw": x3,
            "y3d_raw": y3,
            "z3d_raw": z3,
            "x3d": x3,
            "y3d": y3,
            "z3d": z3,
            "X": x3,
            "Y": y3,
            "Z": z3,
            "status": status,
        }

    def _on_add_requested(self, x: float, y: float, z: float):
        status = "mapped_snapped" if self.snap_to_vertices else "mapped_surface"
        mapped_values = self._surface_row_values(x, y, z, allow_snap=True, status=status)
        if mapped_values is None:
            QMessageBox.warning(self, "Add point", "Could not infer UV for the clicked location.")
            return

        try:
            df3d = pd.read_csv(self.csv3d_path)
        except Exception:
            df3d = pd.DataFrame()

        row3d = {
            "area": float(0.0),
            "contour_id": int(-1),
        }
        row3d.update(mapped_values)

        for k in row3d.keys():
            if k not in df3d.columns:
                df3d[k] = np.nan

        new_row_idx = int(len(df3d))
        df3d.loc[new_row_idx] = row3d
        self.undo_stack.append({"type": "add", "row_idx": new_row_idx})

        self._persist_current_state(df3d)
        self._push_points_to_js()
        self._update_count_label()

    def _on_remove_requested(self, row_idx: int):
        try:
            df3d = pd.read_csv(self.csv3d_path)
        except Exception:
            return

        if df3d.empty:
            return

        ridx = int(row_idx)
        if ridx not in df3d.index:
            return

        removed_row = df3d.loc[ridx].to_dict()
        self.undo_stack.append({"type": "remove", "row_idx": ridx, "row": removed_row})
        df3d = df3d.drop(index=ridx).reset_index(drop=True)

        self._persist_current_state(df3d)
        self._push_points_to_js()
        self._update_count_label()

    def _on_move_requested(self, row_idx: int, x: float, y: float, z: float):
        mapped_values = self._surface_row_values(
            x,
            y,
            z,
            allow_snap=False,
            status="mapped_surface_adjusted",
        )
        if mapped_values is None:
            QMessageBox.warning(self, "Move point", "Could not infer UV for the dragged location.")
            self._push_points_to_js()
            return

        try:
            df3d = pd.read_csv(self.csv3d_path)
        except Exception:
            return

        if df3d.empty:
            return

        ridx = int(row_idx)
        if ridx not in df3d.index:
            return

        row_before = df3d.loc[ridx].to_dict()
        for col in mapped_values.keys():
            if col not in df3d.columns:
                df3d[col] = np.nan
        for col, value in mapped_values.items():
            df3d.at[ridx, col] = value

        self.undo_stack.append({"type": "move", "row_idx": ridx, "row_before": row_before})

        self._persist_current_state(df3d)
        self._push_points_to_js()
        self._update_count_label()

    def closeEvent(self, event):
        self._closing = True
        self._page_ready = False
        self._sync_from_disk()
        super().closeEvent(event)


# --------------------------------------------------------------------------------------
# Three.js HTML viewer
# --------------------------------------------------------------------------------------


def _wrap_threejs_viewer(payload: dict, editable: bool) -> str:
    payload_json = json.dumps(payload)
    vendor = _vendor_dir().resolve().as_posix()

    controls_text = """
    <b>Controls</b><br/>
    • Left drag: orbit<br/>
    • Mouse wheel: zoom<br/>
    • Right drag: pan<br/>
    """ if not editable else """
    <b>Controls</b><br/>
    • Left drag: orbit<br/>
    • Mouse wheel: zoom<br/>
    • Right drag: pan<br/>
    • <b>Left Click</b> over visible point: delete point<br/>
    • <b>Left Drag</b> visible point: move point on surface<br/>
    • <b>Shift + Left Click</b> over mesh: add point<br/>
    • Z: undo | R: reset camera | ENTER: continue<br/>
    """

    template = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,height=device-height,initial-scale=1.0" />
  <style>
    html, body {
      width: 100%;
      height: 100%;
      margin: 0;
      padding: 0;
      overflow: hidden;
      background: #1f1f1f;
      font-family: Arial, sans-serif;
    }

    #root {
      position: fixed;
      inset: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: #f1f1f1;
    }

    #viewer {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      display: block;
      outline: none;
      touch-action: none;
    }

    #overlay {
      position: absolute;
      top: 10px;
      left: 10px;
      z-index: 1000;
      background: rgba(0,0,0,0.55);
      color: #fff;
      padding: 10px 12px;
      border-radius: 10px;
      font-size: 13px;
      line-height: 1.35;
      max-width: 420px;
      pointer-events: none;
      user-select: none;
    }

    #errorbox {
      position: absolute;
      top: 10px;
      right: 10px;
      z-index: 1001;
      background: rgba(140,0,0,0.90);
      color: #fff;
      padding: 10px 12px;
      border-radius: 10px;
      font-family: Consolas, monospace;
      font-size: 12px;
      line-height: 1.35;
      max-width: 460px;
      white-space: pre-wrap;
      display: none;
    }
  </style>

  <script src="file:///__VENDOR__/three.min.js"></script>
  <script src="file:///__VENDOR__/OBJLoader.js"></script>
  <script src="file:///__VENDOR__/MTLLoader.js"></script>
  <script src="file:///__VENDOR__/OrbitControls.js"></script>
  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
</head>
<body>
  <div id="root">
    <canvas id="viewer"></canvas>
    <div id="overlay">
      __CONTROLS__
      <hr style="border:0;border-top:1px solid rgba(255,255,255,0.2);margin:8px 0;">
      <div style="font-size:12px;line-height:1.35;">
        <b>Points:</b> <span id="point_count">0</span>
      </div>
    </div>
    <div id="errorbox"></div>
  </div>

  <script>
    const PAYLOAD = __PAYLOAD_JSON__;
    const EDITABLE = __EDITABLE__;

    const root = document.getElementById("root");
    const canvas = document.getElementById("viewer");
    const errorBox = document.getElementById("errorbox");
    const pointCountEl = document.getElementById("point_count");

    let bridge = null;
    let scene = null;
    let camera = null;
    let renderer = null;
    let controls = null;
    let raycaster = null;
    let mouse = null;
    let handRoot = null;
    let handMeshes = [];
    let pointsGroup = null;
    let isShiftDown = false;
    let pointRadius = 1.0;
    let resizeObserver = null;

    let pointerDownInfo = null;
    let pendingEditAction = null;

    function showError(msg) {
      errorBox.style.display = "block";
      errorBox.textContent = String(msg);
      console.error(msg);
    }

    window.addEventListener("error", function(ev) {
      showError("JS error:\\n" + (ev.message || "Unknown JS error"));
    });

    window.addEventListener("unhandledrejection", function(ev) {
      showError("Promise error:\\n" + (ev.reason || "Unknown promise rejection"));
    });

    function initChannel() {
      try {
        new QWebChannel(qt.webChannelTransport, function(channel) {
          bridge = channel.objects.bridge || null;
        });
      } catch (e) {
        bridge = null;
        console.warn("QWebChannel init failed:", e);
      }
    }

    function getViewportSize() {
      const rect = root.getBoundingClientRect();
      return {
        width: Math.max(1, Math.floor(rect.width)),
        height: Math.max(1, Math.floor(rect.height))
      };
    }

    function initScene() {
      renderer = new THREE.WebGLRenderer({
        canvas: canvas,
        antialias: true,
        alpha: false,
        preserveDrawingBuffer: false
      });

      renderer.outputEncoding = THREE.sRGBEncoding;
      renderer.setPixelRatio(window.devicePixelRatio || 1);

      scene = new THREE.Scene();
      scene.background = new THREE.Color(0xf1f1f1);

      const size = getViewportSize();
      camera = new THREE.PerspectiveCamera(
        38,
        size.width / size.height,
        0.01,
        100000
      );

      renderer.setSize(size.width, size.height, false);

      controls = new THREE.OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.screenSpacePanning = true;
      controls.rotateSpeed = 0.9;
      controls.zoomSpeed = 1.0;
      controls.panSpeed = 0.9;

      const hemi = new THREE.HemisphereLight(0xffffff, 0x666666, 1.15);
      hemi.position.set(0, 200, 0);
      scene.add(hemi);

      const dir1 = new THREE.DirectionalLight(0xffffff, 1.05);
      dir1.position.set(180, 220, 140);
      scene.add(dir1);

      const dir2 = new THREE.DirectionalLight(0xffffff, 0.75);
      dir2.position.set(-120, 100, -160);
      scene.add(dir2);

      const ambient = new THREE.AmbientLight(0xffffff, 0.40);
      scene.add(ambient);

      raycaster = new THREE.Raycaster();
      mouse = new THREE.Vector2();

      pointsGroup = new THREE.Group();
      pointsGroup.name = "detections_group";
      scene.add(pointsGroup);

      window.addEventListener("keydown", function(e) {
        if (e.key === "Shift") isShiftDown = true;
      });

      window.addEventListener("keyup", function(e) {
        if (e.key === "Shift") isShiftDown = false;
      });

      renderer.domElement.addEventListener("contextmenu", function(e) {
        e.preventDefault();
        return false;
      });

      renderer.domElement.addEventListener("pointerdown", onPointerDownCapture, true);
      renderer.domElement.addEventListener("pointermove", onPointerMoveCapture, true);
      renderer.domElement.addEventListener("pointerup", onPointerUpCapture, true);
      renderer.domElement.addEventListener("pointercancel", onPointerCancelCapture, true);

      window.addEventListener("resize", onResize);

      if (window.ResizeObserver) {
        resizeObserver = new ResizeObserver(function() {
          onResize();
        });
        resizeObserver.observe(root);
      }
    }

    function onResize() {
      if (!camera || !renderer) return;

      const size = getViewportSize();
      camera.aspect = size.width / size.height;
      camera.updateProjectionMatrix();
      renderer.setSize(size.width, size.height, false);
    }

    function fitCameraToObject(object3D) {
      const box = new THREE.Box3().setFromObject(object3D);
      const size = box.getSize(new THREE.Vector3());
      const center = box.getCenter(new THREE.Vector3());

      const maxDim = Math.max(size.x, size.y, size.z);
      const fov = camera.fov * (Math.PI / 180.0);

      let dist = Math.abs((maxDim * 0.70) / Math.tan(fov / 2));
      if (!isFinite(dist) || dist <= 0) {
        dist = maxDim * 2.2;
      }

      camera.position.set(
        center.x,
        center.y - dist * 0.10,
        center.z + dist * 1.10
      );

      camera.near = Math.max(0.01, maxDim / 2000);
      camera.far = Math.max(1000, maxDim * 30);
      camera.updateProjectionMatrix();

      controls.target.copy(center);
      controls.update();

      pointRadius = Math.max(maxDim * 0.006, 0.28);
    }

    function applyGoodMaterialDefaultsToMaterial(mat) {
      if (!mat) return;

      mat.side = THREE.DoubleSide;
      mat.transparent = false;
      mat.opacity = 1.0;

      if (mat.color) {
        mat.color.setRGB(1, 1, 1);
      }

      if (mat.map) {
        mat.map.encoding = THREE.sRGBEncoding;
        mat.map.needsUpdate = true;
      }

      if ("shininess" in mat) {
        mat.shininess = 10;
      }

      if (mat.specular) {
        mat.specular.setRGB(0.08, 0.08, 0.08);
      }

      mat.needsUpdate = true;
    }

    function makeFallbackMaterial(texture) {
      texture.encoding = THREE.sRGBEncoding;
      texture.flipY = true;
      texture.wrapS = THREE.ClampToEdgeWrapping;
      texture.wrapT = THREE.ClampToEdgeWrapping;

      try {
        const maxAniso = renderer.capabilities.getMaxAnisotropy();
        texture.anisotropy = Math.min(8, maxAniso);
      } catch (e) {}

      texture.needsUpdate = true;

      return new THREE.MeshPhongMaterial({
        map: texture,
        color: new THREE.Color(0xffffff),
        side: THREE.DoubleSide,
        shininess: 10,
        specular: new THREE.Color(0x141414)
      });
    }

    function makePointMesh(point) {
      const geom = new THREE.SphereGeometry(pointRadius, 18, 18);
      const mat = new THREE.MeshPhongMaterial({
        color: 0x017d34,
        shininess: 20,
        specular: new THREE.Color(0x222222)
      });

      const mesh = new THREE.Mesh(geom, mat);
      mesh.position.set(point.x, point.y, point.z);
      mesh.userData.row_idx = point.row_idx;
      mesh.userData.isDetectionPoint = true;
      return mesh;
    }

    function rebuildPoints(points) {
      const safePoints = Array.isArray(points) ? points : [];

      while (pointsGroup.children.length > 0) {
        const child = pointsGroup.children[0];
        pointsGroup.remove(child);
        if (child.geometry) child.geometry.dispose();
        if (child.material) child.material.dispose();
      }

      for (const p of safePoints) {
        pointsGroup.add(makePointMesh(p));
      }

      updatePointCount(safePoints.length);
    }

    function updatePointCount(count) {
      if (pointCountEl) {
        pointCountEl.textContent = String(count || 0);
      }
    }

    function getMouseNDC(event) {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    }

    function intersectObjects(event, objects) {
      getMouseNDC(event);
      raycaster.setFromCamera(mouse, camera);
      return raycaster.intersectObjects(objects, true);
    }

    function isClickLikeFromDown(down, event) {
      if (!down) return false;

      const dist2 = pointerDistance2FromDown(down, event);
      const dt = Date.now() - down.t;

      return dist2 <= 25 && dt <= 500;
    }

    function pointerDistance2FromDown(down, event) {
      if (!down) return 0;

      const dx = event.clientX - down.x;
      const dy = event.clientY - down.y;
      return dx * dx + dy * dy;
    }

    function getSurfaceCandidate(event) {
      const meshHits = intersectObjects(event, handMeshes);
      if (meshHits.length === 0) return null;

      const hit = meshHits[0];
      const p = hit.point;
      return {
        x: parseFloat(p.x),
        y: parseFloat(p.y),
        z: parseFloat(p.z)
      };
    }

    function getVisiblePointCandidate(event) {
      const pointHits = intersectObjects(event, pointsGroup.children);
      if (pointHits.length === 0) return null;

      const meshHits = intersectObjects(event, handMeshes);
      const nearestPointHit = pointHits[0];
      const nearestMeshHit = meshHits.length > 0 ? meshHits[0] : null;

      if (nearestMeshHit && nearestMeshHit.distance < nearestPointHit.distance - 1e-6) {
        return null;
      }

      const picked = nearestPointHit.object;
      const rowIdx = picked && picked.userData ? picked.userData.row_idx : null;
      if (rowIdx === undefined || rowIdx === null) return null;

      return {
        type: "point",
        rowIdx: parseInt(rowIdx),
        object: picked,
        dragging: false,
        lastSurface: null,
        original: {
          x: parseFloat(picked.position.x),
          y: parseFloat(picked.position.y),
          z: parseFloat(picked.position.z)
        }
      };
    }

    function getAddCandidate(event) {
      const p = getSurfaceCandidate(event);
      if (!p) return null;

      return {
        type: "add",
        x: p.x,
        y: p.y,
        z: p.z
      };
    }

    function buildEditCandidate(event) {
      const shiftMode = !!(event.shiftKey || isShiftDown);

      if (shiftMode) {
        return getAddCandidate(event);
      }

      return getVisiblePointCandidate(event);
    }

    function consumeEventForEdit(event) {
      event.preventDefault();
      event.stopPropagation();
      if (event.stopImmediatePropagation) {
        event.stopImmediatePropagation();
      }
    }

    function onPointerDownCapture(event) {
      if (!EDITABLE) return;
      if (event.button !== 0) return;

      pointerDownInfo = {
        x: event.clientX,
        y: event.clientY,
        button: event.button,
        shift: !!(event.shiftKey || isShiftDown),
        t: Date.now()
      };

      pendingEditAction = buildEditCandidate(event);

      if (pendingEditAction) {
        consumeEventForEdit(event);
        if (controls) controls.enabled = false;
      }
    }

    function onPointerMoveCapture(event) {
      if (!EDITABLE) return;

      if (pendingEditAction) {
        consumeEventForEdit(event);

        if (pendingEditAction.type === "point") {
          const movedEnough = pointerDistance2FromDown(pointerDownInfo, event) > 25;
          if (!pendingEditAction.dragging && movedEnough) {
            pendingEditAction.dragging = true;
          }

          if (pendingEditAction.dragging) {
            const p = getSurfaceCandidate(event);
            if (p) {
              pendingEditAction.lastSurface = p;
              pendingEditAction.object.position.set(p.x, p.y, p.z);
            }
          }
        }
      }
    }

    function restorePendingPointIfNeeded() {
      if (!pendingEditAction || pendingEditAction.type !== "point") return;
      if (!pendingEditAction.object || !pendingEditAction.original) return;

      const p = pendingEditAction.original;
      pendingEditAction.object.position.set(p.x, p.y, p.z);
    }

    function clearPendingEdit(options) {
      const opts = options || {};
      if (opts.restorePoint) {
        restorePendingPointIfNeeded();
      }
      pendingEditAction = null;
      pointerDownInfo = null;
      if (controls) {
        controls.enabled = true;
        controls.update();
      }
    }

    function onPointerCancelCapture(event) {
      if (!EDITABLE) return;

      if (pendingEditAction) {
        consumeEventForEdit(event);
      }
      clearPendingEdit({ restorePoint: true });
    }

    function onPointerUpCapture(event) {
      if (!EDITABLE) return;

      const down = pointerDownInfo;
      const pending = pendingEditAction;

      if (pending) {
        consumeEventForEdit(event);
      }

      if (event.button !== 0) {
        clearPendingEdit({ restorePoint: true });
        return;
      }

      if (!down) {
        clearPendingEdit({ restorePoint: true });
        return;
      }

      const clickLike = isClickLikeFromDown(down, event);

      if (pending && pending.type === "point" && pending.dragging) {
        if (pending.lastSurface && bridge && bridge.move_point) {
          bridge.move_point(
            pending.rowIdx,
            pending.lastSurface.x,
            pending.lastSurface.y,
            pending.lastSurface.z
          );
        } else {
          restorePendingPointIfNeeded();
        }
      } else if (pending && clickLike) {
        if (pending.type === "add") {
          if (bridge && bridge.add_point) {
            bridge.add_point(pending.x, pending.y, pending.z);
          }
        } else if (pending.type === "point") {
          if (bridge && bridge.remove_point) {
            bridge.remove_point(pending.rowIdx);
          }
        }
      } else if (pending && pending.type === "point") {
        restorePendingPointIfNeeded();
      }

      clearPendingEdit();
    }

    function finalizeObject(obj) {
      handRoot = obj;
      handMeshes = [];

      handRoot.traverse(function(child) {
        if (!child.isMesh) return;

        if (child.geometry) {
          child.geometry.computeVertexNormals();
        }

        if (Array.isArray(child.material)) {
          child.material.forEach(applyGoodMaterialDefaultsToMaterial);
        } else {
          applyGoodMaterialDefaultsToMaterial(child.material);
        }

        child.castShadow = false;
        child.receiveShadow = false;
        handMeshes.push(child);
      });

      scene.add(handRoot);
      fitCameraToObject(handRoot);
      rebuildPoints(PAYLOAD.points || []);
    }

    function loadWithMtl() {
      return new Promise(function(resolve, reject) {
        const mtlLoader = new THREE.MTLLoader();
        mtlLoader.setPath(PAYLOAD.obj_dir_url);
        mtlLoader.setResourcePath(PAYLOAD.obj_dir_url);
        mtlLoader.setMaterialOptions({
          side: THREE.DoubleSide
        });

        mtlLoader.load(
          PAYLOAD.mtl_name,
          function(materials) {
            materials.preload();

            const matDict = materials.materials || {};
            Object.keys(matDict).forEach(function(key) {
              applyGoodMaterialDefaultsToMaterial(matDict[key]);
            });

            const objLoader = new THREE.OBJLoader();
            objLoader.setMaterials(materials);
            objLoader.setPath(PAYLOAD.obj_dir_url);

            objLoader.load(
              PAYLOAD.obj_name,
              function(obj) {
                resolve(obj);
              },
              undefined,
              function(err) {
                reject(err);
              }
            );
          },
          undefined,
          function(err) {
            reject(err);
          }
        );
      });
    }

    function loadWithFallbackTexture() {
      return new Promise(function(resolve, reject) {
        const textureLoader = new THREE.TextureLoader();
        textureLoader.load(
          PAYLOAD.texture_url,
          function(texture) {
            const fallbackMaterial = makeFallbackMaterial(texture);

            const objLoader = new THREE.OBJLoader();
            objLoader.load(
              PAYLOAD.obj_url,
              function(obj) {
                obj.traverse(function(child) {
                  if (child.isMesh) {
                    child.material = fallbackMaterial;
                  }
                });
                resolve(obj);
              },
              undefined,
              function(err) {
                reject(err);
              }
            );
          },
          undefined,
          function(err) {
            reject(err);
          }
        );
      });
    }

    async function loadHand() {
      const textureLoader = new THREE.TextureLoader();
      textureLoader.load(
        PAYLOAD.texture_url,
        function(texture) {
          const fallbackMaterial = makeFallbackMaterial(texture);

          const objLoader = new THREE.OBJLoader();
          objLoader.load(
            PAYLOAD.obj_url,
            function(obj) {
              handMeshes = [];

              obj.traverse(function(child) {
                if (!child.isMesh) return;

                if (child.geometry) {
                  child.geometry.computeVertexNormals();
                }

                child.material = fallbackMaterial;
                child.castShadow = false;
                child.receiveShadow = false;
                handMeshes.push(child);
              });

              handRoot = obj;
              scene.add(handRoot);
              fitCameraToObject(handRoot);
              rebuildPoints(PAYLOAD.points || []);
            },
            undefined,
            function(err) {
              showError("Could not load OBJ:\\n" + err);
            }
          );
        },
        undefined,
        function(err) {
          showError("Could not load texture:\\n" + err);
        }
      );
    }

    window.updateDetections = function(points) {
      rebuildPoints(points || []);
    };

    window.renderViewerOnce = function() {
      if (controls) controls.update();
      if (renderer && scene && camera) {
        renderer.render(scene, camera);
      }
    };

    window.resetCameraView = function() {
      if (handRoot && camera && controls) {
        fitCameraToObject(handRoot);
      }
    };

    function handleEditorShortcut(e) {
      if (!EDITABLE) return;

      const tag = (e.target && e.target.tagName ? e.target.tagName : "").toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return;

      const key = String(e.key || "").toLowerCase();
      if (key === "z" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        if (bridge && bridge.undo) bridge.undo();
      } else if (key === "r" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        if (bridge && bridge.reset_points) bridge.reset_points();
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (bridge && bridge.continue_editor) bridge.continue_editor();
      }
    }

    window.addEventListener("keydown", handleEditorShortcut, true);

    function animate() {
      requestAnimationFrame(animate);
      if (controls) controls.update();
      if (renderer && scene && camera) {
        renderer.render(scene, camera);
      }
    }

    try {
      if (typeof THREE === "undefined") {
        throw new Error("THREE is not available.");
      }
      if (!THREE.OBJLoader) {
        throw new Error("THREE.OBJLoader is not available.");
      }
      if (!THREE.MTLLoader) {
        throw new Error("THREE.MTLLoader is not available.");
      }
      if (!THREE.OrbitControls) {
        throw new Error("THREE.OrbitControls is not available.");
      }

      initChannel();
      initScene();
      loadHand();
      animate();
    } catch (err) {
      showError(err && err.stack ? err.stack : err);
    }
  </script>
</body>
</html>
"""
    return (
        template
        .replace("__VENDOR__", vendor)
        .replace("__CONTROLS__", controls_text)
        .replace("__PAYLOAD_JSON__", payload_json)
        .replace("__EDITABLE__", "true" if editable else "false")
    )


# --------------------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------------------


def _compute_vertex_uv(*, V: np.ndarray, VT: np.ndarray, Fv: np.ndarray, Fvt: np.ndarray) -> np.ndarray:
    if VT.size == 0 or Fv.size == 0 or Fvt.size == 0:
        return np.full((len(V), 2), np.nan, dtype=np.float32)

    acc = [[] for _ in range(len(V))]
    for face_v, face_vt in zip(Fv, Fvt):
        for vi, vti in zip(face_v, face_vt):
            acc[int(vi)].append(VT[int(vti)])

    out = np.full((len(V), 2), np.nan, dtype=np.float32)
    for i, lst in enumerate(acc):
        if not lst:
            continue
        arr = np.asarray(lst, dtype=np.float32)
        out[i] = np.mean(arr, axis=0)
    return out


def _uv_to_px(u: float, v: float, W: int, H: int, v_flip: bool = True) -> tuple[int, int]:
    u = float(np.clip(u, 0.0, 1.0))
    v = float(np.clip(v, 0.0, 1.0))
    x = u * float(W) - 0.5
    if v_flip:
        y = (1.0 - v) * float(H) - 0.5
    else:
        y = v * float(H) - 0.5
    px = int(np.clip(round(x), 0, W - 1))
    py = int(np.clip(round(y), 0, H - 1))
    return px, py


def _closest_point_on_triangle(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ab = b - a
    ac = c - a
    ap = p - a

    d1 = np.dot(ab, ap)
    d2 = np.dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return a, np.array([1.0, 0.0, 0.0], dtype=np.float32)

    bp = p - b
    d3 = np.dot(ab, bp)
    d4 = np.dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return b, np.array([0.0, 1.0, 0.0], dtype=np.float32)

    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3 + 1e-12)
        q = a + v * ab
        return q, np.array([1.0 - v, v, 0.0], dtype=np.float32)

    cp = p - c
    d5 = np.dot(ab, cp)
    d6 = np.dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return c, np.array([0.0, 0.0, 1.0], dtype=np.float32)

    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6 + 1e-12)
        q = a + w * ac
        return q, np.array([1.0 - w, 0.0, w], dtype=np.float32)

    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6) + 1e-12)
        q = b + w * (c - b)
        return q, np.array([0.0, 1.0 - w, w], dtype=np.float32)

    denom = 1.0 / (va + vb + vc + 1e-12)
    v = vb * denom
    w = vc * denom
    u = 1.0 - v - w
    q = a + ab * v + ac * w
    return q, np.array([u, v, w], dtype=np.float32)


def _uv_from_surface_point(
    p: np.ndarray,
    *,
    tri_v: np.ndarray,
    tri_uv: np.ndarray,
    tri_centroids: np.ndarray,
    k: int = 80,
) -> tuple[Optional[np.ndarray], np.ndarray]:
    if tri_v.size == 0:
        return None, p.astype(np.float32)

    d2 = np.sum((tri_centroids - p[None, :]) ** 2, axis=1)
    k = int(np.clip(k, 1, len(d2)))
    cand = np.argpartition(d2, kth=k - 1)[:k]

    best_d2 = float("inf")
    best_uv = None
    best_q = p.astype(np.float32)

    for fi in cand:
        a, b, c = tri_v[fi]
        q, w = _closest_point_on_triangle(p, a, b, c)
        dd = float(np.sum((q - p) ** 2))
        if dd < best_d2:
            best_d2 = dd
            best_q = q.astype(np.float32)

            uvs = tri_uv[fi]
            if np.isfinite(uvs).all():
                uv = w[0] * uvs[0] + w[1] * uvs[1] + w[2] * uvs[2]
                best_uv = uv.astype(np.float32)
            else:
                best_uv = None

    return best_uv, best_q
