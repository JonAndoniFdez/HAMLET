from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QProgressBar,
    QPushButton, QHBoxLayout, QTextEdit, QScrollArea
)

from ...core.blender_scripts import blender_script_path
from ...core.paths import resolve_blender_exe
from ...core.output_cleanup import threshold_preview_dir
from ...core.settings import load_settings
from ...core.blender_runner import (
    build_blender_cmd, run_blender_rebake_stream, expected_outputs
)


def _safe_emit(signal, *args):
    try:
        signal.emit(*args)
    except RuntimeError:
        # El objeto Qt origen de la señal ya no existe.
        pass


class _WorkerSignals(QObject):
    log = Signal(str)
    done = Signal(dict)
    fail = Signal(str)


class _BlenderWorker(QRunnable):
    def __init__(self, cmd: list[str], obj_in: Path, outdir: Path, payload_factory=None):
        super().__init__()
        self.cmd = cmd
        self.obj_in = obj_in
        self.outdir = outdir
        self.payload_factory = payload_factory
        self.signals = _WorkerSignals()

    def run(self):
        try:
            proc = run_blender_rebake_stream(self.cmd)
            assert proc.stdout is not None

            for line in proc.stdout:
                if line:
                    _safe_emit(self.signals.log, line.rstrip("\n"))

            rc = proc.wait()
            out_obj, out_png = expected_outputs(self.obj_in, self.outdir)

            if rc != 0:
                _safe_emit(self.signals.fail, f"Blender finished with error (returncode={rc}).")
                return

            if not out_obj.exists():
                _safe_emit(self.signals.fail, f"Expected output OBJ not found: {out_obj}")
                return

            if not out_png.exists():
                _safe_emit(self.signals.fail, f"Expected baked texture not found: {out_png}")
                return

            if self.payload_factory is not None:
                payload = self.payload_factory(out_obj, out_png, self.outdir)
            else:
                payload = {
                    "blender_outdir": str(self.outdir),
                    "uv_obj_path": str(out_obj),
                    "rebaked_texture_path": str(out_png),
                    "threshold_texture_path": str(out_png),
                    "work_obj_path": str(out_obj),
                    "work_texture_path": str(out_png),
                    "uv_rebake_skipped": False,
                }

            _safe_emit(self.signals.done, payload)

        except Exception as e:
            _safe_emit(self.signals.fail, str(e))


