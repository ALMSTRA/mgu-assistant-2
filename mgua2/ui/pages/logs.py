"""Registro: archivos de log (censurados) y exportacion."""
from __future__ import annotations

import webbrowser
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QListWidget, QPushButton

from ...i18n import tr
from ...security.redaction import hide_home
from ..widgets import muted
from . import BasePage


class LogsPage(BasePage):
    title = tr("Registro", "Logs")
    subtitle = tr("Todo lo que ocurre queda en la consola inferior y en archivos de log con VIN, tokens y llaves censurados. "
                  "Aqui estan los archivos de esta y otras sesiones, incluidos los logs de sesion de la herramienta oficial.",
                  "Everything that happens is shown in the console below and saved to log files with VIN, tokens and keys "
                  "redacted. Here are the files from this and other sessions, including the official tool's session logs.")
    key = "Registro"
    nav = tr("Registro", "Logs")

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        row = QHBoxLayout()
        b1 = QPushButton(tr("Abrir carpeta de logs", "Open logs folder"))
        b1.clicked.connect(lambda: webbrowser.open(Path(self.ctx.paths.logs).as_uri()))
        b2 = QPushButton(tr("Exportar consola actual…", "Export current console…"))
        b2.clicked.connect(self.export)
        b3 = QPushButton(tr("Actualizar", "Refresh"))
        b3.clicked.connect(self.refresh)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addWidget(b3)
        row.addStretch(1)
        self.body().addLayout(row)
        self.cur = muted("")
        self.body().addWidget(self.cur)
        self.list = QListWidget()
        self.list.setMinimumHeight(300)
        self.list.itemDoubleClicked.connect(lambda it: webbrowser.open(Path(self.ctx.paths.logs, it.text()).as_uri()))
        self.body().addWidget(self.list)
        self.body().addStretch(1)

    def refresh(self) -> None:
        log = hide_home(str(self.ctx.bus.path))
        self.cur.setText(tr(f"Log de esta sesion: {log}", f"This session's log: {log}"))
        self.list.clear()
        for p in sorted(self.ctx.paths.logs.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True):
            self.list.addItem(p.name)

    def export(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, tr("Guardar log", "Save log"), "mgua2-consola.log", "Log (*.log *.txt)")
        if p:
            Path(p).write_text(self.ctx.bus.export_text(), encoding="utf-8")
            self.ctx.bus.ok(tr(f"Consola exportada a {p}", f"Console exported to {p}"))

    def on_enter(self) -> None:
        self.refresh()
