from __future__ import annotations

from pathlib import Path
import shutil
import pandas as pd

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QProgressBar,
    QPushButton, QHBoxLayout, QMessageBox, QDialog, QGridLayout,
    QButtonGroup, QRadioButton, QScrollArea
)

from PySide6.QtGui import QPixmap

from ...core.paths import asset_path
from ...core.settings import load_settings
from ...core.paths import resolve_blender_exe
from ...core.output_cleanup import processing_dir, cleanup_legacy_output_clutter
from ...core.openpose_render import render_hand_topview_for_openpose
from ...core.openpose_hand import run_openpose_hand_2d
from ...core.openpose_rig import build_armature_from_openpose
from ...core.label_points import label_points_from_template
from ...core.label_correction import (
    run_interactive_label_editor,
    apply_labels_in_blender,
    persist_corrected_csv,
)


def _safe_emit(signal, *args):
    try:
        signal.emit(*args)
        return True
    except RuntimeError:
        # The Qt signal source may already have been destroyed if the page is
        # being rebuilt while a background worker is unwinding.
        return False


class _Signals(QObject):
    status = Signal(str, str, object)   # phase, key, value
    phase = Signal(str)                 # active phase
    done = Signal(dict)
    fail = Signal(str)


class _WorkflowWorker(QRunnable):
    def __init__(
        self,
        phase: str,
        settings: dict,
        out_dir: Path,
        obj_path: Path | None = None,
        resolution: int = 1024,
        rig_payload: dict | None = None,
        label_payload: dict | None = None,
        mesh_path: Path | None = None,
    ):
        super().__init__()
        self.phase_to_start = phase
        self.settings = settings or {}
        self.out_dir = Path(out_dir)
        self.obj_path = Path(obj_path) if obj_path else None
        self.resolution = int(resolution)
        self.rig_payload = dict(rig_payload or {})
        self.label_payload = dict(label_payload or {})
        self.mesh_path = Path(mesh_path) if mesh_path else None
        self.signals = _Signals()

    def run(self):
        try:
            payload: dict = {}

            if self.phase_to_start == "rigging":
                payload.update(self._run_rigging())
                self.rig_payload = dict(payload)
                payload.update(self._run_labeling(self.rig_payload))
                self.label_payload = dict(payload)
                payload.update(self._run_editor(self.label_payload))

            elif self.phase_to_start == "labeling":
                if not self.rig_payload.get("out_blend"):
                    _safe_emit(self.signals.fail, "Cannot retry Automatic Labeling because the rigged .blend is missing.")
                    return
                payload.update(self.rig_payload)
                payload.update(self._run_labeling(self.rig_payload))
                self.label_payload = dict(payload)
                payload.update(self._run_editor(self.label_payload))

            elif self.phase_to_start == "editor":
                if not self.label_payload.get("labeled_csv") or not self.label_payload.get("labeled_blend"):
                    _safe_emit(self.signals.fail, "Cannot retry the Interactive Label Editor because labeled files are missing.")
                    return
                payload.update(self.label_payload)
                payload.update(self._run_editor(self.label_payload))

            else:
                _safe_emit(self.signals.fail, f"Unknown workflow phase: {self.phase_to_start}")
                return

            _safe_emit(self.signals.done, payload)

        except Exception as e:
            _safe_emit(self.signals.fail, str(e))

    def _run_rigging(self) -> dict:
        if self.obj_path is None:
            raise RuntimeError("Missing OBJ path for Skeleton-Based Rigging.")

        _safe_emit(self.signals.phase, "rigging")

        openpose_dir = processing_dir(self.out_dir, "openpose")

        _safe_emit(self.signals.status, "rigging", "Automatic 3D Joint Estimation", "running…")
        res = render_hand_topview_for_openpose(
            obj_path=self.obj_path,
            out_dir=openpose_dir,
            resolution=self.resolution,
            log=lambda s: None,
        )
        if not res.ok or not res.png_path:
            raise RuntimeError(res.message)

        op = run_openpose_hand_2d(
            render_png=res.png_path,
            out_dir=openpose_dir,
            log=lambda s: None,
        )
        if not op.ok:
            raise RuntimeError(op.message)
        if not op.keypoints_csv:
            raise RuntimeError("OpenPose did not generate keypoints_csv.")
        _safe_emit(self.signals.status, "rigging", "Automatic 3D Joint Estimation", "OK")
        if op.overlay_png:
            _safe_emit(self.signals.status, "rigging", "__openpose_overlay__", str(op.overlay_png))

        _safe_emit(self.signals.status, "rigging", "Joint Review", "OK")

        _safe_emit(self.signals.status, "rigging", "Building Armature", "running…")
        rig_res = build_armature_from_openpose(
            settings=self.settings,
            obj_path=self.obj_path,
            csv_2d_path=Path(op.keypoints_csv),
            out_dir=self.out_dir,
            resolution=self.resolution,
            log=lambda s: None,
        )
        if not rig_res.ok:
            raise RuntimeError("Could not build the armature:\n" + rig_res.message)
        _safe_emit(self.signals.status, "rigging", "Building Armature", "OK")

        return {
            "render_png": str(res.png_path),
            "overlay_png": str(op.overlay_png) if op.overlay_png else None,
            "keypoints_csv": str(op.keypoints_csv) if op.keypoints_csv else None,
            "out_blend": str(rig_res.out_blend) if rig_res.out_blend else None,
            "joints_3d_csv": str(rig_res.joints_csv) if rig_res.joints_csv else None,
        }

    def _run_labeling(self, base_payload: dict) -> dict:
        blend_path = base_payload.get("out_blend")
        if not blend_path:
            raise RuntimeError("Missing rigged .blend for Automatic Labeling.")

        _safe_emit(self.signals.phase, "labeling")
        _safe_emit(self.signals.status, "labeling", "Running procedure", "running…")
        res = label_points_from_template(
            settings=self.settings,
            blend_path=Path(blend_path),
            out_dir=self.out_dir,
            marker_prefix="Sphere_",
            max_dist=None,
            save_blend=True,
            log=lambda s: None,
        )
        if not res.ok:
            raise RuntimeError(res.message + ("\n" + res.stderr if res.stderr else ""))

        _safe_emit(self.signals.status, "labeling", "Running procedure", "OK")
        unlabeled = self._count_unlabeled(res.out_csv)
        _safe_emit(self.signals.status, "labeling", "Unlabeled spheres", unlabeled)

        return {
            "labeled_csv": str(res.out_csv) if res.out_csv else None,
            "labeled_blend": str(res.out_blend) if res.out_blend else None,
            "unlabeled_spheres": unlabeled,
        }

    def _run_editor(self, base_payload: dict) -> dict:
        labeled_csv = base_payload.get("labeled_csv")
        labeled_blend = base_payload.get("labeled_blend")
        if not labeled_csv or not labeled_blend:
            raise RuntimeError("Missing labeled CSV or labeled .blend for Interactive Label Editor.")

        mesh_path = self.mesh_path
        if mesh_path is None:
            if self.obj_path is not None:
                mesh_path = self.obj_path
            else:
                raise RuntimeError("Missing mesh path for Interactive Label Editor.")

        template_csv = asset_path("data", "markers_template.csv")
        if not template_csv.exists():
            raise RuntimeError(f"markers_template.csv does not exist at: {template_csv}")

        _safe_emit(self.signals.phase, "editor")
        _safe_emit(self.signals.status, "editor", "Launching interactive editor", "running…")

        editor_dir = processing_dir(self.out_dir, "label_editor")
        corrected_csv = editor_dir / "detections_labeled_corrected.csv"
        ed = run_interactive_label_editor(
            detections_csv=Path(labeled_csv),
            template_csv=template_csv,
            out_csv=corrected_csv,
            mesh_path=mesh_path,
            label_scale_factor=0.75,
            help_scale=0.8,
            no_align_bbox=True,
            log=lambda s: None,
        )
        if not ed.ok or not ed.corrected_csv:
            raise RuntimeError(ed.message)

        blender_exe = self._resolve_blender_exe()
        if not blender_exe:
            raise RuntimeError(
                "Blender executable not found. Expected bundled path: <app>/blender/blender.exe"
            )

        labeled_blend_path = Path(labeled_blend)
        corrected_blend = editor_dir / f"{labeled_blend_path.stem}_manual.blend"
        ap = apply_labels_in_blender(
            blender_exe=blender_exe,
            labeled_blend=labeled_blend_path,
            corrected_csv=ed.corrected_csv,
            out_blend=corrected_blend,
            log=lambda s: None,
        )
        if not ap.ok:
            raise RuntimeError(ap.message)

        persisted_csv = persist_corrected_csv(
            out_dir=self.out_dir,
            base_labeled_csv=Path(labeled_csv),
            corrected_csv=ed.corrected_csv,
            log=lambda s: None,
            create_backup=False,
        )

        # Keep one canonical labeled .blend in the project root instead of adding
        # a second *_manual.blend next to the workflow files.
        if ap.corrected_blend and Path(ap.corrected_blend).exists():
            shutil.copy2(ap.corrected_blend, labeled_blend_path)

        # The editor CSV and temporary corrected blend are only transport files.
        # Once their contents are persisted, remove them from the output tree.
        for tmp in (ed.corrected_csv, ap.corrected_blend):
            try:
                if tmp and Path(tmp).exists():
                    Path(tmp).unlink()
            except Exception:
                pass

        _safe_emit(self.signals.status, "editor", "Launching interactive editor", "OK")
        _safe_emit(self.signals.status, "editor", "Process complete", "OK")

        return {
            "corrected_csv": str(persisted_csv),
            "corrected_blend": str(labeled_blend_path),
            "labeled_csv": str(persisted_csv),
            "labeled_blend": str(labeled_blend_path),
        }

    def _resolve_blender_exe(self) -> str | None:
        persisted = load_settings() or {}
        merged_settings = dict(persisted)
        if isinstance(self.settings, dict):
            merged_settings.update(self.settings)

        blender_exe = resolve_blender_exe(merged_settings)
        return str(blender_exe) if blender_exe else None

    @staticmethod
    def _count_unlabeled(csv_path: Path | None) -> int:
        if not csv_path or not Path(csv_path).exists():
            return 0
        try:
            df = pd.read_csv(csv_path)
            if "label" not in df.columns:
                return 0
            labels = df["label"].fillna("").astype(str).str.strip()
            return int((labels == "").sum())
        except Exception:
            return 0


