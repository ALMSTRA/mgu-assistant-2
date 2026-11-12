"""Catalogo de apps ID7 y preparacion de USB offline."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPushButton, QTableWidget, QTableWidgetItem)

from ...core.models import RiskLevel
from ...i18n import tr
from ...services.store import github_input
from ...services.tools import UPSTREAM
from ..qt_bridge import ProcessController, Worker
from ..theme import RISK_COLORS, RISK_LABEL_ES
from ..widgets import hline, muted, section
from . import BasePage

ACCESS_ES = {"read": tr("lectura", "read-only"), "write": tr("escribe/controla", "writes/controls"),
             "mixed": tr("mixto", "mixed")}


class AppsPage(BasePage):
    title = tr("Apps y herramientas (iDrive 7)", "Apps and tools (iDrive 7)")
    subtitle = tr("Catalogo generado de los manifiestos reales. Verde: lectura. Amarillo: modifica la unidad, red, pista "
                  "o parche reversible. Rojo: escribe/controla el vehiculo. Gris: declara solo ID8. Las apps se instalan "
                  "desde el Store en la pantalla del coche, o sin internet con una memoria USB preparada aqui.",
                  "Catalog generated from the real manifests. Green: read-only. Yellow: modifies the unit, network, track "
                  "or reversible patch. Red: writes to/controls the vehicle. Grey: declares ID8 only. Apps are installed "
                  "from the Store on the car's screen, or offline with a USB stick prepared here.")
    key = "Apps"
    nav = tr("Apps", "Apps")

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        f = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Buscar…", "Search…"))
        self.search.textChanged.connect(self.apply)
        self.risk = QComboBox()
        self.risk.addItem(tr("Todos los riesgos", "All risks"), None)
        for r in (RiskLevel.GREEN, RiskLevel.YELLOW, RiskLevel.RED, RiskLevel.GREY):
            self.risk.addItem(RISK_LABEL_ES[r], r)
        self.risk.currentIndexChanged.connect(self.apply)
        self.only_id7 = QCheckBox(tr("Solo ID7", "ID7 only"))
        self.only_id7.setChecked(True)
        self.only_id7.stateChanged.connect(self.apply)
        reload = QPushButton(tr("Recargar", "Reload"))
        reload.clicked.connect(self.reload)
        f.addWidget(self.search, 2)
        f.addWidget(self.risk, 1)
        f.addWidget(self.only_id7)
        f.addWidget(reload)
        self.body().addLayout(f)
        self.count = muted("")
        self.body().addWidget(self.count)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([tr("Nombre", "Name"), "Repo", "Version", "Gen", tr("Riesgo", "Risk"),
                                              tr("Acceso", "Access"), "Internet", tr("Reinicio", "Restart")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self.detail)
        self.table.setMinimumHeight(300)
        self.body().addWidget(self.table)
        self.det = QLabel(tr("Seleccione una entrada.", "Select an entry."))
        self.det.setWordWrap(True)
        self.det.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body().addWidget(self.det)
        self.body().addWidget(hline())

        self.body().addWidget(section(tr("Memoria USB offline (instalar apps sin internet en el coche)",
                                         "Offline USB stick (install apps in the car without internet)")))
        self.body().addWidget(muted(tr("Prepara en la memoria un repositorio con los paquetes elegidos. En el coche: Store → USB → instalar. "
                                       "La primera app conviene que sea conservadora (Warm-Up o Live Data).",
                                       "Builds a repository with the chosen packages on the stick. In the car: Store → USB → install. "
                                       "Make the first app a conservative one (Warm-Up or Live Data).")))
        urow = QHBoxLayout()
        self.stick = QLineEdit()
        self.stick.setPlaceholderText(tr("Carpeta raiz de la memoria USB (p. ej. E:\\)", "Root folder of the USB stick (e.g. E:\\)"))
        b = QPushButton(tr("Elegir…", "Browse…"))
        b.clicked.connect(self._pick_stick)
        urow.addWidget(QLabel("USB:"))
        urow.addWidget(self.stick, 1)
        urow.addWidget(b)
        self.body().addLayout(urow)
        rrow = QHBoxLayout()
        self.repo_checks: dict[str, QCheckBox] = {}
        for name in ("mgu-store", "idrive7-apps", "idrive-apps", "car-apps"):
            c = QCheckBox(name)
            c.setChecked(name in ("mgu-store", "idrive7-apps"))
            self.repo_checks[name] = c
            rrow.addWidget(c)
        self.usb_extras = QCheckBox(tr("+ fuentes comunitarias activas", "+ active community sources"))
        rrow.addWidget(self.usb_extras)
        self.btn_usb = QPushButton(tr("💽 Preparar USB", "💽 Prepare USB"))
        self.btn_usb.setObjectName("Primary")
        self.btn_usb.clicked.connect(self.prepare_usb)
        rrow.addWidget(self.btn_usb)
        rrow.addStretch(1)
        self.body().addLayout(rrow)
        self.body().addWidget(hline())

        # --- Fuentes comunitarias ---
        self.body().addWidget(section(tr("Fuentes de apps (repositorios GitHub)", "App sources (GitHub repositories)")))
        self.body().addWidget(muted(tr("Las 4 oficiales siempre estan. Activa fuentes de la comunidad para incluirlas en el catalogo "
                                       "y en el USB (tambien puedes anadirlas en el Store del coche, pestana Sources). NO estan "
                                       "verificadas: se clasifican por riesgo igual que las oficiales.",
                                       "The 4 official ones are always there. Enable community sources to include them in the catalog "
                                       "and on the USB stick (you can also add them in the car's Store, Sources tab). They are NOT "
                                       "verified: they get the same risk rating as the official ones.")))
        srow = QHBoxLayout()
        self.btn_discover = QPushButton(tr("🔎 Descubrir nuevas en GitHub", "🔎 Discover new ones on GitHub"))
        self.btn_discover.clicked.connect(self.discover)
        self.custom_repo = QLineEdit()
        self.custom_repo.setPlaceholderText(tr("owner/repo (o URL de GitHub)", "owner/repo (or GitHub URL)"))
        self.btn_add = QPushButton(tr("Anadir", "Add"))
        self.btn_add.clicked.connect(self.add_custom)
        self.btn_fetch = QPushButton(tr("⬇ Descargar fuentes activas y recargar", "⬇ Download active sources and reload"))
        self.btn_fetch.setObjectName("Primary")
        self.btn_fetch.clicked.connect(self.fetch_enabled)
        srow.addWidget(self.btn_discover)
        srow.addWidget(self.custom_repo, 1)
        srow.addWidget(self.btn_add)
        srow.addWidget(self.btn_fetch)
        self.body().addLayout(srow)
        self.src_table = QTableWidget(0, 5)
        self.src_table.setHorizontalHeaderLabels([tr("Activa", "Active"), tr("Repositorio", "Repository"), "★",
                                                  tr("Actualizado", "Updated"), tr("Descripcion", "Description")])
        hh = self.src_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        self.src_table.setWordWrap(False)
        self.src_table.verticalHeader().setVisible(False)
        self.src_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.src_table.setMinimumHeight(260)
        self.body().addWidget(self.src_table)
        self._src_worker = Worker()
        self._src_worker.done.connect(self._sources_fetched)
        self._src_worker.failed.connect(lambda tb: (self.ctx.bus.error(tb), self.btn_fetch.setEnabled(True)))
        self.body().addStretch(1)
        self._items = []
        self._rows = []
        self._worker = Worker()
        self._worker.done.connect(self._loaded)
        self._worker.failed.connect(lambda tb: self.ctx.bus.error(tb))
        self._ctl = ProcessController()
        self._ctl.finished.connect(lambda r: self.ctx.bus.log("OK" if r.ok else "WARN",
                                                              "USB: " + (tr("listo", "done") if r.ok else tr("fallo", "failed"))))

    def reload(self) -> None:
        self.count.setText(tr("Leyendo manifiestos…", "Reading manifests…"))
        self._worker.run(self.ctx.build_catalog)

    def _loaded(self, items) -> None:
        self._items = items or []
        self.apply()

    def apply(self) -> None:
        text = self.search.text().strip().lower()
        rf = self.risk.currentData()
        rows = []
        for it in self._items:
            eff = it.effective_risk()
            if self.only_id7.isChecked() and not it.id7:
                continue
            if text and text not in f"{it.id} {it.name} {it.description} {it.description_es}".lower():
                continue
            if rf is not None and eff != rf:
                continue
            rows.append((it, eff))
        self._rows = rows
        self.table.setRowCount(len(rows))
        yes = tr("si", "yes")
        for r, (it, eff) in enumerate(rows):
            vals = [it.name, it.repo, it.version or "—", "+".join(str(h) for h in it.hmi) or "—", str(eff).upper(),
                    ACCESS_ES.get(str(it.access), str(it.access)), yes if it.requires_internet else "—",
                    yes if it.requires_restart else "—"]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if c == 4:
                    bg, fg = RISK_COLORS[eff]
                    item.setBackground(QColor(bg))
                    item.setForeground(QColor(fg))
                self.table.setItem(r, c, item)
        n = {r: sum(1 for _, e in rows if e == r) for r in RiskLevel}
        self.count.setText(tr(f"{len(rows)} entradas · verde {n[RiskLevel.GREEN]} · amarillo {n[RiskLevel.YELLOW]} · rojo {n[RiskLevel.RED]} · gris {n[RiskLevel.GREY]}",
                              f"{len(rows)} entries · green {n[RiskLevel.GREEN]} · yellow {n[RiskLevel.YELLOW]} · red {n[RiskLevel.RED]} · grey {n[RiskLevel.GREY]}"))

    def detail(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows or rows[0].row() >= len(self._rows):
            return
        it, eff = self._rows[rows[0].row()]
        flags = [t for ok, t in ((it.parked_only, tr("solo estacionado", "parked only")),
                                 (it.track_only, tr("solo pista cerrada", "closed track only")),
                                 (it.clears_faults, tr("puede borrar fallas", "can clear faults")),
                                 (it.reversible_patch, tr("parche reversible", "reversible patch")),
                                 (it.electric_only, tr("solo electrico", "electric only")),
                                 (it.experimental, "experimental")) if ok]
        notes = "".join(f"<li>{n}</li>" for n in it.notes_es)
        desc = it.description_es or it.description
        risk = RISK_LABEL_ES[eff]
        access = ACCESS_ES.get(str(it.access), '')
        gen = '+'.join(str(h) for h in it.hmi)
        deps = ', '.join(it.dependencies) or tr('ninguna', 'none')
        commit = it.commit or tr('n/d', 'n/a')
        compat = it.compatibility_es()
        self.det.setText(
            tr(f"<b>{it.name}</b> <span style='color:#9aa3ad'>({it.id})</span><br>{desc}<br><br>"
               f"<b>Riesgo:</b> {risk} · <b>Acceso:</b> {access} · "
               f"<b>Gen:</b> {gen}<br><b>Dependencias:</b> {deps}<br>"
               f"<b>Repositorio:</b> {it.repo} @ {commit}<br><b>Compatibilidad:</b> {compat}",
               f"<b>{it.name}</b> <span style='color:#9aa3ad'>({it.id})</span><br>{desc}<br><br>"
               f"<b>Risk:</b> {risk} · <b>Access:</b> {access} · "
               f"<b>Gen:</b> {gen}<br><b>Dependencies:</b> {deps}<br>"
               f"<b>Repository:</b> {it.repo} @ {commit}<br><b>Compatibility:</b> {compat}")
            + (tr(f"<br><b>Notas:</b><ul>{notes}</ul>", f"<br><b>Notes:</b><ul>{notes}</ul>") if notes else "")
            + (tr(f"<b>Banderas:</b> {', '.join(flags)}", f"<b>Flags:</b> {', '.join(flags)}") if flags else ""))

    def _pick_stick(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Carpeta raiz de la memoria USB", "Root folder of the USB stick"))
        if d:
            self.stick.setText(d)

    def prepare_usb(self) -> None:
        d = self.ctx.sm.can_prepare_usb()
        if not d:
            self.ctx.bus.warn(d.reason)
            return
        stick = self.stick.text().strip()
        if not stick:
            self.ctx.bus.warn(tr("Indique la carpeta de la memoria USB.", "Choose the USB stick folder."))
            return
        inputs = [github_input(f"{UPSTREAM[n][0]}/{UPSTREAM[n][1]}") for n, c in self.repo_checks.items() if c.isChecked()]
        if self.usb_extras.isChecked():
            inputs += [github_input(r) for r in self.ctx.sources.enabled()]
        plan = self.ctx.store.plan_usb_repo(stick, inputs)
        self.ctx.bus.info("USB: " + plan.display)
        self._ctl.start(self.ctx.store.run_usb_repo, plan=plan)

    # -- fuentes ------------------------------------------------------------------
    def refresh_sources(self) -> None:
        srcs = self.ctx.sources.all_known()
        self.src_table.blockSignals(True)
        self.src_table.setRowCount(len(srcs))
        for r, s in enumerate(srcs):
            chk = QCheckBox()
            chk.setChecked(self.ctx.sources.is_enabled(s.repo))
            chk.stateChanged.connect(lambda st, repo=s.repo: self.ctx.sources.set_enabled(repo, bool(st)))
            self.src_table.setCellWidget(r, 0, chk)
            self.src_table.setItem(r, 1, QTableWidgetItem(s.repo + (tr("  (propia)", "  (custom)") if s.custom else "")))
            self.src_table.setItem(r, 2, QTableWidgetItem(str(s.stars)))
            self.src_table.setItem(r, 3, QTableWidgetItem(s.pushed_at[:10]))
            self.src_table.setItem(r, 4, QTableWidgetItem(s.description + (f"  — {s.note_es}" if s.note_es else "")))
        self.src_table.blockSignals(False)

    def discover(self) -> None:
        if self.ctx.demo:
            self.ctx.bus.info(tr("[demo] descubrimiento simulado: se muestra la instantanea.",
                                 "[demo] simulated discovery: showing the snapshot."))
            self.refresh_sources()
            return
        self.btn_discover.setEnabled(False)
        self.ctx.bus.info(tr("Buscando repositorios del ecosistema en GitHub…", "Searching GitHub for ecosystem repositories…"))
        w = Worker()
        w.done.connect(lambda _: (self.btn_discover.setEnabled(True), self.refresh_sources()))
        w.failed.connect(lambda tb: (self.btn_discover.setEnabled(True), self.ctx.bus.error(tb)))
        self._discover_worker = w
        w.run(self.ctx.sources.discover)

    def add_custom(self) -> None:
        try:
            s = self.ctx.sources.add_custom(self.custom_repo.text())
            self.ctx.sources.set_enabled(s.repo, True)
            self.custom_repo.clear()
            self.ctx.bus.ok(tr(f"Fuente anadida y activada: {s.repo}", f"Source added and enabled: {s.repo}"))
            self.refresh_sources()
        except ValueError as e:
            self.ctx.bus.warn(str(e))

    def fetch_enabled(self) -> None:
        extras = self.ctx.sources.enabled()
        if not extras:
            self.ctx.bus.info(tr("No hay fuentes comunitarias activas; recargando catalogo oficial.",
                                 "No active community sources; reloading the official catalog."))
            self.reload()
            return
        if self.ctx.demo:
            self.ctx.bus.info(tr("[demo] no se descargan fuentes.", "[demo] sources are not downloaded."))
            return
        self.btn_fetch.setEnabled(False)
        self.ctx.bus.info(tr(f"Descargando {len(extras)} fuente(s) comunitaria(s)…", f"Downloading {len(extras)} community source(s)…"))
        self._src_worker.run(lambda: [self.ctx.tools.fetch_source(r) for r in extras])

    def _sources_fetched(self, _result) -> None:
        self.btn_fetch.setEnabled(True)
        self.refresh_sources()
        self.reload()

    def status(self):
        return (("ok", tr(f"{len(self._items)} entradas", f"{len(self._items)} entries")) if self._items
                else ("pending", tr("Catalogo sin cargar", "Catalog not loaded")))

    def on_enter(self) -> None:
        self.refresh_sources()
        if not self._items:
            self.reload()
