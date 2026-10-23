"""Protect the existing flat-hand navigation and original OBJ/texture flow."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from src.gui.appWindow import AppWindow


class FlatHandWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.settings = patch.dict(os.environ, {"APPDATA": str(self.root / "settings")})
        self.settings.start()
        self.addCleanup(self.settings.stop)
        self.window = AppWindow()
        self.addCleanup(self.window.close)
        self.addCleanup(self.window.deleteLater)

    def test_only_flat_hand_is_selected_even_with_old_mode(self):
        self.window.app_state["measurement_mode"] = "posed_hand"
        self.window.go_to_model_setup("posed_hand")
        self.assertEqual(self.window.app_state["measurement_mode"], "flat_hand")
        self.assertEqual(self.window.model_setup_page.measurement_mode, "flat_hand")
        self.assertEqual(self.window.stack.count(), 8)
        self.assertEqual(len(self.window._steps), 6)

    def test_model_setup_passes_original_files_without_rebake(self):
        obj, texture = self.root / "hand.obj", self.root / "hand.png"
        obj.write_text("# original model\n", encoding="utf-8")
        texture.write_bytes(b"original texture")
        output = self.root / "results"
        payload = {"obj_path": str(obj), "texture_path": str(texture), "out_dir": str(output)}
        with patch.object(self.window.threshold_page, "load") as load:
            self.window.on_model_setup_next(payload)
        load.assert_called_once_with(texture_path=str(texture), out_dir=str(output), obj_path=str(obj), measurement_mode="flat_hand")
        self.assertEqual(self.window.app_state["work_obj_path"], str(obj))
        self.assertEqual(self.window.app_state["work_texture_path"], str(texture))
        self.assertTrue(self.window.app_state["uv_rebake_skipped"])
        self.assertFalse(self.window.app_state["preview_rebake_generated"])
        self.assertEqual(list(output.iterdir()), [])
        self.assertEqual(obj.read_text(encoding="utf-8"), "# original model\n")
        self.assertEqual(texture.read_bytes(), b"original texture")

    def test_detected_spheres_are_preserved_for_rigging(self):
        original = str(self.root / "hand.obj")
        spheres = str(self.root / "hand_with_points.obj")
        self.window.app_state.update({"obj_path": original, "out_dir": str(self.root), "measurement_mode": "flat_hand"})
        with patch.object(self.window.rigging_page, "start") as start:
            self.window.on_detect_map_completed({"hand_with_points_obj": spheres})
        self.assertEqual(start.call_args.kwargs["obj_path"], spheres)


if __name__ == "__main__":
    unittest.main()
