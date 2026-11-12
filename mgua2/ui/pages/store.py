"""Instalar MGU Store con el instalador oficial standalone."""
from __future__ import annotations

import webbrowser

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QRadioButton, QWidget)

from ...core.models import HOTSPOT_HOST
from ...i18n import tr
from ...security.keyfile import validate_key_path
from ...services.doctor import hints_for_output
from ...services.sshtool import UPSTREAM_ISSUE_SETTINGS_RESET
from ..qt_bridge import ProcessController
from ..widgets import hline, muted, section
from . import BasePage
from .enable_ssh import ip_source_label

RECODE_HELP = tr(
    "✗ El instalador se nego (codigo 2): la codificacion del HU esta en valores por defecto porque el flasheo borro el "
    "CAFD. Sin codificacion valida oapcontroller no arranca MainApp, asi que el Store no puede instalarse; reconfigurar "
    "la pantalla a mano NO basta y los ajustes se pierden al reiniciar. Que hacer: 1) recodificar HU_MGU por orden de "
    "vehiculo (VO) con E-Sys —via recomendada por upstream y la que funciono en su issue #10; 'restaurar respaldo' de "
    "BimmerCode se reporto insuficiente— o en un taller con E-Sys/ISTA; 2) reiniciar la unidad; 3) repetir el "
    "diagnostico (debe aparecer un CAFD real, no FFFFFFFF); 4) volver a 'Instalar MGU Store'. El respaldo preflight "
    "(RESTORE.txt) sirve para comparar el resultado; esta app nunca escribe codificacion.",
    "✗ The installer refused (code 2): the head unit coding is at default values because the flash wiped the CAFD. "
    "Without valid coding oapcontroller does not start MainApp, so the Store cannot be installed; reconfiguring the "
    "screen by hand is NOT enough and the settings are lost on restart. What to do: 1) recode HU_MGU from the vehicle "
    "order (VO) with E-Sys —the route upstream recommends and the one that worked in their issue #10; BimmerCode's "
    "'restore backup' was reported as not enough— or at a shop with E-Sys/ISTA; 2) restart the unit; 3) run the "
    "diagnostics again (a real CAFD must show up, not FFFFFFFF); 4) come back to 'Install MGU Store'. The preflight "
    "backup (RESTORE.txt) is for comparing the result; this app never writes coding."
)


