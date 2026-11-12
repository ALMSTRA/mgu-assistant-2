"""Entorno: comprobaciones del Doctor con correcciones automaticas y adaptadores."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from ...i18n import tr
from ...services import netinfo
from ..qt_bridge import Worker
from ..widgets import Card, hline, muted, section
from . import BasePage


class EnvironmentPage(BasePage):
    title = tr("Entorno de la computadora", "Computer environment")
    subtitle = tr("El Doctor revisa administrador, OpenSSH, internet, herramientas y el adaptador ENET, y aplica "
                  "correcciones automaticas cuando es seguro. Nada se instala sin que lo veas aqui.",
                  "The Doctor checks administrator rights, OpenSSH, internet, tools and the ENET adapter, and applies "
                  "automatic fixes when it is safe. Nothing gets installed without you seeing it here.")
    key = "Entorno"
    nav = tr("Entorno", "Environment")

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        row = QHBoxLayout()
        self.btn_check = QPushButton(tr("Revisar ahora", "Check now"))
        self.btn_check.clicked.connect(self.run_checks)
        self.btn_fix = QPushButton(tr("Corregir todo automaticamente", "Fix everything automatically"))
        self.btn_fix.setObjectName("Primary")
        self.btn_fix.clicked.connect(self.fix_all)
        row.addWidget(self.btn_check)
        row.addWidget(self.btn_fix)
        row.addStretch(1)
        self.body().addLayout(row)

        self._findings_box = QVBoxLayout()
        self.body().addLayout(self._findings_box)
        self.body().addWidget(hline())
        self.body().addWidget(section(tr("Adaptadores de red", "Network adapters")))
        self.body().addWidget(muted(tr("El ENET aparece como un adaptador cableado 'Up' con direccion 169.254.x.x (sin DHCP).",
                                       "ENET shows up as a wired adapter that is 'Up' with a 169.254.x.x address (no DHCP).")))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr("Nombre", "Name"), tr("Descripcion", "Description"),
                                              tr("Estado", "Status"), "IPv4", "ENET?"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setMinimumHeight(160)
        self.body().addWidget(self.table)
        self.body().addStretch(1)
        self._worker = Worker()
        self._worker.done.connect(self._show)
        self._worker.failed.connect(lambda tb: self.ctx.bus.error(tb))
        self._findings = []

    def run_checks(self) -> None:
        self.btn_check.setEnabled(False)
        self._worker.run(lambda: (self.ctx.doctor.check_environment(),
                                  [] if self.ctx.demo else netinfo.list_adapters()))

    def _clear(self) -> None:
        while self._findings_box.count():
            it = self._findings_box.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

    def _show(self, result) -> None:
        self.btn_check.setEnabled(True)
        if result is None:
            return
        findings, adapters = result
        self._findings = findings
        self._clear()
        for f in findings:
            card = Card()
            top = QHBoxLayout()
            glyph = {"ok": "✓", "warn": "!", "error": "✗"}.get(f.severity, "•")
            color = {"ok": "#2fbf71", "warn": "#f2b134", "error": "#ff5c5c"}.get(f.severity, "#9aa3ad")
            g = QLabel(glyph)
            g.setStyleSheet(f"color:{color}; font-weight:700; font-size:15px;")
            g.setFixedWidth(16)
            t = QLabel(f"<b>{f.title}</b> — {f.detail}")
            t.setWordWrap(True)
            top.addWidget(g)
            top.addWidget(t, 1)
            if f.fix_id:
                b = QPushButton(f.fix_label or tr("Corregir", "Fix"))
                b.clicked.connect(lambda _=False, fid=f.fix_id: self._fix(fid))
                top.addWidget(b)
            card.lay.addLayout(top)
            self._findings_box.addWidget(card)
        self.table.setRowCount(len(adapters))
        for r, a in enumerate(adapters):
            vals = [a.name, a.description, a.status, ", ".join(a.ipv4) or "—", tr("SI", "YES") if a.looks_enet else ""]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if c == 4 and a.looks_enet:
                    item.setForeground(Qt.green)
                self.table.setItem(r, c, item)
        self.ctx.state.admin = any(f.id == "ADMIN" and f.severity == "ok" for f in findings)
        self.ctx.state.openssh_ok = any(f.id == "OPENSSH" and f.severity == "ok" for f in findings)
        self.changed.emit()

    def _fix(self, fix_id: str) -> None:
        if fix_id in ("DOWNLOAD_TOOLS", "REDOWNLOAD_TOOLS"):
            # Descarga larga: en un Worker, y se re-comprueba al TERMINAR (no antes).
            self.btn_fix.setEnabled(False)
            w = Worker()

            def done(status) -> None:
                self.ctx.state.tools_ready = bool(status and status.all_ready)
                self.btn_fix.setEnabled(True)
                self.run_checks()

            w.done.connect(done)
            w.failed.connect(lambda tb: (self.ctx.bus.error(tb), self.btn_fix.setEnabled(True), self.run_checks()))
            self._dl_worker = w
            w.run(self.ctx.tools.install_all, force=(fix_id == "REDOWNLOAD_TOOLS"),
                  extra_sources=self.ctx.sources.enabled())
            return
        try:
            self.ctx.doctor.fix(fix_id, done=lambda ok, msg: None)
        except SystemExit:
            from PySide6.QtWidgets import QApplication
            QApplication.instance().quit()
            return
        self.run_checks()

    def fix_all(self) -> None:
        auto = [f for f in self._findings if f.fix_id and f.auto and f.severity != "ok"]
        if not auto:
            self.ctx.bus.info(tr("Doctor: nada que corregir automaticamente.", "Doctor: nothing to fix automatically."))
            self.run_checks()
            return
        for f in auto:
            self.ctx.bus.info(tr(f"Doctor: aplicando '{f.fix_label}'…", f"Doctor: applying '{f.fix_label}'…"))
            self._fix(f.fix_id)

    def status(self):
        s = self.ctx.state
        if s.admin and s.openssh_ok:
            return ("ok", tr("Administrador y OpenSSH listos", "Administrator and OpenSSH ready"))
        if s.openssh_ok:
            return ("warn", tr("Sin administrador (necesario para ENET)", "Not administrator (needed for ENET)"))
        return ("warn", tr("Revise OpenSSH / administrador", "Check OpenSSH / administrator"))

    def on_enter(self) -> None:
        self.run_checks()
