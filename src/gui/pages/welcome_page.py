from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame,
    QMessageBox, QScrollArea
)

from ...core.app_info import APP_DISPLAY_NAME, APP_SHORT_NAME
from ...core.paths import app_root


def _get_app_version(fallback: str = "v1.0.0") -> str:
    """
    Tries to get the installed package version.
    If there is no metadata (dev mode / standalone script), uses fallback.
    """
    try:
        from importlib.metadata import version, PackageNotFoundError
        # If no package metadata exists in dev/portable mode, the fallback is used.
        try:
            return f"v{version(APP_SHORT_NAME)}"
        except PackageNotFoundError:
            return fallback
    except Exception:
        return fallback



class WelcomePage(QWidget):
    """
    Welcome screen:
    - Top: title + subtitle (and optional logo)
    - Center: main buttons (first time / new measurement)
    - Bottom: version + discreet buttons (about)

    """

    def __init__(self, on_start, on_open_project=None, on_first_time=None, on_about=None, app_version: str | None = None):
        super().__init__()
        self.on_start = on_start
        self.on_open_project = on_open_project
        self.on_first_time = on_first_time
        # callback for the about button (optional)
        self.on_about = on_about
        self.app_version = app_version or _get_app_version("v1.0.0")

        self._build_ui()

    def _build_ui(self):
        # Responsive layout:
        # - Fixed header (title/subtitle/logo)
        # - Middle scroll area so controls never fall outside on small windows
        # - Fixed footer (version + about)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setSpacing(18)

        # -------------------------
        # Top area (logo + title + subtitle)
        # -------------------------
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        left_top = QVBoxLayout()
        left_top.setSpacing(6)

        title = QLabel(APP_SHORT_NAME)
        title_font = QFont()
        title_font.setPointSize(26)
        title_font.setBold(True)
        title.setFont(title_font)

        subtitle = QLabel(
            "Hand Anthropometric Measurement and Landmark Extraction Tool. \n\n"
            "Start a new measurement, open an existing output project or check the quick guide if it's your first time."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("role", "subtitle")

        left_top.addWidget(title)
        left_top.addWidget(subtitle)

        top_row.addLayout(left_top, stretch=1)

        # NOTE: The UJI logo is now displayed globally in the main AppWindow header
        # so it remains visible throughout the whole application.

        outer.addLayout(top_row)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        outer.addWidget(line)

        # -------------------------
        # Middle scroll (main actions)
        # -------------------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(14)

        body_layout.addStretch(1)

        center = QVBoxLayout()
        center.setSpacing(14)

        # Button: New measurement (main)
        self.btn_new = QPushButton("New measurement")
        self.btn_new.setFixedHeight(64)
        self.btn_new.setCursor(Qt.PointingHandCursor)
        self.btn_new.setProperty("variant", "primary")
        self.btn_new.clicked.connect(self._on_new_measurement_clicked)

        # Button: Open project
        self.btn_open_project = QPushButton("Open project")
        self.btn_open_project.setFixedHeight(56)
        self.btn_open_project.setCursor(Qt.PointingHandCursor)
        self.btn_open_project.setProperty("variant", "secondary")
        self.btn_open_project.clicked.connect(self._on_open_project_clicked)

        # Centered container
        center_wrap = QHBoxLayout()
        center_wrap.addStretch(1)

        center_box = QWidget()
        center_box_layout = QVBoxLayout(center_box)
        center_box_layout.setContentsMargins(0, 0, 0, 0)
        center_box_layout.setSpacing(14)
        center_box_layout.addWidget(self.btn_new)
        center_box_layout.addWidget(self.btn_open_project)
        center_box.setMaximumWidth(420)

        center_wrap.addWidget(center_box)
        center_wrap.addStretch(1)

        body_layout.addLayout(center_wrap)
        body_layout.addStretch(1)

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # -------------------------
        # Bottom area (discreet)
        # -------------------------
        bottom = QHBoxLayout()
        bottom.setSpacing(10)

        self.lbl_version = QLabel(f"Version: {self.app_version}")
        self.lbl_version.setProperty("role", "muted")
        bottom.addWidget(self.lbl_version)

        bottom.addStretch(1)


        self.btn_first_time = QPushButton("Getting started")
        self.btn_first_time.setFixedHeight(32)
        self.btn_first_time.setCursor(Qt.PointingHandCursor)
        self.btn_first_time.setProperty("variant", "tertiary")
        self.btn_first_time.clicked.connect(self._on_first_time_clicked)
        bottom.addWidget(self.btn_first_time)

        self.btn_about = QPushButton("About")
        self.btn_about.setFixedHeight(32)
        self.btn_about.setCursor(Qt.PointingHandCursor)
        self.btn_about.setProperty("variant", "tertiary")
        self.btn_about.clicked.connect(self._on_about_clicked)

        bottom.addWidget(self.btn_about)

        outer.addLayout(bottom)

    # -------------------------
    # Actions
    # -------------------------
    def _on_new_measurement_clicked(self):
        if callable(self.on_start):
            self.on_start("flat_hand")

    def _on_open_project_clicked(self):
        if callable(self.on_open_project):
            self.on_open_project()
            return

        QMessageBox.information(self, "Open project", "Open project action is not configured yet.")

    def _on_first_time_clicked(self):
        if callable(self.on_first_time):
            self.on_first_time()
            return

        dlg = GettingStartedDialog(self)
        dlg.exec()

    def _on_about_clicked(self):
        dlg = AboutDialog(self, version=self.app_version)
        dlg.exec()

    def _show_about(self):
        msg = (
            f"{APP_DISPLAY_NAME}\n"
            f"{self.app_version}\n\n"
            "Application to create, manage and export measurements.\n"
        )
        QMessageBox.information(self, "About…", msg)


class GettingStartedDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Getting started")
        self.setModal(True)
        self.setMinimumWidth(460)

        self._docs_pdf = app_root() / "docs" / "README.pdf"

        title = QLabel("<b>Getting started</b>")
        title.setTextFormat(Qt.RichText)

        info = QLabel(
            """
            <p>
            This tool guides you through the automatic processing of a textured 3D hand model
            to detect, label and review anatomical landmarks.
            </p>
            <p><b>From this screen you can:</b></p>
            <ul>
                <li>Start a new measurement.</li>
                <li>Open an existing output project.</li>
            </ul>
            <p><b>Before starting, make sure your model includes:</b></p>
            <ul>
                <li>3D model, material file and texture.</li>
                <li>Clearly visible anatomical markers.</li>
                <li>Correct orientation: dorsal side to Z+, fingertips to Y+ and wrist to Y-.</li>
            </ul>
            """
        )
        info.setWordWrap(True)
        info.setTextFormat(Qt.RichText)

        docs_link = QLabel('<a href="open-docs">Open application documentation</a>')
        docs_link.setTextFormat(Qt.RichText)
        docs_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        docs_link.setOpenExternalLinks(False)
        docs_link.linkActivated.connect(self._open_documentation)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(btn_close)

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(title)
        lay.addWidget(info)
        lay.addWidget(docs_link)
        lay.addLayout(btn_row)

    def _open_documentation(self, _link: str = ""):
        if not self._docs_pdf.exists():
            QMessageBox.warning(
                self,
                "Documentation not found",
                f"The documentation file could not be found:\n{self._docs_pdf}",
            )
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._docs_pdf.resolve())))