class _StepCard(QFrame):
    _STYLE_DEFAULT = """
        QFrame#RigLabelStepCard {
            border: 1px solid #444;
            border-radius: 10px;
            background: rgba(255,255,255,0.035);
        }
    """
    _STYLE_ACTIVE = """
        QFrame#RigLabelStepCard {
            border: 2px solid #1976d2;
            border-radius: 10px;
            background: rgba(25,118,210,0.10);
        }
    """
    _STYLE_DONE = """
        QFrame#RigLabelStepCard {
            border: 2px solid #2e7d32;
            border-radius: 10px;
            background: rgba(46,125,50,0.10);
        }
    """

    def __init__(self, number: int, title: str, details: list[str]):
        super().__init__()
        self.setObjectName("RigLabelStepCard")
        self.setFrameShape(QFrame.StyledPanel)
        self._detail_labels: dict[str, QLabel] = {}
        self._state = "default"
        self.setStyleSheet(self._STYLE_DEFAULT)

        layout = QVBoxLayout(self)
        self._layout = layout
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header = QLabel(f"{number}. {title}")
        header.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(header)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        for key in details:
            lbl = QLabel(f"{key}: —")
            lbl.setWordWrap(True)
            lbl.setStyleSheet("font-size: 13px;")
            self._detail_labels[key] = lbl
            layout.addWidget(lbl)

        layout.addStretch(1)

    def set_state(self, state: str):
        self._state = state
        if state == "active":
            self.setStyleSheet(self._STYLE_ACTIVE)
        elif state == "done":
            self.setStyleSheet(self._STYLE_DONE)
        else:
            self.setStyleSheet(self._STYLE_DEFAULT)

    def set_value(self, key: str, value):
        if key in self._detail_labels:
            self._detail_labels[key].setText(f"{key}: {value}")

    def add_action_button(self, text: str, callback):
        btn = QPushButton(text)
        btn.setFixedHeight(32)
        btn.setVisible(False)
        btn.setEnabled(False)
        btn.clicked.connect(callback)
        # Insert before the final stretch so it stays inside the information area.
        insert_at = max(0, self._layout.count() - 1)
        self._layout.insertWidget(insert_at, btn)
        return btn

    def clear_values(self):
        for key, lbl in self._detail_labels.items():
            lbl.setText(f"{key}: —")
        self.set_state("default")


