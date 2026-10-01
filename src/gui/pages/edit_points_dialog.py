from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsEllipseItem, QGraphicsRectItem,
    QSlider
)


def _cv_bgr_to_qimage(img_bgr: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
    return qimg.copy()


@dataclass
class _UndoOp:
    kind: str  # "remove" | "add"
    payload: pd.DataFrame  # removed rows OR added rows


class _EditView(QGraphicsView):
    """
    - Left drag: selection rect => remove points inside on release
    - Right click: add point when enabled
    - Wheel: zoom
    - Middle / Right drag pan not needed here; right used for add.
    """
    point_added = Signal(int, int)
    rect_committed = Signal(int, int, int, int)  # xmin,ymin,xmax,ymax

    def __init__(self, allow_add_points: bool = True):
        super().__init__()
        self.allow_add_points = bool(allow_add_points)
        self.setScene(QGraphicsScene(self))
        self._pix_item = QGraphicsPixmapItem()
        self.scene().addItem(self._pix_item)

        self._img_w = 1
        self._img_h = 1

        self._dragging = False
        self._drag_start = None
        self._rect_item: QGraphicsRectItem | None = None

        self._panning = False
        self._pan_start = None

        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setFrameShape(QFrame.Box)

        self._zoom_step = 1.25
        self._min_scale = 0.05
        self._max_scale = 40.0

    def set_image(self, pix: QPixmap, w: int, h: int):
        self._img_w = w
        self._img_h = h
        self._pix_item.setPixmap(pix)
        self.scene().setSceneRect(0, 0, w, h)
        self.fitInView(self._pix_item, Qt.KeepAspectRatio)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = self._zoom_step if delta > 0 else (1.0 / self._zoom_step)
        cur = self.transform().m11()
        tgt = cur * factor
        if tgt < self._min_scale or tgt > self._max_scale:
            return
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        # --- PAN with middle button ---
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        # --- Rectangle for deletion (left) ---
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start = self.mapToScene(event.position().toPoint())
            if self._rect_item is None:
                pen = QPen(QColor(255, 0, 0))
                pen.setWidth(2)
                self._rect_item = QGraphicsRectItem()
                self._rect_item.setPen(pen)
                self.scene().addItem(self._rect_item)
            self._rect_item.setRect(QRectF(self._drag_start, self._drag_start))
            event.accept()
            return

        # --- Add point (right), only when enabled ---
        if event.button() == Qt.RightButton:
            if self.allow_add_points:
                sp = self.mapToScene(event.position().toPoint())
                x = int(sp.x()); y = int(sp.y())
                if 0 <= x < self._img_w and 0 <= y < self._img_h:
                    self.point_added.emit(x, y)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # --- PAN with middle button ---
        if self._panning and self._pan_start is not None:
            delta = event.position().toPoint() - self._pan_start
            self._pan_start = event.position().toPoint()

            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())

            event.accept()
            return

        # --- Rectangle for deletion (left) ---
        if self._dragging and self._drag_start is not None and self._rect_item is not None:
            cur = self.mapToScene(event.position().toPoint())
            r = QRectF(self._drag_start, cur).normalized()
            self._rect_item.setRect(r)
            event.accept()
            return

        super().mouseMoveEvent(event)


    def mouseReleaseEvent(self, event):
        # --- END PAN ---
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self._pan_start = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return

        # --- Commit rect (left) ---
        if event.button() == Qt.LeftButton and self._dragging and self._rect_item is not None:
            self._dragging = False
            r = self._rect_item.rect().normalized()
            self._rect_item.setRect(QRectF(0, 0, 0, 0))
            xmin = int(max(0, min(self._img_w - 1, r.left())))
            xmax = int(max(0, min(self._img_w - 1, r.right())))
            ymin = int(max(0, min(self._img_h - 1, r.top())))
            ymax = int(max(0, min(self._img_h - 1, r.bottom())))
            if xmax >= xmin and ymax >= ymin:
                self.rect_committed.emit(xmin, ymin, xmax, ymax)
            event.accept()
            return

        super().mouseReleaseEvent(event)



