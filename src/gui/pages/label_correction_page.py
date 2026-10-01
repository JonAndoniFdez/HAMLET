from __future__ import annotations

from pathlib import Path
import shutil

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QProgressBar,
    QPushButton, QHBoxLayout, QTextEdit, QScrollArea
)

from ...core.paths import asset_path
from ...core.label_correction import (
    run_interactive_label_editor,
    apply_labels_in_blender,
    persist_corrected_csv,
)
from ...core.settings import load_settings
from ...core.paths import resolve_blender_exe
from ...core.output_cleanup import processing_dir, cleanup_legacy_output_clutter

class _Signals(QObject):
    log = Signal(str)
    done = Signal(dict)
    fail = Signal(str)


class _Worker(QRunnable):
    def __init__(self, settings: dict, out_dir: Path, labeled_csv: Path, labeled_blend: Path, mesh_path: Path):
        super().__init__()
        self.settings = settings
        self.out_dir = out_dir
        self.labeled_csv = labeled_csv
        self.labeled_blend = labeled_blend
        self.mesh_path = mesh_path
        self.signals = _Signals()

    def run(self):
        try:
            template_csv = asset_path("data", "markers_template.csv")
            if not template_csv.exists():
                self.signals.fail.emit(f"markers_template.csv does not exist at: {template_csv}")
                return

            editor_dir = processing_dir(self.out_dir, "label_editor")
            corrected_csv = editor_dir / "detections_labeled_corrected.csv"

            # 1) Editor interactivo
            ed = run_interactive_label_editor(
                detections_csv=self.labeled_csv,
                template_csv=template_csv,
                out_csv=corrected_csv,
                mesh_path=self.mesh_path,
                label_scale_factor=0.75,
                help_scale=0.8,
                no_align_bbox=True,
                log=lambda s: self.signals.log.emit(str(s)),
            )
            if not ed.ok or not ed.corrected_csv:
                self.signals.fail.emit(ed.message)
                return

            # 2) Blender aplica etiquetas sobre el .blend etiquetado.
            # La resolución es segura: no convierte rutas vacías en Path(".").
            persisted = load_settings() or {}
            merged_settings = dict(persisted)
            if isinstance(self.settings, dict):
                merged_settings.update(self.settings)

            blender_exe = resolve_blender_exe(merged_settings)

            if blender_exe is None:
                self.signals.fail.emit(
                    "Blender executable not found. Expected bundled path: <app>/blender/blender.exe"
                )
                return

            corrected_blend = editor_dir / f"{Path(self.labeled_blend).stem}_manual.blend"

            ap = apply_labels_in_blender(
                blender_exe=blender_exe,
                labeled_blend=self.labeled_blend,
                corrected_csv=ed.corrected_csv,
                out_blend=corrected_blend,
                log=lambda s: self.signals.log.emit(str(s)),
            )
            if not ap.ok:
                self.signals.fail.emit(ap.message)
                return

            # 3) Persistir CSV y blend corregidos como archivos canónicos.
            persisted_csv = persist_corrected_csv(
                out_dir=self.out_dir,
                base_labeled_csv=self.labeled_csv,
                corrected_csv=ed.corrected_csv,
                log=lambda s: self.signals.log.emit(str(s)),
                create_backup=False,
            )

            if ap.corrected_blend and Path(ap.corrected_blend).exists():
                shutil.copy2(ap.corrected_blend, self.labeled_blend)

            for tmp in (ed.corrected_csv, ap.corrected_blend):
                try:
                    if tmp and Path(tmp).exists():
                        Path(tmp).unlink()
                except Exception:
                    pass

            cleanup_legacy_output_clutter(self.out_dir)

            self.signals.done.emit({
                "corrected_csv": str(persisted_csv),
                "corrected_blend": str(self.labeled_blend),
            })

        except Exception as e:
            self.signals.fail.emit(str(e))


