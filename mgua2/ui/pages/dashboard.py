"""Inicio: vehiculo, estado general y acciones automaticas."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QPushButton

from ...core.models import id7_vehicles
from ...i18n import tr
from ..widgets import StatusCard, hline, muted, section
from . import BasePage

ORDER = [
    tr("1) Preparar: descarga y verifica las herramientas oficiales (automatico).",
       "1) Prepare: downloads and verifies the official tools (automatic)."),
    tr("2) Diagnostico de SOLO lectura por ENET: confirma MGU ID7 y BTLD soportado.",
       "2) READ-ONLY diagnostics over ENET: confirms MGU ID7 and a supported BTLD."),
    tr("3) Respaldo de codificacion (preflight, solo lectura) + lista de seguridad.",
       "3) Coding backup (preflight, read-only) + safety checklist."),
    tr("4) Habilitar SSH una sola vez en la GUI oficial (Flash + Enable) y verificar.",
       "4) Enable SSH once in the official GUI (Flash + Enable) and verify it."),
    tr("4b) Recodificar HU_MGU por orden de vehiculo (E-Sys): el flasheo borra la codificacion y sin ella el Store no instala. "
       "Repetir el diagnostico para comprobar el CAFD.",
       "4b) Recode HU_MGU to the vehicle order (E-Sys): flashing wipes the coding and without it the Store will not "
       "install. Run the diagnostics again to check the CAFD."),
    tr("5) Instalar MGU Store (por Wi-Fi del coche o ENET) y reiniciar cuando lo pida.",
       "5) Install MGU Store (over the car's Wi-Fi or ENET) and restart when asked."),
    tr("6) Instalar una app conservadora desde la pantalla (Warm-Up / Live Data) o por USB.",
       "6) Install a low-risk app from the screen (Warm-Up / Live Data) or via USB."),
    tr("¿SSH ya habilitado de antes? La app detecta el enrollment: vaya directo a 'Habilitar SSH' → Probar SSH → Store. "
       "No repita el respaldo ni el flasheo.",
       "SSH already enabled before? The app detects the enrollment: go straight to 'Enable SSH' → Test SSH → Store. "
       "Do not repeat the backup or the flash."),
]


class DashboardPage(BasePage):
    title = "MGU Assistant 2 — iDrive 7"
    subtitle = tr("Instalador y asistente automatizado para BMW con iDrive 7 (MGU ID7). Descarga y verifica todo "
                  "lo necesario, diagnostica en solo lectura, respalda la codificacion y guia el unico paso manual "
                  "(habilitar SSH) antes de instalar MGU Store y sus apps.",
                  "Automated installer and assistant for BMWs with iDrive 7 (MGU ID7). It downloads and verifies "
                  "everything needed, runs read-only diagnostics, backs up the coding and guides you through the only "
                  "manual step (enabling SSH) before installing MGU Store and its apps.")
    key = "Inicio"
    nav = tr("Inicio", "Home")
    go_to = Signal(str)        # nav de la pagina destino
    prepare_all = Signal()
    run_doctor = Signal()

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("<b>Vehiculo:</b>", "<b>Vehicle:</b>")))
        self.vehicle = QComboBox()
        for v in id7_vehicles():
            self.vehicle.addItem(f"{v.display_name}  ·  {v.years}", v.key)
        self.vehicle.currentIndexChanged.connect(self._on_vehicle)
        row.addWidget(self.vehicle, 1)
        self.body().addLayout(row)
        self._vnote = muted("")
        self.body().addWidget(self._vnote)

        actions = QHBoxLayout()
        self.btn_prepare = QPushButton(tr("⚡ Preparar todo (automatico)", "⚡ Prepare everything (automatic)"))
        self.btn_prepare.setObjectName("Primary")
        self.btn_prepare.clicked.connect(self.prepare_all.emit)
        self.btn_doctor = QPushButton(tr("🩺 Doctor: revisar y corregir", "🩺 Doctor: check and fix"))
        self.btn_doctor.clicked.connect(self.run_doctor.emit)
        actions.addWidget(self.btn_prepare)
        actions.addWidget(self.btn_doctor)
        actions.addStretch(1)
        self.body().addLayout(actions)

        self.body().addWidget(section(tr("Estado", "Status")))
        grid = QGridLayout()
        grid.setSpacing(10)
        self.cards: dict[str, StatusCard] = {}
        for i, (key, title) in enumerate([("env", tr("Entorno", "Environment")), ("tools", tr("Herramientas", "Tools")),
                                           ("diag", tr("Diagnostico", "Diagnostics")), ("backup", tr("Respaldo", "Backup")),
                                           ("ssh", "SSH"), ("store", "Store")]):
            c = StatusCard(title)
            c.clicked.connect(lambda k=key: self.go_to.emit(k))
            self.cards[key] = c
            grid.addWidget(c, i // 3, i % 3)
        self.body().addLayout(grid)

        self.body().addWidget(hline())
        self.body().addWidget(section(tr("Orden recomendado", "Recommended order")))
        for line in ORDER:
            self.body().addWidget(muted(line))
        self.body().addStretch(1)
        self._on_vehicle()

    def _on_vehicle(self) -> None:
        key = self.vehicle.currentData()
        for v in id7_vehicles():
            if v.key == key:
                self.ctx.sm.select_vehicle(v)
                self._vnote.setText(v.note + tr("  La compatibilidad real la confirma el diagnostico (SVK/BTLD).",
                                                "  Actual compatibility is confirmed by the diagnostics (SVK/BTLD)."))
                break
        self.changed.emit()

    def refresh(self, statuses: dict[str, tuple[str, str]]) -> None:
        for k, (st, text) in statuses.items():
            if k in self.cards:
                self.cards[k].set_state(st, text)