class BlenderUvPage(QWidget):
    """
    Screen 3:
      1) Ask user whether to run UV rebake or skip it
      2) If yes -> run Blender
      3) If no  -> create compatible outputs by copying originals
    """
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.threadpool = QThreadPool.globalInstance()
        self._build_ui()
        self._payload_ok = None
        self._last_args = None
        self._worker = None
        self._is_closing = False

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setSpacing(14)

        title = QLabel("Preparing the model in Blender")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")

        subtitle = QLabel(
            "Choose whether you want to regenerate the UVs and rebake the texture in Blender.\n"
            "If you skip this step, the application will create compatible output files from the original model and texture."
        )
        subtitle.setProperty("role", "subtitle")
        subtitle.setWordWrap(True)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)

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

        self.status = QLabel("Select an option to continue.")
        self.status.setWordWrap(True)

        bottom = QHBoxLayout()
        bottom.addStretch(1)

        self.btn_retry = QPushButton("Retry")
        self.btn_retry.setFixedHeight(40)
        self.btn_retry.setEnabled(False)
        self.btn_retry.clicked.connect(self._retry)

        self.btn_run_uv = QPushButton("Run UV rebake")
        self.btn_run_uv.setFixedHeight(40)
        self.btn_run_uv.clicked.connect(self._run_uv_rebake)

        self.btn_skip_uv = QPushButton("Skip UV rebake")
        self.btn_skip_uv.setFixedHeight(40)
        self.btn_skip_uv.clicked.connect(self._skip_uv_rebake)

        self.btn_continue = QPushButton("Continue")
        self.btn_continue.setFixedHeight(40)
        self.btn_continue.setFixedWidth(160)
        self.btn_continue.setEnabled(False)
        self.btn_continue.clicked.connect(self._continue)

        bottom.addWidget(self.btn_retry)
        bottom.addWidget(self.btn_run_uv)
        bottom.addWidget(self.btn_skip_uv)
        bottom.addWidget(self.btn_continue)

        outer.addWidget(title)
        outer.addWidget(subtitle)
        outer.addWidget(line)

        body_layout.addWidget(self.progress)
        body_layout.addWidget(QLabel("Process log:"))
        body_layout.addWidget(self.log_box)
        body_layout.addWidget(self.status)
        body_layout.addStretch(1)

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        outer.addLayout(bottom)

    def closeEvent(self, event):
        self._is_closing = True
        super().closeEvent(event)

    def _create_passthrough_outputs(self, obj_path: str, outdir: str, texture_path: str) -> dict:
        """
        Preserve the original OBJ/texture without creating surrogate copies.

        Older versions copied the original model into *_UVB.obj and duplicated the
        texture as NewHandTexture.png. Those files are not needed when UV rebake
        is skipped because downstream pages can use the original paths directly.
        """
        obj_in = Path(obj_path).resolve()
        tex_in = Path(texture_path).resolve()
        out_dir = Path(outdir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        if not obj_in.exists():
            raise FileNotFoundError(f"Original OBJ not found: {obj_in}")
        if not tex_in.exists():
            raise FileNotFoundError(f"Original texture not found: {tex_in}")

        return {
            "blender_outdir": str(out_dir),
            "uv_obj_path": str(obj_in),
            "rebaked_texture_path": str(tex_in),
            "threshold_texture_path": str(tex_in),
            "work_obj_path": str(obj_in),
            "work_texture_path": str(tex_in),
            "uv_rebake_skipped": True,
            "preview_rebake_generated": False,
        }

    def start(
        self,
        obj_path: str,
        outdir: str,
        texture_path: str,
        size: int = 4096,
        margin: int = 16,
        uvb_name: str = "UVMap_2",
    ):
        """
        Called when entering this page.
        It no longer launches Blender automatically.
        """
        self._payload_ok = None
        self._last_args = (obj_path, outdir, texture_path, size, margin, uvb_name)

        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.log_box.clear()
        self.status.setStyleSheet("")
        self.status.setText(
            "Do you want to rebake the UVs in Blender?\n"
            "- Click 'Run UV rebake' to process the model in Blender.\n"
            "- Click 'Skip UV rebake' to preserve the original files and continue."
        )

        self.btn_continue.setEnabled(False)
        self.btn_retry.setEnabled(False)
        self.btn_run_uv.setEnabled(True)
        self.btn_skip_uv.setEnabled(True)

    def _run_uv_rebake(self):
        if not self._last_args:
            return

        obj_path, outdir, texture_path, size, margin, uvb_name = self._last_args

        self._payload_ok = None
        self.btn_continue.setEnabled(False)
        self.btn_retry.setEnabled(False)
        self.btn_run_uv.setEnabled(False)
        self.btn_skip_uv.setEnabled(False)
        self.progress.setRange(0, 0)
        self.log_box.clear()
        self.status.setStyleSheet("")
        self.status.setText("Running Blender...")

        s = load_settings() or {}
        blender_exe = resolve_blender_exe(s)

        if blender_exe is None:
            self._fail("Blender executable not found. Expected bundled path: <app>/blender/blender.exe")
            return

        rebake_script = blender_script_path("rebake_traced.py")
        if not rebake_script.exists():
            self._fail(f"Blender script not found: {rebake_script}")
            return

        obj_in = Path(obj_path)
        out_dir = Path(outdir)
        out_dir.mkdir(parents=True, exist_ok=True)

        cmd = build_blender_cmd(
            blender_exe=blender_exe,
            rebake_script=rebake_script,
            obj_in=obj_in,
            outdir=out_dir,
            size=size,
            margin=margin,
            uvb_name=uvb_name,
        )

        worker = _BlenderWorker(cmd, obj_in=obj_in, outdir=out_dir)
        self._worker = worker
        worker.signals.log.connect(self._append_log)
        worker.signals.done.connect(self._done)
        worker.signals.fail.connect(self._fail)
        self.threadpool.start(worker)

    def _skip_uv_rebake(self):
        if not self._last_args:
            return

        obj_path, outdir, texture_path, size, margin, uvb_name = self._last_args

        try:
            self.btn_run_uv.setEnabled(False)
            self.btn_skip_uv.setEnabled(False)
            self.btn_retry.setEnabled(False)
            self.btn_continue.setEnabled(False)

            self.progress.setRange(0, 0)
            self.log_box.clear()
            self.status.setStyleSheet("")
            self.status.setText(
                "Keeping the original files for the pipeline and trying to generate an auxiliary rebaked texture for threshold selection..."
            )

            payload_base = self._create_passthrough_outputs(
                obj_path=obj_path,
                outdir=outdir,
                texture_path=texture_path,
            )
            self.log_box.append("[INFO] UV rebake skipped by user for the main pipeline.")
            self.log_box.append(f"[INFO] Working OBJ preserved from original: {payload_base['uv_obj_path']}")
            self.log_box.append(f"[INFO] Working texture preserved from original: {payload_base['rebaked_texture_path']}")
            self.log_box.append("[INFO] No passthrough OBJ/texture copies were generated in the output folder.")

            s = load_settings() or {}
            blender_exe = resolve_blender_exe(s)

            rebake_script = blender_script_path("rebake_traced.py")

            if blender_exe is None or not rebake_script.exists():
                reason = (
                    "Blender executable not found. Expected bundled path: <app>/blender/blender.exe"
                    if blender_exe is None
                    else f"Blender script not found: {rebake_script}"
                )
                self._finish_skip_without_preview(payload_base, reason)
                return

            preview_out_dir = threshold_preview_dir(Path(outdir).resolve())
            preview_out_dir.mkdir(parents=True, exist_ok=True)
            obj_in = Path(obj_path).resolve()

            cmd = build_blender_cmd(
                blender_exe=blender_exe,
                rebake_script=rebake_script,
                obj_in=obj_in,
                outdir=preview_out_dir,
                size=size,
                margin=margin,
                uvb_name=uvb_name,
            )

            def _payload_factory(_out_obj, out_png, _preview_dir):
                payload = dict(payload_base)
                payload.update({
                    "threshold_texture_path": str(out_png),
                    "preview_rebake_generated": True,
                    "preview_rebake_outdir": str(preview_out_dir),
                })
                return payload

            worker = _BlenderWorker(
                cmd,
                obj_in=obj_in,
                outdir=preview_out_dir,
                payload_factory=_payload_factory,
            )
            self._worker = worker
            worker.signals.log.connect(self._append_log)
            worker.signals.done.connect(self._done)
            worker.signals.fail.connect(lambda msg, base=payload_base: self._finish_skip_without_preview(base, msg))
            self.threadpool.start(worker)

        except Exception as e:
            self._fail(f"Could not skip UV rebake safely:\n{e}")

    def _finish_skip_without_preview(self, payload: dict, reason: str | None = None):
        fallback = dict(payload)
        fallback["preview_rebake_generated"] = False
        fallback["threshold_texture_path"] = fallback.get("rebaked_texture_path")

        if reason:
            self.log_box.append(f"[WARN] Auxiliary threshold preview not generated: {reason}")

        self._done(fallback)

    def _append_log(self, line: str):
        if self._is_closing:
            return
        try:
            self.log_box.append(line)
        except RuntimeError:
            pass

    def _done(self, payload: dict):
        self._worker = None
        if self._is_closing:
            return

        self._payload_ok = payload
        self.progress.setRange(0, 1)
        self.progress.setValue(1)

        if payload.get("uv_rebake_skipped"):
            self.status.setStyleSheet("color: #8a5a00; font-weight: 600;")
            if payload.get("preview_rebake_generated"):
                self.status.setText(
                    "⚠ UV rebake skipped for the main pipeline.\n"
                    "Original files were preserved for the workflow, and an auxiliary rebaked texture was generated for threshold selection.\n"
                    "You can continue."
                )
                self.log_box.append(f"[INFO] Threshold preview texture: {payload.get('threshold_texture_path')}")
            else:
                self.status.setText(
                    "⚠ UV rebake skipped.\n"
                    "Original files were preserved for the workflow. The threshold page will use the preserved texture because the auxiliary rebaked preview could not be generated.\n"
                    "You can continue."
                )
        else:
            self.status.setStyleSheet("color: #1b5e20; font-weight: 600;")
            self.status.setText("✅ Process completed. You can continue.")

        self.btn_continue.setEnabled(True)
        self.btn_run_uv.setEnabled(False)
        self.btn_skip_uv.setEnabled(False)

    def _fail(self, msg: str):
        self._worker = None
        if self._is_closing:
            return

        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status.setStyleSheet("color: #b00020; font-weight: 600;")
        self.status.setText("❌ Error in Blender process.\n" + msg)
        self.btn_retry.setEnabled(True)
        self.btn_run_uv.setEnabled(False)
        self.btn_skip_uv.setEnabled(False)

        try:
            self.failed.emit(msg)
        except RuntimeError:
            pass

    def _retry(self):
        if not self._last_args:
            return

        self._payload_ok = None
        self._worker = None

        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.log_box.clear()
        self.status.setStyleSheet("")
        self.status.setText(
            "Do you want to rebake the UVs in Blender?\n"
            "- Click 'Run UV rebake' to process the model in Blender.\n"
            "- Click 'Skip UV rebake' to preserve the original files and continue."
        )
        self.btn_retry.setEnabled(False)
        self.btn_continue.setEnabled(False)
        self.btn_run_uv.setEnabled(True)
        self.btn_skip_uv.setEnabled(True)

    def _continue(self):
        if self._payload_ok is None:
            return
        try:
            self.completed.emit(self._payload_ok)
        except RuntimeError:
            pass
