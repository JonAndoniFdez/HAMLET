import argparse
import csv
import sys
from pathlib import Path

import numpy as np

#PaperRelease
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

try:
    from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
except Exception:  # pragma: no cover
    from vtk.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

try:
    from vtkmodules.vtkRenderingCore import vtkPropPicker
except Exception:  # pragma: no cover
    from vtk.vtkRenderingCore import vtkPropPicker

try:
    from vtkmodules.vtkRenderingCore import vtkTextActor
except Exception:  # pragma: no cover
    try:
        from vtk.vtkRenderingCore import vtkTextActor
    except Exception:
        vtkTextActor = None

try:
    from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
except Exception:  # pragma: no cover
    try:
        from vtk import vtkInteractorStyleTrackballCamera
    except Exception:
        vtkInteractorStyleTrackballCamera = None

from vedo import Mesh, Sphere


# -------------------------------------------------------
# Argument parsing
# -------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Interactive 3D label editor")
    p.add_argument("--detections", required=True, help="CSV of labeled detections (detections_labeled.csv)")
    p.add_argument("--template", required=True, help="CSV of markers_template.csv")
    p.add_argument("--mesh", required=False, help="3D model of the hand (OBJ/PLY) for visualization")
    p.add_argument("--out", required=True, help="Output CSV with corrected labels")
    p.add_argument("--top_k", type=int, default=10, help="Maximum number of candidates to show in dropdown")
    p.add_argument(
        "--label_scale_factor",
        type=float,
        default=1.0,
        help="Multiplier factor for the base size of 3D labels (Text3D).",
    )
    p.add_argument(
        "--help_scale",
        type=float,
        default=0.6,
        help="Reserved for compatibility with previous editor versions.",
    )
    p.add_argument(
        "--no_align_bbox",
        action="store_true",
        help="Do not align the bounding box of points to the mesh (by default it IS aligned)",
    )
    p.add_argument(
        "--colors_csv",
        required=False,
        help="Optional CSV mapping labels to colors (columns like 'label;color' or 'label,color').",
    )
    return p.parse_args()


# -------------------------------------------------------
# Loading CSVs
# -------------------------------------------------------

