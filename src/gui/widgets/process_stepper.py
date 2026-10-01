from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QToolButton,
)


@dataclass(frozen=True)
class Step:
    title: str


class ProcessStepper(QFrame):
    """Barra de pasos del flujo principal.

    - Muestra únicamente los pasos del proceso, sin título redundante tipo
      "Paso X/N".
    - El paso actual queda resaltado.
    - Permite navegar a pasos ya visitados.
    - Los botones se reparten horizontalmente por todo el ancho disponible.
    """

    step_clicked = Signal(int)  # index 0-based

    def __init__(self, steps: list[Step], parent=None):
        super().__init__(parent)
        self._steps = steps
        self._buttons: list[QToolButton] = []
        self._current = 0
        self._max_enabled = 0
        self._navigation_enabled = True

        self.setObjectName("ProcessStepper")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)

        for i, st in enumerate(self._steps):
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setAutoRaise(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setText(f"{i + 1}. {st.title}")
            btn.clicked.connect(lambda checked=False, idx=i: self._emit_step_clicked(idx))
            btn.setProperty("variant", "step")

            # Make every stage occupy a balanced portion of the header.
            # This removes the old left-side "Paso X/N" label and lets the
            # process itself use the complete width of the window.
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setMinimumHeight(36)

            self._buttons.append(btn)
            lay.addWidget(btn, 1)

        self.set_state(current_index=0, max_enabled_index=0)

    def set_navigation_enabled(self, enabled: bool):
        """Control whether clicking the step buttons navigates between pages."""
        self._navigation_enabled = bool(enabled)
        cursor = Qt.PointingHandCursor if self._navigation_enabled else Qt.ArrowCursor
        tooltip = "" if self._navigation_enabled else "Use the Back button and page actions to move through the workflow."
        for btn in self._buttons:
            btn.setCursor(cursor)
            btn.setToolTip(tooltip)

    def _emit_step_clicked(self, idx: int):
        if not self._navigation_enabled:
            self.set_state(self._current, self._max_enabled)
            return
        self.step_clicked.emit(idx)

    def set_state(self, current_index: int, max_enabled_index: int):
        """Actualiza el paso actual y qué botones están habilitados.

        - current_index: 0..N-1
        - max_enabled_index: 0..N-1 (inclusive).
        """
        n = len(self._steps)
        self._current = max(0, min(n - 1, int(current_index)))
        self._max_enabled = max(0, min(n - 1, int(max_enabled_index)))

        for i, b in enumerate(self._buttons):
            b.setEnabled(i <= self._max_enabled)
            b.setChecked(i == self._current)
