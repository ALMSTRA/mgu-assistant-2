"""Respaldo: preflight (codificacion, solo lectura) + lista de seguridad + frase."""
from __future__ import annotations

import webbrowser
from pathlib import Path

from PySide6.QtWidgets import QHBoxLayout, QHeaderView, QPushButton, QTableWidget, QTableWidgetItem

from ...i18n import tr
from ...security.redaction import hide_home
from ...services.doctor import hints_for_output
from ..qt_bridge import ProcessController
from ..widgets import AcceptBox, hline, muted, section
from . import BasePage

CONFIRM = [
    tr("Tengo una fuente de alimentacion regulada conectada al coche (no solo un mantenedor).",
       "I have a regulated power supply connected to the car (not just a battery maintainer)."),
    tr("El vehiculo esta estacionado y sin posibilidad de moverse; laptop a corriente.",
       "The vehicle is parked and cannot move; the laptop is plugged into power."),
    tr("Entiendo que el flasheo BORRA la codificacion/CAFD, preferencias y la BMW Digital Key (habra que re-emparejarla), "
       "y que si se interrumpe puede danar la unidad.",
       "I understand that flashing WIPES the coding/CAFD, settings and the BMW Digital Key (it will have to be paired "
       "again), and that an interruption can damage the unit."),
    tr("Se que tras el flasheo la unidad queda con codificacion de FABRICA: la pantalla se desconfigura y el Store NO se "
       "instala hasta recodificar HU_MGU por orden de vehiculo (E-Sys, o un taller con E-Sys/ISTA). Tengo como hacerlo.",
       "I know that after flashing the unit is left with FACTORY coding: the screen loses its configuration and the "
       "Store will NOT install until HU_MGU is recoded to the vehicle order (E-Sys, or a shop with E-Sys/ISTA). "
       "I have a way to do it."),
    tr("Ademas del preflight, hice (o acepto no tener) un respaldo externo con BimmerCode / E-Sys / ISTA.",
       "Besides the preflight, I made (or accept not having) an external backup with BimmerCode / E-Sys / ISTA."),
    tr("Se que se flashea UNA sola vez: despues SSH queda permanente y no debo repetirlo.",
       "I know the flash is done only ONCE: after that SSH stays permanent and I must not repeat it."),
]