def load_template(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            for key in (
                "x_local1",
                "y_local1",
                "z_local1",
                "x_local2",
                "y_local2",
                "z_local2",
            ):
                if key in r and r[key] not in ("", None):
                    r[key] = float(r[key])
            rows.append(r)
    if not rows:
        raise RuntimeError(f"markers_template.csv '{path}' is empty or has no rows.")
    return rows


def load_detections(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise RuntimeError(f"Detections CSV '{path}' has no headers.")
        for r in reader:
            for key in (
                "x",
                "y",
                "z",
                "x_local1_det",
                "y_local1_det",
                "z_local1_det",
                "x_local2_det",
                "y_local2_det",
                "z_local2_det",
            ):
                if key in r and r[key] not in ("", None):
                    r[key] = float(r[key])
            rows.append(r)
    if not rows:
        raise RuntimeError(f"Detections CSV '{path}' is empty or has no rows.")
    return rows, fieldnames


def _normalize_hex_color(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if not raw.startswith("#"):
        raw = f"#{raw}"
    if len(raw) != 7:
        return None
    hex_part = raw[1:]
    if any(ch not in "0123456789abcdefABCDEF" for ch in hex_part):
        return None
    return raw.upper()


def load_label_colors(path):
    path = Path(path)
    if not path.exists():
        raise RuntimeError(f"Colors CSV not found: {path}")

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        delimiter = ";"
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ";" if ";" in sample else ","

        reader = csv.DictReader(f, delimiter=delimiter)
        if not reader.fieldnames:
            raise RuntimeError(f"Colors CSV '{path}' has no headers.")

        fields_lower = {name.strip().lower(): name for name in reader.fieldnames if name}
        label_key = next((fields_lower[k] for k in ("label", "point", "marker") if k in fields_lower), None)
        color_key = next((fields_lower[k] for k in ("color", "colour", "hex") if k in fields_lower), None)

        if label_key is None or color_key is None:
            raise RuntimeError(
                f"Colors CSV '{path}' must contain label/point/marker and color/hex columns."
            )

        label_colors = {}
        for row in reader:
            label = (row.get(label_key, "") or "").strip()
            color = _normalize_hex_color(row.get(color_key, ""))
            if not label or not color:
                continue
            label_colors[label] = color

    return label_colors




# -------------------------------------------------------
# Camera interaction style
# -------------------------------------------------------

if vtkInteractorStyleTrackballCamera is not None:
    class AmanoTrackballCameraStyle(vtkInteractorStyleTrackballCamera):
        """
        Normalized camera controls shared with the 3D landmark editor.

        - Left drag: rotate camera
        - Right drag: pan camera
        - Middle drag: zoom/dolly camera
        - Mouse wheel: zoom/dolly camera
        """

        def __init__(self):
            super().__init__()
            self.AddObserver("LeftButtonPressEvent", self._left_button_press_event)
            self.AddObserver("LeftButtonReleaseEvent", self._left_button_release_event)
            self.AddObserver("RightButtonPressEvent", self._right_button_press_event)
            self.AddObserver("RightButtonReleaseEvent", self._right_button_release_event)
            self.AddObserver("MiddleButtonPressEvent", self._middle_button_press_event)
            self.AddObserver("MiddleButtonReleaseEvent", self._middle_button_release_event)

        def _left_button_press_event(self, _obj, _event):
            # Default TrackballCamera behavior: left button rotates.
            self.OnLeftButtonDown()

        def _left_button_release_event(self, _obj, _event):
            self.OnLeftButtonUp()

        def _right_button_press_event(self, _obj, _event):
            # Default TrackballCamera middle button pans.
            # Mapping it here makes right drag behave as pan.
            self.OnMiddleButtonDown()

        def _right_button_release_event(self, _obj, _event):
            self.OnMiddleButtonUp()

        def _middle_button_press_event(self, _obj, _event):
            # Default TrackballCamera right button dollies/zooms.
            # Mapping it here makes middle drag behave as zoom.
            self.OnRightButtonDown()

        def _middle_button_release_event(self, _obj, _event):
            self.OnRightButtonUp()
else:  # pragma: no cover
    AmanoTrackballCameraStyle = None


# -------------------------------------------------------
# Scoring candidates by label
# -------------------------------------------------------

def score_detection_for_template(det_row, tpl_row, world_dist_fallback=None):
    score_terms = []

    tpl_b1 = tpl_row["bone_name1"]
    det_b1 = det_row.get("bone_name1_det", "")

    if det_b1 and det_b1 == tpl_b1:
        dx = det_row["x_local1_det"] - tpl_row["x_local1"]
        dy = det_row["y_local1_det"] - tpl_row["y_local1"]
        dz = det_row["z_local1_det"] - tpl_row["z_local1"]
        score_terms.append((dx * dx + dy * dy + dz * dz) ** 0.5)

    tpl_b2 = tpl_row.get("bone_name2", "")
    det_b2 = det_row.get("bone_name2_det", "")

    if tpl_b2 and det_b2 and det_b2 == tpl_b2:
        dx = det_row["x_local2_det"] - tpl_row["x_local2"]
        dy = det_row["y_local2_det"] - tpl_row["y_local2"]
        dz = det_row["z_local2_det"] - tpl_row["z_local2"]
        score_terms.append((dx * dx + dy * dy + dz * dz) ** 0.5)

    if score_terms:
        return sum(score_terms) / len(score_terms)

    if world_dist_fallback is not None:
        return world_dist_fallback

    return 1e9


def compute_candidates_for_detection(det_row, template_rows, top_k=10):
    cands = []
    for tpl in template_rows:
        label = tpl["label"]
        s = score_detection_for_template(det_row, tpl, world_dist_fallback=None)
        cands.append((label, s))
    cands.sort(key=lambda x: x[1])
    if top_k is not None:
        cands = cands[:top_k]
    return cands


class LabelChoiceDialog(QDialog):
    def __init__(self, parent, pid, current_label, near_labels, all_labels):
        super().__init__(parent)
        self.setWindowTitle(f"Point {pid}")
        self.setModal(True)

        layout = QVBoxLayout(self)

        title = QLabel("<b>Point editing</b>")
        current = QLabel(f"Point {pid}<br>Current label: {current_label or '-'}")
        current.setTextFormat(Qt.RichText)
        layout.addWidget(title)
        layout.addWidget(current)

        form = QFormLayout()
        layout.addLayout(form)

        self.mode_group = QButtonGroup(self)
        self.near_radio = QRadioButton("Nearby points")
        self.all_radio = QRadioButton("All points")
        self.mode_group.addButton(self.near_radio)
        self.mode_group.addButton(self.all_radio)

        self.near_combo = QComboBox()
        self.near_combo.addItems(near_labels)
        self.all_combo = QComboBox()
        self.all_combo.addItems(all_labels)

        if near_labels:
            self.near_combo.setCurrentIndex(0)
        if current_label and current_label in all_labels:
            self.all_combo.setCurrentText(current_label)
        elif all_labels:
            self.all_combo.setCurrentIndex(0)

        self.near_radio.setChecked(True)

        near_row = QWidget()
        near_layout = QHBoxLayout(near_row)
        near_layout.setContentsMargins(0, 0, 0, 0)
        near_layout.addWidget(self.near_radio)
        near_layout.addWidget(self.near_combo, 1)

        all_row = QWidget()
        all_layout = QHBoxLayout(all_row)
        all_layout.setContentsMargins(0, 0, 0, 0)
        all_layout.addWidget(self.all_radio)
        all_layout.addWidget(self.all_combo, 1)

        form.addRow(near_row)
        form.addRow(all_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.near_radio.toggled.connect(self._refresh_ui)
        self._refresh_ui()

    def _refresh_ui(self):
        use_near = self.near_radio.isChecked()
        self.near_combo.setEnabled(use_near)
        self.all_combo.setEnabled(not use_near)

    def selected_label(self):
        if self.near_radio.isChecked():
            return self.near_combo.currentText().strip()
        return self.all_combo.currentText().strip()


class InteractiveLabelEditorWindow(QMainWindow):
    def __init__(
        self,
        detections,
        template_rows,
        mesh_path,
        top_k,
        out_csv,
        det_fieldnames,
        align_bbox=True,
        label_scale_factor=1.0,
        help_scale=0.6,
        label_colors=None,
    ):
        super().__init__()
        self.setWindowTitle("Interactive label editor")
        self.resize(1500, 950)

        self.detections = detections
        self.template_rows = template_rows
        self.mesh_path = mesh_path
        self.top_k = top_k
        self.out_csv = Path(out_csv)
        self.det_fieldnames = det_fieldnames
        self.align_bbox = align_bbox
        self.label_scale_factor = float(label_scale_factor)
        self.help_scale = float(help_scale)
        self.label_colors = dict(label_colors or {})
        self._saved = False
        self._cancelled = False
        self._dialog_open = False
        self._pending_pick_pid = None
        self._vtk_left_press_observer_id = None
        self._vtk_mouse_move_observer_id = None
        self._hover_pid = None
        self._help_actor = None
        self._camera_style = None
        self._initial_detections = [dict(d) for d in detections]

        self.pts_coords = np.array([[d["x"], d["y"], d["z"]] for d in detections], dtype=float)
        self.pts_vis_coords = self.pts_coords.copy()
        self.mesh_obj = None
        if mesh_path is not None and Path(mesh_path).exists():
            self.mesh_obj = Mesh(str(mesh_path))

        self.labels = [(d.get("label", "") or "") for d in detections]
        self.label_to_pid = {}
        self._rebuild_label_index()
        self.all_labels_sorted = sorted({tpl["label"] for tpl in template_rows if tpl.get("label")})
        self.undo_stack = []
        self.point_actors = {}
        self.actor_to_pid = {}
        self.label_actors = []

        self._prepare_visual_coordinates()
        self._prepare_sizes()
        self._build_ui()
        self._build_scene()

    def _prepare_visual_coordinates(self):
        print("\n[DEBUG] Points CSV extent (original coords):")
        print("  min:", self.pts_coords.min(axis=0))
        print("  max:", self.pts_coords.max(axis=0))

        if self.mesh_obj is not None:
            print(f"[DEBUG] OBJ mesh for visualization: {self.mesh_path}")
            print("  bounds mesh:", self.mesh_obj.bounds())
        else:
            print("[DEBUG] No OBJ mesh, only points will be shown.")

        if self.mesh_obj is not None and self.align_bbox:
            p_min = self.pts_coords.min(axis=0)
            p_max = self.pts_coords.max(axis=0)
            p_center = 0.5 * (p_min + p_max)
            p_diag = np.linalg.norm(p_max - p_min)

            bx = self.mesh_obj.bounds()
            m_min = np.array([bx[0], bx[2], bx[4]], dtype=float)
            m_max = np.array([bx[1], bx[3], bx[5]], dtype=float)
            m_center = 0.5 * (m_min + m_max)
            m_diag = np.linalg.norm(m_max - m_min)

            scale = (m_diag / p_diag) if (p_diag > 0 and m_diag > 0) else 1.0
            print("[DEBUG] Aligning bbox points->mesh (visual only):")
            print("  scale:", scale)
            self.pts_vis_coords = (self.pts_coords - p_center) * scale + m_center

    def _prepare_sizes(self):
        bbox_min = self.pts_vis_coords.min(axis=0)
        bbox_max = self.pts_vis_coords.max(axis=0)
        self.diag = float(np.linalg.norm(bbox_max - bbox_min)) or 1.0

        self.base_text_scale = self.diag * 0.03 * self.label_scale_factor

        # Debe comenzar en 20
        self.text_slider_value = 20
        self.text_scale_factor = max(0.25, float(self.text_slider_value) / 100.0)
        self.text_scale = self.base_text_scale * self.text_scale_factor

        self.y_offset = self.diag * 0.01

        # Debe comenzar en 2
        self.point_radius = 2.0

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        sliders_layout = QHBoxLayout()
        sliders_layout.setContentsMargins(0, 0, 0, 0)
        sliders_layout.setSpacing(12)

        sliders_layout.addWidget(QLabel("Sphere size"))
        self.sphere_slider = QSlider(Qt.Horizontal)
        self.sphere_slider.setRange(1, 5)
        self.sphere_slider.setValue(2)
        self.sphere_value = QLabel("2")
        self.sphere_value.setMinimumWidth(36)
        sliders_layout.addWidget(self.sphere_slider, 1)
        sliders_layout.addWidget(self.sphere_value)

        sliders_layout.addSpacing(24)

        sliders_layout.addWidget(QLabel("Text size"))
        self.text_slider = QSlider(Qt.Horizontal)
        self.text_slider.setRange(10, 100)
        self.text_slider.setValue(20)
        self.text_value = QLabel("20")
        self.text_value.setMinimumWidth(48)
        sliders_layout.addWidget(self.text_slider, 1)
        sliders_layout.addWidget(self.text_value)

        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(12)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self._cancel_editor)
        self.btn_undo = QPushButton("Undo (Z)")
        self.btn_reset = QPushButton("Reset Camera (R)")
        self.btn_continue = QPushButton("Continue (ENTER)")

        for button in (self.btn_cancel, self.btn_undo, self.btn_reset, self.btn_continue):
            button.setMinimumHeight(36)

        self.btn_cancel.setFixedWidth(110)
        self.btn_undo.setFixedWidth(110)
        self.btn_reset.setFixedWidth(150)
        self.btn_continue.setFixedWidth(160)

        buttons_layout.addWidget(self.btn_cancel)
        buttons_layout.addStretch(1)
        buttons_layout.addWidget(self.btn_undo)
        buttons_layout.addWidget(self.btn_reset)
        buttons_layout.addWidget(self.btn_continue)

        controls_layout.addLayout(sliders_layout)
        controls_layout.addLayout(buttons_layout)

        self.vtk_widget = QVTKRenderWindowInteractor(central)
        self.vtk_widget.setFocusPolicy(Qt.StrongFocus)

        hover_row = QWidget()
        hover_layout = QHBoxLayout(hover_row)
        hover_layout.setContentsMargins(0, 0, 0, 0)
        hover_layout.setSpacing(0)
        self.hover_label = QLabel("Etiqueta: -")
        self.hover_label.setMinimumWidth(260)
        self.hover_label.setStyleSheet(
            "QLabel {"
            "background: #111820;"
            "color: #f2f6ff;"
            "border: 1px solid #4f6f91;"
            "border-radius: 4px;"
            "padding: 6px 10px;"
            "font-weight: 600;"
            "font-size: 18px;"
            "}"
        )
        hover_layout.addWidget(self.hover_label, 0, Qt.AlignLeft)
        hover_layout.addStretch(1)

        layout.addWidget(controls)
        layout.addWidget(self.vtk_widget, 1)
        layout.addWidget(hover_row)

        self.sphere_slider.valueChanged.connect(self._on_sphere_slider_changed)
        self.text_slider.valueChanged.connect(self._on_text_slider_changed)
        self.btn_undo.clicked.connect(self._undo_last_change)
        self.btn_reset.clicked.connect(self._reset_camera_view)
        self.btn_continue.clicked.connect(self.close)

    def _build_scene(self):
        from vedo import Plotter, Text3D

        self._Text3D = Text3D
        self.plt = Plotter(qt_widget=self.vtk_widget, bg="black")

        if self.mesh_obj is not None:
            self.mesh_obj.c("white").alpha(0.7)
            self.mesh_obj.pickable(False)
            self.plt.add(self.mesh_obj)

        self._rebuild_point_actors()
        self._rebuild_label_actors()
        self._add_help_legend_actor()

        if hasattr(self.plt, "add_callback"):
            self.plt.add_callback("KeyPress", self._on_key_press)

        print("\n[INFO] Interactive window opened.")
        print("       -> LEFT DRAG rotates the camera.")
        print("       -> RIGHT DRAG pans the camera.")
        print("       -> MIDDLE DRAG or MOUSE WHEEL zooms the camera.")
        print("       -> LEFT CLICK on a point to edit its label.")
        print("       -> Press Z to undo the last change.")
        print("       -> Press R to reset the camera.")
        print("       -> Press ENTER or click Continue when done.\n")

        self.plt.show(resetcam=True, interactive=False)

        try:
            self.vtk_widget.Initialize()
        except Exception:
            pass
        try:
            self.vtk_widget.Start()
        except Exception:
            pass

        self._apply_normalized_camera_controls()
        self._install_vtk_interaction_hooks()

    def _apply_normalized_camera_controls(self):
        """Apply the same camera-button mapping used by the 3D landmark editor."""
        if AmanoTrackballCameraStyle is None:
            print("[WARNING] Custom VTK camera style is not available; using default controls.")
            return

        iren = self._vtk_interactor()
        if iren is None:
            print("[WARNING] Could not get VTK interactor; default camera controls remain active.")
            return

        try:
            style = AmanoTrackballCameraStyle()
            style.SetDefaultRenderer(self._vtk_renderer())
            iren.SetInteractorStyle(style)
            self._camera_style = style  # Keep Python reference alive.
            print("[INFO] Camera controls normalized: left=rotate, right=pan, middle=zoom.")
        except Exception as e:
            print(f"[WARNING] Could not apply normalized camera controls: {e}")

    def _add_help_legend_actor(self):
        """Add a compact, styled controls legend inside the VTK viewport."""
        if vtkTextActor is None:
            return

        try:
            actor = vtkTextActor()
            actor.SetInput(
                "    \n"
                "  LABEL EDITOR  \n"
                "  -----------------------------  \n"
                "  Left drag       Rotate view  \n"
                "  Right drag      Pan view  \n"
                "  Middle drag     Zoom view  \n"
                "  Mouse wheel     Zoom view  \n"
                "  Left click      Edit point label  \n"
                "  Z               Undo last change  \n"
                "  R               Reset camera  \n"
                "  ENTER           Continue  "
                "    \n"

            )

            try:
                actor.SetTextScaleModeToNone()
            except Exception:
                pass

            prop = actor.GetTextProperty()
            try:
                prop.SetFontFamilyToArial()
            except Exception:
                pass
            try:
                prop.SetFontSize(17)
            except Exception:
                pass
            try:
                prop.SetColor(0.94, 0.96, 1.0)
            except Exception:
                pass
            try:
                prop.BoldOff()
            except Exception:
                pass
            try:
                prop.ShadowOn()
                prop.SetShadowOffset(1, -1)
                prop.SetShadowColor(0.0, 0.0, 0.0)
            except Exception:
                pass
            try:
                prop.SetLineSpacing(1.18)
            except Exception:
                pass
            try:
                prop.SetBackgroundColor(0.08, 0.09, 0.11)
                prop.SetBackgroundOpacity(0.78)
            except Exception:
                pass
            try:
                prop.SetFrame(1)
                prop.SetFrameColor(0.35, 0.48, 0.65)
            except Exception:
                pass
            try:
                prop.SetVerticalJustificationToTop()
            except Exception:
                pass

            try:
                actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
                actor.GetPositionCoordinate().SetValue(0.018, 0.965)
            except Exception:
                pass

            renderer = getattr(self.plt, "renderer", None)
            if renderer is not None and hasattr(renderer, "AddActor2D"):
                renderer.AddActor2D(actor)
                self._help_actor = actor
        except Exception as e:
            print(f"[WARNING] Could not create help legend: {e}")

    def _reset_camera_view(self):
        try:
            if hasattr(self, "plt") and self.plt is not None:
                try:
                    self.plt.reset_camera()
                except Exception:
                    renderer = getattr(self.plt, "renderer", None)
                    if renderer is not None and hasattr(renderer, "ResetCamera"):
                        renderer.ResetCamera()
                self.plt.render()
        except Exception as e:
            print(f"[WARNING] Could not reset camera: {e}")

    def _rebuild_label_index(self):
        self.label_to_pid = {}
        for i, lab in enumerate(self.labels):
            lab = (lab or "").strip()
            if lab:
                self.label_to_pid[lab] = i

    def _reset_to_initial_labels(self):
        self.detections = [dict(d) for d in self._initial_detections]
        self.labels = [(d.get("label", "") or "") for d in self.detections]
        self._rebuild_label_index()
        self.undo_stack.clear()
        self._saved = False
        self._rebuild_point_actors()
        self._rebuild_label_actors()
        self._refresh_hover_label()
        self.plt.render()
        print("[RESET] Initial labels restored.")

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
            self._undo_last_change()
            event.accept()
            return
        if text == "r":
            self._reset_camera_view()
            event.accept()
            return
        if key in (key_return, key_enter, key_escape):
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def _install_vtk_interaction_hooks(self):
        iren = self._vtk_interactor()
        if iren is None:
            print("[WARNING] Could not get VTK interactor; click interception disabled.")
            return

        try:
            if self._vtk_left_press_observer_id is not None:
                iren.RemoveObserver(self._vtk_left_press_observer_id)
        except Exception:
            pass
        try:
            if self._vtk_mouse_move_observer_id is not None:
                iren.RemoveObserver(self._vtk_mouse_move_observer_id)
        except Exception:
            pass

        try:
            self._vtk_left_press_observer_id = iren.AddObserver(
                "LeftButtonPressEvent",
                self._on_left_button_press_vtk,
                1.0,
            )
        except TypeError:
            self._vtk_left_press_observer_id = iren.AddObserver(
                "LeftButtonPressEvent",
                self._on_left_button_press_vtk,
            )

        try:
            self._vtk_mouse_move_observer_id = iren.AddObserver(
                "MouseMoveEvent",
                self._on_mouse_move_vtk,
                0.8,
            )
        except TypeError:
            self._vtk_mouse_move_observer_id = iren.AddObserver(
                "MouseMoveEvent",
                self._on_mouse_move_vtk,
            )

    def _hover_text_for_pid(self, pid):
        if pid is None or pid < 0 or pid >= len(self.labels):
            return "Etiqueta: -"
        label = (self.labels[pid] or "").strip() or "(sin etiqueta)"
        return f"Etiqueta: {label}"

    def _set_hover_pid(self, pid):
        if pid == self._hover_pid:
            return
        self._hover_pid = pid
        self._refresh_hover_label()

    def _refresh_hover_label(self):
        if hasattr(self, "hover_label"):
            self.hover_label.setText(self._hover_text_for_pid(self._hover_pid))

    def _on_mouse_move_vtk(self, _obj, _evt_name):
        if self._dialog_open:
            self._set_hover_pid(None)
            return

        iren = self._vtk_interactor()
        self._set_hover_pid(self._pick_point_pid_at_event(iren))

    @staticmethod
    def _classify_suffix(label: str) -> str:
        u = (label or "").strip().upper()
        if u.endswith("MCP"):
            return "MCP"
        if u.endswith("PIP"):
            return "PIP"
        if u.endswith("DIP"):
            return "DIP"
        if u.endswith("MP"):
            return "MP"
        return "OTHER"

    def _group_color(self, group: str) -> str:
        return {
            "MCP": "darkblue",
            "PIP": "green",
            "MP": "blue",
            "DIP": "green",
            "OTHER": "cyan",
        }[group]

    def _point_color_for_label(self, label: str) -> str:
        mapped = self.label_colors.get((label or "").strip())
        if mapped:
            return mapped
        return self._group_color(self._classify_suffix(label))

    def _rebuild_point_actors(self):
        for _pid, actor in list(self.point_actors.items()):
            try:
                self.plt.remove(actor)
            except Exception:
                pass

        self.point_actors = {}
        self.actor_to_pid = {}

        for pid, lab in enumerate(self.labels):
            p_vis = self.pts_vis_coords[pid]
            color = self._point_color_for_label(lab)

            actor = Sphere(
                pos=(float(p_vis[0]), float(p_vis[1]), float(p_vis[2])),
                r=float(self.point_radius),
                c=color,
                res=20,
            )
            actor.pickable(True)

            self.plt.add(actor)
            self.point_actors[pid] = actor
            self.actor_to_pid[actor] = pid

    def _label_position_for_pid(self, pid):
        p_vis = self.pts_vis_coords[pid]
        return (float(p_vis[0]), float(p_vis[1] + self.y_offset), float(p_vis[2]))

    def _rebuild_label_actors(self):
        for actor in list(self.label_actors):
            if actor is None:
                continue
            try:
                actor.pickable(False)
            except Exception:
                pass
            try:
                self.plt.remove(actor)
            except Exception:
                pass

        self.label_actors = [None] * len(self.labels)

        for pid, lab in enumerate(self.labels):
            lab = (lab or "").strip()
            if not lab:
                continue

            pos = self._label_position_for_pid(pid)
            txt = self._Text3D(lab, pos=pos, s=float(self.text_scale), c="white", justify="center")
            try:
                txt.pickable(False)
            except Exception:
                pass
            self.label_actors[pid] = txt
            self.plt.add(txt)

    def _replace_label_actor(self, pid, new_text):
        old_actor = self.label_actors[pid] if pid < len(self.label_actors) else None
        if old_actor is not None:
            try:
                self.plt.remove(old_actor)
            except Exception:
                pass

        new_text = (new_text or "").strip()
        if not new_text:
            if pid < len(self.label_actors):
                self.label_actors[pid] = None
            return

        pos = self._label_position_for_pid(pid)
        new_actor = self._Text3D(new_text, pos=pos, s=float(self.text_scale), c="white", justify="center")
        try:
            new_actor.pickable(False)
        except Exception:
            pass

        if pid < len(self.label_actors):
            self.label_actors[pid] = new_actor
        else:
            while len(self.label_actors) < pid:
                self.label_actors.append(None)
            self.label_actors.append(new_actor)
        self.plt.add(new_actor)

    def _set_label(self, pid, new_label):
        old_label = (self.detections[pid].get("label", "") or "").strip()
        if old_label and self.label_to_pid.get(old_label, None) == pid:
            del self.label_to_pid[old_label]

        self.detections[pid]["label"] = new_label
        self.labels[pid] = new_label
        if new_label:
            self.label_to_pid[new_label] = pid

        self._replace_label_actor(pid, new_label)
        self._rebuild_point_actors()
        self._refresh_hover_label()

    def _apply_swap(self, pid_a, pid_b, label_a, label_b):
        self.detections[pid_a]["label"] = label_b
        self.labels[pid_a] = label_b
        self.detections[pid_b]["label"] = label_a
        self.labels[pid_b] = label_a

        if label_a:
            self.label_to_pid[label_a] = pid_b
        if label_b:
            self.label_to_pid[label_b] = pid_a

        self._replace_label_actor(pid_a, label_b)
        self._replace_label_actor(pid_b, label_a)
        self._rebuild_point_actors()
        self._refresh_hover_label()

    def _on_sphere_slider_changed(self, value):
        self.point_radius = max(1.0, float(value))
        self.sphere_value.setText(str(int(round(self.point_radius))))
        self._rebuild_point_actors()
        self.plt.render()

    def _on_text_slider_changed(self, value):
        self.text_slider_value = int(value)
        self.text_scale_factor = max(0.25, float(value) / 100.0)
        self.text_scale = self.base_text_scale * self.text_scale_factor
        self.text_value.setText(str(int(value)))
        self._rebuild_label_actors()
        self.plt.render()

    def _vtk_interactor(self):
        try:
            rw = self.vtk_widget.GetRenderWindow()
            if rw is None:
                return None
            return rw.GetInteractor()
        except Exception:
            return None

    def _vtk_renderer(self):
        try:
            rw = self.vtk_widget.GetRenderWindow()
            if rw is None:
                return None
            return rw.GetRenderers().GetFirstRenderer()
        except Exception:
            return None

    def _pick_point_pid_at_event(self, iren):
        renderer = self._vtk_renderer()
        if iren is None or renderer is None:
            return None

        try:
            x, y = iren.GetEventPosition()
        except Exception:
            return None

        picker = vtkPropPicker()
        try:
            picker.Pick(x, y, 0, renderer)
        except Exception:
            return None

        vtk_actor = picker.GetActor()
        if vtk_actor is None:
            return None

        pid = self.actor_to_pid.get(vtk_actor, None)
        if pid is not None:
            return pid

        for actor_obj, actor_pid in self.actor_to_pid.items():
            try:
                if hasattr(actor_obj, "actor") and actor_obj.actor == vtk_actor:
                    return actor_pid
            except Exception:
                pass
            try:
                if hasattr(actor_obj, "_actor") and actor_obj._actor == vtk_actor:
                    return actor_pid
            except Exception:
                pass

        return None

    def _abort_vtk_event(self, obj):
        for name in ("AbortFlagOn", "SetAbortFlag"):
            fn = getattr(obj, name, None)
            if callable(fn):
                try:
                    if name == "SetAbortFlag":
                        fn(1)
                    else:
                        fn()
                    return
                except Exception:
                    pass

    def _release_camera_like_old_working_version(self):
        """
        Reproduce the behavior of the old script that correctly released
        the camera drag state when opening/closing the editing window.
        """
        iren = self._vtk_interactor()
        if iren is None:
            return None, None

        style = None
        try:
            style = iren.GetInteractorStyle()
        except Exception:
            style = None

        # Igual que en el script viejo: forzar "mouse up" antes del popup
        try:
            if style is not None and hasattr(style, "OnLeftButtonUp"):
                style.OnLeftButtonUp()
        except Exception:
            pass

        try:
            self.vtk_widget.releaseMouse()
        except Exception:
            pass

        try:
            iren.Disable()
        except Exception:
            pass

        return iren, style

    def _restore_camera_after_dialog_like_old_version(self, iren, style):
        """
        Restore interaction using the same idea as the old working version.
        """
        try:
            if iren is not None:
                iren.Enable()
        except Exception:
            pass

        # Igual que en el script viejo: asegurar que no queda el botón "pulsado"
        try:
            if style is not None and hasattr(style, "OnLeftButtonUp"):
                style.OnLeftButtonUp()
        except Exception:
            pass

        try:
            self.vtk_widget.releaseMouse()
        except Exception:
            pass

        try:
            self.vtk_widget.setFocus(Qt.OtherFocusReason)
        except Exception:
            pass

        try:
            self.activateWindow()
            self.raise_()
        except Exception:
            pass

    def _stop_camera_interaction(self):
        iren = self._vtk_interactor()
        if iren is None:
            return

        try:
            style = iren.GetInteractorStyle()
        except Exception:
            style = None

        if style is not None:
            for name in (
                "EndRotate",
                "EndPan",
                "EndSpin",
                "EndDolly",
                "EndZoom",
                "StopState",
            ):
                fn = getattr(style, name, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass

        try:
            self.vtk_widget.releaseMouse()
        except Exception:
            pass

    def _after_label_dialog_closed(self):
        self._dialog_open = False
        self._pending_pick_pid = None

    def _undo_last_change(self):
        if not self.undo_stack:
            print("[INFO] Undo: no actions to undo.")
            return

        action = self.undo_stack.pop()
        print(f"[UNDO] Reverting action: {action['type']}")

        if action["type"] == "set":
            self._set_label(action["pid"], action["label_before"])
        elif action["type"] == "swap":
            a = action["pid_a"]
            b = action["pid_b"]
            lab_a = action["label_a_before"]
            lab_b = action["label_b_before"]

            self.detections[a]["label"] = lab_a
            self.labels[a] = lab_a
            self.detections[b]["label"] = lab_b
            self.labels[b] = lab_b

            if lab_a:
                self.label_to_pid[lab_a] = a
            if lab_b:
                self.label_to_pid[lab_b] = b

            self._replace_label_actor(a, lab_a)
            self._replace_label_actor(b, lab_b)
            self._rebuild_point_actors()

        self.plt.render()

    def _on_key_press(self, evt):
        key = (getattr(evt, "keypress", "") or "").strip().lower()

        if key == "r":
            self._reset_camera_view()
            return

        if key == "z":
            self._undo_last_change()
            return

        if key in ("return", "enter", "escape", "esc"):
            self.close()
            return

    def _on_left_button_press_vtk(self, obj, _evt_name):
        if self._dialog_open:
            self._abort_vtk_event(obj)
            return

        iren = self._vtk_interactor()
        pid = self._pick_point_pid_at_event(iren)

        if pid is None:
            return

        self._dialog_open = True
        self._pending_pick_pid = pid

        # Cortamos el evento para que no inicie rotación
        self._stop_camera_interaction()
        self._abort_vtk_event(obj)

        # Abrimos el diálogo justo después, aplicando la lógica del script viejo
        QTimer.singleShot(0, lambda pid=pid: self._open_label_dialog_for_pid(pid))

    def _open_label_dialog_for_pid(self, pid):
        if pid is None or pid < 0 or pid >= len(self.detections):
            self._after_label_dialog_closed()
            return

        iren, style = self._release_camera_like_old_working_version()

        try:
            det = self.detections[pid]
            current_label = (det.get("label", "") or "").strip()
            print(f"\n[INFO] Clicked point idx={pid}, current label='{current_label}'")

            candidates = compute_candidates_for_detection(det, self.template_rows, top_k=self.top_k)
            candidate_labels_ordered = []
            added = set()

            if current_label:
                candidate_labels_ordered.append(current_label)
                added.add(current_label)

            for lab, _score in candidates:
                if lab and lab not in added:
                    candidate_labels_ordered.append(lab)
                    added.add(lab)

            if not candidate_labels_ordered and current_label:
                candidate_labels_ordered = [current_label]

            dialog = LabelChoiceDialog(self, pid, current_label, candidate_labels_ordered, self.all_labels_sorted)
            result = dialog.exec()

            if result != QDialog.Accepted:
                return

            new_label = dialog.selected_label().strip()
            old_label = current_label

            if not new_label or new_label == old_label:
                return

            other_pid = self.label_to_pid.get(new_label, None)
            if other_pid is not None and other_pid != pid:
                print(f"[SWAP] Point {pid} ('{old_label}') <-> Point {other_pid} ('{new_label}')")
                self.undo_stack.append(
                    {
                        "type": "swap",
                        "pid_a": pid,
                        "pid_b": other_pid,
                        "label_a_before": old_label,
                        "label_b_before": new_label,
                    }
                )
                self._apply_swap(pid, other_pid, old_label, new_label)
            else:
                print(f"[CHANGE] Point {pid}: '{old_label}' -> '{new_label}'")
                self.undo_stack.append(
                    {
                        "type": "set",
                        "pid": pid,
                        "label_before": old_label,
                        "label_after": new_label,
                    }
                )
                self._set_label(pid, new_label)

            self.plt.render()

        finally:
            self._restore_camera_after_dialog_like_old_version(iren, style)
            self._after_label_dialog_closed()

    def save_csv(self):
        if self._saved:
            return
        self.out_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(self.out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.det_fieldnames)
            writer.writeheader()
            for d in self.detections:
                writer.writerow(d)
        self._saved = True
        print(f"[OK] Corrected CSV saved to: {self.out_csv}")

    def _cancel_editor(self):
        self._cancelled = True
        self.close()

    def closeEvent(self, event):
        if self._cancelled:
            try:
                self.plt.close()
            except Exception:
                pass
            super().closeEvent(event)
            return

        try:
            self.save_csv()
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))
            event.ignore()
            return

        try:
            self.plt.close()
        except Exception:
            pass
        super().closeEvent(event)


def run_interactive_editor(
    detections,
    template_rows,
    mesh_path,
    top_k,
    out_csv,
    det_fieldnames,
    align_bbox=True,
    label_scale_factor=1.0,
    help_scale=0.6,
    label_colors=None,
):
    app = QApplication.instance() or QApplication(sys.argv)
    win = InteractiveLabelEditorWindow(
        detections=detections,
        template_rows=template_rows,
        mesh_path=mesh_path,
        top_k=top_k,
        out_csv=out_csv,
        det_fieldnames=det_fieldnames,
        align_bbox=align_bbox,
        label_scale_factor=label_scale_factor,
        help_scale=help_scale,
        label_colors=label_colors,
    )
    win.showMaximized()
    app.exec()
    return 130 if getattr(win, "_cancelled", False) else 0


def main():
    args = parse_args()

    detections, det_fieldnames = load_detections(args.detections)
    template_rows = load_template(args.template)

    mesh_path = args.mesh if args.mesh else None
    if mesh_path is not None and not Path(mesh_path).exists():
        print(f"[WARNING] Mesh not found at {mesh_path}, it will be ignored.")
        mesh_path = None

    colors_csv = args.colors_csv
    if not colors_csv:
        candidate = Path(__file__).with_name("pointsColor.csv")
        if candidate.exists():
            colors_csv = str(candidate)

    label_colors = {}
    if colors_csv:
        try:
            label_colors = load_label_colors(colors_csv)
            print(f"[INFO] Loaded {len(label_colors)} label colors from: {colors_csv}")
        except Exception as e:
            print(f"[WARNING] Could not load colors CSV '{colors_csv}': {e}")

    return_code = run_interactive_editor(
        detections=detections,
        template_rows=template_rows,
        mesh_path=mesh_path,
        top_k=args.top_k,
        out_csv=args.out,
        det_fieldnames=det_fieldnames,
        align_bbox=not args.no_align_bbox,
        label_scale_factor=args.label_scale_factor,
        help_scale=args.help_scale,
        label_colors=label_colors,
    )
    if return_code:
        sys.exit(return_code)


if __name__ == "__main__":
    main()
