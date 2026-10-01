from pathlib import Path

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QPixmap, QPalette
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QStackedWidget,
    QMessageBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QGridLayout,
)

from ..core.app_info import APP_DISPLAY_NAME
from ..core.paths import asset_path
from ..core.settings import load_settings

from .pages.welcome_page import WelcomePage
from .pages.open_project_page import OpenProjectPage
from .pages.model_setup_page import ModelSetupPage
from .pages.threshold_page import ThresholdPage
from .pages.detect_map_page import DetectMapPage
from .pages.rigging_page import RiggingPage
from .pages.measures_selector_page import MeasuresSelectorPage
from .pages.measures_page import MeasuresPage


from .widgets.process_stepper import ProcessStepper, Step


class AppWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.resize(1100, 720)

        # Global (always visible) logo
        self._logo_src: QPixmap | None = None
        self._logo_label: QLabel | None = None

        self.out_dir: Path | None = None

        self.app_state = {}

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)

        # ------------------------------------------------------------
        # Progress bar / navigation
        # - allows returning to previously reached steps
        # - future steps remain disabled (avoids invalid states)
        # ------------------------------------------------------------
        self._steps = [
            Step("Input Data"),
            Step("Thresholds"),
            Step("Landmark Detection + 2D/3D Validation"),
            Step("Rigging + Labeling"),
            Step("Measures selector"),
            Step("Final Results"),
        ]

        # Welcome and Open Project are entry/utility screens, not stages of the
        # linear execution flow. The stepper is therefore hidden on those pages
        # and only appears once the user enters the actual workflow.
        #
        # Stack pages:
        #   0 Welcome             <- entry screen, not in stepper
        #   1 Open Project        <- utility page, not in stepper
        #   2 Model Setup
        #   3 Thresholds
        #   4 Detection + Mapping
        #   5 Rigging + Labeling
        #   6 Measures selector
        #   7 Final Results
        #
        # Flow steps shown in the stepper:
        #   0 Model Setup
        #   1 Thresholds
        #   2 Detection + Mapping
        #   3 Rigging + Labeling
        #   4 Measures selector
        #   5 Measurements
        self._stack_to_flow_step = {
            2: 0,
            3: 1,
            4: 2,
            5: 3,
            6: 4,
            7: 5,
        }
        self._flow_step_to_stack = {v: k for k, v in self._stack_to_flow_step.items()}

        self.stepper = ProcessStepper(self._steps)
        self.stepper.set_navigation_enabled(False)
        self._max_reached_step = 0
        self.stepper.step_clicked.connect(self._on_step_clicked)
        layout.addWidget(self.stepper)

        # ------------------------------------------------------------
        # Content area
        # - Stack with pages
        # - UJI logo overlaid in the top-right of the page area
        #   (so it aligns with the page header/title margins)
        # ------------------------------------------------------------
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)

        self.stack = QStackedWidget()
        grid.addWidget(self.stack, 0, 0)

        # Overlay wrapper to give consistent margins like the pages (40px)
        logo_wrap = QWidget()
        logo_lay = QHBoxLayout(logo_wrap)
        logo_lay.setContentsMargins(40, 40, 40, 0)
        logo_lay.setSpacing(0)
        logo_lay.addStretch(1)

        self._logo_label = QLabel()
        self._logo_label.setAlignment(Qt.AlignRight | Qt.AlignTop)
        self._logo_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        # IMPORTANT: don't let the layout collapse the label to 0x0
        self._logo_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self._logo_label.setMinimumSize(120, 44)
        self._logo_label.setMaximumWidth(260)
        logo_lay.addWidget(self._logo_label, 0)

        logo_file = asset_path("icons", "marca-uji-blanc.png")
        if logo_file.exists():
            self._logo_src = QPixmap(str(logo_file))
            self._update_header_logo_pixmap()
        else:
            self._logo_label.setMinimumHeight(44)

        grid.addWidget(logo_wrap, 0, 0, alignment=Qt.AlignTop | Qt.AlignRight)

        layout.addWidget(content)

        # stepper navigation state (must exist before first currentChanged)
        self._max_step_enabled = 0
        self._last_valid_index = 0

        self.stack.currentChanged.connect(self._on_stack_changed)

        # Page 1
        self.welcome_page = WelcomePage(on_start=self.go_to_model_setup, on_open_project=self.go_to_open_project)
        self.stack.addWidget(self.welcome_page)

        # Page 1.5
        self.open_project_page = OpenProjectPage()
        self.open_project_page.open_markers_requested.connect(self.open_project_markers)
        self.open_project_page.open_labels_requested.connect(self.open_project_labels)
        self.open_project_page.open_measures_requested.connect(self.open_project_measures)
        self.open_project_page.back_clicked.connect(self.go_to_welcome)
        self.stack.addWidget(self.open_project_page)

        # Page 2
        self.model_setup_page = ModelSetupPage()
        self.model_setup_page.next_clicked.connect(self.on_model_setup_next)
        self.model_setup_page.back_clicked.connect(self.go_to_welcome)
        self.stack.addWidget(self.model_setup_page)

        # Page 3: Color threshold
        self.threshold_page = ThresholdPage()
        self.threshold_page.next_clicked.connect(self.on_threshold_next)
        self.threshold_page.back_clicked.connect(self.go_to_previous_flow_step)
        self.stack.addWidget(self.threshold_page)

        # Page 5: automatic landmark detection + 2D/3D validation
        self.detect_map_page = DetectMapPage()
        self.detect_map_page.completed.connect(self.on_detect_map_completed)
        self.detect_map_page.back_clicked.connect(self.go_to_previous_flow_step)
        self.stack.addWidget(self.detect_map_page)

        # Page 6: Collapsed rigging + automatic labeling + interactive correction
        self.rigging_page = RiggingPage()
        self.rigging_page.completed.connect(self.on_rigging_completed)
        self.rigging_page.back_clicked.connect(self.go_to_previous_flow_step)
        self.stack.addWidget(self.rigging_page)

        # Page 7: Select which measures to compute
        self.measures_selector_page = MeasuresSelectorPage()
        self.measures_selector_page.completed.connect(self.on_measures_selector_completed)
        self.measures_selector_page.back_clicked.connect(self.go_to_previous_flow_step)
        self.stack.addWidget(self.measures_selector_page)

        # Page 8: Measurement calculation
        self.measures_page = MeasuresPage()
        self.measures_page.completed.connect(self.on_measures_completed)
        self.measures_page.back_clicked.connect(self.go_to_previous_flow_step)
        self.stack.addWidget(self.measures_page)

        self.stack.setCurrentWidget(self.welcome_page)
        self._on_stack_changed(self.stack.currentIndex())

    def _force_flat_hand_mode(self):
        self.app_state["measurement_mode"] = "flat_hand"

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_header_logo_pixmap()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange, QEvent.StyleChange):
            self._update_header_logo_pixmap()

    def _is_light_theme(self) -> bool:
        return self.palette().color(QPalette.Window).lightness() >= 128

    def _header_logo_for_current_theme(self) -> QPixmap:
        if self._logo_src is None or self._logo_src.isNull():
            return QPixmap()
        if not self._is_light_theme():
            return self._logo_src

        img = self._logo_src.toImage()
        img.invertPixels()
        return QPixmap.fromImage(img)

    def _update_header_logo_pixmap(self):
        """Scale the global header logo to fit and avoid overflowing small windows."""
        if not self._logo_label or self._logo_src is None or self._logo_src.isNull():
            return

        # Keep it visible but not dominant: max 240px wide or 22% of window width.
        max_w = min(240, max(110, int(self.width() * 0.22)))
        pix = self._header_logo_for_current_theme().scaledToWidth(max_w, Qt.SmoothTransformation)
        self._logo_label.setPixmap(pix)
        # Make sure the widget gets space according to the pixmap.
        self._logo_label.setFixedSize(pix.size())


    # ---------------- Stepper helpers ----------------
    def _on_stack_changed(self, idx: int):
        """Synchronize the stepper with the linear flow.

        Open Project is intentionally excluded from the stepper because it is a
        utility entry point, not a mandatory stage. When that page is shown, the
        stepper keeps the previous linear flow state instead of adding a fake
        step.
        """
        flow_idx = self._stack_to_flow_step.get(idx)

        # Entry/utility pages, such as Welcome and Open Project, do not advance
        # the flow and should not show a workflow stepper.
        if flow_idx is None:
            self.stepper.setVisible(False)
            return

        self.stepper.setVisible(True)

        # When we advance in the real flow, enable navigation back.
        if flow_idx > self._max_step_enabled:
            self._max_step_enabled = flow_idx

        self.stepper.set_state(
            current_index=flow_idx,
            max_enabled_index=self._max_step_enabled,
        )
        

    def _on_step_clicked(self, idx: int):
        """Safe navigation through the linear flow shown by the stepper."""
        if idx > self._max_step_enabled:
            QMessageBox.information(
                self,
                "Not Yet Available",
                "You haven't reached that step in the flow yet.\n"
                "Complete the previous steps to enable it.",
            )
            return

        if self._current_flow_page_is_busy():
            QMessageBox.information(
                self,
                "Process running",
                "A workflow step is still running. Wait until it finishes before moving to another step.",
            )
            return

        stack_idx = self._flow_step_to_stack.get(idx)
        if stack_idx is None:
            return

        self.stack.setCurrentIndex(stack_idx)

        if idx == 2:
            self._restore_detect_map_page_if_possible()

    def _current_flow_page_is_busy(self) -> bool:
        current = self.stack.currentWidget()
        is_busy = getattr(current, "is_busy", None)
        if callable(is_busy):
            try:
                return bool(is_busy())
            except Exception:
                return False
        return False

    def _detect_map_restore_args(self) -> dict | None:
        """Collect enough state to reopen the Landmark Detection page from saved CSVs."""
        texture_path = (
            self.app_state.get("texture_path_work")
            or self.app_state.get("work_texture_path")
            or self.app_state.get("rebaked_texture_path")
            or self.app_state.get("texture_path")
        )
        obj_path = (
            self.app_state.get("obj_uvb_path")
            or self.app_state.get("work_obj_path")
            or self.app_state.get("uv_obj_path")
            or self.app_state.get("obj_path")
        )
        out_dir = self.app_state.get("out_dir") or self.app_state.get("blender_outdir")
        csv_2d = self.app_state.get("csv_2d")
        csv_3d = self.app_state.get("csv_3d")

        if not all([texture_path, obj_path, out_dir, csv_2d, csv_3d]):
            return None

        return {
            "texture_path": str(texture_path),
            "obj_path": str(obj_path),
            "out_dir": str(out_dir),
            "csv_2d": str(csv_2d),
            "csv_3d": str(csv_3d),
            "target_json": str(self.app_state.get("target_json")) if self.app_state.get("target_json") else None,
            "measurement_mode": "flat_hand",
        }

    def _restore_detect_map_page_if_possible(self) -> bool:
        """Load or unlock the 2D/3D validation page when navigating back to it.

        This covers two cases:
        1. Normal workflow: Continue() temporarily disabled Retry while generating
           hand_with_points.obj, so returning to the page must unlock the buttons.
        2. Open Project from labels/measures: the Detection page may never have
           been initialized in this session, so it must be reconstructed from the
           existing detection CSVs before Retry can work.
        """
        args = self._detect_map_restore_args()
        if args is None:
            self.detect_map_page.prepare_for_return_navigation()
            return False

        if self.detect_map_page.has_loaded_state_for(args["csv_2d"], args["csv_3d"]):
            self.detect_map_page.prepare_for_return_navigation()
        else:
            self.detect_map_page.start_from_existing(
                texture_path=args["texture_path"],
                obj_path=args["obj_path"],
                out_dir=args["out_dir"],
                csv_2d=args["csv_2d"],
                csv_3d=args["csv_3d"],
                v_flip=True,
                snap_to_vertices=True,
                target_json=args.get("target_json"),
                measurement_mode="flat_hand",
            )
        return True

    def go_to_welcome(self):
        self.stack.setCurrentWidget(self.welcome_page)

    def go_to_previous_flow_step(self):
        if self._current_flow_page_is_busy():
            QMessageBox.information(
                self,
                "Process running",
                "A workflow step is still running. Wait until it finishes before going back.",
            )
            return

        current_stack_idx = self.stack.currentIndex()
        current_flow_idx = self._stack_to_flow_step.get(current_stack_idx)
        if current_flow_idx is None:
            self.go_to_welcome()
            return

        if current_flow_idx <= 0:
            self.go_to_welcome()
            return

        previous_flow_idx = current_flow_idx - 1
        previous_stack_idx = self._flow_step_to_stack.get(previous_flow_idx)
        if previous_stack_idx is None:
            return

        self.stack.setCurrentIndex(previous_stack_idx)
        if previous_flow_idx == 2:
            self._restore_detect_map_page_if_possible()

    def go_to_model_setup(self, measurement_mode: str = "flat_hand"):
        self._force_flat_hand_mode()
        self.model_setup_page.set_measurement_mode("flat_hand")
        self.stack.setCurrentWidget(self.model_setup_page)

    def go_to_open_project(self):
        self.stack.setCurrentWidget(self.open_project_page)

    def _open_project_settings(self) -> dict:
        settings = load_settings() or {}
        merged = dict(settings)
        merged.update(self.app_state)
        self.app_state.update(merged)
        self._force_flat_hand_mode()
        return dict(self.app_state)

    def open_project_markers(self, payload: dict):
        self.app_state.update(payload)
        self._force_flat_hand_mode()
        self._open_project_settings()
        self.stack.setCurrentWidget(self.detect_map_page)
        self.detect_map_page.start_from_existing(
            texture_path=self.app_state["texture_path"],
            obj_path=self.app_state["obj_path"],
            out_dir=self.app_state["out_dir"],
            csv_2d=self.app_state["csv_2d"],
            csv_3d=self.app_state["csv_3d"],
            v_flip=True,
            snap_to_vertices=True,
            target_json=self.app_state.get("target_json"),
            measurement_mode="flat_hand",
        )

    def open_project_labels(self, payload: dict):
        self.app_state.update(payload)
        self._force_flat_hand_mode()
        self._open_project_settings()
        self.stack.setCurrentWidget(self.rigging_page)
        self.rigging_page.start_from_manual_correction(
            settings=self.app_state,
            out_dir=str(self.app_state["out_dir"]),
            labeled_csv=str(self.app_state["labeled_csv"]),
            labeled_blend=str(self.app_state["labeled_blend"]),
            mesh_path=str(self.app_state["obj_path"]),
        )

    def open_project_measures(self, payload: dict):
        self.app_state.update(payload)
        self._force_flat_hand_mode()
        self._open_project_settings()
        self.stack.setCurrentWidget(self.measures_selector_page)
        self.measures_selector_page.start(
            out_dir=self.app_state["out_dir"],
            ops_csv=self.app_state.get("selected_ops_csv"),
        )

    def on_threshold_next(self, payload: dict):
        self.app_state.update(payload)
        self._force_flat_hand_mode()

        # --- Always choose canonical post-Blender artifacts ---
        # OBJ used by the main pipeline.
        # In the normal path it is the rebaked *_UVB.obj, and in skip mode it is the passthrough copy.
        obj_uvb = self.app_state.get("work_obj_path") or self.app_state.get("uv_obj_path") or self.app_state.get("obj_uvb_path")
        if not obj_uvb:
            obj_uvb = self.app_state.get("obj_path")  # fallback (not ideal, but avoids crash)

        # Texture used by the main pipeline.
        # In the normal path it is the rebaked texture, and in skip mode it is the preserved original copy.
        tex_rebaked = self.app_state.get("work_texture_path") or self.app_state.get("rebaked_texture_path")
        if not tex_rebaked:
            tex_rebaked = self.app_state.get("texture_path")  # fallback

        # out_dir (in your flow blender_outdir == out_dir normally)
        out_dir = self.app_state.get("blender_outdir") or self.app_state.get("out_dir")

        # Save normalized to state for next steps
        self.app_state["obj_uvb_path"] = obj_uvb
        self.app_state["texture_path_work"] = tex_rebaked  # <- explicit name to NOT overwrite original
        self.app_state["out_dir"] = out_dir

        # target_json comes from ThresholdPage
        target_json = self.app_state.get("target_json")

        self.stack.setCurrentWidget(self.detect_map_page)
        self.detect_map_page.start(
            texture_path=self.app_state["texture_path_work"],  # ✅ NewHandTexture.png
            obj_path=self.app_state["obj_uvb_path"],           # ✅ *_UVB.obj
            out_dir=self.app_state["out_dir"],
            target_json=target_json,
            v_flip=True,
            snap_to_vertices=True,
            measurement_mode="flat_hand",
        )


    def on_detect_map_completed(self, payload: dict):
        self.app_state.update(payload)

        # Rigging must preserve the detection spheres because the next step
        # (Automatic Labeling) labels those objects inside the generated .blend.
        # Therefore, prefer hand_with_points.obj if Detection+Mapping generated it.
        #
        # For the OpenPose render itself, the Blender render script hides helper
        # spheres and selects the real hand mesh, so using hand_with_points.obj is
        # safe and keeps the full downstream flow coherent.
        obj_for_rig = self.app_state.get("hand_with_points_obj")
        if not obj_for_rig:
            obj_for_rig = self.app_state.get("obj_uvb_path") or self.app_state.get("uv_obj_path")
        if not obj_for_rig:
            obj_for_rig = self.app_state.get("obj_path")

        self.app_state["obj_for_rigging"] = obj_for_rig

        self.stack.setCurrentWidget(self.rigging_page)
        self.rigging_page.start(
            obj_path=obj_for_rig,
            out_dir=self.app_state["out_dir"],
            resolution=1024,
            settings=self.app_state,
        )


    def on_model_setup_next(self, payload: dict):
        """
        After selecting the OBJ model and its texture, the application now goes
        directly to the threshold selection screen.

        The old Blender post-processing page has been removed from the normal
        workflow. The original OBJ/texture are kept as the canonical working
        files for detection and mapping. Blender is only executed later if the
        user explicitly chooses manual threshold selection.
        """
        self.app_state.update(payload)
        self._force_flat_hand_mode()

        outdir = Path(self.app_state["out_dir"])
        outdir.mkdir(parents=True, exist_ok=True)

        obj_path = self.app_state["obj_path"]
        texture_path = self.app_state["texture_path"]

        # Normal workflow: no UV rebake, no copied surrogate files.
        # Keep these compatibility keys because downstream pages already use
        # them to decide which OBJ/texture should be processed.
        self.app_state.update({
            "blender_outdir": str(outdir),
            "uv_obj_path": obj_path,
            "obj_uvb_path": obj_path,
            "work_obj_path": obj_path,
            "rebaked_texture_path": texture_path,
            "threshold_texture_path": texture_path,
            "work_texture_path": texture_path,
            "texture_path_work": texture_path,
            "uv_rebake_skipped": True,
            "preview_rebake_generated": False,
        })

        self.stack.setCurrentWidget(self.threshold_page)
        self.threshold_page.load(
            texture_path=texture_path,
            out_dir=str(outdir),
            obj_path=obj_path,
            measurement_mode="flat_hand",
        )

    def on_rigging_completed(self, payload: dict):
        self.app_state.update(payload)

        # The rigging page now includes Automatic Rigging, Automatic Labeling
        # and the Interactive Label Editor. Once it finishes, the flow can go
        # directly to the measures selector.
        self.stack.setCurrentWidget(self.measures_selector_page)
        self.measures_selector_page.start(out_dir=self.app_state["out_dir"])


    def on_measures_selector_completed(self, payload: dict):
        self.app_state.update(payload)

        # Go to measurements using selected ops CSV (if any)
        self.stack.setCurrentWidget(self.measures_page)
        self.measures_page.start(
            out_dir=self.app_state["out_dir"],
            ops_csv=self.app_state.get("selected_ops_csv"),
        )


    def on_measures_completed(self, payload: dict):
        self.app_state.update(payload)
        print("[UI] Measurements completed:", payload)
        # Here you can display a final screen, or leave it as is.
