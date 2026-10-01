from __future__ import annotations

from pathlib import Path
import json
import re
import pandas as pd
import numpy as np
import cv2

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, QTimer, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QProgressBar,
    QPushButton, QHBoxLayout, QMessageBox, QDialog, QScrollArea,
    QGridLayout, QButtonGroup, QRadioButton
)

from ...core.detect_map import run_detect_and_map, reconcile_points_with_3d_priority
from ...core.subprocess_utils import run_hidden
from ...core.worker_commands import internal_worker_command, internal_worker_cwd
from .view3d_dialog import Edit3DDialog
from .edit_points_dialog import EditPointsDialog
from .landmark_validation_dialog import LandmarkValidationDialog
from .threshold_page import BlenderPreviewDialog
from ...core.hand_with_points import run_make_hand_with_points
from ...core.output_cleanup import (
    detections_mapped_3d_csv,
    hand_with_points_obj,
    project_context_path,
    threshold_preview_dir,
)


class _Signals(QObject):
    log = Signal(str)
    done = Signal(dict)
    fail = Signal(str)


class _Worker(QRunnable):
    def __init__(self, texture_path: Path, obj_path: Path, out_dir: Path, target_json: Path | None, v_flip: bool, snap_to_vertices: bool):
        super().__init__()
        self.texture_path = texture_path
        self.obj_path = obj_path
        self.out_dir = out_dir
        self.target_json = target_json
        self.v_flip = v_flip
        self.snap_to_vertices = snap_to_vertices
        self.signals = _Signals()

    def run(self):
        try:
            payload = self._run_isolated()
            for line in payload.get("logs", []):
                self.signals.log.emit(str(line))
            if not payload.get("ok"):
                self.signals.fail.emit(str(payload.get("message") or "Detection worker failed."))
                return
            self.signals.done.emit({
                "csv_2d": payload.get("csv_2d"),
                "csv_3d": payload.get("csv_3d"),
                "n_2d": int(payload.get("n_2d") or 0),
                "n_3d_mapped": int(payload.get("n_3d_mapped") or 0),
            })
        except Exception as e:
            self.signals.fail.emit(str(e))

    def _run_isolated(self) -> dict:
        cmd = [
            *internal_worker_command("detect-map"),
            "--texture", str(self.texture_path),
            "--obj", str(self.obj_path),
            "--out_dir", str(self.out_dir),
            "--v_flip", "1" if self.v_flip else "0",
            "--snap_to_vertices", "1" if self.snap_to_vertices else "0",
        ]
        if self.target_json:
            cmd += ["--target_json", str(self.target_json)]

        completed = run_hidden(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(internal_worker_cwd()),
        )

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        result_line = None
        for line in stdout.splitlines():
            if line.startswith("JSON_RESULT "):
                result_line = line[len("JSON_RESULT "):]

        if result_line:
            payload = json.loads(result_line)
            if completed.returncode != 0 and payload.get("ok"):
                payload["ok"] = False
            if completed.returncode != 0 and not payload.get("message"):
                payload["message"] = f"Detection worker exited with code {completed.returncode}"
            if stderr.strip():
                payload.setdefault("logs", []).append(stderr.strip())
            return payload

        detail = stderr.strip() or stdout.strip()
        raise RuntimeError(
            f"Detection worker exited with code {completed.returncode} without returning a result."
            + (f"\n{detail}" if detail else "")
        )


class _MakePointsWorker(QRunnable):
    def __init__(self, base_obj: Path, points_csv: Path, out_obj: Path, sphere_radius: float):
        super().__init__()
        self.base_obj = base_obj
        self.points_csv = points_csv
        self.out_obj = out_obj
        self.sphere_radius = sphere_radius
        self.signals = _Signals()

    def run(self):
        try:
            res = run_make_hand_with_points(
                base_obj=self.base_obj,
                points_csv=self.points_csv,
                out_obj=self.out_obj,
                sphere_radius=self.sphere_radius,
                log=lambda s: self.signals.log.emit(str(s)),
            )
            if not res.ok:
                self.signals.fail.emit(res.message)
                return
            self.signals.done.emit({"hand_with_points_obj": str(res.out_obj)})
        except Exception as e:
            self.signals.fail.emit(str(e))


class _StepCard(QFrame):
    _STYLE_DEFAULT = """
        QFrame#FlowStepCard {
            border: 1px solid #444;
            border-radius: 10px;
            background: rgba(255,255,255,0.035);
        }
    """
    _STYLE_ACTIVE = """
        QFrame#FlowStepCard {
            border: 2px solid #2e7d32;
            border-radius: 10px;
            background: rgba(46,125,50,0.13);
        }
    """
    _STYLE_COMPLETED = """
        QFrame#FlowStepCard {
            border: 2px solid #2e7d32;
            border-radius: 10px;
            background: rgba(46,125,50,0.06);
        }
    """

    def __init__(self, number: int, title: str, details: list[str]):
        super().__init__()
        self.setObjectName("FlowStepCard")
        self.setFrameShape(QFrame.StyledPanel)
        self._active = False
        self._completed = False
        self._detail_labels: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        self.header = QLabel(f"{number}. {title}")
        self.header.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(self.header)

        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        for key in details:
            lbl = QLabel(f"{key}: —")
            lbl.setWordWrap(True)
            lbl.setStyleSheet("font-size: 13px;")
            self._detail_labels[key] = lbl
            layout.addWidget(lbl)

        layout.addStretch(1)

    def _refresh_style(self):
        if self._active:
            self.setStyleSheet(self._STYLE_ACTIVE)
        elif self._completed:
            self.setStyleSheet(self._STYLE_COMPLETED)
        else:
            self.setStyleSheet(self._STYLE_DEFAULT)

    def set_active(self, active: bool):
        self._active = bool(active)
        self._refresh_style()

    def set_completed(self, completed: bool = True):
        self._completed = bool(completed)
        self._refresh_style()

    def set_value(self, key: str, value):
        if key in self._detail_labels:
            self._detail_labels[key].setText(f"{key}: {value}")

    def clear_values(self):
        for key, lbl in self._detail_labels.items():
            lbl.setText(f"{key}: —")
        self._active = False
        self._completed = False
        self._refresh_style()