class _ImagePreviewDialog(QDialog):
    def __init__(self, image_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Joint estimation result preview")
        self.setModal(True)
        self.resize(1180, 820)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Joint estimation result")
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        layout.addWidget(title)

        subtitle = QLabel("This preview shows the render or rendered views after OpenPose processing.")
        subtitle.setWordWrap(True)
        subtitle.setProperty("role", "subtitle")
        layout.addWidget(subtitle)

        pix = QPixmap(str(image_path))
        img_label = QLabel()
        img_label.setAlignment(Qt.AlignCenter)
        if pix.isNull():
            img_label.setText(f"Could not load image:\n{image_path}")
        else:
            scaled = pix.scaled(1120, 680, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            img_label.setPixmap(scaled)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(img_label)
        layout.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        layout.addLayout(bottom)


class _RetryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Retry rigging and labeling workflow")
        self.setModal(True)
        self.resize(500, 230)
        self.selected = "rigging"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Repeat from:")
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        layout.addWidget(title)

        self.group = QButtonGroup(self)
        options = [
            ("rigging", "Skeleton-Based Rigging"),
            ("labeling", "Automatic Labeling"),
            ("editor", "Interactive Label Editor"),
        ]
        for i, (key, text) in enumerate(options):
            rb = QRadioButton(text)
            rb.setChecked(i == 0)
            rb.toggled.connect(lambda checked, k=key: setattr(self, "selected", k) if checked else None)
            self.group.addButton(rb)
            layout.addWidget(rb)

        layout.addStretch(1)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Retry")
        ok.clicked.connect(self.accept)
        bottom.addWidget(cancel)
        bottom.addWidget(ok)
        layout.addLayout(bottom)


class RiggingPage(QWidget):
    """Collapsed workflow: Skeleton-Based Rigging + Automatic Labeling + Interactive Label Editor."""

    completed = Signal(dict)
    failed = Signal(str)
    back_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.threadpool = QThreadPool.globalInstance()
        self._payload_ok: dict | None = None
        self._last_args = None
        self._settings: dict = {}
        self._obj_path: Path | None = None
        self._out_dir: Path | None = None
        self._mesh_path: Path | None = None
        self._resolution = 1024
        self._openpose_overlay_path: Path | None = None
        self._busy: bool = False
        self._active_workers: list[QRunnable] = []
        self._active_signals: list[QObject] = []
        self._build_ui()

    def is_busy(self) -> bool:
        return bool(self._busy)

    def _start_worker(self, worker: QRunnable):
        try:
            worker.setAutoDelete(False)
        except Exception:
            pass
        self._active_workers.append(worker)
        signals = getattr(worker, "signals", None)
        if signals is not None:
            self._active_signals.append(signals)
        self.threadpool.start(worker)

    def _release_worker(self, worker: QRunnable | None = None):
        if worker is None:
            self._active_workers.clear()
            self._active_signals.clear()
            return

        try:
            self._active_workers.remove(worker)
        except ValueError:
            pass

        signals = getattr(worker, "signals", None)
        if signals is not None:
            try:
                self._active_signals.remove(signals)
            except ValueError:
                pass

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setSpacing(14)

        title = QLabel("Rigging and Labeling")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        subtitle = QLabel(
            "The application builds the hand rig, assigns labels automatically and then opens the interactive label editor for final correction."
        )
        subtitle.setProperty("role", "subtitle")
        subtitle.setWordWrap(True)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)

        cards_row = QGridLayout()
        cards_row.setHorizontalSpacing(16)
        cards_row.setVerticalSpacing(16)

        self.card_rig = _StepCard(1, "Skeleton-Based Rigging", [
            "Automatic 3D Joint Estimation",
            "Joint Review",
            "Building Armature",
        ])
        self.btn_view_openpose = self.card_rig.add_action_button(
            "View joint estimation result",
            self._show_openpose_preview,
        )

        self.card_label = _StepCard(2, "Automatic Labeling", [
            "Running procedure",
            "Unlabeled spheres",
        ])
        self.card_editor = _StepCard(3, "Interactive Label Editor", [
            "Launching interactive editor",
            "Process complete",
        ])

        cards_row.addWidget(self.card_rig, 0, 0)
        cards_row.addWidget(self.card_label, 0, 1)
        cards_row.addWidget(self.card_editor, 0, 2)
        cards_row.setColumnStretch(0, 1)
        cards_row.setColumnStretch(1, 1)
        cards_row.setColumnStretch(2, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)

        bottom = QHBoxLayout()
        self.btn_back = QPushButton("Back")
        self.btn_back.setFixedHeight(40)
        self.btn_back.setFixedWidth(120)
        self.btn_back.clicked.connect(self.back_clicked.emit)
        bottom.addWidget(self.btn_back)
        bottom.addStretch(1)
        self.btn_retry = QPushButton("Retry")
        self.btn_retry.setFixedHeight(40)
        self.btn_retry.setFixedWidth(140)
        self.btn_retry.setEnabled(False)
        self.btn_retry.clicked.connect(self._open_retry_dialog)

        self.btn_continue = QPushButton("Continue")
        self.btn_continue.setFixedHeight(40)
        self.btn_continue.setFixedWidth(160)
        self.btn_continue.setEnabled(False)
        self.btn_continue.clicked.connect(self._continue)

        bottom.addWidget(self.btn_retry)
        bottom.addWidget(self.btn_continue)

        outer.addWidget(title)
        outer.addWidget(subtitle)
        outer.addWidget(line)
        outer.addWidget(self.progress)
        outer.addLayout(cards_row)
        outer.addWidget(self.status)
        outer.addStretch(1)
        outer.addLayout(bottom)

    def start(self, obj_path: str, out_dir: str, resolution: int = 1024, settings: dict | None = None):
        self._payload_ok = None
        self._settings = settings or {}
        self._obj_path = Path(obj_path)
        self._mesh_path = self._obj_path
        self._out_dir = Path(out_dir)
        cleanup_legacy_output_clutter(self._out_dir)
        self._resolution = int(resolution)
        self._last_args = (obj_path, out_dir, resolution, settings)
        self._reset_ui(clear_all=True)
        self._run_from("rigging")

    def start_from_manual_correction(self, settings: dict, out_dir: str, labeled_csv: str, labeled_blend: str, mesh_path: str):
        """Used when opening an existing project directly at the label-correction stage."""
        self._payload_ok = {
            "labeled_csv": labeled_csv,
            "labeled_blend": labeled_blend,
        }
        self._settings = settings or {}
        self._out_dir = Path(out_dir)
        cleanup_legacy_output_clutter(self._out_dir)
        self._mesh_path = Path(mesh_path)
        self._obj_path = self._mesh_path
        self._reset_ui(clear_all=True)
        self.card_rig.set_value("Automatic 3D Joint Estimation", "loaded from project")
        self.card_rig.set_value("Joint Review", "loaded from project")
        self.card_rig.set_value("Building Armature", "loaded from project")
        self.card_rig.set_state("done")
        self.card_label.set_value("Running procedure", "loaded from project")
        self.card_label.set_value("Unlabeled spheres", self._count_unlabeled_local(Path(labeled_csv)))
        self.card_label.set_state("done")
        self._set_openpose_preview_path(self._find_existing_openpose_preview())
        self._run_from("editor")

    def _reset_ui(self, clear_all: bool):
        if clear_all:
            self.card_rig.clear_values()
            self.card_label.clear_values()
            self.card_editor.clear_values()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status.setStyleSheet("")
        self.status.setText("")
        if clear_all:
            self._set_openpose_preview_path(None)
        self.btn_retry.setEnabled(False)
        self.btn_continue.setEnabled(False)

    def _run_from(self, phase: str):
        if self._out_dir is None:
            QMessageBox.warning(self, "Missing output folder", "Output folder is not available.")
            return

        if phase == "rigging":
            self.card_rig.clear_values()
            self.card_label.clear_values()
            self.card_editor.clear_values()
            self._set_openpose_preview_path(None)
        elif phase == "labeling":
            self.card_label.clear_values()
            self.card_editor.clear_values()
        elif phase == "editor":
            self.card_editor.clear_values()

        self.progress.setRange(0, 0)
        self.status.setStyleSheet("")
        self.status.setText("Running workflow…")
        self.btn_retry.setEnabled(False)
        self.btn_continue.setEnabled(False)
        self._busy = True

        worker = _WorkflowWorker(
            phase=phase,
            settings=self._settings,
            out_dir=self._out_dir,
            obj_path=self._obj_path,
            resolution=self._resolution,
            rig_payload=self._payload_ok if phase in {"labeling", "editor"} else None,
            label_payload=self._payload_ok if phase == "editor" else None,
            mesh_path=self._mesh_path,
        )
        worker.signals.phase.connect(self._set_active_phase)
        worker.signals.status.connect(self._set_card_value)
        worker.signals.done.connect(lambda payload, w=worker: self._done(payload, w))
        worker.signals.fail.connect(lambda msg, w=worker: self._fail(msg, w))
        self._start_worker(worker)

    def _set_active_phase(self, phase: str):
        if phase == "rigging":
            self.card_rig.set_state("active")
            self.card_label.set_state("default")
            self.card_editor.set_state("default")
        elif phase == "labeling":
            self.card_rig.set_state("done")
            self.card_label.set_state("active")
            self.card_editor.set_state("default")
        elif phase == "editor":
            self.card_rig.set_state("done")
            self.card_label.set_state("done")
            self.card_editor.set_state("active")

    def _set_card_value(self, phase: str, key: str, value):
        if phase == "rigging" and key == "__openpose_overlay__":
            self._set_openpose_preview_path(Path(str(value)) if value else None)
            return

        card = {
            "rigging": self.card_rig,
            "labeling": self.card_label,
            "editor": self.card_editor,
        }.get(phase)
        if card is not None:
            card.set_value(key, value)

    def _set_openpose_preview_path(self, path: Path | None):
        self._openpose_overlay_path = path if path and path.exists() else None
        enabled = self._openpose_overlay_path is not None
        if hasattr(self, "btn_view_openpose"):
            self.btn_view_openpose.setVisible(enabled)
            self.btn_view_openpose.setEnabled(enabled)

    def _find_existing_openpose_preview(self) -> Path | None:
        """Recover OpenPose preview images when reopening an existing project."""
        if self._out_dir is None:
            return None

        out_dir = Path(self._out_dir)
        values = []
        if isinstance(self._settings, dict):
            values.extend([
                self._settings.get("overlay_png"),
                self._settings.get("openpose_overlay_png"),
                self._settings.get("openpose_preview_png"),
            ])

        candidates: list[Path] = []
        for value in values:
            if value:
                candidates.append(Path(str(value)))

        candidates.extend([
            processing_dir(out_dir, "openpose", create=False) / "hand_openpose_keypoints_overlay.png",
            out_dir / "hand_openpose_keypoints_overlay.png",
        ])

        for p in candidates:
            if not p.is_absolute():
                p = out_dir / p
            try:
                p = p.resolve()
            except Exception:
                continue
            if p.exists() and p.is_file():
                return p

        processing_root = processing_dir(out_dir, create=False)
        if not processing_root.exists() or not processing_root.is_dir():
            return None

        preferred_patterns = [
            "**/hand_openpose_keypoints_overlay.png",
            "**/*_openpose.png",
            "**/*openpose*overlay*.png",
        ]
        seen: set[Path] = set()
        for pattern in preferred_patterns:
            for p in sorted(processing_root.glob(pattern)):
                try:
                    p = p.resolve()
                except Exception:
                    continue
                if p in seen:
                    continue
                seen.add(p)
                if p.exists() and p.is_file():
                    return p

        return None

    def _show_openpose_preview(self):
        if not self._openpose_overlay_path or not self._openpose_overlay_path.exists():
            QMessageBox.information(self, "Joint estimation result", "The joint estimation preview image is not available yet.")
            return
        dlg = _ImagePreviewDialog(self._openpose_overlay_path, self)
        dlg.exec()

    def _done(self, payload: dict, worker: QRunnable | None = None):
        self._release_worker(worker)
        self._busy = False
        merged = dict(self._payload_ok or {})
        merged.update(payload)
        self._payload_ok = merged
        if merged.get("overlay_png"):
            self._set_openpose_preview_path(Path(str(merged["overlay_png"])))
        self.card_rig.set_state("done")
        self.card_label.set_state("done")
        self.card_editor.set_state("done")
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.status.setStyleSheet("color:#1b5e20; font-weight:600;")
        self.status.setText("Rigging, automatic labeling and interactive correction completed.")
        if self._out_dir is not None:
            cleanup_legacy_output_clutter(self._out_dir)
        self.btn_retry.setEnabled(True)
        self.btn_continue.setEnabled(True)

    def _fail(self, msg: str, worker: QRunnable | None = None):
        self._release_worker(worker)
        self._busy = False
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status.setStyleSheet("color:#b00020; font-weight:600;")
        self.status.setText("Workflow error.\n" + msg)
        self.btn_retry.setEnabled(True)
        self.failed.emit(msg)

    def _open_retry_dialog(self):
        if self._out_dir is None:
            return
        dlg = _RetryDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.selected == "labeling" and not (self._payload_ok or {}).get("out_blend"):
            QMessageBox.information(self, "Retry", "Automatic Labeling cannot be repeated because the rigged .blend is not available.")
            return
        if dlg.selected == "editor" and not (self._payload_ok or {}).get("labeled_csv"):
            QMessageBox.information(self, "Retry", "Interactive Label Editor cannot be repeated because the labeled CSV is not available.")
            return
        self._run_from(dlg.selected)

    def _continue(self):
        if self._payload_ok is None:
            return
        self.completed.emit(self._payload_ok)

    @staticmethod
    def _count_unlabeled_local(csv_path: Path) -> int:
        try:
            df = pd.read_csv(csv_path)
            if "label" not in df.columns:
                return 0
            labels = df["label"].fillna("").astype(str).str.strip()
            return int((labels == "").sum())
        except Exception:
            return 0