class LabelCorrectionPage(QWidget):
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.threadpool = QThreadPool.globalInstance()
        self._payload_ok = None
        self._last_args = None

        self._build_ui()

    def _build_ui(self):
        # Responsive layout strategy:
        # - Fixed header (title/subtitle)
        # - Scrollable middle content so it adapts to small windows
        # - Fixed footer (buttons)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setSpacing(12)

        title = QLabel("Manual label correction")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")

        subtitle = QLabel(
            "1) Interactive editor will open to correct labels.\n"
            "2) Then Blender will apply those changes to the labeled .blend.\n"
            "3) The canonical detections_labeled.csv and labeled .blend will be updated."
        )
        subtitle.setProperty("role", "subtitle")
        subtitle.setWordWrap(True)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)

        # ---- Scrollable body ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(10)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        # Evitar mínimos grandes: el scroll gestiona el overflow.
        self.log_box.setMinimumHeight(160)

        self.status = QLabel("")
        self.status.setWordWrap(True)

        # Footer
        bottom = QHBoxLayout()
        bottom.addStretch(1)

        self.btn_retry = QPushButton("Retry")
        self.btn_retry.setFixedHeight(40)
        self.btn_retry.setEnabled(False)
        self.btn_retry.clicked.connect(self._retry)

        self.btn_continue = QPushButton("Continue")
        self.btn_continue.setFixedHeight(40)
        self.btn_continue.setFixedWidth(160)
        self.btn_continue.setEnabled(False)
        self.btn_continue.clicked.connect(self._continue)

        bottom.addWidget(self.btn_retry)
        bottom.addWidget(self.btn_continue)

        # Compose
        outer.addWidget(title)
        outer.addWidget(subtitle)
        outer.addWidget(line)

        body_layout.addWidget(self.progress)
        body_layout.addWidget(QLabel("Log:"))
        body_layout.addWidget(self.log_box)
        body_layout.addWidget(self.status)
        body_layout.addStretch(1)

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        outer.addLayout(bottom)

    def start(self, settings: dict, out_dir: str, labeled_csv: str, labeled_blend: str, mesh_path: str):
        self._payload_ok = None
        self._last_args = (settings, out_dir, labeled_csv, labeled_blend, mesh_path)
        cleanup_legacy_output_clutter(Path(out_dir))

        self.progress.setRange(0, 0)
        self.log_box.clear()
        self.status.setText("Preparing editor...")
        self.btn_retry.setEnabled(False)
        self.btn_continue.setEnabled(False)

        worker = _Worker(
            settings=settings,
            out_dir=Path(out_dir),
            labeled_csv=Path(labeled_csv),
            labeled_blend=Path(labeled_blend),
            mesh_path=Path(mesh_path),
        )
        worker.signals.log.connect(self._log)
        worker.signals.done.connect(self._done)
        worker.signals.fail.connect(self._fail)
        self.threadpool.start(worker)

    def _log(self, s: str):
        self.log_box.append(s)

    def _done(self, payload: dict):
        self._payload_ok = payload
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.status.setStyleSheet("color:#1b5e20; font-weight:600;")
        self.status.setText(
            "✅ Correction applied.\n"
            f"Corrected CSV: {payload.get('corrected_csv')}\n"
            f"Corrected Blend: {payload.get('corrected_blend')}\n"
            "You can press 'Retry' to edit again."
        )

        self.btn_continue.setEnabled(True)

        # IMPORTANTE: permitir re-editar tras éxito
        self.btn_retry.setEnabled(True)

        # IMPORTANTE: el reintento debe partir del .blend corregido (si existe)
        if self._last_args:
            settings, out_dir, labeled_csv, labeled_blend, mesh_path = self._last_args
            new_blend = payload.get("corrected_blend") or labeled_blend
            self._last_args = (settings, out_dir, labeled_csv, new_blend, mesh_path)

    def _fail(self, msg: str):
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status.setStyleSheet("color:#b00020; font-weight:600;")
        self.status.setText("❌ Correction error.\n" + msg)
        self.btn_retry.setEnabled(True)
        self.failed.emit(msg)

    def _retry(self):
        if not self._last_args:
            return
        self.start(*self._last_args)

    def _continue(self):
        if self._payload_ok is None:
            return
        self.completed.emit(self._payload_ok)
