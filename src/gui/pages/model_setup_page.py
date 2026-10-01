from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QLineEdit, QPushButton,
    QFileDialog, QFrame, QScrollArea, QMessageBox
)


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"]

def _auto_find_texture_for_obj(obj_path: Path) -> Path | None:
    """
    Searches in the same folder as the .obj for a texture with the same base name.
    Ex: hand.obj -> hand.png / hand.bmp / hand.jpg / hand.jpeg
    """
    base = obj_path.stem
    folder = obj_path.parent

    candidates = [
        folder / f"{base}.png",
        folder / f"{base}.bmp",
        folder / f"{base}.jpg",
        folder / f"{base}.jpeg",
    ]

    for c in candidates:
        if c.exists() and c.is_file():
            return c

    return None


def _measurement_mode_label(mode: str) -> str:
    return "Flat hand procedure"


def _folder_has_content(path: Path) -> bool:
    try:
        return path.exists() and path.is_dir() and any(path.iterdir())
    except Exception:
        return False


_DATED_INSTANCE_RE = re.compile(r"^(?P<base>.+)_(?P<date>\d{8})_(?P<index>\d{2})$")


def _base_output_path(path: Path) -> Path:
    match = _DATED_INSTANCE_RE.match(path.name)
    if not match:
        return path
    return path.with_name(match.group("base"))


def _next_dated_output_instance(path: Path) -> Path:
    """Return a sibling output folder with a date and per-day instance suffix."""
    date_part = datetime.now().strftime("%Y%m%d")
    match = _DATED_INSTANCE_RE.match(path.name)
    if match and match.group("date") == date_part and not _folder_has_content(path):
        return path

    base_path = _base_output_path(path)
    parent = base_path.parent
    stem = base_path.name

    index = 1
    while True:
        candidate = parent / f"{stem}_{date_part}_{index:02d}"
        if not candidate.exists():
            return candidate
        index += 1


def _existing_output_dirs(parent: Path, prefix: str = "_output") -> list[Path]:
    try:
        if not parent.exists() or not parent.is_dir():
            return []
        return sorted(
            p for p in parent.iterdir()
            if p.is_dir() and p.name.startswith(prefix)
        )
    except Exception:
        return []