class EditPointsDialog(QDialog):
    changed = Signal()

    """
    Editor like notebook:
      - Right click add when enabled
      - Left drag remove
      - Z undo, R reset camera, ESC/ENTER/window close apply
    """
    def __init__(self, texture_path: Path, df2d: pd.DataFrame, parent=None, allow_add_points: bool = True):
        super().__init__(parent)
        self.allow_add_points = bool(allow_add_points)
        self.setWindowTitle("Edit detected points (2D)")
        self.resize(1200, 820)

        self.texture_path = Path(texture_path)
        self._img_bgr = cv2.imread(str(self.texture_path), cv2.IMREAD_COLOR)
        if self._img_bgr is None:
            raise FileNotFoundError(self.texture_path)

        self.start_df = df2d.copy().reset_index(drop=True)
        self.df = df2d.copy().reset_index(drop=True)
        self.undo_stack: list[_UndoOp] = []

        self._overlay_items = []
        self._point_radius = 6
        self._apply_callback = self.accept
        self._cancel_callback = self.reject
        self._reset_callback = None
        self._build_ui()
        self._render()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        title = QLabel("Point removal on 2D texture")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")

        help_text = (
            "Controls:\n"
            "• Left + drag: removes points inside the rectangle\n"
            "• Z: undo | R: reset camera | ESC/ENTER/window close: apply"
        )
        if self.allow_add_points:
            help_text = (
                "Controls:\n"
                "• Left + drag: removes points inside the rectangle\n"
                "• Right click: adds a point\n"
                "• Z: undo | R: reset camera | ESC/ENTER/window close: apply"
            )
        help_ = QLabel(help_text)
        help_.setProperty("role", "subtitle")
        help_.setWordWrap(True)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)

        point_size_row = QHBoxLayout()
        point_size_row.setSpacing(10)

        lbl_point_size = QLabel("Point size")
        lbl_point_size.setProperty("role", "sectiontitle")

        self.slider_point_size = QSlider(Qt.Horizontal)
        self.slider_point_size.setRange(3, 200)
        self.slider_point_size.setSingleStep(1)
        self.slider_point_size.setPageStep(1)
        self.slider_point_size.setValue(self._point_radius)
        self.slider_point_size.valueChanged.connect(self._on_point_size_changed)

        self.lbl_point_size_value = QLabel(f"{self._point_radius}px")
        self.lbl_point_size_value.setMinimumWidth(48)
        self.lbl_point_size_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        point_size_row.addWidget(lbl_point_size)
        point_size_row.addWidget(self.slider_point_size, 1)
        point_size_row.addWidget(self.lbl_point_size_value)

        self.view = _EditView(allow_add_points=self.allow_add_points)
        if self.allow_add_points:
            self.view.point_added.connect(self._add_point)
        self.view.rect_committed.connect(self._remove_in_rect)

        bgr = self._img_bgr
        pix = QPixmap.fromImage(_cv_bgr_to_qimage(bgr))
        self.view.set_image(pix, w=bgr.shape[1], h=bgr.shape[0])

        # footer
        bottom = QHBoxLayout()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self._trigger_cancel)
        bottom.addWidget(self.btn_cancel)

        self.lbl_stats = QLabel("")
        self.lbl_stats.setProperty("role", "sectiontitle")
        bottom.addWidget(self.lbl_stats, 0, Qt.AlignLeft)
        bottom.addStretch(1)

        self.btn_undo = QPushButton("Undo (Z)")
        self.btn_reset = QPushButton("Reset Camera (R)")
        self.btn_apply = QPushButton("Apply (ENTER)")

        self.btn_undo.clicked.connect(self._undo)
        self.btn_reset.clicked.connect(self._trigger_reset)
        self.btn_apply.clicked.connect(self.accept)

        bottom.addWidget(self.btn_undo)
        bottom.addWidget(self.btn_reset)
        bottom.addWidget(self.btn_apply)

        outer.addWidget(title)
        outer.addWidget(help_)
        outer.addWidget(line)
        outer.addLayout(point_size_row)
        outer.addWidget(self.view, 1)
        outer.addLayout(bottom)

    def set_apply_callback(self, callback, text: str | None = None):
        """Replace the default Apply button action.

        This is used when the editor is embedded inside a larger validation
        dialog, where Continue must close the parent dialog instead of this
        child widget.
        """
        try:
            self.btn_apply.clicked.disconnect()
        except (TypeError, RuntimeError):
            pass
        if text is not None:
            self.btn_apply.setText(text)
        self._apply_callback = callback
        self.btn_apply.clicked.connect(callback)

    def set_cancel_callback(self, callback):
        """Replace the default Cancel action."""
        self._cancel_callback = callback

    def set_reset_callback(self, callback):
        """Replace the default Reset Camera action."""
        self._reset_callback = callback

    def _trigger_apply(self):
        try:
            self._apply_callback()
        except TypeError:
            self.accept()

    def _trigger_cancel(self):
        try:
            self._cancel_callback()
        except TypeError:
            self.reject()

    def _trigger_reset(self):
        if self._reset_callback is None:
            self.view.fitInView(self.view._pix_item, Qt.KeepAspectRatio)
            return
        try:
            self._reset_callback()
        except TypeError:
            self.view.fitInView(self.view._pix_item, Qt.KeepAspectRatio)

    def set_result_df(self, df2d: pd.DataFrame, reset_start: bool = False, emit_changed: bool = False):
        """Replace the points currently shown by the editor and redraw them."""
        self.df = df2d.copy().reset_index(drop=True)
        if reset_start:
            self.start_df = self.df.copy().reset_index(drop=True)
            self.undo_stack.clear()
        self._render()
        self.view.scene().update()
        self.view.viewport().update()
        self.update()
        if emit_changed:
            self.changed.emit()

    def current_count(self) -> int:
        return int(len(self.df))

    def keyPressEvent(self, event):
        k = event.key()
        if k == Qt.Key_Z:
            self._undo()
            return
        if k == Qt.Key_R:
            self._trigger_reset()
            return
        if k == Qt.Key_Escape:
            self._trigger_apply()
            return
        if k in (Qt.Key_Return, Qt.Key_Enter):
            self._trigger_apply()
            return
        super().keyPressEvent(event)


    def closeEvent(self, event):
        # Closing the 2D editor is treated as applying the current state.
        # This avoids forcing the complete detection workflow to be repeated
        # when the user closes the dialog with the window close button.
        self._trigger_apply()
        event.accept()

    def _add_point(self, x: int, y: int):
        if not self.allow_add_points:
            return
        new_row = pd.DataFrame([{"pixel_x": int(x), "pixel_y": int(y)}])
        self.undo_stack.append(_UndoOp("add", new_row))
        self.df = pd.concat([self.df, new_row], ignore_index=True)
        self._render()
        self.changed.emit()

    def _remove_in_rect(self, xmin: int, ymin: int, xmax: int, ymax: int):
        if self.df.empty:
            return
        inside = (self.df["pixel_x"].between(xmin, xmax)) & (self.df["pixel_y"].between(ymin, ymax))
        removed = self.df[inside]
        if removed.empty:
            return
        self.undo_stack.append(_UndoOp("remove", removed.copy()))
        self.df = self.df[~inside].reset_index(drop=True)
        self._render()
        self.changed.emit()

    def _undo(self):
        if not self.undo_stack:
            return
        op = self.undo_stack.pop()
        if op.kind == "remove":
            self.df = pd.concat([self.df, op.payload], ignore_index=True).reset_index(drop=True)
        elif op.kind == "add":
            n = len(op.payload)
            if n > 0 and len(self.df) >= n:
                self.df = self.df.iloc[:-n].reset_index(drop=True)
        self._render()
        self.changed.emit()

    def _reset(self):
        self.df = self.start_df.copy().reset_index(drop=True)
        self.undo_stack.clear()
        self._render()
        self.changed.emit()

    def _on_point_size_changed(self, value: int):
        self._point_radius = int(value)
        self.lbl_point_size_value.setText(f"{self._point_radius}px")
        self._render()

    def _clear_overlay(self):
        for it in self._overlay_items:
            self.view.scene().removeItem(it)
        self._overlay_items = []

    def _render(self):
        self._clear_overlay()

        # dibujar puntos
        outer_radius = self._point_radius
        inner_radius = max(outer_radius - 1, 1)
        outer_diameter = outer_radius * 2
        inner_diameter = inner_radius * 2

        pen_outer = QPen(QColor(0, 0, 0)); pen_outer.setWidth(max(2, outer_radius // 4))
        pen_inner = QPen(QColor(0, 255, 255)); pen_inner.setWidth(max(2, inner_radius // 4))

        for _, r in self.df.iterrows():
            x = int(r["pixel_x"]); y = int(r["pixel_y"])
            e1 = QGraphicsEllipseItem(x - outer_radius, y - outer_radius, outer_diameter, outer_diameter); e1.setPen(pen_outer)
            e2 = QGraphicsEllipseItem(x - inner_radius, y - inner_radius, inner_diameter, inner_diameter); e2.setPen(pen_inner)
            self.view.scene().addItem(e1); self.view.scene().addItem(e2)
            self._overlay_items.extend([e1, e2])

        # stats
        removed_total = sum(len(op.payload) for op in self.undo_stack if op.kind == "remove")
        added_total = sum(len(op.payload) for op in self.undo_stack if op.kind == "add")
        self.lbl_stats.setText(f"Editing: -{removed_total} +{added_total} | Total: {len(self.df)}")

    def get_result_df(self) -> pd.DataFrame:
        return self.df.copy().reset_index(drop=True)
