from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout, QPushButton,
    QFileDialog, QLineEdit, QScrollArea, QGroupBox, QGridLayout, QCheckBox,
    QDialog, QFormLayout, QDialogButtonBox, QComboBox, QMessageBox, QCompleter
)


from ...core.measure_ops import (
    OP_COLUMNS,
    OP_DIMENSION_COL,
    OP_FINGER_COL,
    OP_MARKER_1_COL,
    OP_MARKER_2_COL,
    OP_TYPE_COL,
    drop_invalid_marker_ops,
    normalize_ops_columns,
)
from ...core.paths import asset_path
from ...core.output_cleanup import detections_labeled_csv, selected_ops_csv


@dataclass(frozen=True)
class _OpRow:
    tipo: str
    finger: str
    dim: str
    m1: str
    m2: str


class MeasuresSelectorPage(QWidget):
    """Step 9: Select which measures (operations) will be computed."""

    completed = Signal(dict)
    failed = Signal(str)
    back_clicked = Signal()

    def __init__(self):
        super().__init__()
        self._out_dir: Path | None = None
        self._ops_csv_path: Path | None = None

        # UI state
        self._checkbox_by_row: dict[_OpRow, QCheckBox] = {}
        self._rows_in_order: list[_OpRow] = []
        self._extras_rows: list[_OpRow] = []
        self._custom_rows: list[_OpRow] = []
        self._extras_box: QGroupBox | None = None

        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setSpacing(12)

        title = QLabel("Measures selector")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")

        subtitle = QLabel(
            "Choose which measures will be computed in the next step.\n"
            "The initial list is loaded from LandmarksOperations_data.csv."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("role", "subtitle")

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)

        # --- CSV picker ---
        picker = QHBoxLayout()
        picker.addWidget(QLabel("Measures CSV:"))
        self.txt_csv = QLineEdit()
        self.txt_csv.setReadOnly(True)
        self.btn_browse = QPushButton("Browse")
        self.btn_browse.clicked.connect(self._browse)
        picker.addWidget(self.txt_csv, 1)
        picker.addWidget(self.btn_browse)

        # --- Quick toggles ---
        toggles = QHBoxLayout()
        self.btn_all = QPushButton("Select all")
        self.btn_none = QPushButton("Select none")
        self.btn_all.clicked.connect(lambda: self._set_all(True))
        self.btn_none.clicked.connect(lambda: self._set_all(False))
        toggles.addWidget(self.btn_all)
        toggles.addWidget(self.btn_none)
        toggles.addStretch(1)

        # --- Scrollable body ---
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(12)
        self.scroll.setWidget(self.body)
        self._bottom_anchor = QWidget()
        self._bottom_anchor.setFixedHeight(1)
        self.body_layout.addWidget(self._bottom_anchor)
        self.body_layout.addStretch(1)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)

        # --- Bottom ---
        bottom = QHBoxLayout()
        self.btn_back = QPushButton("Back")
        self.btn_back.setFixedHeight(40)
        self.btn_back.setFixedWidth(120)
        self.btn_back.clicked.connect(self.back_clicked.emit)
        bottom.addWidget(self.btn_back)
        bottom.addStretch(1)
        
        self.btn_new_custom = QPushButton("New Custom Measure")
        self.btn_new_custom.setFixedHeight(40)
        self.btn_new_custom.clicked.connect(self._open_new_custom_dialog)
        bottom.addWidget(self.btn_new_custom)
        
        self.btn_continue = QPushButton("Continue")
        self.btn_continue.setFixedHeight(40)
        self.btn_continue.setFixedWidth(160)
        self.btn_continue.setEnabled(False)
        self.btn_continue.clicked.connect(self._continue)
        bottom.addWidget(self.btn_continue)

                
        outer.addWidget(title)
        outer.addWidget(subtitle)
        outer.addWidget(line)
        outer.addLayout(picker)
        outer.addLayout(toggles)
        outer.addWidget(self.scroll, 1)
        outer.addWidget(self.lbl_status)
        outer.addLayout(bottom)

    def start(self, out_dir: str, ops_csv: str | None = None):
        self._out_dir = Path(out_dir)
        self._out_dir.mkdir(parents=True, exist_ok=True)

        self._ops_csv_path = Path(ops_csv) if ops_csv else asset_path("data", "LandmarksOperations_data.csv")
        self.txt_csv.setText(str(self._ops_csv_path))

        self._load_ops(self._ops_csv_path)

    # ---------------- internal helpers ----------------
    def _browse(self):
        fn, _ = QFileDialog.getOpenFileName(
            self,
            "Select LandmarksOperations CSV",
            str(self._ops_csv_path.parent if self._ops_csv_path else Path.cwd()),
            "CSV files (*.csv);;All files (*.*)",
        )
        if not fn:
            return
        self._ops_csv_path = Path(fn)
        self.txt_csv.setText(str(self._ops_csv_path))
        self._load_ops(self._ops_csv_path)

    def _load_available_labels(self) -> list[str]:
        # 1) intentar desde out_dir/detections_labeled.csv
        if self._out_dir:
            p = detections_labeled_csv(self._out_dir, create=False)
            if not p.exists():
                p = self._out_dir / "detections_labeled.csv"
            if p.exists():
                import pandas as pd
                det = pd.read_csv(p)
                for c in ("label", "Label", "LABEL", "name", "Name"):
                    if c in det.columns:
                        labels = sorted(set(det[c].astype(str).str.strip().tolist()))
                        labels = [x for x in labels if x]
                        if labels:
                            return labels

        # 2) fallback: markers_template.csv
        from ...core.paths import asset_path
        tpl = asset_path("data", "markers_template.csv")
        if tpl.exists():
            import pandas as pd
            df = pd.read_csv(tpl)
            if "label" in df.columns:
                labels = sorted(set(df["label"].astype(str).str.strip().tolist()))
                labels = [x for x in labels if x]
                return labels

        return []


    def _clear_body(self):
        self._checkbox_by_row.clear()
        self._rows_in_order.clear()
        self._extras_rows.clear()
        self._custom_rows.clear()
        self._extras_box = None

        # Remove everything except the bottom anchor and the stretch
        for i in reversed(range(self.body_layout.count())):
            item = self.body_layout.itemAt(i)
            w = item.widget()
            if w is None:
                continue

            if w is self._bottom_anchor:
                continue

            self.body_layout.removeWidget(w)
            w.deleteLater()


    def _read_ops(self, ops_csv: Path) -> pd.DataFrame:
        try:
            return pd.read_csv(ops_csv, sep=";", encoding="latin1")
        except Exception:
            return pd.read_csv(ops_csv, sep=";", encoding="utf-8")

    def _load_ops(self, ops_csv: Path):
        self._clear_body()

        if not ops_csv.exists():
            self.lbl_status.setStyleSheet("color:#b00020; font-weight:600;")
            self.lbl_status.setText(f"❌ Operations CSV not found: {ops_csv}")
            self.btn_continue.setEnabled(False)
            return

        try:
            ops = self._read_ops(ops_csv)
        except Exception as e:
            self.lbl_status.setStyleSheet("color:#b00020; font-weight:600;")
            self.lbl_status.setText(f"❌ Could not read CSV: {e}")
            self.btn_continue.setEnabled(False)
            return

        ops, missing = normalize_ops_columns(ops)
        if missing:
            self.lbl_status.setStyleSheet("color:#b00020; font-weight:600;")
            self.lbl_status.setText(
                "❌ Missing columns in operations CSV: " + ", ".join(missing)
                + "\nColumns found: " + ", ".join(map(str, ops.columns))
            )
            self.btn_continue.setEnabled(False)
            return

        ops = ops[OP_COLUMNS].copy()
        ops[OP_TYPE_COL] = ops[OP_TYPE_COL].ffill()
        ops[OP_FINGER_COL] = ops[OP_FINGER_COL].ffill()

        def norm_cell(v):
            if pd.isna(v):
                return ""
            return str(v).strip()

        for c in OP_COLUMNS:
            ops[c] = ops[c].apply(norm_cell)

        ops = ops[ops[OP_DIMENSION_COL].astype(bool)].copy()
        ops, skipped_invalid_ops = drop_invalid_marker_ops(ops)

        # Build rows
        rows: list[_OpRow] = []
        extras_rows: list[_OpRow] = []

        for _, r in ops.iterrows():
            tipo = r[OP_TYPE_COL]
            finger = r[OP_FINGER_COL]
            dim = r[OP_DIMENSION_COL]
            m1 = r[OP_MARKER_1_COL]
            m2 = r[OP_MARKER_2_COL]

            op = _OpRow(tipo=tipo, finger=finger, dim=dim, m1=m1, m2=m2)
            rows.append(op)

            # Template-defined extra measures are rendered apart, but they are
            # still part of the base CSV and must not trigger the custom-save dialog.
            is_extra = (finger.strip().lower() == "extras") or (tipo.strip().upper() == "EXTRAS")
            if is_extra:
                extras_rows.append(op)

        self._rows_in_order = rows
        self._extras_rows = extras_rows


        # Group by finger, then by tipo
        by_finger: dict[str, dict[str, list[_OpRow]]] = {}
        for row in rows:
            is_extra = (row.finger.strip().lower() == "extras") or (row.tipo.strip().upper() == "EXTRAS")
            if is_extra:
                continue  # se renderiza aparte

            by_finger.setdefault(row.finger or "(Unknown)", {}).setdefault(row.tipo or "(Unknown)", []).append(row)


        tipo_order = ["LENGTHS", "BREADTHS", "DEPTHS"]
        tipo_label = {"LENGTHS": "Lengths", "BREADTHS": "Breadths", "DEPTHS": "Depths"}

        # Render
        for finger, by_tipo in by_finger.items():
            box = QGroupBox(finger)
            grid = QGridLayout(box)
            grid.setContentsMargins(12, 12, 12, 12)
            grid.setHorizontalSpacing(22)
            grid.setVerticalSpacing(6)

            # headers
            for c, t in enumerate(tipo_order):
                h = QLabel(tipo_label.get(t, t))
                h.setStyleSheet("font-weight:700;")
                grid.addWidget(h, 0, c, alignment=Qt.AlignLeft)

            # Create three vertical lists using layouts inside widgets
            col_widgets = []
            for c in range(3):
                w = QWidget()
                v = QVBoxLayout(w)
                v.setContentsMargins(0, 0, 0, 0)
                v.setSpacing(4)
                col_widgets.append((w, v))
                grid.addWidget(w, 1, c)

            for col_idx, t in enumerate(tipo_order):
                ops_list = by_tipo.get(t, [])
                if not ops_list:
                    col_widgets[col_idx][1].addWidget(QLabel("—"))
                    continue
                for op in ops_list:
                    cb = QCheckBox(op.dim)
                    cb.setChecked(True)
                    cb.setToolTip(f"{op.m1}  →  {op.m2}")
                    self._checkbox_by_row[op] = cb
                    col_widgets[col_idx][1].addWidget(cb)

            self.body_layout.addWidget(box)

        self._render_extras_capsule()

        self.lbl_status.setStyleSheet("")
        status = f"Loaded {len(rows)} measures from: {ops_csv}"
        if skipped_invalid_ops:
            status += f"\nSkipped {skipped_invalid_ops} unsupported line-based operations."
        self.lbl_status.setText(status)
        self.btn_continue.setEnabled(len(rows) > 0)

    def _open_new_custom_dialog(self):
        labels = self._load_available_labels()
        if not labels:
            QMessageBox.warning(self, "No labels found",
                "Could not find any labels to build the dropdown list.\n"
                "Expected detections_labeled.csv in out_dir or markers_template.csv in assets.")
            return

        dlg = NewCustomMeasureDialog(labels, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        name, p1, p2 = dlg.get_value()

        # Validaciones mínimas
        name = name.strip()
        if not name:
            QMessageBox.warning(self, "Invalid name", "Measure name cannot be empty.")
            return
        if p1 == p2:
            QMessageBox.warning(self, "Invalid points", "PTO1 and PTO2 must be different.")
            return

        new_row = _OpRow(tipo="EXTRAS", finger="Extras", dim=name, m1=p1, m2=p2)

        # evitar duplicados por nombre
        if any(r.dim == name for r in self._rows_in_order):
            QMessageBox.warning(self, "Duplicate name", f"A custom measure named '{name}' already exists.")
            return

        self._rows_in_order.append(new_row)
        self._extras_rows.append(new_row)
        self._custom_rows.append(new_row)

        # Render / update capsule
        self._render_extras_capsule()


    def _render_extras_capsule(self):
        # borrar previa si existe
        if self._extras_box is not None:
            self._extras_box.deleteLater()
            self._extras_box = None

        if not self._extras_rows:
            return  # no se muestra si no hay extras

        box = QGroupBox("Extras")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(6)

        for op in self._extras_rows:
            cb = self._checkbox_by_row.get(op)
            if cb is None:
                cb = QCheckBox(op.dim)
                cb.setChecked(True)
                cb.setToolTip(f"{op.m1}  →  {op.m2}")
                self._checkbox_by_row[op] = cb
            lay.addWidget(cb)

        self._extras_box = box

        # Insert antes del stretch final si existe, si no al final
        anchor_index = self.body_layout.indexOf(self._bottom_anchor)
        if anchor_index < 0:
            # fallback (shouldn't happen)
            self.body_layout.addWidget(box)
        else:
            self.body_layout.insertWidget(anchor_index, box)



    def _set_all(self, value: bool):
        for cb in self._checkbox_by_row.values():
            cb.setChecked(value)

    def _continue(self):
        if not self._out_dir:
            QMessageBox.warning(self, "Missing output", "Output directory is not set.")
            return

        selected_rows: list[_OpRow] = [r for r, cb in self._checkbox_by_row.items() if cb.isChecked()]
        if not selected_rows:
            QMessageBox.information(self, "No measures selected", "Please select at least one measure to continue.")
            return

        # Preservar orden original del CSV base
        selected_set = set(selected_rows)
        ordered = [r for r in self._rows_in_order if r in selected_set]

        # IMPORTANTE: incluir extras si están seleccionadas (y mantener su orden de creación)
        # Las extras cargadas desde la plantilla base no se consideran personalizadas.
        for r in self._extras_rows:
            if r in selected_set and r not in ordered:
                ordered.append(r)

        out_csv = selected_ops_csv(self._out_dir)

        try:
            import pandas as pd

            df = pd.DataFrame(
                [
                    {
                        OP_TYPE_COL: r.tipo,
                        OP_FINGER_COL: r.finger,
                        OP_DIMENSION_COL: r.dim,
                        OP_MARKER_1_COL: r.m1,
                        OP_MARKER_2_COL: r.m2,
                    }
                    for r in ordered
                ]
            )

            df.to_csv(out_csv, sep=";", index=False, encoding="utf-8")

        except Exception as e:
            QMessageBox.warning(self, "Save failed", f"Could not save CSV:\n{e}")
            self.failed.emit(str(e))
            return

        selected_custom_rows = [r for r in self._custom_rows if r in selected_set]

        # Si el usuario ha creado medidas nuevas, ofrecer "Guardar como..."
        if selected_custom_rows:
            fn, _ = QFileDialog.getSaveFileName(
                self,
                "Save selected measures CSV",
                str(out_csv),
                "CSV files (*.csv);;All files (*.*)",
            )
            if fn:
                try:
                    # Copia el archivo ya guardado (no dependemos de df)
                    from shutil import copyfile
                    copyfile(out_csv, Path(fn))
                except Exception as e:
                    QMessageBox.warning(self, "Save failed", f"Could not save CSV:\n{e}")

        self.completed.emit(
            {
                "selected_ops_csv": str(out_csv),
                "selected_ops_count": int(len(ordered)),
            }
        )


class NewCustomMeasureDialog(QDialog):
    """
    Dialog to create a new custom measure.
    The user must define:
        - Measure name
        - PTO1
        - PTO2
    """

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)

        self.setWindowTitle("New Custom Measure")
        self.setMinimumWidth(400)

        self._labels = sorted(labels)

        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)

        # --- Measure name ---
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Enter new measure name")
        layout.addRow("Measure name:", self.txt_name)

        # --- PTO1 ---
        self.cmb_p1 = QComboBox()
        self._setup_combo(self.cmb_p1)
        layout.addRow("PTO1:", self.cmb_p1)

        # --- PTO2 ---
        self.cmb_p2 = QComboBox()
        self._setup_combo(self.cmb_p2)
        layout.addRow("PTO2:", self.cmb_p2)

        # --- OK / Cancel ---
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout.addRow(buttons)

    def _setup_combo(self, combo: QComboBox):
        """
        Configure combo:
        - Editable
        - Sorted labels
        - Autocomplete with substring matching
        """
        combo.setEditable(True)
        combo.addItems(self._labels)

        completer = QCompleter(self._labels, combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)  # <- search by substring
        combo.setCompleter(completer)

    def _validate_and_accept(self):
        name = self.txt_name.text().strip()
        p1 = self.cmb_p1.currentText().strip()
        p2 = self.cmb_p2.currentText().strip()

        if not name:
            QMessageBox.warning(self, "Invalid name", "Measure name cannot be empty.")
            return

        if not p1 or not p2:
            QMessageBox.warning(self, "Invalid points", "Both PTO1 and PTO2 must be selected.")
            return

        if p1 == p2:
            QMessageBox.warning(self, "Invalid points", "PTO1 and PTO2 must be different.")
            return

        self.accept()

    def get_value(self) -> tuple[str, str, str]:
        """
        Returns:
            (measure_name, pto1, pto2)
        """
        return (
            self.txt_name.text().strip(),
            self.cmb_p1.currentText().strip(),
            self.cmb_p2.currentText().strip(),
        )
