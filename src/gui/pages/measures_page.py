from __future__ import annotations

import os, pandas as pd
import shutil
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QTimer, QRunnable, QThreadPool, Qt, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame,
    QPushButton, QHBoxLayout, QTextEdit,
    QTableWidget, QTableWidgetItem, QScrollArea, QApplication, QSizePolicy
)

from ...core.hand_measures import compute_hand_measures
from ...core.measure_ops import (
    OP_DIMENSION_COL,
    OP_FINGER_COL,
    OP_MARKER_1_COL,
    OP_MARKER_2_COL,
    OP_TYPE_COL,
)
from ...core.output_cleanup import (
    cleanup_legacy_output_clutter,
    detections_labeled_csv,
    hand_rigged_labeled_blend,
    results_dir as output_results_dir,
)


def _read_table_flexible(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".xlsx":
        return pd.read_excel(path)

    for kwargs in (
        {"sep": ";", "encoding": "utf-8-sig"},
        {"sep": ",", "encoding": "utf-8-sig"},
        {"sep": ";", "encoding": "utf-8"},
        {"sep": ",", "encoding": "utf-8"},
    ):
        try:
            df = pd.read_csv(path, **kwargs)
            if len(df.columns) > 1:
                return df
        except Exception:
            pass
    return pd.read_csv(path)


class _Signals(QObject):
    log = Signal(str)
    done = Signal(dict)
    fail = Signal(str)


class _Worker(QRunnable):
    def __init__(self, out_dir: Path, ops_csv: Path | None = None):
        super().__init__()
        self.out_dir = out_dir
        self.ops_csv = ops_csv
        self.signals = _Signals()

    def run(self):
        try:
            results_dir = output_results_dir(self.out_dir)

            labeled_csv = detections_labeled_csv(self.out_dir, create=False)
            if not labeled_csv.exists():
                labeled_csv = self.out_dir / "detections_labeled.csv"

            res = compute_hand_measures(
                out_dir=results_dir,
                labeled_csv=labeled_csv,
                ops_csv=self.ops_csv,
                log=lambda s: self.signals.log.emit(str(s)),
            )
            if not res.ok:
                self.signals.fail.emit(res.message)
                return

            # --- preview top-10 desde el XLSX detallado ---
            preview_rows = []
            try:
                import pandas as pd
                if res.detailed_xlsx and Path(res.detailed_xlsx).exists():
                    df_prev = _read_table_flexible(Path(res.detailed_xlsx))
                    # Asegurar columnas esperadas (si faltan, se rellenan en blanco)
                    wanted = [OP_TYPE_COL, OP_FINGER_COL, OP_DIMENSION_COL, OP_MARKER_1_COL, OP_MARKER_2_COL, "DIST_EUCLIDEA", "STATUS"]
                    for c in wanted:
                        if c not in df_prev.columns:
                            df_prev[c] = ""
                    df_prev = df_prev[wanted].fillna("")
                    preview_rows = df_prev.values.tolist()
            except Exception:
                preview_rows = []

            self.signals.done.emit({
                "measures_detailed_xlsx": str(res.detailed_xlsx) if res.detailed_xlsx else None,
                "measures_ok": res.n_ok,
                "measures_missing": res.n_missing,
                "measures_invalid": res.n_invalid,
                "missing_markers": res.missing_markers or [],
                "preview_rows": preview_rows,
            })

        except Exception as e:
            self.signals.fail.emit(str(e))


class MeasuresPage(QWidget):
    """Final page: calculation of measures (distances) from detections_labeled.csv."""

    completed = Signal(dict)
    failed = Signal(str)
    back_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.threadpool = QThreadPool.globalInstance()

        self._payload_ok = None
        self._out_dir: Path | None = None
        self._busy: bool = False

        self._build_ui()

    def is_busy(self) -> bool:
        return bool(self._busy)

    def _build_ui(self):
        # Responsive layout strategy:
        # - Fixed header (title/subtitle)
        # - Scrollable middle content (tables/logs/etc.) so buttons never fall outside
        # - Fixed footer (buttons)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setSpacing(12)

        title = QLabel("Calculation of measures (distances)")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")

        subtitle = QLabel(
            "Euclidean distances calculated\n \n"
            "Outputs:\n"
            "• OUT_DIR/results/hand_measures_detailed.xlsx\n"
            "• OUT_DIR/results/points_xyz.xlsx\n"
            "• OUT_DIR/results/hand_rigged_labeled.blend"
        )
        subtitle.setProperty("role", "subtitle")
        subtitle.setWordWrap(True)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)

        # ---- Scrollable body (everything that may grow) ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(10)

        # --- Vista previa de medidas (Top 10) ---
        self.lbl_preview = QLabel("Preview (first 10 measures):")
        self.lbl_preview.setProperty("role", "sectiontitle")

        self.tbl_preview = QTableWidget()
        self.tbl_preview.setColumnCount(7)
        self.tbl_preview.setHorizontalHeaderLabels([
            OP_TYPE_COL, OP_FINGER_COL, OP_DIMENSION_COL, OP_MARKER_1_COL, OP_MARKER_2_COL, "DIST_EUCLIDEA", "STATUS"
        ])
        distance_header = self.tbl_preview.horizontalHeaderItem(5)
        if distance_header is not None:
            distance_header.setBackground(QBrush(QColor("#c8f2d0")))
            distance_header.setForeground(QBrush(QColor("#14532d")))
        self.tbl_preview.setRowCount(0)
        self.tbl_preview.setEditTriggers(self.tbl_preview.EditTrigger.NoEditTriggers)
        # No imponemos un mínimo alto: que el layout pueda encoger.
        self.tbl_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tbl_preview.setMinimumHeight(440)
        self.tbl_preview.setProperty("role", "preview")

        # Ajustes visuales útiles
        hdr = self.tbl_preview.horizontalHeader()
        hdr.setStretchLastSection(True)
        hdr.setDefaultAlignment(Qt.AlignLeft)
        self.tbl_preview.setColumnWidth(5, 180)

        self.status = QLabel("")
        self.status.setWordWrap(True)

        bottom = QHBoxLayout()
        self.btn_back = QPushButton("Back")
        self.btn_back.setFixedHeight(40)
        self.btn_back.setFixedWidth(120)
        self.btn_back.clicked.connect(self.back_clicked.emit)
        bottom.addWidget(self.btn_back)
        bottom.addStretch(1)

        self.btn_finish = QPushButton("Finish")
        self.btn_finish.setFixedHeight(40)
        self.btn_finish.setFixedWidth(160)
        self.btn_finish.setEnabled(False)
        self.btn_finish.clicked.connect(self._finish)


        self.btn_open_csv = QPushButton("Open XLSX")
        self.btn_open_csv.setFixedHeight(40)
        self.btn_open_csv.setEnabled(False)
        self.btn_open_csv.clicked.connect(self._open_csv)

        bottom.addWidget(self.btn_open_csv)
        bottom.addWidget(self.btn_finish)

        outer.addWidget(title)
        outer.addWidget(subtitle)
        outer.addWidget(line)

        body_layout.addWidget(self.lbl_preview)
        body_layout.addWidget(self.tbl_preview)
        body_layout.addWidget(QLabel("Log:"))
        body_layout.addWidget(self.status)
        body_layout.addStretch(1)

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        outer.addLayout(bottom)


    def start(self, out_dir: str, ops_csv: str | None = None):
        self._payload_ok = None
        self._out_dir = Path(out_dir)
        self._busy = True
        cleanup_legacy_output_clutter(self._out_dir)

        self.status.setText("Calculating measures…")

        self.btn_finish.setEnabled(False)
        self.btn_open_csv.setEnabled(False)

        worker = _Worker(self._out_dir, Path(ops_csv) if ops_csv else None)
        worker.signals.done.connect(self._done)
        worker.signals.fail.connect(self._fail)
        self.threadpool.start(worker)

    def _fmt3(self, v):
        # Convierte a float si es número; si no, devuelve tal cual
        try:
            # pandas suele traer numpy types; float(...) los soporta
            f = float(v)
            return f"{f:.3f}"
        except Exception:
            return "" if v is None else str(v)

    def _safe_to_points_xyz_xlsx(self, df: pd.DataFrame, path: Path) -> Path:
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
            from openpyxl.utils import get_column_letter
        except ImportError as e:
            raise RuntimeError("openpyxl is required to generate points_xyz.xlsx") from e

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        wb = Workbook()
        ws = wb.active
        ws.title = "Points XYZ"

        headers = list(df.columns)
        ws.append(headers)
        for _, row in df.iterrows():
            ws.append([None if pd.isna(v) else v for v in row.tolist()])

        header_fill = PatternFill("solid", fgColor="E8EDF3")
        header_font = Font(bold=True, color="1F2937")
        coord_fill = PatternFill("solid", fgColor="EEF7FF")

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="left", vertical="center")

        for row_idx in range(2, ws.max_row + 1):
            for col_idx in range(2, min(4, ws.max_column) + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.fill = coord_fill
                cell.alignment = Alignment(horizontal="right", vertical="center")
                cell.number_format = "0.000000"

        for col_idx, header in enumerate(headers, start=1):
            letter = get_column_letter(col_idx)
            values = [header]
            for row_idx in range(2, ws.max_row + 1):
                value = ws.cell(row=row_idx, column=col_idx).value
                values.append("" if value is None else str(value))
            width = max(len(str(v)) for v in values) + 2
            ws.column_dimensions[letter].width = min(max(width, 12), 32)

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        tmp = path.with_name(f"{path.stem}.tmp{path.suffix}")
        try:
            wb.save(tmp)
            try:
                os.replace(tmp, path)
                return path
            except PermissionError:
                from datetime import datetime
                stamped = path.with_name(f"{path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{path.suffix}")
                os.replace(tmp, stamped)
                return stamped
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass

    def _export_points_xyz_xlsx(self, out_dir: Path, results_dir: Path) -> Path | None:
        """
        Crea results/points_xyz.xlsx con columnas:
        'Nombre de la etiqueta', 'POS X', 'POS Y', 'POS Z'
        leyendo OUT_DIR/detections_labeled.csv.
        """
        src = detections_labeled_csv(out_dir, create=False)
        if not src.exists():
            src = out_dir / "detections_labeled.csv"
        if not src.exists():
            return None

        df = pd.read_csv(src)

        # Intentamos detectar nombres de columnas típicos (por robustez)
        # etiqueta
        label_col = None
        for c in ["label", "LABEL", "name", "NAME", "tag", "TAG", "marker", "MARKER"]:
            if c in df.columns:
                label_col = c
                break

        # xyz
        x_col = next((c for c in ["X", "x", "pos_x", "POS_X"] if c in df.columns), None)
        y_col = next((c for c in ["Y", "y", "pos_y", "POS_Y"] if c in df.columns), None)
        z_col = next((c for c in ["Z", "z", "pos_z", "POS_Z"] if c in df.columns), None)

        # Si tu detections_labeled.csv tiene otras columnas (por ejemplo x3d,y3d,z3d),
        # las probamos también:
        if x_col is None:
            x_col = next((c for c in ["x3d", "x3d_raw"] if c in df.columns), None)
        if y_col is None:
            y_col = next((c for c in ["y3d", "y3d_raw"] if c in df.columns), None)
        if z_col is None:
            z_col = next((c for c in ["z3d", "z3d_raw"] if c in df.columns), None)

        if label_col is None or x_col is None or y_col is None or z_col is None:
            return None

        out = pd.DataFrame({
            "NAME": df[label_col].astype(str),
            "POS X": df[x_col],
            "POS Y": df[y_col],
            "POS Z": df[z_col],
        })

        # Opcional: orden estable
        out = out.reset_index(drop=True)

        stale_csv = results_dir / "points_xyz.csv"
        if stale_csv.exists():
            try:
                stale_csv.unlink()
            except Exception:
                pass

        return self._safe_to_points_xyz_xlsx(out, results_dir / "points_xyz.xlsx")

    def _copy_labeled_scene_to_results(self, out_dir: Path, results_dir: Path) -> Path | None:
        candidates = [
            hand_rigged_labeled_blend(out_dir, create=False),
            out_dir / "hand_rigged_labeled.blend",
        ]
        src = next((p for p in candidates if p.exists() and p.is_file()), None)
        if src is None:
            return None

        dst = results_dir / "hand_rigged_labeled.blend"
        shutil.copy2(src, dst)
        return dst

    def _done(self, payload: dict):
        self._busy = False
        Tx = payload.get("measures_detailed_xlsx")
        ok = payload.get("measures_ok", 0)
        miss = payload.get("measures_missing", 0)
        inv = payload.get("measures_invalid", 0)

        self.status.setStyleSheet("color:#1b5e20; font-weight:600;")
        self.status.setText(
            "✅ Measures calculated.\n"
            f"Detailed XLSX: {Tx}\n"
            f"Summary -> OK={ok} | MISSING={miss} | INVALID={inv}"
        )

        self._payload_ok = payload
        if self._out_dir is not None:
            cleanup_legacy_output_clutter(self._out_dir)

        # --- Llenar tabla de preview ---
        rows = payload.get("preview_rows") or []
        self.tbl_preview.setRowCount(len(rows))

        for r_idx, row in enumerate(rows):
            for c_idx, val in enumerate(row):
                # Solo formateamos la columna DIST_EUCLIDEA (índice 5)
                text = self._fmt3(val) if c_idx == 5 else ("" if val is None else str(val))
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if c_idx == 5:
                    item.setBackground(QBrush(QColor("#dff7e5")))
                    item.setForeground(QBrush(QColor("#14532d")))
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_preview.setItem(r_idx, c_idx, item)                            

        if len(rows) <= 200:
            self.tbl_preview.resizeColumnsToContents()
        else:
            self.tbl_preview.horizontalHeader().setStretchLastSection(True)

        self.tbl_preview.setColumnWidth(5, max(self.tbl_preview.columnWidth(5), 180))

        self.btn_open_csv.setText("Open XLSX")
        self.btn_open_csv.setEnabled(bool(payload.get("measures_detailed_xlsx")))

        self.btn_finish.setEnabled(True)

    def _fail(self, msg: str):
        self._busy = False
        self.status.setStyleSheet("color:#b00020; font-weight:600;")
        self.status.setText("❌ Error in measures calculation.\n" + msg)
        self.failed.emit(msg)

    def _finish(self):
        out_dir = self._out_dir
        if not out_dir or not out_dir.exists():
            QApplication.quit()
            return

        results_dir = output_results_dir(out_dir)

        copied_any = False

        points_xlsx = None
        try:
            points_xlsx = self._export_points_xyz_xlsx(out_dir, results_dir)
            if points_xlsx and points_xlsx.exists():
                copied_any = True
        except Exception:
            # no rompemos Finish si algo va mal
            pass

        try:
            labeled_scene = self._copy_labeled_scene_to_results(out_dir, results_dir)
            if labeled_scene and labeled_scene.exists():
                copied_any = True
        except Exception:
            pass

        detailed_xlsx = None
        if self._payload_ok:
            detailed_xlsx = self._payload_ok.get("measures_detailed_xlsx")

        if detailed_xlsx and Path(detailed_xlsx).exists():
            copied_any = True

        cleanup_legacy_output_clutter(out_dir)

        # Si no se copió nada, abrimos out_dir para que el usuario vea qué pasó
        folder_to_open = results_dir if copied_any else out_dir

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder_to_open.resolve())))
        QTimer.singleShot(150, QApplication.quit)




    def _open_csv(self):
        if not self._payload_ok:
            return

        xlsx_path = self._payload_ok.get("measures_detailed_xlsx")
        if not xlsx_path:
            return

        p = Path(xlsx_path)
        if not p.exists():
            # Si por alguna razón no está, no hacemos nada (o podrías mostrar QMessageBox)
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
