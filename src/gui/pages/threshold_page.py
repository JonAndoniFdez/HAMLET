from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import cv2

from PySide6.QtCore import Qt, Signal, QObject, QRunnable, QThreadPool
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QColor, QFont,
    QBrush, QPalette
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QFrame,
    QRadioButton, QButtonGroup, QSpinBox, QGroupBox, QDialog,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsEllipseItem, QGraphicsTextItem, QGraphicsRectItem, QProgressBar,
    QTextEdit
)

from ...core.blender_scripts import blender_script_path
from ...core.paths import asset_path, resolve_blender_exe
from ...core.settings import load_settings
from ...core.blender_runner import (
    build_blender_cmd,
    expected_threshold_preview_output,
    expected_outputs,
    run_blender_rebake_stream,
)
from ...core.output_cleanup import target_ranges_path, threshold_preview_dir

from ...core.thresholds import (
    BLUE_RANGES, apply_preproc_bgr, bgr_to_hsv,
    hsv_wrap_ranges, median_hsv_patch, Pick
)

logger = logging.getLogger(__name__)


def _cv_bgr_to_qimage(img_bgr: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
    return qimg.copy()


class _ImageView(QGraphicsView):
    """
    Viewer with zoom/pan. Left click = pick.
    Right button = pan (drag). Wheel = zoom.
    """
    clicked = Signal(int, int)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self._pix_item = QGraphicsPixmapItem()
        self.scene().addItem(self._pix_item)

        self._overlay_items = []
        self._img_w = 1
        self._img_h = 1

        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QBrush(self.palette().color(QPalette.Base)))
        self.setFrameShape(QFrame.Box)

        self._panning = False
        self._pan_start = None
        self._zoom_step = 1.25
        self._min_scale = 0.05
        self._max_scale = 40.0
        self._interactive = True

        self._disabled_overlay = QGraphicsRectItem(0, 0, 1, 1)
        self._disabled_overlay.setPen(Qt.NoPen)
        self._disabled_overlay.setBrush(self._make_disabled_brush())
        self._disabled_overlay.setZValue(10_000)
        self._disabled_overlay.setVisible(False)
        self.scene().addItem(self._disabled_overlay)

    def _make_disabled_brush(self) -> QBrush:
        base = self.palette().color(QPalette.Base)
        lum = 0.2126 * base.red() + 0.7152 * base.green() + 0.0722 * base.blue()
        if lum < 128:
            return QBrush(QColor(0, 0, 0, 98))
        return QBrush(QColor(255, 255, 255, 98))

    def set_interactive(self, enabled: bool):
        self._interactive = enabled
        self._disabled_overlay.setVisible(not enabled)
        if not enabled and self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)

    def set_image(self, pix: QPixmap, img_w: int, img_h: int):
        self._img_w = img_w
        self._img_h = img_h
        self._pix_item.setPixmap(pix)
        self.scene().setSceneRect(0, 0, img_w, img_h)
        self._disabled_overlay.setRect(0, 0, img_w, img_h)
        self.fit_to_view()

    def fit_to_view(self):
        if self._pix_item.pixmap().isNull():
            return
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self.resetTransform()
        self.fitInView(self._pix_item, Qt.KeepAspectRatio)

    def reset_100(self):
        self.resetTransform()

    def zoom_in(self):
        self._apply_zoom(self._zoom_step)

    def zoom_out(self):
        self._apply_zoom(1.0 / self._zoom_step)

    def _apply_zoom(self, factor: float):
        current = self.transform().m11()
        target = current * factor
        if target < self._min_scale or target > self._max_scale:
            return
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.scale(factor, factor)

    def wheelEvent(self, event):
        if not self._interactive:
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom_in()
        elif delta < 0:
            self.zoom_out()

    def mousePressEvent(self, event):
        if not self._interactive:
            event.ignore()
            return

        if event.button() == Qt.RightButton:
            self._panning = True
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            scene_pos = self.mapToScene(pos)
            x = int(scene_pos.x())
            y = int(scene_pos.y())
            if 0 <= x < self._img_w and 0 <= y < self._img_h:
                self.clicked.emit(x, y)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._interactive:
            event.ignore()
            return

        if self._panning:
            delta = event.position().toPoint() - self._pan_start
            self._pan_start = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if not self._interactive:
            event.ignore()
            return

        if event.button() == Qt.RightButton and self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def clear_overlays(self):
        for it in self._overlay_items:
            self.scene().removeItem(it)
        self._overlay_items = []

    def set_picks_overlay(self, picks: list[Pick]):
        self.clear_overlays()
        if not picks:
            return

        pen_outer = QPen(QColor(0, 0, 0))
        pen_outer.setWidth(2)
        pen_inner = QPen(QColor(0, 255, 255))
        pen_inner.setWidth(2)

        font = QFont()
        font.setPointSize(10)
        font.setBold(True)

        for i, p in enumerate(picks):
            x, y = p.px, p.py
            e1 = QGraphicsEllipseItem(x - 6, y - 6, 12, 12)
            e1.setPen(pen_outer)
            e2 = QGraphicsEllipseItem(x - 5, y - 5, 10, 10)
            e2.setPen(pen_inner)

            t = QGraphicsTextItem(str(i + 1))
            t.setDefaultTextColor(QColor(255, 255, 255))
            t.setFont(font)
            t.setPos(x + 8, y - 10)

            self.scene().addItem(e1)
            self.scene().addItem(e2)
            self.scene().addItem(t)
            self._overlay_items.extend([e1, e2, t])




