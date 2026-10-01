
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


# -----------------------------
# Detección de tema del sistema
# -----------------------------
def _color_scheme_from_style_hints(app: QApplication) -> str | None:
    """
    Qt6 expone QStyleHints.colorScheme() en versiones relativamente recientes.
    Devolvemos "dark" / "light" o None si no está disponible.
    """
    try:
        hints = app.styleHints()
        if not hasattr(hints, "colorScheme"):
            return None
        scheme = hints.colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
        if scheme == Qt.ColorScheme.Light:
            return "light"
        return None
    except Exception:
        return None


def _palette_is_dark(pal: QPalette) -> bool:
    bg = pal.color(QPalette.Window)
    return bg.lightness() < 128


def detect_system_theme(app: QApplication) -> str:
    """
    Devuelve "dark" o "light".
    Intenta usar QStyleHints.colorScheme() si existe; si no, cae a brillo de paleta.
    """
    by_hint = _color_scheme_from_style_hints(app)
    if by_hint in ("dark", "light"):
        return by_hint
    return "dark" if _palette_is_dark(app.palette()) else "light"


# -----------------------------
# Paletas (Fusion) + QSS
# -----------------------------
def _make_dark_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(32, 32, 32))
    pal.setColor(QPalette.WindowText, Qt.white)
    pal.setColor(QPalette.Base, QColor(24, 24, 24))
    pal.setColor(QPalette.AlternateBase, QColor(36, 36, 36))
    pal.setColor(QPalette.ToolTipBase, Qt.white)
    pal.setColor(QPalette.ToolTipText, Qt.white)
    pal.setColor(QPalette.Text, Qt.white)
    pal.setColor(QPalette.Button, QColor(45, 45, 45))
    pal.setColor(QPalette.ButtonText, Qt.white)
    pal.setColor(QPalette.BrightText, Qt.red)
    pal.setColor(QPalette.Highlight, QColor(45, 108, 223))
    pal.setColor(QPalette.HighlightedText, Qt.white)
    pal.setColor(QPalette.PlaceholderText, QColor(170, 170, 170))
    return pal


_LIGHT_QSS = r"""
/* Roles semánticos */
QLabel[role="subtitle"] { color: #555; }
QLabel[role="muted"] { color: #666; font-size: 12px; }
QLabel[role="sectiontitle"] { font-weight: 600; color: #333; }

/* Botones por variante */
QPushButton[variant="primary"] {
    font-size: 18px;
    font-weight: 700;
    padding: 12px 18px;
    border-radius: 12px;
    border: 1px solid #2e7d32;
    background: #2e7d32;
    color: white;
}
QPushButton[variant="primary"]:hover { background: #276b2b; }
QPushButton[variant="primary"]:pressed { background: #1f5523; }

QPushButton[variant="secondary"] {
    font-size: 16px;
    font-weight: 600;
    padding: 10px 18px;
    border-radius: 10px;
    border: 1px solid #cfcfcf;
    background: #f7f7f7;
    color: #222;
}
QPushButton[variant="secondary"]:hover { background: #efefef; }
QPushButton[variant="secondary"]:pressed { background: #e6e6e6; }

QPushButton[variant="tertiary"] {
    font-size: 12px;
    padding: 6px 12px;
    border-radius: 8px;
    border: 1px solid #d7d7d7;
    background: #ffffff;
    color: #222;
}
QPushButton[variant="tertiary"]:hover { background: #f5f5f5; }

/* Panels de preview (imágenes / tablas) */
QLabel[role="imagepanel"], QTableWidget[role="preview"] {
    background: #ffffff;
    color: #222;
    border: 1px solid #cfcfcf;
    border-radius: 8px;
}

/* Stepper */
#ProcessStepper { background:#f6f7f9; border:1px solid #e3e6ea; border-radius:10px; }
#ProcessStepper QLabel[role="stepper_title"] { font-weight:600; color:#333; }
#ProcessStepper QLabel[role="stepper_sep"] { color:#999; }
#ProcessStepper QToolButton[variant="step"] { padding:6px 10px; border-radius:8px; color:#333; }
#ProcessStepper QToolButton[variant="step"]:checked { background:#2d6cdf; color:white; }
#ProcessStepper QToolButton[variant="step"]:disabled { color:#9aa4b2; }
"""

