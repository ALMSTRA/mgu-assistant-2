"""Widgets reutilizables: tarjetas de estado, consola, badges, checklist."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QTextCharFormat, QColor, QTextCursor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from ..core.models import RiskLevel
from ..i18n import tr
from .theme import ERR, LEVEL_COLORS, MUTED, OK, RISK_COLORS, WARN


class Card(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(14, 12, 14, 12)
        self.lay.setSpacing(8)


class StatusCard(Card):
    """Tarjeta con titulo, estado (ok/warn/err/pending) y texto."""

    clicked = Signal()

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        top = QHBoxLayout()
        self._dot = QLabel("○")
        self._dot.setFixedWidth(16)
        self._title = QLabel(f"<b>{title}</b>")
        top.addWidget(self._dot)
        top.addWidget(self._title, 1)
        self.lay.addLayout(top)
        self._text = QLabel("")
        self._text.setWordWrap(True)
        self._text.setObjectName("Muted")
        self.lay.addWidget(self._text)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(88)

    def set_state(self, state: str, text: str) -> None:
        color = {"ok": OK, "warn": WARN, "err": ERR}.get(state, MUTED)
        glyph = {"ok": "✓", "warn": "!", "err": "✗"}.get(state, "○")
        self._dot.setText(glyph)
        self._dot.setStyleSheet(f"color:{color}; font-weight:700; font-size:15px;")
        self._text.setText(text)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        self.clicked.emit()
        super().mousePressEvent(e)


class RiskBadge(QLabel):
    def __init__(self, risk: RiskLevel, text: str = "", parent=None) -> None:
        super().__init__(parent)
        bg, fg = RISK_COLORS.get(risk, ("#555", "#fff"))
        self.setText(text or str(risk).upper())
        self.setStyleSheet(f"background:{bg}; color:{fg}; border-radius:5px; padding:2px 8px; font-weight:600; font-size:11px;")
        self.setAlignment(Qt.AlignCenter)


class KV(QWidget):
    """Fila clave: valor para resultados."""

    def __init__(self, key: str, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        k = QLabel(key)
        k.setObjectName("Muted")
        k.setFixedWidth(150)
        self.v = QLabel("—")
        self.v.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(k)
        lay.addWidget(self.v, 1)

    def set(self, value: str, state: str = "") -> None:
        self.v.setText(value)
        color = {"ok": OK, "warn": WARN, "err": ERR}.get(state, "")
        self.v.setStyleSheet(f"color:{color}; font-weight:600;" if color else "")


class ChecklistItem(QCheckBox):
    """(Legado) casilla individual; las paginas usan ahora AcceptBox."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)


class AcceptBox(QGroupBox):
    """Puntos a leer + UN solo boton 'Acepto', estilo terminos y condiciones.

    Sustituye a las casillas una por una y a la frase escrita (2026-11-09). El boton se
    bloquea al aceptar; `set_available(False)` lo deshabilita mientras falte un requisito previo.
    """

    accepted_changed = Signal(bool)

    def __init__(self, title: str, points: list[str], button_text: str = tr("✓ Lei y acepto", "✓ I have read and accept"),
                 parent=None) -> None:
        super().__init__(title, parent)
        lay = QVBoxLayout(self)
        html = "<ul style='margin:0 0 0 16px;'>" + "".join(f"<li>{p}</li>" for p in points) + "</ul>"
        self.points = QLabel(html)
        self.points.setWordWrap(True)
        self.points.setTextFormat(Qt.RichText)
        lay.addWidget(self.points)
        row = QHBoxLayout()
        self.btn = QPushButton(button_text)
        self.btn.setObjectName("Primary")
        self.btn.clicked.connect(lambda: self.set_accepted(True))
        self.state_lbl = QLabel("")
        row.addWidget(self.btn)
        row.addWidget(self.state_lbl)
        row.addStretch(1)
        lay.addLayout(row)
        self._accepted = False
        self._available = True
        self._refresh()

    @property
    def accepted(self) -> bool:
        return self._accepted

    def set_available(self, value: bool) -> None:
        self._available = bool(value)
        self._refresh()

    def set_accepted(self, value: bool, emit: bool = True) -> None:
        self._accepted = bool(value)
        self._refresh()
        if emit:
            self.accepted_changed.emit(self._accepted)

    def _refresh(self) -> None:
        self.btn.setEnabled(self._available and not self._accepted)
        if self._accepted:
            self.state_lbl.setText(tr("✓ Aceptado", "✓ Accepted"))
            self.state_lbl.setStyleSheet(f"color:{OK};")
        elif not self._available:
            self.state_lbl.setText(tr("Complete primero el paso anterior", "Complete the previous step first"))
            self.state_lbl.setStyleSheet(f"color:{MUTED};")
        else:
            self.state_lbl.setText(tr("Pendiente de aceptar", "Not accepted yet"))
            self.state_lbl.setStyleSheet(f"color:{WARN};")