def _safe_emit(signal, *args):
    try:
        signal.emit(*args)
    except RuntimeError:
        pass


class _PreviewWorkerSignals(QObject):
    log = Signal(str)
    done = Signal(str)
    fail = Signal(str)


class _PreviewRebakeWorker(QRunnable):
    """Runs the reduced Blender process that only generates the manual-selection preview texture."""

    def __init__(self, cmd: list[str], out_png: Path, out_smartuv_obj: Path | None = None):
        super().__init__()
        self.cmd = cmd
        self.out_png = out_png
        self.out_smartuv_obj = out_smartuv_obj
        self.signals = _PreviewWorkerSignals()

    def run(self):
        try:
            proc = run_blender_rebake_stream(self.cmd)
            assert proc.stdout is not None

            for line in proc.stdout:
                if line:
                    _safe_emit(self.signals.log, line.rstrip("\n"))

            rc = proc.wait()

            if rc != 0:
                _safe_emit(self.signals.fail, f"Blender finished with error (returncode={rc}).")
                return
            if not self.out_png.exists():
                _safe_emit(self.signals.fail, f"Expected preview texture not found: {self.out_png}")
                return
            if self.out_smartuv_obj is not None and not self.out_smartuv_obj.exists():
                _safe_emit(self.signals.fail, f"Expected SmartUV reference OBJ not found: {self.out_smartuv_obj}")
                return

            _safe_emit(self.signals.done, str(self.out_png))
        except Exception as e:
            _safe_emit(self.signals.fail, str(e))


