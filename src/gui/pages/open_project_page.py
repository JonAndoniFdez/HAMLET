from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QLineEdit,
    QMessageBox,
)

from ...core.open_project import inspect_output_project, OpenProjectState


class OpenProjectPage(QWidget):
    open_markers_requested = Signal(dict)
    open_labels_requested = Signal(dict)
    open_measures_requested = Signal(dict)
    back_clicked = Signal()

    def __init__(self):
        super().__init__()
        self._state: OpenProjectState | None = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setSpacing(12)

        title = QLabel("Open project")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")

        subtitle = QLabel(
            "Select the output folder of a previous project. "
            "The application will inspect the files already generated and will let you reopen the desired part of the flow."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("role", "subtitle")

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)

        picker = QHBoxLayout()
        picker.addWidget(QLabel("Output folder:"))

        self.txt_folder = QLineEdit()
        self.txt_folder.setReadOnly(True)

        self.btn_browse = QPushButton("Browse…")
        self.btn_browse.clicked.connect(self._browse)

        picker.addWidget(self.txt_folder, 1)
        picker.addWidget(self.btn_browse)

        self.lbl_status = QLabel("Choose a project folder to continue.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._set_neutral_status("Choose a project folder to continue.")

        self.btn_markers = QPushButton("Modify markers / detections (2D + 3D view)")
        self.btn_markers.setFixedHeight(44)
        self.btn_markers.clicked.connect(self._emit_markers)

        self.btn_labels = QPushButton("Modify labels manually")
        self.btn_labels.setFixedHeight(44)
        self.btn_labels.clicked.connect(self._emit_labels)

        self.btn_measures = QPushButton("Modify measures to obtain")
        self.btn_measures.setFixedHeight(44)
        self.btn_measures.clicked.connect(self._emit_measures)

        for b in (self.btn_markers, self.btn_labels, self.btn_measures):
            b.setEnabled(False)

        outer.addWidget(title)
        outer.addWidget(subtitle)
        outer.addWidget(line)
        outer.addLayout(picker)
        outer.addWidget(self.lbl_status)
        outer.addSpacing(8)
        outer.addWidget(self.btn_markers)
        outer.addWidget(self.btn_labels)
        outer.addWidget(self.btn_measures)
        outer.addStretch(1)

        bottom = QHBoxLayout()
        self.btn_back = QPushButton("Back")
        self.btn_back.setFixedHeight(40)
        self.btn_back.setFixedWidth(120)
        self.btn_back.clicked.connect(self.back_clicked.emit)
        bottom.addWidget(self.btn_back)
        bottom.addStretch(1)
        outer.addLayout(bottom)

    def _browse(self):
        start_dir = str(Path.home())
        if self.txt_folder.text().strip():
            start_dir = self.txt_folder.text().strip()

        folder = QFileDialog.getExistingDirectory(self, "Select output folder", start_dir)
        if not folder:
            return

        self.load_project(folder)

    def load_project(self, folder: str | Path):
        self._state = inspect_output_project(folder)
        self.txt_folder.setText(str(self._state.out_dir))

        is_compatible = self._state.is_compatible
        self.btn_markers.setEnabled(is_compatible and self._state.can_edit_markers)
        self.btn_labels.setEnabled(is_compatible and self._state.can_edit_labels)
        self.btn_measures.setEnabled(is_compatible and self._state.can_edit_measures)

        self._update_action_tooltips()

        if not is_compatible:
            self._set_error_status(self._build_invalid_project_message())
            return

        available_actions = self._state.available_actions
        self._set_ok_status(
            "Project loaded successfully. Compatible actions: "
            + ", ".join(available_actions)
            + "."
        )

    def _build_invalid_project_message(self) -> str:
        if self._state is None:
            return "Invalid output folder."

        lines = [
            "Invalid output folder. The selected folder is not compatible with the current workflow.",
        ]

        if self._state.missing_required:
            lines.append("Main issue: " + " ".join(self._state.missing_required))

        details = []
        for title, key in (
            ("Markers/detections", "markers"),
            ("Manual labels", "labels"),
            ("Measures", "measures"),
        ):
            errors = self._state.stage_errors.get(key, [])
            if errors:
                details.append(f"• {title}: " + "; ".join(errors[:4]))

        if details:
            lines.append("Missing requirements by action:")
            lines.extend(details)

        return "\n".join(lines)

    def _update_action_tooltips(self):
        if self._state is None:
            return
        mapping = [
            (self.btn_markers, "markers"),
            (self.btn_labels, "labels"),
            (self.btn_measures, "measures"),
        ]
        for btn, key in mapping:
            errors = self._state.stage_errors.get(key, [])
            if errors:
                btn.setToolTip("This action is unavailable because: " + "; ".join(errors))
            else:
                btn.setToolTip("This action is available for the selected project.")

    def _payload(self) -> dict | None:
        if self._state is None:
            QMessageBox.information(
                self,
                "No project loaded",
                "Please select an output folder first.",
            )
            return None

        if not self._state.is_compatible:
            QMessageBox.warning(
                self,
                "Invalid project",
                "The selected folder is not compatible with the current workflow.",
            )
            return None

        return {
            "out_dir": str(self._state.out_dir),
            "results_dir": str(self._state.results_dir) if self._state.results_dir else None,
            "texture_path": str(self._state.texture_path) if self._state.texture_path else None,
            "obj_path": str(self._state.obj_path) if self._state.obj_path else None,
            "hand_with_points_obj": str(self._state.hand_with_points_obj) if self._state.hand_with_points_obj else None,
            "target_json": str(self._state.target_json) if self._state.target_json else None,
            "measurement_mode": self._state.measurement_mode,
            "csv_2d": str(self._state.csv_2d) if self._state.csv_2d else None,
            "csv_3d": str(self._state.csv_3d) if self._state.csv_3d else None,
            "labeled_csv": str(self._state.labeled_csv) if self._state.labeled_csv else None,
            "labeled_blend": str(self._state.labeled_blend) if self._state.labeled_blend else None,
            "selected_ops_csv": str(self._state.selected_ops_csv) if self._state.selected_ops_csv else None,
        }

    def _emit_markers(self):
        payload = self._payload()
        if not payload:
            return

        if not self._state or not self._state.can_edit_markers:
            QMessageBox.warning(
                self,
                "Incomplete project",
                "This project does not contain the files needed to reopen the marker editing step.",
            )
            return

        self.open_markers_requested.emit(payload)

    def _emit_labels(self):
        payload = self._payload()
        if not payload:
            return

        if not self._state or not self._state.can_edit_labels:
            QMessageBox.warning(
                self,
                "Incomplete project",
                "This project does not contain the files needed to reopen manual label correction.",
            )
            return

        self.open_labels_requested.emit(payload)

    def _emit_measures(self):
        payload = self._payload()
        if not payload:
            return

        if not self._state or not self._state.can_edit_measures:
            QMessageBox.warning(
                self,
                "Incomplete project",
                "This project does not contain the files needed to reopen the measures step.",
            )
            return

        self.open_measures_requested.emit(payload)

    def _set_ok_status(self, text: str):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet("""
            QLabel {
                color: #9be39b;
                background-color: rgba(40, 120, 40, 0.18);
                border: 1px solid rgba(100, 200, 100, 0.45);
                border-radius: 8px;
                padding: 10px 12px;
                font-weight: 600;
            }
        """)

    def _set_error_status(self, text: str):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet("""
            QLabel {
                color: #ff9b9b;
                background-color: rgba(140, 40, 40, 0.18);
                border: 1px solid rgba(220, 90, 90, 0.45);
                border-radius: 8px;
                padding: 10px 12px;
                font-weight: 600;
            }
        """)

    def _set_neutral_status(self, text: str):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet("""
            QLabel {
                color: #d8d8d8;
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
                padding: 10px 12px;
                font-weight: 500;
            }
        """)