class ConsoleWidget(QWidget):
    """Consola de log con colores por nivel, filtro, copiar y guardar."""

    save_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        bar = QHBoxLayout()
        self.filter = QComboBox()
        # El filtro se decide por indice (_passes), asi que traducir los textos no cambia el comportamiento.
        self.filter.addItems([tr("Todo", "All"), tr("Sin salida de procesos (OUT)", "Hide process output (OUT)"),
                              tr("Solo avisos y errores", "Warnings and errors only")])
        self.filter.currentIndexChanged.connect(self._refilter)
        self.autoscroll = QCheckBox(tr("Auto-desplazar", "Auto-scroll"))
        self.autoscroll.setChecked(True)
        clear = QPushButton(tr("Limpiar", "Clear"))
        clear.clicked.connect(self.clear)
        copy = QPushButton(tr("Copiar", "Copy"))
        copy.clicked.connect(self._copy)
        save = QPushButton(tr("Guardar log…", "Save log…"))
        save.clicked.connect(self.save_requested.emit)
        bar.addWidget(QLabel(tr("<b>Consola</b>", "<b>Console</b>")))
        bar.addSpacing(10)
        bar.addWidget(self.filter)
        bar.addWidget(self.autoscroll)
        bar.addStretch(1)
        bar.addWidget(clear)
        bar.addWidget(copy)
        bar.addWidget(save)
        lay.addLayout(bar)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(20000)
        self.text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self.text, 1)
        self._lines: list[tuple[str, str, str]] = []

    def _passes(self, level: str) -> bool:
        i = self.filter.currentIndex()
        if i == 1:
            return level != "OUT"
        if i == 2:
            return level in ("WARN", "ERROR")
        return True

    def append(self, ts: str, level: str, msg: str) -> None:
        self._lines.append((ts, level, msg))
        if self._passes(level):
            self._write(ts, level, msg)

    def _write(self, ts: str, level: str, msg: str) -> None:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(LEVEL_COLORS.get(level, "#ffffff")))
        if level in ("ERROR", "OK", "CMD"):
            fmt.setFontWeight(700)
        cursor = self.text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(f"{ts} [{level:5}] {msg}\n", fmt)
        if self.autoscroll.isChecked():
            self.text.setTextCursor(cursor)
            self.text.ensureCursorVisible()

    def _refilter(self) -> None:
        self.text.clear()
        for ts, lv, m in self._lines:
            if self._passes(lv):
                self._write(ts, lv, m)

    def clear(self) -> None:
        self._lines.clear()
        self.text.clear()

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.text.toPlainText())


def hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("color:#262c36;")
    return f


def section(text: str) -> QLabel:
    l = QLabel(text)
    l.setObjectName("Section")
    return l


def muted(text: str) -> QLabel:
    l = QLabel(text)
    l.setObjectName("Muted")
    l.setWordWrap(True)
    return l