class BackupPage(BasePage):
    title = tr("Respaldo de codificacion y seguridad", "Coding backup and safety")
    subtitle = tr("El comando 'preflight' de la herramienta oficial lee la codificacion del MGU por ENET (solo lectura) y "
                  "la guarda con verificacion (backup.json, coding_MGU.txt, RESTORE.txt, SHA256SUMS). Despues lea las "
                  "confirmaciones y pulse 'Acepto' para desbloquear el paso de SSH.",
                  "The official tool's 'preflight' command reads the MGU coding over ENET (read-only) and saves it "
                  "with verification (backup.json, coding_MGU.txt, RESTORE.txt, SHA256SUMS). Then read the "
                  "confirmations and accept them to unlock the SSH step.")
    key = "Respaldo"
    nav = tr("Respaldo", "Backup")

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        row = QHBoxLayout()
        self.btn_pre = QPushButton(tr("💾 Respaldar codificacion (preflight, solo lectura)",
                                      "💾 Back up coding (preflight, read-only)"))
        self.btn_pre.setObjectName("Primary")
        self.btn_pre.clicked.connect(self.run_preflight)
        self.btn_cancel = QPushButton(tr("Cancelar", "Cancel"))
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(lambda: self._ctl.cancel())
        row.addWidget(self.btn_pre)
        row.addWidget(self.btn_cancel)
        row.addStretch(1)
        self.body().addLayout(row)
        self.result = muted("")
        self.body().addWidget(self.result)

        self.body().addWidget(section(tr("Respaldos encontrados", "Backups found")))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr("Fecha", "Date"), "VIN", tr("Verificado", "Verified"), "SHA256SUMS",
                                              tr("Carpeta", "Folder")])
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setMinimumHeight(120)
        self.body().addWidget(self.table)
        brow = QHBoxLayout()
        self.btn_copy = QPushButton(tr("Copiar a mis respaldos", "Copy to my backups"))
        self.btn_copy.clicked.connect(self._copy)
        self.btn_open = QPushButton(tr("Abrir carpeta", "Open folder"))
        self.btn_open.clicked.connect(self._open)
        brow.addWidget(self.btn_copy)
        brow.addWidget(self.btn_open)
        brow.addStretch(1)
        self.body().addLayout(brow)
        self.body().addWidget(hline())

        # Un solo 'Acepto' tras leer las confirmaciones (antes: casillas una por una + frase escrita).
        self.accept = AcceptBox(tr("Confirmaciones de seguridad (lea y acepte)", "Safety confirmations (read and accept)"),
                                CONFIRM,
                                tr("✓ Lei todo y acepto: desbloquear el paso de SSH",
                                   "✓ I have read everything and accept: unlock the SSH step"))
        self.accept.accepted_changed.connect(self._confirm)
        self.body().addWidget(self.accept)
        self.body().addStretch(1)
        self._ctl = ProcessController()
        self._ctl.finished.connect(self._finished)
        self._backups = []

    def run_preflight(self) -> None:
        d = self.ctx.sm.can_run_preflight()
        if not d:
            self.ctx.bus.warn(d.reason)
            return
        self.btn_pre.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self._ctl.start(self.ctx.sshtool.run_preflight)

    def _finished(self, result) -> None:
        self.btn_pre.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        hints = hints_for_output(result.lines)
        incomplete = any(h.id == "PREFLIGHT_INCOMPLETE" for h in hints)
        folder = ""
        for ln in result.lines:
            low = ln.lower()
            if "coding backup written to" in low:
                folder = ln[low.index("written to") + len("written to"):].strip()
        s = self.ctx.state
        if result.error:
            self.ctx.bus.error(result.error)
        if result.ok and folder:
            s.preflight_done, s.preflight_folder, s.preflight_complete = True, folder, not incomplete
            self.result.setText((tr("✓ Respaldo guardado en ", "✓ Backup saved to ") + hide_home(folder))
                                + (tr("  — ⚠ lectura incompleta: repitalo y no lo use como unico respaldo.",
                                      "  — ⚠ incomplete read: run it again and do not use it as your only backup.")
                                   if incomplete else ""))
            self.result.setStyleSheet("color:#f2b134;" if incomplete else "color:#2fbf71;")
        else:
            self.result.setText(tr("✗ El preflight no termino bien. Revise la consola (ENET, contacto, administrador).",
                                   "✗ The preflight did not finish correctly. Check the console (ENET, ignition, "
                                   "administrator)."))
            self.result.setStyleSheet("color:#ff5c5c;")
        self._refresh_backups()
        if result.ok and folder and self._backups:
            # La ruta impresa viene censurada ("...-[VIN-CENSURADO]"); la real es la carpeta mas reciente.
            s.preflight_folder = self._backups[0].folder
        self._reeval()
        self.changed.emit()

    def _refresh_backups(self) -> None:
        self._backups = self.ctx.sshtool.find_preflight_backups()
        self.table.setRowCount(len(self._backups))
        for r, b in enumerate(self._backups):
            vals = [b.taken or "—", b.vin_masked, tr("si", "yes") if b.complete else "NO",
                    tr("si", "yes") if b.has_sums else "no", hide_home(b.folder)]   # solo se muestra; abrir/copiar usan b.folder
            for c, v in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(v))
        if self._backups and not self.ctx.state.preflight_done:
            self.ctx.state.preflight_done = True
            self.ctx.state.preflight_folder = self._backups[0].folder

    def _selected(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        idx = rows[0].row() if rows else 0
        return self._backups[idx] if self._backups and idx < len(self._backups) else None

    def _copy(self) -> None:
        b = self._selected()
        if b:
            self.ctx.sshtool.copy_backup(b.folder)

    def _open(self) -> None:
        b = self._selected()
        if b and Path(b.folder).exists():
            webbrowser.open(Path(b.folder).as_uri())

    def _reeval(self) -> None:
        s = self.ctx.state
        # Sin preflight no hay nada que aceptar: el boton espera a que exista el respaldo.
        self.accept.set_available(s.preflight_done)
        # Estado -> widget en AMBOS sentidos: cambiar de vehiculo resetea backup_confirmed y el boton
        # quedaba "✓ Aceptado" sin poder volver a aceptar (revision 2026-11-09).
        if s.backup_confirmed and not self.accept.accepted:
            self.accept.set_accepted(True, emit=False)
        elif not s.backup_confirmed and self.accept.accepted:
            self.accept.set_accepted(False, emit=False)
        self.btn_pre.setEnabled(bool(self.ctx.sm.can_run_preflight()) and not self._ctl.running)

    def _confirm(self, accepted: bool = True) -> None:
        if not accepted:
            return
        d = self.ctx.sm.confirm_backup(True)
        if not d:
            self.accept.set_accepted(False, emit=False)
        self.ctx.bus.log("OK" if d else "WARN",
                         tr("Confirmaciones aceptadas: paso de SSH desbloqueado.",
                            "Confirmations accepted: SSH step unlocked.") if d else d.reason)
        self.changed.emit()

    def status(self):
        s = self.ctx.state
        if s.preflight_done and s.backup_confirmed:
            return ("ok", tr("Preflight hecho y confirmado", "Preflight done and confirmed"))
        if s.preflight_done:
            return ("warn", tr("Preflight hecho; falta confirmar la lista", "Preflight done; the checklist is not confirmed yet"))
        return ("pending", tr("Pendiente", "Pending"))

    def is_unlocked(self) -> bool:
        return bool(self.ctx.sm.can_run_preflight())

    def on_enter(self) -> None:
        self._refresh_backups()
        self._reeval()
