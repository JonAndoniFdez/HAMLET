from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QProgressBar,
    QPushButton, QHBoxLayout, QTextEdit, QScrollArea
)

from ...core.label_points import label_points_from_template


class _Signals(QObject):
    log = Signal(str)
    done = Signal(dict)
    fail = Signal(str)


class _Worker(QRunnable):
    def __init__(self, settings: dict, blend_path: Path, out_dir: Path):
        super().__init__()
        self.settings = settings
        self.blend_path = blend_path
        self.out_dir = out_dir
        self.signals = _Signals()

    def run(self):
        try:
            res = label_points_from_template(
                settings=self.settings,
                blend_path=self.blend_path,
                out_dir=self.out_dir,
                marker_prefix="Sphere_",
                max_dist=None,
                save_blend=True,
                log=lambda s: self.signals.log.emit(str(s)),
            )
            if not res.ok:
                self.signals.fail.emit(res.message + ("\n" + res.stderr if res.stderr else ""))
                return

            self.signals.done.emit({
                "labeled_csv": str(res.out_csv) if res.out_csv else None,
                "labeled_blend": str(res.out_blend) if res.out_blend else None,
            })
        except Exception as e:
            self.signals.fail.emit(str(e))


class LabelPointsPage(QWidget):
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.threadpool = QThreadPool.globalInstance()

        self._last_args = None
        self._payload_ok = None
        self._settings = None

        self._build_ui()

    def _build_ui(self):
        # Responsive layout:
        # - Fixed header
        # - Scrollable middle (log)
        # - Fixed footer (buttons)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setSpacing(12)

        title = QLabel("Automatic point labeling (Blender + template)")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")

        subtitle = QLabel(
            "The .blend of the rig (armature + spheres) will be opened and labels will be assigned "
            "using markers_template.csv with the Blender script."
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
        self.log_box.setMinimumHeight(160)

        self.status = QLabel("")
        self.status.setWordWrap(True)

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

    def start(self, settings: dict, blend_path: str, out_dir: str):
        self._payload_ok = None
        self._settings = settings
        self._last_args = (settings, blend_path, out_dir)

        self.progress.setRange(0, 0)
        self.log_box.clear()
        self.status.setText("Labeling…")
        self.btn_retry.setEnabled(False)
        self.btn_continue.setEnabled(False)

        worker = _Worker(settings, Path(blend_path), Path(out_dir))
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
            "✅ Labeling completed.\n"
            f"CSV: {payload.get('labeled_csv')}\n"
            f"Blend: {payload.get('labeled_blend')}"
        )
        self.btn_continue.setEnabled(True)

    def _fail(self, msg: str):
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status.setStyleSheet("color:#b00020; font-weight:600;")
        self.status.setText("❌ Error labeling.\n" + msg)
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