_DARK_QSS = r"""
/* Roles semánticos */
QLabel[role="subtitle"] { color: #cfcfcf; }
QLabel[role="muted"] { color: #bdbdbd; font-size: 12px; }
QLabel[role="sectiontitle"] { font-weight: 600; color: #e0e0e0; }

/* Botones por variante */
QPushButton[variant="primary"] {
    font-size: 18px;
    font-weight: 700;
    padding: 12px 18px;
    border-radius: 12px;
    border: 1px solid #2e7d32;
    background: #2e7d32;
    color: white;
}
QPushButton[variant="primary"]:hover { background: #276b2b; }
QPushButton[variant="primary"]:pressed { background: #1f5523; }

QPushButton:disabled {
    /* Slightly brighter disabled text for readability on dark backgrounds,
       with a very subtle depressed background and low-contrast border. */
    color: rgba(89, 89, 89, 0.45);
    background-color: rgba(37, 37, 37, 0.02);
    border-color: rgba(33, 33, 33, 0.06);
}
QLineEdit:disabled, QSpinBox:disabled {
    /* Disabled inputs use a muted foreground and a darker, subtle background */
    color: rgba(220, 220, 220, 0.45);
    background-color: rgba(0, 0, 0, 0.12);
}


QPushButton[variant="secondary"] {
    font-size: 16px;
    font-weight: 600;
    padding: 10px 18px;
    border-radius: 10px;
    border: 1px solid #5a5a5a;
    background: #2b2b2b;
    color: #f0f0f0;
}
QPushButton[variant="secondary"]:hover { background: #333333; }
QPushButton[variant="secondary"]:pressed { background: #3a3a3a; }

QPushButton[variant="tertiary"] {
    font-size: 12px;
    padding: 6px 12px;
    border-radius: 8px;
    border: 1px solid #5a5a5a;
    background: #2b2b2b;
    color: #f0f0f0;
}
QPushButton[variant="tertiary"]:hover { background: #333333; }

/* Panels de preview (imágenes / tablas) */
QLabel[role="imagepanel"], QTableWidget[role="preview"] {
    background: #1b1b1b;
    color: #e6e6e6;
    border: 1px solid #444;
    border-radius: 8px;
}

/* Stepper */
#ProcessStepper { background:#2b2b2b; border:1px solid #444; border-radius:10px; }
#ProcessStepper QLabel[role="stepper_title"] { font-weight:600; color:#e6e6e6; }
#ProcessStepper QLabel[role="stepper_sep"] { color:#aaaaaa; }
#ProcessStepper QToolButton[variant="step"] { padding:6px 10px; border-radius:8px; color:#e6e6e6; }
#ProcessStepper QToolButton[variant="step"]:checked { background:#2d6cdf; color:white; }
#ProcessStepper QToolButton[variant="step"]:disabled { color:#777; }
"""


def apply_theme(app: QApplication, mode: str = "auto") -> str:
    """
    Aplica tema global:
      - mode: "auto" | "dark" | "light"
    Devuelve el tema aplicado ("dark" o "light").
    """
    mode = (mode or "auto").lower().strip()
    if mode not in ("auto", "dark", "light"):
        mode = "auto"

    theme = detect_system_theme(app) if mode == "auto" else mode

    # Fusion ayuda a que la paleta se respete igual en Windows/macOS/Linux
    try:
        app.setStyle("Fusion")
    except Exception:
        pass

    if theme == "dark":
        app.setPalette(_make_dark_palette())
        app.setStyleSheet(_DARK_QSS)
    else:
        # Restaurar paleta estándar de Fusion para claro
        try:
            app.setPalette(app.style().standardPalette())
        except Exception:
            pass
        app.setStyleSheet(_LIGHT_QSS)

    return theme


def install_theme_listener(app: QApplication, mode: str = "auto") -> None:
    """
    Si el sistema cambia de tema en caliente (Windows/macOS),
    re-aplicamos. Esto depende de Qt version; si no está disponible,
    no pasa nada.
    """
    try:
        hints = app.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            # Qt emitirá Qt.ColorScheme
            hints.colorSchemeChanged.connect(lambda *_: apply_theme(app, mode=mode))
    except Exception:
        pass