class ModelSetupPage(QWidget):
    """
    Screen 2:
      - Selection of .obj
      - Selection of texture
      - Validation and enable "Next"
    """
    next_clicked = Signal(dict)  # we emit a dict with the paths
    back_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.obj_path: Path | None = None
        self.tex_path: Path | None = None
        self.out_dir: Path | None = None
        self.measurement_mode = "flat_hand"
        self._warned_output_base: Path | None = None

        self._build_ui()
        self._set_default_outdir()
        self._update_state()

    def _build_ui(self):
        # Responsive layout:
        # - Fixed header (title/subtitle)
        # - Scrollable body (form fields) so the footer stays visible
        # - Fixed footer (Next)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setSpacing(16)

        title = QLabel("Input Data")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")

        subtitle = QLabel(
            "Select the 3D model file (.obj) of the hand and its texture.\n"
            "When both are valid, you can continue."
        )
        subtitle.setProperty("role", "subtitle")
        subtitle.setWordWrap(True)

        self.mode_label = QLabel("")
        self.mode_label.setProperty("role", "muted")
        self.mode_label.setStyleSheet("font-weight: 600;")
        self._update_mode_label()

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)

        # --- OBJ ---
        obj_label = QLabel("3D Model (.obj)")
        obj_label.setStyleSheet("font-weight: 600;")

        obj_row = QHBoxLayout()
        self.obj_edit = QLineEdit()
        self.obj_edit.setPlaceholderText("Select the .obj file…")
        self.obj_edit.setReadOnly(True)

        self.obj_btn = QPushButton("Browse…")
        self.obj_btn.clicked.connect(self._browse_obj)

        obj_row.addWidget(self.obj_edit, 1)
        obj_row.addWidget(self.obj_btn)

        # --- Textura ---
        tex_label = QLabel("Texture (png/jpg/...)")
        tex_label.setStyleSheet("font-weight: 600;")

        tex_row = QHBoxLayout()
        self.tex_edit = QLineEdit()
        self.tex_edit.setPlaceholderText("Select the texture…")
        self.tex_edit.setReadOnly(True)

        self.tex_btn = QPushButton("Browse…")
        self.tex_btn.clicked.connect(self._browse_texture)

        tex_row.addWidget(self.tex_edit, 1)
        tex_row.addWidget(self.tex_btn)

        # --- Estado / validación ---
        self.status = QLabel("")
        self.status.setWordWrap(True)

        # ---- Scrollable body ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(12)

        body_layout.addWidget(obj_label)
        body_layout.addLayout(obj_row)

        body_layout.addWidget(tex_label)
        body_layout.addLayout(tex_row)

        # --- Output dir ---
        out_label = QLabel("Output folder")
        out_label.setStyleSheet("font-weight: 600;")

        out_row = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Select the folder where results will be saved…")
        self.out_edit.setReadOnly(True)

        self.out_btn = QPushButton("Choose…")
        self.out_btn.clicked.connect(self._browse_outdir)

        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(self.out_btn)

        body_layout.addWidget(out_label)
        body_layout.addLayout(out_row)
        body_layout.addWidget(self.status)
        body_layout.addStretch(1)

        # --- Botonera ---
        bottom = QHBoxLayout()

        self.btn_back = QPushButton("Back")
        self.btn_back.setFixedHeight(40)
        self.btn_back.setFixedWidth(120)
        self.btn_back.clicked.connect(self.back_clicked.emit)

        bottom.addWidget(self.btn_back)
        bottom.addStretch(1)

        self.btn_next = QPushButton("Next")
        self.btn_next.setEnabled(False)  # enabled by default 
        self.btn_next.setFixedHeight(40)
        self.btn_next.setFixedWidth(160)
        self.btn_next.clicked.connect(self._emit_next)

        bottom.addWidget(self.btn_next)
        outer.addWidget(title)
        outer.addWidget(subtitle)
        outer.addWidget(self.mode_label)
        outer.addWidget(line)

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        outer.addLayout(bottom)

    def set_measurement_mode(self, mode: str):
        self.measurement_mode = "flat_hand"
        self._update_mode_label()

    def _update_mode_label(self):
        if not hasattr(self, "mode_label"):
            return
        self.mode_label.setText(f"Selected procedure: {_measurement_mode_label(self.measurement_mode)}")

    def _browse_obj(self):
        start_dir = str(self.obj_path.parent) if self.obj_path else str(Path.home())
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select the .obj model",
            start_dir,
            "Wavefront OBJ (*.obj);;All (*.*)"
        )
        if not file_path:
            return

        p = Path(file_path)
        self.obj_path = p
        self.obj_edit.setText(str(p))

        # --- Auto-detection of texture ---
        auto_tex = _auto_find_texture_for_obj(p)
        if auto_tex is not None:
            self.tex_path = auto_tex
            self.tex_edit.setText(str(auto_tex))
        # If not found, we do not erase if the user had already chosen one manually.
        # But if you prefer to force emptying it, tell me and we'll change it.

        self._set_default_outdir()
        self._update_state()        

    def _browse_outdir(self):
        start_dir = str(_base_output_path(self.out_dir)) if self.out_dir else str(Path.home())
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select the output folder",
            start_dir
        )
        if not folder:
            return

        p = Path(folder)
        self._set_output_dir_preview(p)
        self._update_state()

    def _browse_texture(self):
        start_dir = str(self.tex_path.parent) if self.tex_path else str(Path.home())
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select the texture",
            start_dir,
            "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp);;All (*.*)"
        )
        if not file_path:
            return

        p = Path(file_path)
        self.tex_path = p
        self.tex_edit.setText(str(p))
        self._update_state()

    def _set_default_outdir(self):                  
        """
        By default: folder next to the OBJ (if it exists), otherwise None.
        """
        if self.obj_path is not None and self.obj_path.exists():
            default_dir = self.obj_path.parent / "_output"
            self._set_output_dir_preview(default_dir)
            self._warn_if_hand_was_processed(default_dir, self.out_dir)

    def _set_output_dir_preview(self, base_dir: Path):
        preview_dir = _next_dated_output_instance(base_dir)
        self.out_dir = preview_dir
        self.out_edit.setText(str(preview_dir))

    def _warn_if_hand_was_processed(self, base_dir: Path, new_out_dir: Path | None):
        existing = _existing_output_dirs(base_dir.parent, prefix=base_dir.name)
        if not existing or new_out_dir is None:
            return

        try:
            self._warned_output_base = base_dir.resolve()
        except Exception:
            self._warned_output_base = base_dir

        shown = "\n".join(f"• {p.name}" for p in existing[:5])
        if len(existing) > 5:
            shown += f"\n• ... and {len(existing) - 5} more"

        QMessageBox.warning(
            self,
            "Previous output detected",
            "This hand appears to have already been processed because output folders were found next to the selected OBJ:\n\n"
            f"{shown}\n\n"
            "The new project will be saved in:\n"
            f"{new_out_dir}",
        )

    def _update_state(self):
        errors = []

        if self.obj_path is None:
            errors.append("• Missing selection of the .obj file.")
        else:
            if not self.obj_path.exists():
                errors.append("• The selected .obj does not exist.")
            elif self.obj_path.suffix.lower() != ".obj":
                errors.append("• The model file must be .obj.")

        if self.tex_path is None:
            errors.append("• Missing selection of the texture.")
        else:
            if not self.tex_path.exists():
                errors.append("• The selected texture does not exist.")
            elif not _is_image(self.tex_path):
                errors.append("• The texture must be an image (png/jpg/tif…).")

        if self.out_dir is None:
            errors.append("• Missing selection of the output folder.")
        else:
            # we do not require it to exist; if it does not exist we will create it later
            if self.out_dir.exists() and not self.out_dir.is_dir():
                errors.append("• The output path is not a valid folder.")

        if errors:
            self.btn_next.setEnabled(False)
            self.status.setText("❌ Incomplete configuration:\n" + "\n".join(errors))
            self.status.setStyleSheet("color: #b00020; font-weight: 600;")
        else:
            self.btn_next.setEnabled(True)
            self.status.setText("✅ Correct configuration. You can continue.")
            self.status.setStyleSheet("color: #1b5e20; font-weight: 600;")

    def _emit_next(self):
        out_dir = self.out_dir
        if out_dir is not None:
            selected_out_dir = out_dir
            new_out_dir = _next_dated_output_instance(selected_out_dir)
            base_out_dir = _base_output_path(selected_out_dir)
            has_existing_content = (
                _folder_has_content(selected_out_dir)
                or _folder_has_content(base_out_dir)
            )
            try:
                already_warned = self._warned_output_base == base_out_dir.resolve()
            except Exception:
                already_warned = self._warned_output_base == base_out_dir
            out_dir = new_out_dir
            self.out_dir = new_out_dir
            self.out_edit.setText(str(new_out_dir))

            if has_existing_content and not already_warned:
                QMessageBox.warning(
                    self,
                    "Output folder already exists",
                    "The selected output folder already contains files from a previous project or run.\n\n"
                    "To avoid overwriting existing data, a new dated output folder will be used:\n"
                    f"{new_out_dir}",
                )

        payload = {
            "obj_path": str(self.obj_path),
            "texture_path": str(self.tex_path),
            "out_dir": str(out_dir),
            "measurement_mode": "flat_hand",
        }
        self.next_clicked.emit(payload)
