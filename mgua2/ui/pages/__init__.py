"""Paginas del asistente."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget


class BasePage(QWidget):
    changed = Signal()
    title: str = ""
    subtitle: str = ""
    nav: str = ""        # texto visible (traducido)
    key: str = ""        # identificador estable para navegar (no se traduce)

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self._root = QVBoxLayout(inner)
        self._root.setContentsMargins(28, 22, 28, 22)
        self._root.setSpacing(12)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        if self.title:
            t = QLabel(self.title)
            t.setObjectName("Title")
            self._root.addWidget(t)
        if self.subtitle:
            s = QLabel(self.subtitle)
            s.setObjectName("Subtitle")
            s.setWordWrap(True)
            self._root.addWidget(s)

    def body(self) -> QVBoxLayout:
        return self._root

    def on_enter(self) -> None:
        pass

    def is_unlocked(self) -> bool:
        return True

    def status(self) -> tuple[str, str]:
        """(estado, texto corto) para el panel y la navegacion."""
        return ("pending", "")