class StorePage(BasePage):
    title = tr("Instalar MGU Store", "Install MGU Store")
    subtitle = tr("Usa el binario oficial mgu-install (verificado por SHA256) con la llave del enrollment. Puede ir por "
                  "el hotspot Wi-Fi del coche (sin cable) o por la IP ENET. Instala solo Store y sus dependencias; las "
                  "apps se eligen despues desde la pantalla del coche o por USB.",
                  "Uses the official mgu-install binary (SHA256-verified) with the enrollment key. It can go over the "
                  "car's Wi-Fi hotspot (no cable) or over the ENET IP. It installs only the Store and its dependencies; "
                  "apps are chosen later from the car's screen or via USB.")
    key = "Instalar Store"
    nav = tr("Instalar Store", "Install Store")
    go_to = Signal(str)   # nav de la pagina destino (p. ej. repetir el diagnostico)

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        self.block = QLabel("")
        self.block.setWordWrap(True)
        self.block.setStyleSheet("color:#ff9f6b;")
        self.body().addWidget(self.block)

        krow = QHBoxLayout()
        krow.addWidget(QLabel(tr("Llave SSH:", "SSH key:")))
        self.key_edit = QLineEdit()
        self.key_edit.textChanged.connect(self._reeval)
        krow.addWidget(self.key_edit, 1)
        b = QPushButton(tr("Elegir…", "Browse…"))
        b.clicked.connect(self._browse)
        krow.addWidget(b)
        self.body().addLayout(krow)
        self.key_status = muted("")
        self.body().addWidget(self.key_status)

        self.body().addWidget(section(tr("Conexion con la unidad", "Connection to the unit")))
        self.r_hotspot = QRadioButton(tr(f"Hotspot Wi-Fi del coche ({HOTSPOT_HOST}) — la laptop conectada al Wi-Fi del BMW",
                                         f"Car Wi-Fi hotspot ({HOTSPOT_HOST}) — laptop connected to the BMW's Wi-Fi"))
        self.r_enet = QRadioButton(tr("IP por ENET (del diagnostico / enrollment)", "IP over ENET (from the diagnostics / enrollment)"))
        self.r_custom = QRadioButton(tr("Otra direccion:", "Other address:"))
        self.custom = QLineEdit()
        self.custom.setPlaceholderText(tr("p. ej. 169.254.36.47 o alias SSH", "e.g. 169.254.36.47 or SSH alias"))
        for r in (self.r_hotspot, self.r_enet, self.r_custom):
            r.toggled.connect(self._reeval)
        self.custom.textChanged.connect(self._reeval)
        self.body().addWidget(self.r_hotspot)
        self.body().addWidget(self.r_enet)
        crow = QHBoxLayout()
        crow.addWidget(self.r_custom)
        crow.addWidget(self.custom, 1)
        self.body().addLayout(crow)

        self.body().addWidget(section(tr("Opciones", "Options")))
        self.no_renderer = QCheckBox(tr("--no-renderer (sin el renderizador GPU)", "--no-renderer (without the GPU renderer)"))
        self.no_uplink = QCheckBox(tr("--no-uplink (sin internet uplink)", "--no-uplink (without internet uplink)"))
        for c in (self.no_renderer, self.no_uplink):
            c.stateChanged.connect(self._reeval)
            self.body().addWidget(c)

        self.body().addWidget(section(tr("Comando (rutas censuradas)", "Command (paths masked)")))
        self.cmd = QPlainTextEdit()
        self.cmd.setReadOnly(True)
        self.cmd.setMaximumHeight(70)
        self.body().addWidget(self.cmd)
        self.body().addWidget(hline())
        row = QHBoxLayout()
        self.btn_install = QPushButton(tr("⬇ Instalar MGU Store", "⬇ Install MGU Store"))
        self.btn_install.setObjectName("Primary")
        self.btn_install.clicked.connect(self.install)
        self.btn_uninstall = QPushButton(tr("Desinstalar…", "Uninstall…"))
        self.btn_uninstall.setObjectName("Danger")
        self.btn_uninstall.clicked.connect(self.uninstall)
        row.addWidget(self.btn_install)
        row.addWidget(self.btn_uninstall)
        row.addStretch(1)
        self.body().addLayout(row)
        self.after = QLabel("")
        self.after.setWordWrap(True)
        self.after.setStyleSheet("color:#f2b134;")
        self.body().addWidget(self.after)
        # Acciones cuando la codificacion del HU esta borrada (se muestran solo en ese caso).
        self.recode_box = QWidget()
        rrow = QHBoxLayout(self.recode_box)
        rrow.setContentsMargins(0, 0, 0, 0)
        self.btn_restore_txt = QPushButton(tr("📄 Abrir respaldo preflight (RESTORE.txt)", "📄 Open preflight backup (RESTORE.txt)"))
        self.btn_restore_txt.clicked.connect(lambda: self.ctx.doctor.fix("OPEN_PREFLIGHT_FOLDER"))
        self.btn_issue = QPushButton(tr("🐙 Issue #10 upstream (ajustes que se resetean)", "🐙 Upstream issue #10 (settings that reset)"))
        self.btn_issue.clicked.connect(lambda: webbrowser.open(UPSTREAM_ISSUE_SETTINGS_RESET))
        self.btn_rediag = QPushButton(tr("🔁 Repetir diagnostico", "🔁 Run diagnostics again"))
        self.btn_rediag.clicked.connect(lambda: self.go_to.emit("Diagnostico"))
        for b in (self.btn_restore_txt, self.btn_issue, self.btn_rediag):
            rrow.addWidget(b)
        rrow.addStretch(1)
        self.recode_box.setVisible(False)
        self.body().addWidget(self.recode_box)
        self.body().addStretch(1)
        self._ctl = ProcessController()
        self._ctl.finished.connect(self._done)
        self._retry_without_flag = False
        self._built = True
        self.r_enet.setChecked(True)  # al final: todos los widgets ya existen

    def _browse(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, tr("Llave SSH (id_rsa)", "SSH key (id_rsa)"))
        if p:
            self.key_edit.setText(p)

    def _host(self) -> str:
        if self.r_hotspot.isChecked():
            return HOTSPOT_HOST
        if self.r_custom.isChecked():
            return self.custom.text().strip()
        return self.ctx.state.mgu_ip   # sin IP inventada: viene del diagnostico, del enrollment o del sondeo

    def _plan(self, no_restart_prompt: bool = True):
        return self.ctx.store.plan_first_install(self.key_edit.text().strip(), host=self._host(),
                                                 no_renderer=self.no_renderer.isChecked(),
                                                 no_uplink=self.no_uplink.isChecked(),
                                                 no_restart_prompt=no_restart_prompt)

    def _reeval(self) -> None:
        if not getattr(self, "_built", False):
            return
        key = self.key_edit.text().strip()
        chk = validate_key_path(key) if key else None
        self.ctx.state.key_path = key if (chk and chk.ok) else self.ctx.state.key_path
        if key:
            self.key_status.setText((tr("✓ llave valida", "✓ valid key") + (f" — {chk.warning}" if chk.warning else ""))
                                    if chk.ok else "✗ " + chk.reason)
            self.key_status.setStyleSheet("color:#2fbf71;" if chk.ok else "color:#ff5c5c;")
        host = self._host()
        try:
            self.cmd.setPlainText(self._plan().display if host else tr("(falta la IP de la unidad)", "(unit IP missing)"))
        except Exception as e:
            self.cmd.setPlainText(tr(f"(no disponible: {e})", f"(not available: {e})"))
        d = self.ctx.sm.can_install_store()
        ok = bool(d) and bool(host) and bool(key) and bool(chk and chk.ok) and not self._ctl.running
        self.btn_install.setEnabled(ok)
        self.btn_uninstall.setEnabled(bool(host) and bool(key) and bool(chk and chk.ok) and self.ctx.state.tools_ready)
        if not d:
            self.block.setText("⚠ " + d.reason)
        elif not host:
            self.block.setText(tr("⚠ No se conoce la IP de la unidad: ejecute el diagnostico, use 'Localizar unidad' en "
                                  "Habilitar SSH, elija el hotspot o escriba otra direccion.",
                                  "⚠ The unit's IP is unknown: run the diagnostics, use 'Locate unit' in Enable SSH, "
                                  "choose the hotspot or type another address."))
        else:
            src = self.ctx.state.mgu_ip_source
            self.block.setText("" if (self.r_hotspot.isChecked() or self.r_custom.isChecked() or not src)
                               else f"IP {host} — {ip_source_label(src)}")
        self.recode_box.setVisible(bool(self.ctx.state.coding_missing))

    def install(self) -> None:
        d = self.ctx.sm.can_install_store()
        if not d:
            self.ctx.bus.warn(d.reason)
            return
        self.btn_install.setEnabled(False)
        self.after.setText("")
        try:
            self._ctl.start(self.ctx.store.run_first_install, plan=self._plan(not self._retry_without_flag))
        except Exception as e:
            self.ctx.bus.error(str(e))
            self._reeval()

    def _done(self, result) -> None:
        if result.error:
            self.ctx.bus.error(result.error)   # p. ej. "Llave invalida": antes la consola no decia nada
        hints = hints_for_output(result.lines)
        if any(h.fix_id == "RETRY_WITHOUT_RESTART_FLAG" for h in hints) and not self._retry_without_flag:
            self._retry_without_flag = True
            self.ctx.bus.warn(tr("Doctor: el instalador no acepta --no-restart-prompt; reintento sin la opcion…",
                                 "Doctor: the installer does not accept --no-restart-prompt; retrying without the option…"))
            self.install()
            return
        self._retry_without_flag = False
        if any(h.id == "CODING_DEFAULT" for h in hints):
            # Reintentar no sirve de nada hasta recodificar: se bloquea el boton y se explica que hacer.
            self.ctx.state.coding_missing = True
            self.after.setText(RECODE_HELP)
            for h in hints:
                self.ctx.bus.log("ERROR" if h.id == "CODING_DEFAULT" else "WARN", f"Doctor: {h.title} — {h.detail}")
        elif result.ok:
            self.ctx.state.store_installed = True
            self.after.setText(tr("✓ Store instalado. Reinicie la unidad SOLO cuando el instalador lo indique y confirme el "
                                  "mosaico 'Store' en el coche. Luego instale una app conservadora (Warm-Up / Live Data).",
                                  "✓ Store installed. Restart the unit ONLY when the installer says so, and check for the "
                                  "'Store' tile in the car. Then install a conservative app (Warm-Up / Live Data)."))
            self.ctx.bus.ok(tr("MGU Store instalado.", "MGU Store installed."))
        else:
            self.after.setText(tr("✗ La instalacion no termino bien. Revise la consola.",
                                  "✗ The installation did not finish properly. Check the console."))
            for h in hints:
                self.ctx.bus.warn(f"Doctor: {h.title} — {h.detail}")
        self._reeval()
        self.changed.emit()

    def uninstall(self) -> None:
        if QMessageBox.question(self, tr("Desinstalar MGU Store", "Uninstall MGU Store"),
                                tr("Se desinstalara el Store y sus herramientas de la unidad. ¿Continuar?",
                                   "The Store and its tools will be uninstalled from the unit. Continue?")) != QMessageBox.Yes:
            return
        plan = self.ctx.store.plan_uninstall(self.key_edit.text().strip(), host=self._host())
        self._ctl.start(self.ctx.store.run_uninstall, plan=plan)

    def status(self):
        if self.ctx.state.store_installed:
            return ("ok", tr("Store instalado", "Store installed"))
        if self.ctx.state.ssh_verified:
            return ("warn", tr("Listo para instalar", "Ready to install"))
        return ("pending", tr("Requiere SSH verificado", "Requires verified SSH"))

    def is_unlocked(self) -> bool:
        return self.ctx.state.ssh_verified or self.ctx.state.store_installed

    def on_enter(self) -> None:
        if not self.key_edit.text() and self.ctx.state.key_path:
            self.key_edit.setText(self.ctx.state.key_path)
        self._reeval()