class BlenderPreviewDialog(QDialog):
    """
    Modal waiting window used only for the manual threshold path.
    It runs Blender and returns the generated preview texture path.
    """

    def __init__(
        self,
        obj_path: Path,
        texture_path: Path,
        out_dir: Path,
        parent: QWidget | None = None,
        size: int = 2048,
        margin: int = 8,
        uvb_name: str = "UVMap_2",
        window_title: str = "Preparing manual color selection",
        subtitle_text: str | None = None,
        done_status_text: str = "✅ Preview texture generated. Opening manual color selection…",
    ):
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self.resize(760, 460)
        self.setModal(True)

        self.obj_path = obj_path
        self.texture_path = texture_path
        self.out_dir = out_dir
        self.size = size
        self.margin = margin
        self.uvb_name = uvb_name
        self._subtitle_text = subtitle_text
        self._done_status_text = done_status_text
        self.preview_texture_path: Path | None = None
        self.preview_obj_path: Path | None = None
        self._worker = None
        self._failed = False
        self.threadpool = QThreadPool.globalInstance()

        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)

        title = QLabel("Preparing texture preview in Blender")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")

        subtitle = QLabel(
            self._subtitle_text
            or (
                "The normal workflow skips Blender post-processing. "
                "Because manual color selection was chosen, Blender will now generate "
                "only the auxiliary preview texture needed for threshold sampling."
            )
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("role", "subtitle")

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(190)

        self.status = QLabel("Running Blender…")
        self.status.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_close = QPushButton("Cancel")
        self.btn_close.setFixedHeight(38)
        self.btn_close.clicked.connect(self.reject)
        buttons.addWidget(self.btn_close)

        outer.addWidget(title)
        outer.addWidget(subtitle)
        outer.addWidget(self.progress)
        outer.addWidget(QLabel("Process log:"))
        outer.addWidget(self.log_box, 1)
        outer.addWidget(self.status)
        outer.addLayout(buttons)

    def start(self):
        try:
            blender_exe = self._find_blender_exe()
            preview_script = blender_script_path("rebake_traced.py")

            if blender_exe is None:
                self._fail("Blender executable not found. Expected bundled path: <app>/blender/blender.exe")
                return
            if not preview_script.exists():
                self._fail(f"Blender script not found: {preview_script}")
                return
            if not self.obj_path.exists():
                self._fail(f"OBJ file not found: {self.obj_path}")
                return
            if not self.texture_path.exists():
                self._fail(f"Texture file not found: {self.texture_path}")
                return

            preview_dir = threshold_preview_dir(self.out_dir)
            preview_dir.mkdir(parents=True, exist_ok=True)
            out_png = expected_threshold_preview_output(preview_dir)
            out_smartuv_obj, _ = expected_outputs(self.obj_path, preview_dir)

            if self._can_reuse_preview(out_png):
                self._append_log(f"Reusing existing preview texture: {out_png}")
                self._done(str(out_png))
                return

            cmd = build_blender_cmd(
                blender_exe=blender_exe,
                rebake_script=preview_script,
                obj_in=self.obj_path,
                outdir=preview_dir,
                size=self.size,
                margin=self.margin,
                uvb_name=self.uvb_name,
            )

            worker = _PreviewRebakeWorker(cmd, out_png=out_png, out_smartuv_obj=out_smartuv_obj)
            try:
                worker.setAutoDelete(False)
            except Exception:
                pass
            self._worker = worker
            worker.signals.log.connect(self._append_log)
            worker.signals.done.connect(self._done)
            worker.signals.fail.connect(self._fail)
            self.threadpool.start(worker)

        except Exception as e:
            self._fail(str(e))

    def _can_reuse_preview(self, out_png: Path) -> bool:
        if not out_png.exists():
            return False

        smartuv_obj, _ = expected_outputs(self.obj_path, out_png.parent)
        if not smartuv_obj.exists():
            return False

        meta_path = out_png.with_name("NewHandTexture.meta.json")
        try:
            preview_mtime = out_png.stat().st_mtime
            obj_mtime = self.obj_path.stat().st_mtime
            tex_mtime = self.texture_path.stat().st_mtime
            smartuv_mtime = smartuv_obj.stat().st_mtime
            if meta_path.exists():
                meta_mtime = meta_path.stat().st_mtime
                return min(preview_mtime, meta_mtime, smartuv_mtime) >= max(obj_mtime, tex_mtime)
            return min(preview_mtime, smartuv_mtime) >= max(obj_mtime, tex_mtime)
        except Exception:
            return False

    def _find_blender_exe(self) -> Path | None:
        settings = load_settings() or {}
        return resolve_blender_exe(settings)

    def _append_log(self, line: str):
        self.log_box.append(line)

    def _done(self, texture_path: str):
        self._worker = None
        self.preview_texture_path = Path(texture_path)
        self.preview_obj_path, _ = expected_outputs(self.obj_path, self.preview_texture_path.parent)
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.status.setStyleSheet("color: #1b5e20; font-weight: 600;")
        self.status.setText(self._done_status_text)
        self.btn_close.setEnabled(False)
        self.accept()

    def _fail(self, msg: str):
        self._worker = None
        self._failed = True
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status.setStyleSheet("color: #b00020; font-weight: 600;")
        self.status.setText("❌ Could not generate the manual-selection preview.\n" + msg)
        self.btn_close.setText("Close")
        self.btn_close.setEnabled(True)

class ManualThresholdDialog(QDialog):
    """
    Intermediate window used only when the user chooses manual threshold selection.
    It contains the old texture-based picking workflow.
    """

    def __init__(self, texture_path: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Manual color threshold selection")
        self.resize(1200, 820)

        self.texture_path = texture_path
        self.img_bgr: np.ndarray | None = None
        self.img_pp_bgr: np.ndarray | None = None
        self.img_hsv: np.ndarray | None = None
        self.picks: list[Pick] = []
        self.ranges_parts: list[tuple[list[int], list[int]]] = []

        self._build_ui()
        self._load_texture()
        self._update_ui_state()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(10)

        title = QLabel("Manual color selection")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")

        subtitle = QLabel(
            "Click on one or more blue marker points in the texture. "
            "The application will create the HSV threshold ranges from those samples."
        )
        subtitle.setProperty("role", "subtitle")
        subtitle.setWordWrap(True)

        manual_box = QGroupBox("Parameters (manual)")
        manual_layout = QVBoxLayout(manual_box)
        manual_layout.setContentsMargins(14, 14, 14, 14)
        manual_layout.setSpacing(10)

        criteria_row = QHBoxLayout()
        criteria_label = QLabel("Search strictness")
        criteria_label.setStyleSheet("font-weight:600;")

        self.rb_strict_high = QRadioButton("High")
        self.rb_strict_medium = QRadioButton("Medium")
        self.rb_strict_low = QRadioButton("Low")
        self.rb_strict_custom = QRadioButton("Custom")

        self.rb_strict_high.setToolTip("Very restrictive search: smaller HSV tolerance and smaller sampling radius.")
        self.rb_strict_medium.setToolTip("Balanced search: recommended default for most textures.")
        self.rb_strict_low.setToolTip("Less restrictive search: wider HSV tolerance and larger sampling radius.")
        self.rb_strict_custom.setToolTip("Manual mode: the user can freely edit H_TOL, S_TOL, V_TOL and PICK_RADIUS.")

        self.strictness_group = QButtonGroup(self)
        self.strictness_group.addButton(self.rb_strict_high)
        self.strictness_group.addButton(self.rb_strict_medium)
        self.strictness_group.addButton(self.rb_strict_low)
        self.strictness_group.addButton(self.rb_strict_custom)
        self.rb_strict_medium.setChecked(True)

        criteria_row.addWidget(criteria_label)
        criteria_row.addSpacing(12)
        criteria_row.addWidget(self.rb_strict_high)
        criteria_row.addWidget(self.rb_strict_medium)
        criteria_row.addWidget(self.rb_strict_low)
        criteria_row.addWidget(self.rb_strict_custom)
        criteria_row.addStretch(1)

        def _label(txt: str) -> QLabel:
            l = QLabel(txt)
            l.setStyleSheet("font-weight:600;")
            return l

        self.spin_h = QSpinBox(); self.spin_h.setRange(1, 60); self.spin_h.setValue(6)
        self.spin_s = QSpinBox(); self.spin_s.setRange(0, 255); self.spin_s.setValue(30)
        self.spin_v = QSpinBox(); self.spin_v.setRange(0, 255); self.spin_v.setValue(30)
        self.spin_r = QSpinBox(); self.spin_r.setRange(0, 25); self.spin_r.setValue(3)

        params_row = QHBoxLayout()
        params_row.addWidget(_label("H_TOL")); params_row.addWidget(self.spin_h); params_row.addSpacing(12)
        params_row.addWidget(_label("S_TOL")); params_row.addWidget(self.spin_s); params_row.addSpacing(12)
        params_row.addWidget(_label("V_TOL")); params_row.addWidget(self.spin_v); params_row.addSpacing(12)
        params_row.addWidget(_label("PICK_RADIUS")); params_row.addWidget(self.spin_r)
        params_row.addStretch(1)

        manual_layout.addLayout(criteria_row)
        manual_layout.addLayout(params_row)

        self._strictness_presets = {
            "High": {"h": 4, "s": 18, "v": 18, "r": 2},
            "Medium": {"h": 6, "s": 30, "v": 30, "r": 3},
            "Low": {"h": 10, "s": 50, "v": 50, "r": 5},
        }
        self._custom_values = self._current_threshold_values()
        self.rb_strict_high.toggled.connect(lambda checked: checked and self._apply_strictness_preset("High"))
        self.rb_strict_medium.toggled.connect(lambda checked: checked and self._apply_strictness_preset("Medium"))
        self.rb_strict_low.toggled.connect(lambda checked: checked and self._apply_strictness_preset("Low"))
        self.rb_strict_custom.toggled.connect(self._on_custom_strictness_toggled)
        self._apply_strictness_preset("Medium")

        btns = QHBoxLayout()
        self.btn_undo = QPushButton("Undo last")
        self.btn_reset = QPushButton("Reset picks")
        self.btn_zoom_in = QPushButton("Zoom +")
        self.btn_zoom_out = QPushButton("Zoom −")
        self.btn_fit = QPushButton("Fit")
        self.btn_100 = QPushButton("100%")

        self.btn_undo.clicked.connect(self._undo)
        self.btn_reset.clicked.connect(self._reset)
        self.btn_zoom_in.clicked.connect(lambda: self.image_view.zoom_in())
        self.btn_zoom_out.clicked.connect(lambda: self.image_view.zoom_out())
        self.btn_fit.clicked.connect(lambda: self.image_view.fit_to_view())
        self.btn_100.clicked.connect(lambda: self.image_view.reset_100())

        btns.addWidget(self.btn_undo)
        btns.addWidget(self.btn_reset)
        btns.addSpacing(12)
        btns.addWidget(self.btn_zoom_in)
        btns.addWidget(self.btn_zoom_out)
        btns.addWidget(self.btn_fit)
        btns.addWidget(self.btn_100)
        btns.addStretch(1)

        self.image_view = _ImageView()
        self.image_view.setMinimumHeight(520)
        self.image_view.clicked.connect(self._on_image_click)

        footer = QHBoxLayout()
        self.status = QLabel("")
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_continue = QPushButton("Next")
        self.btn_continue.setFixedHeight(40)
        self.btn_continue.setFixedWidth(160)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_continue.clicked.connect(self.accept)
        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_continue)

        outer.addWidget(title)
        outer.addWidget(subtitle)
        outer.addWidget(manual_box)
        outer.addLayout(btns)
        outer.addWidget(self.image_view, stretch=1)
        outer.addLayout(footer)

    def _current_threshold_values(self) -> dict[str, int]:
        return {
            "h": int(self.spin_h.value()),
            "s": int(self.spin_s.value()),
            "v": int(self.spin_v.value()),
            "r": int(self.spin_r.value()),
        }

    def _set_threshold_values(self, values: dict[str, int]):
        self.spin_h.setValue(int(values.get("h", self.spin_h.value())))
        self.spin_s.setValue(int(values.get("s", self.spin_s.value())))
        self.spin_v.setValue(int(values.get("v", self.spin_v.value())))
        self.spin_r.setValue(int(values.get("r", self.spin_r.value())))

    def _set_threshold_controls_editable(self, editable: bool):
        for spin in (self.spin_h, self.spin_s, self.spin_v, self.spin_r):
            spin.setEnabled(editable)

    def _apply_strictness_preset(self, preset_name: str):
        values = self._strictness_presets.get(preset_name)
        if values is None:
            return
        self._set_threshold_values(values)
        self._set_threshold_controls_editable(False)

    def _on_custom_strictness_toggled(self, checked: bool):
        if checked:
            self._set_threshold_values(self._custom_values)
            self._set_threshold_controls_editable(True)
        else:
            self._custom_values = self._current_threshold_values()

    def _selected_strictness_name(self) -> str:
        if self.rb_strict_high.isChecked():
            return "High"
        if self.rb_strict_medium.isChecked():
            return "Medium"
        if self.rb_strict_low.isChecked():
            return "Low"
        return "Custom"

    def _load_texture(self):
        img = cv2.imread(str(self.texture_path), cv2.IMREAD_COLOR)
        if img is None:
            self._set_error(f"Unable to load texture: {self.texture_path}")
            return

        self.img_bgr = img
        self.img_pp_bgr = apply_preproc_bgr(img)
        self.img_hsv = bgr_to_hsv(self.img_pp_bgr)
        self._render_image()

    def _render_image(self):
        if self.img_bgr is None:
            return
        qimg = _cv_bgr_to_qimage(self.img_bgr)
        pix = QPixmap.fromImage(qimg)
        self.image_view.set_image(pix, img_w=self.img_bgr.shape[1], img_h=self.img_bgr.shape[0])
        self.image_view.set_picks_overlay(self.picks)

    def _on_image_click(self, x: int, y: int):
        if self.img_hsv is None:
            return

        h_tol = int(self.spin_h.value())
        s_tol = int(self.spin_s.value())
        v_tol = int(self.spin_v.value())
        radius = int(self.spin_r.value())

        center = median_hsv_patch(self.img_hsv, x, y, radius)
        parts = hsv_wrap_ranges(center, h_tol, s_tol, v_tol)

        for lo, hi in parts:
            self.ranges_parts.append((lo.astype(int).tolist(), hi.astype(int).tolist()))

        self.picks.append(Pick(
            hsv_center=center.astype(int).tolist(),
            px=x,
            py=y,
            parts_added=len(parts),
        ))

        self._render_image()
        self._update_ui_state()

    def _undo(self):
        if not self.picks:
            return
        last = self.picks.pop()
        n = last.parts_added
        if n > 0 and len(self.ranges_parts) >= n:
            self.ranges_parts = self.ranges_parts[:-n]
        self._render_image()
        self._update_ui_state()

    def _reset(self):
        self.picks = []
        self.ranges_parts = []
        self._render_image()
        self._update_ui_state()

    def _set_error(self, msg: str):
        self.status.setText("❌ " + msg)
        self.status.setStyleSheet("color: #b00020; font-weight: 600;")
        self.btn_continue.setEnabled(False)

    def _update_ui_state(self):
        has_image = self.img_bgr is not None
        has_picks = len(self.picks) > 0

        self.btn_undo.setEnabled(has_picks)
        self.btn_reset.setEnabled(has_picks)
        self.btn_zoom_in.setEnabled(has_image)
        self.btn_zoom_out.setEnabled(has_image)
        self.btn_fit.setEnabled(has_image)
        self.btn_100.setEnabled(has_image)
        self.btn_continue.setEnabled(has_image and has_picks)

        if not has_image:
            self._set_error("No texture loaded yet.")
        elif not has_picks:
            self.status.setText("🖱️ Clicks marked: 0 — Click on the texture to define the color threshold.")
            self.status.setStyleSheet("color: #555; font-weight: 600;")
        else:
            self.status.setText(f"🖱️ Clicks marked: {len(self.picks)} — ✅ Configuration ready to save.")
            self.status.setStyleSheet("color: #1b5e20; font-weight: 600;")

    def get_ranges_parts(self) -> list[tuple[list[int], list[int]]]:
        return list(self.ranges_parts)

    def get_picks_hsv(self) -> list[list[int]]:
        return [p.hsv_center for p in self.picks]

    def get_strictness_name(self) -> str:
        return self._selected_strictness_name()

    def get_threshold_values(self) -> dict[str, int]:
        return self._current_threshold_values()


class ThresholdPage(QWidget):
    """
    Simplified threshold selection page.

    The main page only chooses between:
      - Blue matte preset: continue directly.
      - Manual color selection: open an intermediate dialog before continuing.
    """
    next_clicked = Signal(dict)
    back_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.texture_path: Path | None = None
        self.obj_path: Path | None = None
        self.out_dir: Path | None = None
        self.measurement_mode: str = "flat_hand"
        self.manual_preview_texture_path: Path | None = None
        self._build_ui()
        self._update_ui_state()

    def load(self, texture_path: str, out_dir: str, obj_path: str | None = None, measurement_mode: str = "flat_hand"):
        self.texture_path = Path(texture_path)
        self.obj_path = Path(obj_path) if obj_path else None
        self.out_dir = Path(out_dir)
        self.measurement_mode = "flat_hand"
        self.manual_preview_texture_path = None
        self.rb_preset.setChecked(True)
        self._update_ui_state()
        logger.info("Threshold page loaded. Texture: %s", self.texture_path)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(56, 48, 56, 42)
        outer.setSpacing(18)

        title = QLabel("Color Threshold Selection")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")

        subtitle = QLabel(
            "Choose how the application should define the marker color threshold "
            "before starting the automatic marker detection step."
        )
        subtitle.setProperty("role", "subtitle")
        subtitle.setWordWrap(True)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)

        option_box = QGroupBox("Threshold mode")
        option_layout = QVBoxLayout(option_box)
        option_layout.setContentsMargins(22, 20, 22, 20)
        option_layout.setSpacing(18)

        self.rb_preset = QRadioButton("Blue matte color preset")
        self.rb_manual = QRadioButton("Manual color selection")
        self.rb_preset.setChecked(True)

        self.rb_preset.setStyleSheet("font-size: 17px; font-weight: 600;")
        self.rb_manual.setStyleSheet("font-size: 17px; font-weight: 600;")

        preset_desc = QLabel(
            "Recommended option. Uses the predefined HSV ranges for the blue matte markers "
            "and continues directly to marker detection."
        )
        preset_desc.setWordWrap(True)
        preset_desc.setProperty("role", "subtitle")
        preset_desc.setContentsMargins(28, 0, 0, 0)

        manual_desc = QLabel(
            "Opens an intermediate texture viewer where you can click one or more marker points "
            "to generate custom HSV threshold ranges."
        )
        manual_desc.setWordWrap(True)
        manual_desc.setProperty("role", "subtitle")
        manual_desc.setContentsMargins(28, 0, 0, 0)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.rb_preset)
        self.mode_group.addButton(self.rb_manual)
        self.rb_preset.toggled.connect(self._update_ui_state)
        self.rb_manual.toggled.connect(self._update_ui_state)

        option_layout.addWidget(self.rb_preset)
        option_layout.addWidget(preset_desc)
        option_layout.addSpacing(8)
        option_layout.addWidget(self.rb_manual)
        option_layout.addWidget(manual_desc)

        outer.addWidget(title)
        outer.addWidget(subtitle)
        outer.addWidget(line)
        outer.addWidget(option_box)
        outer.addStretch(1)

        footer = QHBoxLayout()
        self.btn_back = QPushButton("Back")
        self.btn_back.setFixedHeight(46)
        self.btn_back.setFixedWidth(120)
        self.btn_back.clicked.connect(self.back_clicked.emit)
        footer.addWidget(self.btn_back, 0, Qt.AlignLeft)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)

        self.btn_continue = QPushButton("Next")
        self.btn_continue.setFixedHeight(46)
        self.btn_continue.setFixedWidth(180)
        self.btn_continue.clicked.connect(self._continue)
        footer.addWidget(self.btn_continue, 0, Qt.AlignRight)
        outer.addLayout(footer)

    def _update_ui_state(self):
        has_texture = self.texture_path is not None and self.texture_path.exists()
        self.btn_continue.setEnabled(has_texture and self.out_dir is not None)

        if not has_texture:
            self.status.setText("❌ No threshold texture loaded yet.")
            self.status.setStyleSheet("color: #b00020; font-weight: 600;")
            return

        if self.rb_preset.isChecked():
            self.status.setText("✅ Blue matte preset selected. Ready to continue.")
            self.status.setStyleSheet("color: #1b5e20; font-weight: 600;")
        else:
            self.status.setText("ℹ️ Manual selection selected. Press Next to open the color picking window.")
            self.status.setStyleSheet("color: #555; font-weight: 600;")

    def _continue(self):
        if self.out_dir is None:
            self._set_error("Output directory not set (out_dir).")
            return
        if self.texture_path is None or not self.texture_path.exists():
            self._set_error("Threshold texture not found.")
            return

        if self.rb_preset.isChecked():
            self._save_and_continue(
                mode="preset_blue",
                ranges_parts=[(list(lo), list(hi)) for lo, hi in BLUE_RANGES],
                picks_hsv=[],
            )
            return

        if self.obj_path is None or not self.obj_path.exists():
            self._set_error("OBJ model not found. Manual threshold selection requires the original OBJ to generate the preview texture.")
            return

        preview_texture = self.manual_preview_texture_path
        if preview_texture is None or not preview_texture.exists():
            wait_dialog = BlenderPreviewDialog(
                obj_path=self.obj_path,
                texture_path=self.texture_path,
                out_dir=self.out_dir,
                parent=self,
            )
            # Show the dialog and start Blender once the event loop is active.
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, wait_dialog.start)
            if wait_dialog.exec() != QDialog.Accepted:
                self.status.setText("ℹ️ Manual selection cancelled or preview generation failed. Choose a mode and press Next to continue.")
                self.status.setStyleSheet("color: #555; font-weight: 600;")
                return
            preview_texture = wait_dialog.preview_texture_path
            self.manual_preview_texture_path = preview_texture

        if preview_texture is None or not preview_texture.exists():
            self._set_error("Manual-selection preview texture was not generated.")
            return

        dialog = ManualThresholdDialog(preview_texture, self)
        if dialog.exec() != QDialog.Accepted:
            self.status.setText("ℹ️ Manual selection cancelled. Choose a mode and press Next to continue.")
            self.status.setStyleSheet("color: #555; font-weight: 600;")
            return

        self._save_and_continue(
            mode="manual_picks",
            ranges_parts=dialog.get_ranges_parts(),
            picks_hsv=dialog.get_picks_hsv(),
            source_texture=preview_texture,
            preview_rebake_generated=True,
            strictness=dialog.get_strictness_name(),
            threshold_values=dialog.get_threshold_values(),
        )

    def _set_error(self, msg: str):
        self.status.setText("❌ " + msg)
        self.status.setStyleSheet("color: #b00020; font-weight: 600;")
        self.btn_continue.setEnabled(False)

    def _save_and_continue(
        self,
        mode: str,
        ranges_parts: list[tuple[list[int], list[int]]],
        picks_hsv: list[list[int]],
        source_texture: Path | None = None,
        preview_rebake_generated: bool = False,
        strictness: str | None = None,
        threshold_values: dict[str, int] | None = None,
    ):
        if self.out_dir is None:
            self._set_error("Output directory not set (out_dir).")
            return

        self.out_dir.mkdir(parents=True, exist_ok=True)
        target_json = target_ranges_path(self.out_dir)

        payload = {
            "name": "target",
            "mode": mode,
            "picks_hsv": picks_hsv,
            "ranges_parts": [{"lo": lo, "hi": hi} for lo, hi in ranges_parts],
            "source_texture": str(source_texture or self.texture_path) if (source_texture or self.texture_path) else None,
            "original_texture": str(self.texture_path) if self.texture_path else None,
            "obj_path": str(self.obj_path) if self.obj_path else None,
            "measurement_mode": "flat_hand",
            "manual_preview_texture": str(source_texture) if source_texture else None,
            "preview_rebake_generated": bool(preview_rebake_generated),
            "use_preproc_for_pick": True,
        }
        if strictness is not None:
            payload["manual_strictness"] = strictness
        if threshold_values is not None:
            payload["manual_threshold_values"] = threshold_values

        target_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

        emit_payload = {
            "target_json": str(target_json),
            "threshold_mode": mode,
            "preview_rebake_generated": bool(preview_rebake_generated),
            "obj_path": str(self.obj_path) if self.obj_path else None,
            "texture_path": str(self.texture_path) if self.texture_path else None,
            "measurement_mode": "flat_hand",
        }
        if source_texture is not None:
            emit_payload["threshold_texture_path"] = str(source_texture)
            emit_payload["manual_preview_texture"] = str(source_texture)
        self.next_clicked.emit(emit_payload)
