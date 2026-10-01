import sys
import ctypes
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from src.core.app_info import APP_USER_MODEL_ID
    from src.core.paths import asset_path
    from src.gui.theme import apply_theme, install_theme_listener
    from src.gui.appWindow import AppWindow
else:
    from .core.app_info import APP_USER_MODEL_ID
    from .core.paths import asset_path
    from .gui.theme import apply_theme, install_theme_listener
    from .gui.appWindow import AppWindow


def main():
    if sys.platform.startswith("win"):
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )

    app = QApplication(sys.argv)

    # Tema global: se adapta automáticamente a claro/oscuro del sistema
    icon_path = asset_path("icons", "uji_icon.jpg")

    app.setWindowIcon(QIcon(str(icon_path)))
    apply_theme(app, mode="auto")
    install_theme_listener(app, mode="auto")

    win = AppWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