class _RetryDialog(QDialog):
    def __init__(self, parent=None, allow_automatic: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Retry detection workflow")
        self.setModal(True)
        self.resize(460, 220)
        self.selected = "automatic" if allow_automatic else "validation_2d3d"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Repeat from:")
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        layout.addWidget(title)

        self.group = QButtonGroup(self)
        for key, text in [
            ("automatic", "Automatic Landmark Detection"),
            ("validation_2d3d", "2D/3D Validation"),
        ]:
            rb = QRadioButton(text)
            if key == "automatic" and not allow_automatic:
                rb.setEnabled(False)
                rb.setToolTip("Automatic detection can only be repeated when the original detection settings are available.")
            rb.setChecked(key == self.selected)
            rb.toggled.connect(lambda checked, k=key: setattr(self, "selected", k) if checked else None)
            self.group.addButton(rb)
            layout.addWidget(rb)

        layout.addStretch(1)
        bottom = QHBoxLayout(); bottom.addStretch(1)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        ok = QPushButton("Retry"); ok.clicked.connect(self.accept)
        bottom.addWidget(cancel); bottom.addWidget(ok)
        layout.addLayout(bottom)


class DetectMapPage(QWidget):
    """Screen 5: automatic landmark detection + 2D/3D validation workflow."""

    completed = Signal(dict)
    failed = Signal(str)
    back_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.threadpool = QThreadPool.globalInstance()
        self._last_args = None
        self._payload_ok = None
        self._texture_path: Path | None = None
        self._obj_path: Path | None = None
        self._out_dir: Path | None = None
        self._v_flip: bool = True
        self._snap_to_vertices: bool = True
        self._measurement_mode: str = "flat_hand"
        self._auto_open_validators: bool = True
        self._workflow_complete: bool = False
        self._busy: bool = False
        self._active_workers: list[QRunnable] = []
        self._validation_dialog: LandmarkValidationDialog | None = None
        self._build_ui()

    def is_busy(self) -> bool:
        return bool(self._busy)

    def _start_worker(self, worker: QRunnable):
        try:
            worker.setAutoDelete(False)
        except Exception:
            pass
        self._active_workers.append(worker)
        self.threadpool.start(worker)

    def _release_workers(self):
        self._active_workers.clear()

    def _cleanup_validation_dialogs(self):
        dialogs = []
        if self._validation_dialog is not None:
            dialogs.append(self._validation_dialog)
        dialogs.extend(
            child for child in self.findChildren(QDialog)
            if isinstance(child, (LandmarkValidationDialog, BlenderPreviewDialog))
        )

        seen = set()
        for dlg in dialogs:
            if dlg is None or id(dlg) in seen:
                continue
            seen.add(id(dlg))
            try:
                dlg.close()
            except Exception:
                pass
            try:
                dlg.deleteLater()
            except Exception:
                pass
        self._validation_dialog = None

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setSpacing(14)

        title = QLabel("Landmark Detection + 2D/3D Validation")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        subtitle = QLabel(
            "The application detects the landmarks automatically and then opens a combined validation window "
            "with synchronized 2D texture and 3D model editing tabs."
        )
        subtitle.setProperty("role", "subtitle")
        subtitle.setWordWrap(True)
        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
        outer.addWidget(title); outer.addWidget(subtitle); outer.addWidget(line)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1); self.progress.setValue(0)
        outer.addWidget(self.progress)

        cards_row = QGridLayout(); cards_row.setHorizontalSpacing(16); cards_row.setVerticalSpacing(16)
        self.card_auto = _StepCard(1, "Automatic Landmark Detection", ["Initial 2D points", "Mapping points to 3D", "Removing close points", "Total mapped"])
        self.card_validation = _StepCard(2, "2D/3D Validation", ["Points to check", "Final points"])
        cards_row.addWidget(self.card_auto, 0, 0); cards_row.addWidget(self.card_validation, 0, 1)
        cards_row.setColumnStretch(0, 1); cards_row.setColumnStretch(1, 1)
        outer.addLayout(cards_row)

        self.status = QLabel(""); self.status.setWordWrap(True)
        outer.addWidget(self.status)

        outer.addStretch(1)

        bottom = QHBoxLayout()
        self.btn_back = QPushButton("Back"); self.btn_back.setFixedHeight(40); self.btn_back.setFixedWidth(120)
        self.btn_back.clicked.connect(self.back_clicked.emit)
        bottom.addWidget(self.btn_back)
        bottom.addStretch(1)
        self.btn_retry = QPushButton("Retry"); self.btn_retry.setFixedHeight(40); self.btn_retry.setFixedWidth(140); self.btn_retry.setEnabled(False)
        self.btn_retry.clicked.connect(self._open_retry_dialog)
        self.btn_continue = QPushButton("Next"); self.btn_continue.setFixedHeight(40); self.btn_continue.setFixedWidth(160); self.btn_continue.setEnabled(False)
        self.btn_continue.clicked.connect(self._continue)
        bottom.addWidget(self.btn_retry); bottom.addWidget(self.btn_continue); outer.addLayout(bottom)

    def _set_active_step(self, step: str | None):
        self.card_auto.set_active(step == "auto")
        self.card_validation.set_active(step == "validation")

    def _reset_flow_ui(self, clear_detection: bool = True):
        if clear_detection:
            self.card_auto.clear_values()
        self.card_validation.clear_values()
        self._workflow_complete = False
        self.btn_continue.setEnabled(False); self.btn_retry.setEnabled(False)
        self.status.setText("")

    def has_loaded_state_for(self, csv_2d: str | Path | None, csv_3d: str | Path | None) -> bool:
        """Return True when the page already represents the given detection CSVs."""
        if not self._payload_ok or not csv_2d or not csv_3d:
            return False
        try:
            current_2d = Path(str(self._payload_ok.get("csv_2d", ""))).resolve()
            current_3d = Path(str(self._payload_ok.get("csv_3d", ""))).resolve()
            wanted_2d = Path(str(csv_2d)).resolve()
            wanted_3d = Path(str(csv_3d)).resolve()
            return current_2d == wanted_2d and current_3d == wanted_3d
        except Exception:
            return False

    def prepare_for_return_navigation(self):
        """Restore action buttons when the user navigates back to this completed page.

        During Continue(), the buttons are disabled while hand_with_points.obj is
        generated. If the page is later reached again from the stepper, the user
        must be able to reopen Retry / 2D-3D Validation instead of finding the
        page locked in its previous transient state.
        """
        if self._busy or self._payload_ok is None:
            return
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self._workflow_complete = True
        self._set_active_step(None)
        self.card_auto.set_completed(True)
        self.card_validation.set_completed(True)

        n2d = int(self._payload_ok.get("n_2d") or 0)
        raw_n3d = self._payload_ok.get("n_3d_mapped")
        n3d = n2d if raw_n3d is None else int(raw_n3d or 0)
        if n2d:
            self.card_validation.set_value("Points to check", n2d)
            self.card_validation.set_value("Final points", self._format_final_points(n2d, n3d))

        self.btn_retry.setEnabled(True)
        self.btn_continue.setEnabled(True)
        self.status.setStyleSheet("color: #1b5e20; font-weight: 600;")
        self.status.setText("Workflow loaded. You can continue to the next step or retry the 2D/3D validation stage.")


    def _write_open_project_context(self, extra: dict | None = None):
        """Persist the minimal paths needed by Open Project.

        Older versions inferred the project state only from generated filenames,
        which made NewHandTexture.png look mandatory. This metadata keeps the
        original OBJ/texture and the generated CSV paths explicit for future
        sessions.
        """
        if self._out_dir is None:
            return

        payload = {
            "schema": "hand_measurement_project_context",
            "version": 3,
            "out_dir": str(self._out_dir),
            "obj_path": str(self._obj_path) if self._obj_path else None,
            "texture_path": str(self._texture_path) if self._texture_path else None,
            "measurement_mode": "flat_hand",
            "v_flip": bool(self._v_flip),
            "snap_to_vertices": bool(self._snap_to_vertices),
        }
        if self._last_args:
            target_json = self._last_args[3] if len(self._last_args) > 3 else None
            if target_json:
                payload["target_json"] = str(target_json)
        if self._payload_ok:
            payload.update({k: v for k, v in self._payload_ok.items() if v is not None})
        if extra:
            payload.update({k: v for k, v in extra.items() if v is not None})

        try:
            self._out_dir.mkdir(parents=True, exist_ok=True)
            project_context_path(self._out_dir).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            # Metadata is helpful for Open Project but must never interrupt the workflow.
            pass

    def start(
        self,
        texture_path: str,
        obj_path: str,
        out_dir: str,
        target_json: str | None = None,
        v_flip: bool = True,
        snap_to_vertices: bool = True,
        measurement_mode: str = "flat_hand",
    ):
        self._cleanup_validation_dialogs()
        self._payload_ok = None; self._auto_open_validators = True; self._busy = True
        self._texture_path = Path(texture_path); self._obj_path = Path(obj_path); self._out_dir = Path(out_dir)
        self._v_flip = bool(v_flip); self._snap_to_vertices = bool(snap_to_vertices)
        self._measurement_mode = "flat_hand"
        self._last_args = (texture_path, obj_path, out_dir, target_json, v_flip, snap_to_vertices, self._measurement_mode)
        self._write_open_project_context({"target_json": str(target_json) if target_json else None})
        self._reset_flow_ui(clear_detection=True); self._set_active_step("auto")
        self.progress.setRange(0, 0)
        self.status.setStyleSheet("")
        self.status.setText("Running automatic landmark detection and 2D → 3D mapping…")
        self.card_auto.set_value("Mapping points to 3D", "in progress…")
        worker = _Worker(self._texture_path, self._obj_path, self._out_dir, Path(target_json) if target_json else None, self._v_flip, self._snap_to_vertices)
        worker.signals.log.connect(self._append_log); worker.signals.done.connect(self._done); worker.signals.fail.connect(self._fail)
        self._start_worker(worker)

    def start_from_existing(
        self,
        texture_path: str,
        obj_path: str,
        out_dir: str,
        csv_2d: str,
        csv_3d: str,
        v_flip: bool = True,
        snap_to_vertices: bool = True,
        target_json: str | None = None,
        measurement_mode: str = "flat_hand",
    ):
        self._payload_ok = None; self._auto_open_validators = False; self._busy = False
        self._texture_path = Path(texture_path); self._obj_path = Path(obj_path); self._out_dir = Path(out_dir)
        self._v_flip = bool(v_flip); self._snap_to_vertices = bool(snap_to_vertices)
        self._measurement_mode = "flat_hand"
        self._last_args = (texture_path, obj_path, out_dir, target_json, v_flip, snap_to_vertices, self._measurement_mode) if target_json else None
        self._write_open_project_context({"csv_2d": str(csv_2d), "csv_3d": str(csv_3d), "target_json": str(target_json) if target_json else None})
        self._reset_flow_ui(clear_detection=True); self.progress.setRange(0, 1); self.progress.setValue(1)
        csv2d_path = Path(csv_2d); csv3d_path = Path(csv_3d)
        if not csv2d_path.exists():
            self._fail(f"Missing 2D CSV: {csv2d_path}"); return
        if not csv3d_path.exists():
            self._fail(f"Missing 3D CSV: {csv3d_path}"); return
        try:
            df2d = pd.read_csv(csv2d_path); df3d = pd.read_csv(csv3d_path)
            n2d = int(len(df2d)); n3d_mapped = self._count_valid_3d(df3d)
        except Exception as e:
            self._fail(f"Could not load existing CSV files: {e}"); return
        self._append_log("Loaded existing project state. Detection was not run again.")
        self._done({"csv_2d": str(csv2d_path), "csv_3d": str(csv3d_path), "n_2d": n2d, "n_3d_mapped": n3d_mapped})
        self._mark_workflow_complete()

    def _count_valid_3d(self, df3d: pd.DataFrame) -> int:
        if df3d is None or df3d.empty:
            return 0
        if {"x3d", "y3d", "z3d"}.issubset(df3d.columns):
            x = pd.to_numeric(df3d["x3d"], errors="coerce"); y = pd.to_numeric(df3d["y3d"], errors="coerce"); z = pd.to_numeric(df3d["z3d"], errors="coerce")
            return int((x.notna() & y.notna() & z.notna()).sum())
        if {"X", "Y", "Z"}.issubset(df3d.columns):
            x = pd.to_numeric(df3d["X"], errors="coerce"); y = pd.to_numeric(df3d["Y"], errors="coerce"); z = pd.to_numeric(df3d["Z"], errors="coerce")
            return int((x.notna() & y.notna() & z.notna()).sum())
        if "status" in df3d.columns:
            return int((df3d["status"] != "unmapped").sum())
        return int(len(df3d))

    def _append_log(self, line: str):
        """
        Internal progress hook.

        The raw process log is intentionally not shown in this page anymore.
        Instead, relevant messages are translated into the visual step cards.
        """
        text = str(line)

        m = re.search(r"Initial 2D detections:\s*(\d+)\s*points", text, re.IGNORECASE)
        if m:
            self.card_auto.set_value("Initial 2D points", int(m.group(1)))
            self.card_auto.set_value("Mapping points to 3D", "in progress…")
            return

        m = re.search(r"3D post-process removed\s*(\d+)\s*near-duplicate", text, re.IGNORECASE)
        if m:
            self.card_auto.set_value("Mapping points to 3D", "completed")
            self.card_auto.set_value("Removing close points", f"completed ({int(m.group(1))} removed)")
            return

        m = re.search(r"3D post-process found no near-duplicate", text, re.IGNORECASE)
        if m:
            self.card_auto.set_value("Mapping points to 3D", "completed")
            self.card_auto.set_value("Removing close points", "completed (0 removed)")
            return

        m = re.search(r"3D CSV saved:.*\((\d+)\s*points;\s*mapped=(\d+)\)", text, re.IGNORECASE)
        if m:
            total = int(m.group(1))
            mapped = int(m.group(2))
            self.card_auto.set_value("Total mapped", f"{mapped}/{total}" if total != mapped else mapped)
            return

    def _done(self, payload: dict):
        self._release_workers()
        self._busy = False
        self._payload_ok = payload
        self._write_open_project_context(payload)
        self.progress.setRange(0, 1); self.progress.setValue(1)
        n2d = int(payload.get("n_2d") or 0); n3d = int(payload.get("n_3d_mapped") or 0)
        self.card_auto.set_value("Initial 2D points", n2d)
        self.card_auto.set_value("Mapping points to 3D", "completed")
        # "Removing close points" is normally filled from the internal progress log
        # because that message includes how many points were removed. Keep a safe
        # fallback only for cases where the worker did not emit that message.
        removing_text = self.card_auto._detail_labels.get("Removing close points").text() if "Removing close points" in self.card_auto._detail_labels else ""
        if removing_text.endswith(": —"):
            self.card_auto.set_value("Removing close points", "completed")
        self.card_auto.set_value("Total mapped", n3d)
        self.card_auto.set_completed(True)
        self.status.setStyleSheet("color: #1b5e20; font-weight: 600;")
        self.card_validation.set_value("Points to check", n2d)
        self.status.setText("Automatic detection completed. Opening 2D/3D validation…")
        if self._auto_open_validators:
            QTimer.singleShot(300, self._open_2d3d_validation_and_finish)

    def _fail(self, msg: str):
        self._release_workers()
        self._busy = False
        self.progress.setRange(0, 1); self.progress.setValue(0)
        self._set_active_step(None)
        self.status.setStyleSheet("color: #b00020; font-weight: 600;")
        self.status.setText("Error in detection/mapping.\n" + msg)
        self.btn_retry.setEnabled(bool(self._last_args))
        self.failed.emit(msg)

    def _format_final_points(self, n2d: int, n3d: int):
        return n2d if n2d == n3d else f"{n2d} (3D valid: {n3d})"

    def _mark_workflow_complete(self):
        self._set_active_step(None)
        self.card_auto.set_completed(True)
        self.card_validation.set_completed(True)
        if self._payload_ok is not None:
            n2d = int(self._payload_ok.get("n_2d") or 0)
            raw_n3d = self._payload_ok.get("n_3d_mapped")
            n3d = n2d if raw_n3d is None else int(raw_n3d or 0)
            self.card_validation.set_value("Final points", self._format_final_points(n2d, n3d))
        self._workflow_complete = True
        self.btn_continue.setEnabled(True); self.btn_retry.setEnabled(True)
        self.status.setStyleSheet("color: #1b5e20; font-weight: 600;")
        self.status.setText("Workflow completed. You can continue to the next step or retry the validation stage.")

    def _apply_2d_validation_changes(self, df_clean: pd.DataFrame) -> dict:
        """Persist the 2D editor state and rebuild/synchronize the mapped 3D CSV.

        This method is intentionally shared by the combined validation dialog,
        so the 3D tab can be refreshed from exactly the same mapping logic that
        was previously used after the standalone 2D editor.
        """
        if self._payload_ok is None:
            raise RuntimeError("Detection/mapping is not available yet.")
        if self._texture_path is None or self._obj_path is None or self._out_dir is None:
            raise RuntimeError("Missing texture, OBJ or output directory context.")

        csv2d = self._payload_ok.get("csv_2d")
        csv3d = self._payload_ok.get("csv_3d")
        if not csv2d:
            raise RuntimeError("2D CSV path not found.")

        csv2d_path = Path(csv2d)
        out_csv3d = Path(csv3d) if csv3d else detections_mapped_3d_csv(self._out_dir)

        df_before = pd.read_csv(csv2d_path) if csv2d_path.exists() else pd.DataFrame()
        df_clean = df_clean.copy().reset_index(drop=True)
        df_clean.to_csv(csv2d_path, index=False)

        cols_cmp = [c for c in ["pixel_x", "pixel_y", "area", "contour_id"] if c in df_before.columns and c in df_clean.columns]

        if cols_cmp and df_before[cols_cmp].reset_index(drop=True).equals(df_clean[cols_cmp].reset_index(drop=True)):
            df3d_final = pd.read_csv(out_csv3d) if out_csv3d.exists() else pd.DataFrame()
        else:
            img = cv2.imread(str(self._texture_path), cv2.IMREAD_COLOR)
            if img is None:
                raise FileNotFoundError(f"Could not read texture: {self._texture_path}")
            H, W = img.shape[:2]

            df3d_prev = pd.read_csv(out_csv3d) if out_csv3d.exists() else pd.DataFrame()
            key_cols = ["pixel_x", "pixel_y"]

            for c in key_cols:
                if c in df_clean.columns:
                    df_clean[c] = pd.to_numeric(df_clean[c], errors="coerce").fillna(-1).astype(int)
                if c in df3d_prev.columns:
                    df3d_prev[c] = pd.to_numeric(df3d_prev[c], errors="coerce").fillna(-1).astype(int)

            if not df3d_prev.empty and all(c in df3d_prev.columns for c in key_cols):
                keep_pairs = df_clean[key_cols].drop_duplicates()
                df3d_kept = df3d_prev.merge(keep_pairs, on=key_cols, how="inner")
            else:
                df3d_kept = pd.DataFrame()

            if not df3d_kept.empty:
                existing_pairs = df3d_kept[key_cols].drop_duplicates()
                df_new_2d = (
                    df_clean
                    .merge(existing_pairs.assign(_exists=1), on=key_cols, how="left")
                    .query("_exists != 1 or _exists != _exists")
                    .drop(columns=["_exists"], errors="ignore")
                    .reset_index(drop=True)
                )
            else:
                df_new_2d = df_clean.copy()

            if not df_new_2d.empty:
                df3d_new_only = self._map_pixels_to_3d(
                    df_pixels=df_new_2d,
                    obj_path=self._obj_path,
                    tex_w=W,
                    tex_h=H,
                    v_flip=self._v_flip,
                    snap_to_vertices=self._snap_to_vertices,
                )
            else:
                df3d_new_only = pd.DataFrame()

            df3d_final = pd.concat([df3d_kept, df3d_new_only], ignore_index=True)

            if not df3d_final.empty and all(c in df3d_final.columns for c in key_cols):
                order_df = df_clean[key_cols].reset_index().rename(columns={"index": "_order"})
                df3d_final = (
                    order_df
                    .merge(df3d_final, on=key_cols, how="left")
                    .sort_values("_order")
                    .drop(columns=["_order"])
                    .reset_index(drop=True)
                )

            df3d_final, df_clean, removed_close, dedupe_threshold = reconcile_points_with_3d_priority(
                df3d_final,
                obj_path=self._obj_path,
            )
            df_clean.to_csv(csv2d_path, index=False)
            df3d_final.to_csv(out_csv3d, index=False)

        n2d = int(len(df_clean))
        n3d = self._count_valid_3d(df3d_final)

        self._payload_ok["csv_2d"] = str(csv2d_path)
        self._payload_ok["csv_3d"] = str(out_csv3d)
        self._payload_ok["n_2d"] = n2d
        self._payload_ok["n_3d_mapped"] = n3d

        self.card_validation.set_value("Final points", self._format_final_points(n2d, n3d))

        return {"csv_2d": str(csv2d_path), "csv_3d": str(out_csv3d), "n_2d": n2d, "n_3d": n3d}

    def _prepare_validation_smartuv_assets(self) -> tuple[Path | None, Path | None]:
        """Ensure the SmartUV texture and its reference OBJ exist for the 2D validation tab.

        The same reduced Blender process used by manual threshold selection is reused
        here, but the resulting OBJ/texture are only auxiliary validation assets.
        They do not replace the original mesh used by detection, 3D editing or the
        following workflow steps.
        """
        if self._texture_path is None or self._obj_path is None or self._out_dir is None:
            return None, None

        preview_dir = threshold_preview_dir(self._out_dir)
        preview_texture = preview_dir / "NewHandTexture.png"
        smartuv_obj = preview_dir / f"{self._obj_path.stem}_UVB.obj"

        if preview_texture.exists() and smartuv_obj.exists():
            return preview_texture, smartuv_obj

        wait_dialog = BlenderPreviewDialog(
            obj_path=self._obj_path,
            texture_path=self._texture_path,
            out_dir=self._out_dir,
            parent=self,
            window_title="Preparing SmartUV 2D validation",
            subtitle_text=(
                "The 2D validation tab will use an auxiliary SmartUV-baked texture, "
                "similar to the manual color selection preview. Blender will generate "
                "that texture and a reference OBJ used only to project 3D landmarks onto it."
            ),
            done_status_text="✅ SmartUV preview generated. Opening 2D/3D validation…",
        )

        QTimer.singleShot(0, wait_dialog.start)
        if wait_dialog.exec() != QDialog.DialogCode.Accepted:
            QMessageBox.information(
                self,
                "SmartUV 2D validation",
                "The SmartUV validation texture could not be generated. The validation window will use the original 2D texture instead.",
            )
            return None, None

        preview_texture = wait_dialog.preview_texture_path or preview_texture
        smartuv_obj = wait_dialog.preview_obj_path or smartuv_obj
        if preview_texture.exists() and smartuv_obj.exists():
            return preview_texture, smartuv_obj

        QMessageBox.warning(
            self,
            "SmartUV 2D validation",
            "The SmartUV preview finished, but the expected texture or reference OBJ was not found. "
            "The validation window will use the original 2D texture instead.",
        )
        return None, None

    def _open_2d3d_validation_and_finish(self, mark_complete: bool = True) -> bool:
        if self._payload_ok is None:
            QMessageBox.information(self, "Not yet available", "Complete detection/mapping first.")
            return False
        if self._texture_path is None or self._obj_path is None or self._out_dir is None:
            QMessageBox.warning(self, "Incomplete context", "Missing paths (texture/obj/out_dir).")
            return False

        csv2d = self._payload_ok.get("csv_2d")
        csv3d = self._payload_ok.get("csv_3d")
        if not csv2d or not csv3d:
            QMessageBox.warning(self, "Missing CSV", "2D/3D CSV path not found.")
            return False

        csv2d_path = Path(csv2d)
        csv3d_path = Path(csv3d)
        if not csv2d_path.exists() or not csv3d_path.exists():
            QMessageBox.warning(self, "Missing CSV", "2D or 3D CSV file does not exist.")
            return False

        try:
            df2d = pd.read_csv(csv2d_path)
            df3d = pd.read_csv(csv3d_path)
            n2d = int(len(df2d))
            n3d = self._count_valid_3d(df3d)
        except Exception as e:
            QMessageBox.warning(self, "2D/3D validation", f"Could not read validation CSV files:\n{e}")
            return False

        self._set_active_step("validation")
        self.card_validation.set_value("Points to check", n2d)
        self.status.setStyleSheet("color: #1b5e20; font-weight: 600;")
        self.status.setText("2D/3D validation: preparing the SmartUV 2D validation view…")

        smartuv_texture_path, smartuv_obj_path = self._prepare_validation_smartuv_assets()
        self.status.setText("2D/3D validation: use the tabs to edit the same landmark set.")

        try:
            dlg = LandmarkValidationDialog(
                texture_path=self._texture_path,
                obj_path=self._obj_path,
                csv2d_path=csv2d_path,
                csv3d_path=csv3d_path,
                apply_2d_changes=self._apply_2d_validation_changes,
                v_flip=self._v_flip,
                snap_to_vertices=self._snap_to_vertices,
                parent=self,
                smartuv_texture_path=smartuv_texture_path,
                smartuv_obj_path=smartuv_obj_path,
            )
            self._validation_dialog = dlg
        except Exception as e:
            QMessageBox.warning(self, "2D/3D validation", f"Could not open the validation dialog:\n{e}")
            return False

        try:
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self._set_active_step(None)
                self.btn_retry.setEnabled(True)
                self.status.setText("2D/3D validation was cancelled. Use Retry to repeat the validation stage.")
                return False

            df2d = pd.read_csv(csv2d_path) if csv2d_path.exists() else pd.DataFrame()
            df3d = pd.read_csv(csv3d_path) if csv3d_path.exists() else pd.DataFrame()
            n2d = int(len(df2d))
            n3d = self._count_valid_3d(df3d)
            self._payload_ok["n_2d"] = n2d
            self._payload_ok["n_3d_mapped"] = n3d
            self.card_validation.set_value("Final points", self._format_final_points(n2d, n3d))
            self.card_validation.set_completed(True)
            self.status.setText("2D/3D validation completed.")
            if mark_complete:
                self._mark_workflow_complete()
            return True
        except Exception as e:
            self.status.setStyleSheet("color:#b00020; font-weight:600;")
            self.status.setText(f"Could not refresh counts after 2D/3D validation: {e}")
            return False
        finally:
            self._validation_dialog = None
            try:
                dlg.deleteLater()
            except Exception:
                pass

    def _open_retry_dialog(self):
        if self._payload_ok is None and self._last_args is None:
            return
        dlg = _RetryDialog(self, allow_automatic=bool(self._last_args))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.btn_continue.setEnabled(False); self.btn_retry.setEnabled(False)
        if dlg.selected == "automatic":
            if not self._last_args:
                QMessageBox.information(self, "Retry", "Automatic detection cannot be repeated because the original input arguments are not available.")
                self.btn_retry.setEnabled(True); self.btn_continue.setEnabled(self._workflow_complete); return
            self.start(*self._last_args)
        elif dlg.selected == "validation_2d3d":
            self.card_validation.clear_values()
            QTimer.singleShot(100, self._open_2d3d_validation_and_finish)

    def _continue(self):
        if self._payload_ok is None:
            return
        csv3d = self._payload_ok.get("csv_3d")
        if not csv3d:
            QMessageBox.warning(self, "Missing 3D CSV", "3D CSV path not found."); return
        if self._obj_path is None or self._out_dir is None:
            QMessageBox.warning(self, "Incomplete context", "Missing paths (obj/out_dir)."); return
        csv3d_path = Path(csv3d)
        if not csv3d_path.exists():
            QMessageBox.warning(self, "Missing 3D CSV", f"Does not exist: {csv3d_path}"); return
        out_obj = hand_with_points_obj(self._out_dir)
        self._busy = True
        self.btn_continue.setEnabled(False); self.btn_retry.setEnabled(False)
        self.progress.setRange(0, 0); self.status.setText("Generating hand_with_points.obj (hand + spheres)…")
        worker = _MakePointsWorker(self._obj_path, csv3d_path, out_obj, 0.5)
        worker.signals.log.connect(self._append_log); worker.signals.done.connect(self._on_points_obj_done); worker.signals.fail.connect(self._on_points_obj_fail)
        self._start_worker(worker)

    def _on_points_obj_done(self, payload: dict):
        self._release_workers()
        self._busy = False
        self.progress.setRange(0, 1); self.progress.setValue(1)
        self._payload_ok.update(payload)
        self._write_open_project_context(payload)
        self.status.setStyleSheet("color:#1b5e20; font-weight:600;")
        self.status.setText("hand_with_points.obj generated.")
        self.btn_continue.setEnabled(True)
        self.btn_retry.setEnabled(True)
        self.completed.emit(self._payload_ok)

    def _on_points_obj_fail(self, msg: str):
        self._release_workers()
        self._busy = False
        self.progress.setRange(0, 1); self.progress.setValue(0)
        self.status.setStyleSheet("color:#b00020; font-weight:600;")
        self.status.setText("Could not generate hand_with_points.obj:\n" + msg)
        self.btn_continue.setEnabled(True); self.btn_retry.setEnabled(True)

    # -------- UV -> XYZ (equivalent notebook, without Blender) --------
    def _map_pixels_to_3d(
        self,
        df_pixels: pd.DataFrame,
        obj_path: Path,
        tex_w: int,
        tex_h: int,
        v_flip: bool = True,
        snap_to_vertices: bool = True
    ) -> pd.DataFrame:
        """
        - Reads OBJ (V, VT, Fv, Fvt)
        - px -> uv
        - barycentric in UV -> xyz_raw
        - (optional) snap to nearest vertex
        Returns df with columns u,v,x3d_raw,y3d_raw,z3d_raw,x3d,y3d,z3d,X,Y,Z,status
        """
        obj_path = Path(obj_path)
        if not obj_path.exists():
            raise FileNotFoundError(f"OBJ not found: {obj_path}")

        def _norm_idx(i: int, n: int) -> int:
            return i - 1 if i > 0 else n + i

        def parse_obj_uv_tris_strict(path: Path):
            V, VT, Fv, Fvt = [], [], [], []
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("v "):
                        _, x, y, z = line.split()[:4]
                        V.append([float(x), float(y), float(z)])
                    elif line.startswith("vt "):
                        parts = line.split()
                        u, v = float(parts[1]), float(parts[2])
                        VT.append([u, v])
                    elif line.startswith("f "):
                        parts = line.split()[1:]
                        vidx, vtidx = [], []
                        for p in parts:
                            comps = p.split("/")
                            vi = _norm_idx(int(comps[0]), len(V))
                            vidx.append(vi)
                            if len(comps) > 1 and comps[1] != "":
                                vti = _norm_idx(int(comps[1]), len(VT))
                                vtidx.append(vti)
                        if len(vidx) >= 3 and len(vtidx) >= 3:
                            for i in range(1, len(vidx) - 1):
                                Fv.append([vidx[0], vidx[i], vidx[i + 1]])
                                Fvt.append([vtidx[0], vtidx[i], vtidx[i + 1]])

            V = np.asarray(V, np.float32)
            VT = np.asarray(VT, np.float32)
            Fv = np.asarray(Fv, np.int32)
            Fvt = np.asarray(Fvt, np.int32)
            if V.size == 0 or VT.size == 0 or Fv.size == 0 or Fvt.size == 0:
                raise ValueError("OBJ does not contain sufficient geometry/UVs for mapping.")
            return V, VT, Fv, Fvt

        def px_to_uv(x: int, y: int, W: int, H: int, flip_v: bool):
            u = (x + 0.5) / float(W)
            v_img = (y + 0.5) / float(H)
            v = 1.0 - v_img if flip_v else v_img
            return u, v

        def barycentric_uv(P, A, B, C):
            v0 = B - A
            v1 = C - A
            v2 = P - A
            dot00 = float(np.dot(v0, v0))
            dot01 = float(np.dot(v0, v1))
            dot11 = float(np.dot(v1, v1))
            dot02 = float(np.dot(v0, v2))
            dot12 = float(np.dot(v1, v2))
            denom = dot00 * dot11 - dot01 * dot01
            if abs(denom) < 1e-12:
                return None
            inv = 1.0 / denom
            u = (dot11 * dot02 - dot01 * dot12) * inv
            v = (dot00 * dot12 - dot01 * dot02) * inv
            w = 1.0 - u - v
            if u >= -1e-5 and v >= -1e-5 and w >= -1e-5:
                return np.array([u, v, w], np.float32)
            return None

        V_cur, VT_cur, Fv_cur, Fvt_cur = parse_obj_uv_tris_strict(obj_path)
        tri_uv = VT_cur[Fvt_cur]  # (n_tris, 3, 2)

        df3d = df_pixels.copy().reset_index(drop=True)

        # px->uv
        uvs = [
            px_to_uv(int(x), int(y), tex_w, tex_h, flip_v=v_flip)
            for x, y in df3d[["pixel_x", "pixel_y"]].itertuples(index=False, name=None)
        ]
        df3d["u"] = [u for u, _ in uvs]
        df3d["v"] = [v for _, v in uvs]

        xyz_raw = np.full((len(df3d), 3), np.nan, np.float32)

        # UV barycentric -> XYZ
        for idx, (u, v) in enumerate(zip(df3d["u"].to_numpy(), df3d["v"].to_numpy())):
            P = np.array([u, v], np.float32)
            hit = False
            for t in range(tri_uv.shape[0]):
                Auv, Buv, Cuv = tri_uv[t]
                bc = barycentric_uv(P, Auv, Buv, Cuv)
                if bc is not None:
                    A3, B3, C3 = V_cur[Fv_cur[t]][0], V_cur[Fv_cur[t]][1], V_cur[Fv_cur[t]][2]
                    uB, vC, wA = bc
                    xyz_raw[idx] = wA * A3 + uB * B3 + vC * C3
                    hit = True
                    break
            if not hit:
                xyz_raw[idx] = np.array([np.nan, np.nan, np.nan], np.float32)

        df3d["x3d_raw"], df3d["y3d_raw"], df3d["z3d_raw"] = xyz_raw[:, 0], xyz_raw[:, 1], xyz_raw[:, 2]

        # snap to nearest vertex
        xyz_snapped = xyz_raw.copy()
        valid = np.all(np.isfinite(xyz_raw), axis=1)

        if snap_to_vertices:
            for i in range(len(df3d)):
                if not valid[i]:
                    continue
                p = xyz_raw[i]
                d2 = np.sum((V_cur - p[None, :]) ** 2, axis=1)
                j = int(np.argmin(d2))
                xyz_snapped[i] = V_cur[j]

        df3d["x3d"], df3d["y3d"], df3d["z3d"] = xyz_snapped[:, 0], xyz_snapped[:, 1], xyz_snapped[:, 2]
        df3d["X"], df3d["Y"], df3d["Z"] = df3d["x3d"], df3d["y3d"], df3d["z3d"]
        df3d["status"] = np.where(valid, "mapped_snapped" if snap_to_vertices else "mapped", "unmapped")

        return df3d