class AboutDialog(QDialog):
    def __init__(self, parent=None, version: str = "v0.0.0"):
        super().__init__(parent)
        self.setWindowTitle("About")
        self.setModal(True)
        self.setMinimumWidth(520)

        title = QLabel(f"<b>{APP_DISPLAY_NAME}</b>")
        title.setTextFormat(Qt.RichText)
        title.setWordWrap(True)

        info = QLabel(
            f"""
            <p><b>Version:</b> {version}</p>
            <p><b>Authors:</b> Jon A. Fernández-Moyano, Verónica Gracia-Ibáñez,
            Alba Roda-Sales and Carlos Gonell-Cruz.</p>
            <p><b>Affiliation:</b> Department of Mechanical Engineering and Construction,
            Universitat Jaume I.</p>
            <p><b>Original code:</b> GNU GPLv3 (GPL-3.0-only).<br>
            Third-party components retain their own licenses.</p>
            <p style="margin-top:10px;">
            This application generates automatic hand measurements from a 3D hand model and texture,
            guiding the user through detection, mapping, labeling, and measurement export.
            </p>
            """
        )
        info.setWordWrap(True)
        info.setTextFormat(Qt.RichText)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(btn_close)

        lay = QVBoxLayout(self)
        lay.addWidget(title)
        lay.addWidget(info)
        lay.addLayout(btn_row)

        legal_link = QLabel('<a href="licenses">Third-party licenses and source code</a>')
        legal_link.setOpenExternalLinks(False)
        legal_link.linkActivated.connect(self._open_licenses)
        lay.insertWidget(2, legal_link)

    def _open_licenses(self, _link=""):
        notice = app_root() / "third_party_licenses" / "index.html"
        if notice.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(notice.resolve())))
        else:
            QMessageBox.information(self, "Licenses", "See THIRD_PARTY_NOTICES.md and SOURCE_CODE.md in the application folder.")
