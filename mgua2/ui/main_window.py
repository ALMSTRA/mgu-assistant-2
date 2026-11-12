"""Ventana principal: navegacion, paginas, consola inferior y acciones globales."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (QApplication, QComboBox, QDockWidget, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout,
                               QWidget)

from .. import APP_NAME, __version__, i18n
from ..core.context import AppContext
from ..i18n import tr
from ..security.redaction import hide_home
from ..services import netinfo
from .pages.apps import AppsPage
from .pages.backup import BackupPage
from .pages.dashboard import DashboardPage
from .pages.enable_ssh import EnableSshPage
from .pages.enet import EnetPage
from .pages.environment import EnvironmentPage
from .pages.logs import LogsPage
from .pages.store import StorePage
from .pages.tools import ToolsPage
from .qt_bridge import LogBridge, Worker
from .theme import STYLESHEET
from .widgets import ConsoleWidget

CARD_KEYS = {"env": "Entorno", "tools": "Herramientas", "diag": "Diagnostico", "backup": "Respaldo",
             "ssh": "Habilitar SSH", "store": "Instalar Store"}


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(f"{APP_NAME} {__version__} — iDrive 7" + ("  [DEMO]" if ctx.demo else ""))
        self.resize(1240, 820)
        self.setStyleSheet(STYLESHEET)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        # Cabecera
        header = QFrame()
        header.setObjectName("Header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 10, 16, 10)
        self.lbl_vehicle = QLabel("")
        hl.addWidget(self.lbl_vehicle, 1)
        self.lbl_admin = QLabel("")
        hl.addWidget(self.lbl_admin)
        if ctx.demo:
            d = QLabel(tr("MODO DEMO — todo simulado, sin coche/ENET/VIN/llaves",
                          "DEMO MODE — everything simulated, no car/ENET/VIN/keys"))
            d.setStyleSheet("color:#f2b134; font-weight:600; margin-left:12px;")
            hl.addWidget(d)
        self.btn_admin = QPushButton(tr("Reiniciar como administrador", "Restart as administrator"))
        self.btn_admin.clicked.connect(self._relaunch_admin)
        hl.addWidget(self.btn_admin)
        self.btn_demo = QPushButton(tr("Modo demo", "Demo mode"))
        self.btn_demo.setVisible(not ctx.demo)
        self.btn_demo.clicked.connect(self._enable_demo)
        hl.addWidget(self.btn_demo)
        # Idioma: los textos se fijan al importar la UI, asi que cambiarlo guarda la preferencia y reinicia.
        self.lang_combo = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.lang_combo.addItem(name, code)
        self.lang_combo.setCurrentIndex(max(0, self.lang_combo.findData(i18n.get_language())))
        self.lang_combo.setToolTip(tr("Idioma (reinicia la ventana)", "Language (restarts the window)"))
        self.lang_combo.currentIndexChanged.connect(self._change_language)   # despues de fijar el actual
        hl.addWidget(self.lang_combo)
        root.addWidget(header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root.addLayout(body, 1)
        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setFixedWidth(230)
        self.nav.currentRowChanged.connect(self._nav_clicked)
        body.addWidget(self.nav)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)

        # Paginas
        self.dashboard = DashboardPage(ctx)
        self.pages = [self.dashboard, EnvironmentPage(ctx), ToolsPage(ctx), EnetPage(ctx), BackupPage(ctx),
                      EnableSshPage(ctx), StorePage(ctx), AppsPage(ctx), LogsPage(ctx)]
        for p in self.pages:
            self.stack.addWidget(p)
            self.nav.addItem(QListWidgetItem(p.nav))
            p.changed.connect(self.refresh_all)
        self.dashboard.go_to.connect(lambda key: self.go(CARD_KEYS.get(key, "Inicio")))
        self.pages[6].go_to.connect(self.go)   # Store -> "Repetir diagnostico"
        self.dashboard.prepare_all.connect(self.prepare_all)
        self.dashboard.run_doctor.connect(lambda: (self.go("Entorno"), self.pages[1].fix_all()))

        # Consola inferior
        self.console = ConsoleWidget()
        self.console.save_requested.connect(self._save_log)
        dock = QDockWidget(tr("Consola de registro", "Log console"), self)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        dock.setWidget(self.console)
        dock.setMinimumHeight(180)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self._bridge = LogBridge(ctx.bus)
        self._bridge.line.connect(self.console.append)
        for ts, lv, m in ctx.bus.history:
            self.console.append(ts, lv, m)

        # Sin el nombre de usuario de Windows en la barra de estado (C:\Users\<nombre> -> ~).
        base, log = hide_home(str(ctx.paths.base)), hide_home(str(ctx.bus.path))
        self.statusBar().showMessage(tr(f"{APP_NAME} {__version__} · datos: {base} · log: {log}",
                                        f"{APP_NAME} {__version__} · data: {base} · log: {log}"))
        self._current = 0
        self.nav.setCurrentRow(0)
        # Retomar: si ya hay un enrollment (SSH habilitado en otra sesion), se carga la llave y la IP de la
        # unidad desde el arranque, asi Inicio y el Store ya saben que solo falta 'Probar SSH'.
        self.pages[5].find()
        if self.pages[5]._enr:
            ctx.bus.info(tr("Enrollment previo detectado: SSH ya habilitado antes. Vaya a 'Habilitar SSH' → 'Probar SSH'; "
                            "no repita respaldo ni flasheo.",
                            "Previous enrollment found: SSH was already enabled. Go to 'Enable SSH' → 'Test SSH'; "
                            "do not repeat the backup or the flash."))
        self.show_page(0)
        self._prep = Worker()
        self._prep.done.connect(self._prepared)
        self._prep.failed.connect(lambda tb: ctx.bus.error(tb))
        ctx.bus.ok(tr("Interfaz lista.", "Interface ready."))

    # -- navegacion ----------------------------------------------------------
    @staticmethod
    def _page_key(p) -> str:
        # Clave de CLASE: StorePage tiene un atributo de instancia `key` (el QLineEdit de la llave) que tapa
        # al de la clase; si una pagina no define clave se usa su `nav`.
        k = getattr(type(p), "key", "")
        return k if isinstance(k, str) and k else p.nav

    def go(self, key: str) -> None:
        """Navega por la clave ESTABLE de la pagina (la de siempre en espanol), no por el texto visible."""
        for i, p in enumerate(self.pages):
            if self._page_key(p) == key:
                self.show_page(i)
                return

    def _nav_clicked(self, row: int) -> None:
        if row < 0 or row == self._current:
            return
        if self.pages[row].is_unlocked():
            self.show_page(row)
        else:
            self.nav.blockSignals(True)
            self.nav.setCurrentRow(self._current)
            self.nav.blockSignals(False)
            self.ctx.bus.warn(tr(f"'{self.pages[row].nav}' aun no esta disponible: complete los pasos anteriores.",
                                 f"'{self.pages[row].nav}' is not available yet: complete the previous steps first."))

    def show_page(self, idx: int) -> None:
        self._current = idx
        self.stack.setCurrentIndex(idx)
        self.nav.blockSignals(True)
        self.nav.setCurrentRow(idx)
        self.nav.blockSignals(False)
        self.pages[idx].on_enter()
        self.refresh_all()

    def refresh_all(self) -> None:
        s = self.ctx.state
        v = s.vehicle
        self.lbl_vehicle.setText(f"<b>{v.display_name}</b> ({v.model_code}) · iDrive 7 / MGU ID7")
        self.lbl_admin.setText(tr("🛡 Administrador", "🛡 Administrator") if s.admin
                               else tr("⚠ sin administrador", "⚠ no admin rights"))
        self.lbl_admin.setStyleSheet("color:#2fbf71;" if s.admin else "color:#f2b134;")
        self.btn_admin.setVisible(not s.admin and not self.ctx.demo)
        for i, p in enumerate(self.pages):
            it = self.nav.item(i)
            unlocked = p.is_unlocked()
            it.setFlags((it.flags() | Qt.ItemIsEnabled) if unlocked else (it.flags() & ~Qt.ItemIsEnabled))
            st, _ = p.status()
            glyph = {"ok": "✓ ", "warn": "! ", "err": "✗ "}.get(st, "")
            it.setText(glyph + p.nav)
        statuses = {"env": self.pages[1].status(), "tools": self.pages[2].status(), "diag": self.pages[3].status(),
                    "backup": self.pages[4].status(), "ssh": self.pages[5].status(), "store": self.pages[6].status()}
        self.dashboard.refresh(statuses)

    # -- acciones globales ----------------------------------------------------
    def prepare_all(self) -> None:
        """Un clic: descarga/verifica herramientas y luego corre el Doctor."""
        self.ctx.bus.info(tr("Preparar todo: descargando y verificando herramientas…",
                             "Prepare everything: downloading and verifying tools…"))
        self.go("Herramientas")
        self.dashboard.btn_prepare.setEnabled(False)
        self._prep.run(self.ctx.tools.install_all, extra_sources=self.ctx.sources.enabled())

    def _prepared(self, status) -> None:
        self.dashboard.btn_prepare.setEnabled(True)
        self.ctx.state.tools_ready = bool(status and status.all_ready)
        self.pages[2].refresh()
        self.ctx.bus.log("OK" if self.ctx.state.tools_ready else "WARN",
                         tr("Herramientas listas.", "Tools ready.") if self.ctx.state.tools_ready
                         else tr("Faltan herramientas; revise la consola.", "Some tools are missing; check the console."))
        self.go("Entorno")
        self.pages[1].run_checks()

    def _relaunch_admin(self) -> None:
        if netinfo.relaunch_as_admin():
            QApplication.instance().quit()

    # -- idioma ----------------------------------------------------------------
    @staticmethod
    def _relaunch_args() -> list[str]:
        """Argumentos para relanzar la app como se abrio, sin un `--lang X` previo (manda la preferencia guardada)."""
        rest: list[str] = []
        skip = False
        for a in sys.argv[1:]:
            if skip:
                skip = False
            elif a == "--lang":
                skip = True
            else:
                rest.append(a)
        return rest if getattr(sys, "frozen", False) else ["-m", "mgua2"] + rest

    def _change_language(self, _index: int) -> None:
        lang = self.lang_combo.currentData()
        if not lang or lang == i18n.get_language():
            return
        from ..core.paths import data_paths
        args = self._relaunch_args()
        try:
            # Siempre en los datos REALES: en modo demo ctx.paths es una carpeta temporal.
            i18n.save(data_paths().ensure().state, lang)
        except Exception as e:
            self.ctx.bus.warn(tr(f"No se pudo guardar el idioma ({e}); se aplica solo a este reinicio.",
                                 f"Could not save the language ({e}); it applies to this restart only."))
            args += ["--lang", lang]
        if self.ctx.demo and "--demo" not in args:
            args.append("--demo")   # demo activada con el boton: el reinicio vuelve en demo
        # Sin congelar se relanza `python -m mgua2` desde la carpeta que contiene el paquete.
        cwd = "" if getattr(sys, "frozen", False) else str(Path(__file__).resolve().parents[2])
        res = QProcess.startDetached(sys.executable, args, cwd)
        if not (res[0] if isinstance(res, tuple) else res):
            self.ctx.bus.error(tr("No se pudo reiniciar la app: cierrela y abrala de nuevo para cambiar el idioma.",
                                  "Could not restart the app: close it and open it again to change the language."))
            return
        QApplication.instance().quit()

    def _enable_demo(self) -> None:
        # Todo lo simulado va a una carpeta temporal: los datos reales (herramientas descargadas,
        # enrollments, respaldos) quedan intactos.
        self.ctx.switch_to_demo()
        self.btn_demo.setVisible(False)
        self.setWindowTitle(f"{APP_NAME} {__version__} — iDrive 7  [DEMO]")
        base, log = hide_home(str(self.ctx.paths.base)), hide_home(str(self.ctx.bus.path))
        self.statusBar().showMessage(tr(f"{APP_NAME} {__version__} · DEMO en {base} · log: {log}",
                                        f"{APP_NAME} {__version__} · DEMO in {base} · log: {log}"))
        self.pages[7]._items = []
        self.show_page(self._current)

    def _save_log(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, tr("Guardar log", "Save log"), "mgua2-consola.log", "Log (*.log *.txt)")
        if p:
            Path(p).write_text(self.ctx.bus.export_text(), encoding="utf-8")
            self.ctx.bus.ok(tr(f"Log guardado en {p}", f"Log saved to {p}"))

    def closeEvent(self, e) -> None:  # noqa: N802
        self.ctx.close()
        super().closeEvent(e)
