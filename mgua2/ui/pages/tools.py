"""Herramientas: descarga/verificacion automatica de todo lo oficial."""
from __future__ import annotations

import webbrowser
from pathlib import Path

from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QProgressBar, QPushButton, QTableWidget,
                               QTableWidgetItem)

from ...i18n import tr
from ..qt_bridge import Worker
from ..widgets import hline, muted, section
from . import BasePage


class ToolsPage(BasePage):
    title = tr("Herramientas oficiales", "Official tools")
    subtitle = tr("Se descargan y verifican solas: el codigo de la herramienta de SSH (zip de GitHub, sin git), su GUI "
                  "prebuilt MGU-SSH.exe (release), el instalador standalone mgu-install (SHA256 verificado) y los "
                  "repositorios de apps para el catalogo. Tus enrollments y respaldos se conservan al actualizar.",
                  "They are downloaded and verified automatically: the SSH tool source code (GitHub zip, no git), its "
                  "prebuilt GUI MGU-SSH.exe (release), the standalone mgu-install installer (SHA256-verified) and the "
                  "app repositories for the catalog. Your enrollments and backups are kept when updating.")
    key = "Herramientas"
    nav = tr("Herramientas", "Tools")

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        row = QHBoxLayout()
        self.btn_all = QPushButton(tr("⬇ Descargar / actualizar todo", "⬇ Download / update all"))
        self.btn_all.setObjectName("Primary")
        self.btn_all.clicked.connect(lambda: self.install_all(False))
        self.btn_force = QPushButton(tr("Forzar re-descarga", "Force re-download"))
        self.btn_force.clicked.connect(lambda: self.install_all(True))
        self.btn_open = QPushButton(tr("Abrir carpeta de datos", "Open data folder"))
        self.btn_open.clicked.connect(lambda: webbrowser.open(Path(self.ctx.paths.base).as_uri()))
        row.addWidget(self.btn_all)
        row.addWidget(self.btn_force)
        row.addWidget(self.btn_open)
        row.addStretch(1)
        self.body().addLayout(row)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.plabel = muted("")
        self.body().addWidget(self.progress)
        self.body().addWidget(self.plabel)
        self.body().addWidget(hline())
        self.body().addWidget(section(tr("Estado", "Status")))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr("Componente", "Component"), tr("Estado", "Status"), "Version / commit",
                                              tr("Ruta", "Path")])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setMinimumHeight(260)
        self.body().addWidget(self.table)
        self.body().addStretch(1)
        self._worker = Worker()
        self._worker.done.connect(self._done)
        self._worker.failed.connect(self._failed)
        self._prog = Worker()  # para refrescar progreso via senal
        self._prog.done.connect(self._on_progress)

    def _progress_cb(self, label: str, got: int, total: int) -> None:
        self._prog.done.emit((label, got, total))

    def _on_progress(self, data) -> None:
        if not data:
            return
        label, got, total = data
        self.progress.setVisible(True)
        if total > 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(int(got * 100 / total))
        else:
            self.progress.setRange(0, 0)
        self.plabel.setText(f"{label}: {got // 1024} KB" + (f" / {total // 1024} KB" if total > 0 else ""))

    def install_all(self, force: bool) -> None:
        self.btn_all.setEnabled(False)
        self.btn_force.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.plabel.setText(tr("Consultando GitHub…", "Checking GitHub…"))
        self._worker.run(self.ctx.tools.install_all, progress=self._progress_cb, force=force)

    def _done(self, status) -> None:
        self.btn_all.setEnabled(True)
        self.btn_force.setEnabled(True)
        self.progress.setVisible(False)
        self.plabel.setText("")
        self.refresh()

    def _failed(self, tb: str) -> None:
        self.ctx.bus.error(tb)
        self._done(None)

    def refresh(self) -> None:
        st = self.ctx.tools.status()
        rows = [st.ssh_source, st.ssh_prebuilt, st.mgu_install] + list(st.repos.values())
        self.table.setRowCount(len(rows))
        for r, i in enumerate(rows):
            vals = [i.name, tr("✓ listo", "✓ ready") if i.ok else tr("✗ falta", "✗ missing"), i.version or "—",
                    i.path or i.detail]
            for c, v in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(v))
        self.ctx.state.tools_ready = st.all_ready
        self.changed.emit()

    def status(self):
        return (("ok", tr("Todo descargado y verificado", "Everything downloaded and verified")) if self.ctx.state.tools_ready
                else ("warn", tr("Faltan descargas", "Downloads missing")))

    def on_enter(self) -> None:
        self.refresh()
