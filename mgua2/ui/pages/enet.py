"""Diagnostico ENET de solo lectura (status) con auto-correccion."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from ...core.models import SUPPORTED_BTLD
from ...i18n import tr
from ...services import netinfo
from ...services.doctor import Finding, finding_by_id, hints_for_output
from ...services.sshtool import parse_status
from ..qt_bridge import ProcessController, Worker
from ..widgets import AcceptBox, Card, KV, hline, muted, section
from . import BasePage

def _last_line(tb: str) -> str:
    lines = (tb or "").strip().splitlines()
    return lines[-1] if lines else tr("sin detalle", "no details")


def _ip_source_label(src: str) -> str:
    # `mgu_ip_source` guarda estos textos tal cual porque Habilitar SSH los compara; solo se traducen al mostrarlos.
    return {"diagnostico de hoy": tr("diagnostico de hoy", "today's diagnostics"),
            "sondeo ENET": tr("sondeo ENET", "ENET probe"),
            "enrollment (fecha del flash; puede haber cambiado)":
                tr("enrollment (fecha del flash; puede haber cambiado)",
                   "enrollment (as of the flash; may have changed)")}.get(src, src)


CHECKS = [
    tr("El coche esta estacionado (P) y no puede moverse.", "The car is parked (P) and cannot move."),
    tr("Contacto encendido (Start sin pisar el freno) y la unidad despierta.",
       "Ignition on (Start without pressing the brake) and the head unit awake."),
    tr("Cable ENET (plug OBD-II) conectado y el adaptador USB-Ethernet en la laptop.",
       "ENET cable (OBD-II plug) connected and the USB-Ethernet adapter plugged into the laptop."),
    tr("Laptop conectada a corriente; VPN desactivada.", "Laptop plugged into power; VPN turned off."),
]


class EnetPage(BasePage):
    title = tr("Diagnostico de solo lectura (ENET)", "Read-only diagnostics (ENET)")
    subtitle = tr("Ejecuta unicamente 'status' de la herramienta oficial: lee SVK/BTLD, IP de la unidad y el estado "
                  "del puerto 22. No escribe nada. La propia herramienta rechaza unidades NBT/EVO. Si la unidad no "
                  "responde, el Doctor reintenta con pasarela fija y revisa el adaptador.",
                  "Runs only the official tool's 'status' command: reads SVK/BTLD, the head unit's IP and the state "
                  "of port 22. It writes nothing. The tool itself rejects NBT/EVO units. If the unit does not "
                  "respond, the Doctor retries with a fixed gateway and checks the adapter.")
    key = "Diagnostico"
    nav = tr("Diagnostico", "Diagnostics")

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        # Un solo boton 'Acepto' tras leer la lista (antes: una casilla por punto).
        self.accept = AcceptBox(tr("Lista previa (lea y acepte)", "Pre-check list (read and accept)"), CHECKS,
                                tr("✓ Lei la lista y acepto", "✓ I have read the list and accept"))
        self.accept.accepted_changed.connect(lambda _v: self._reeval())
        self.body().addWidget(self.accept)

        self.adapter_lbl = muted(tr("Adaptador ENET: comprobando…", "ENET adapter: checking…"))
        self.body().addWidget(self.adapter_lbl)

        adv = QHBoxLayout()
        adv.addWidget(QLabel(tr("Pasarela:", "Gateway:")))
        self.gateway = QLineEdit()
        self.gateway.setPlaceholderText(tr("auto (descubrimiento UDP) — p. ej. 169.254.254.36",
                                           "auto (UDP discovery) — e.g. 169.254.254.36"))
        adv.addWidget(self.gateway, 1)
        self.body().addLayout(adv)

        row = QHBoxLayout()
        self.btn_run = QPushButton(tr("▶ Ejecutar diagnostico (solo lectura)", "▶ Run diagnostics (read-only)"))
        self.btn_run.setObjectName("Primary")
        self.btn_run.clicked.connect(lambda: self.run(None))
        self.btn_cancel = QPushButton(tr("Cancelar", "Cancel"))
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(lambda: self._ctl.cancel())
        row.addWidget(self.btn_run)
        row.addWidget(self.btn_cancel)
        row.addStretch(1)
        self.body().addLayout(row)
        self.body().addWidget(hline())

        self.body().addWidget(section(tr("Resultado", "Result")))
        card = Card()
        self.kv_gw = KV(tr("Unidad por ENET", "Unit over ENET"))
        self.kv_mgu = KV(tr("Tipo de unidad", "Unit type"))
        self.kv_btld = KV("BTLD")
        self.kv_sw = KV("Software (SWFL)")
        self.kv_cafd = KV(tr("Codificacion (CAFD)", "Coding (CAFD)"))
        self.kv_ip = KV(tr("IP de la unidad", "Unit IP"))
        self.kv_p22 = KV(tr("Puerto 22 (SSH)", "Port 22 (SSH)"))
        self.kv_vin = KV(tr("VIN (enmascarado)", "VIN (masked)"))
        for kv in (self.kv_gw, self.kv_mgu, self.kv_btld, self.kv_sw, self.kv_cafd, self.kv_ip, self.kv_p22, self.kv_vin):
            card.lay.addWidget(kv)
        self.body().addWidget(card)
        self._hints_box = QVBoxLayout()
        self.body().addLayout(self._hints_box)
        self.body().addStretch(1)

        self._ctl = ProcessController()
        self._ctl.finished.connect(self._finished)
        self._net = Worker()
        self._net.done.connect(self._adapter_info)
        self._net.failed.connect(lambda tb: self.ctx.bus.warn(
            tr("Adaptadores: fallo al listarlos — ", "Adapters: could not list them — ") + _last_line(tb)))
        self._link = Worker()                 # informe del enlace ENET cuando el coche no responde
        self._link.done.connect(self._link_done)
        self._link.failed.connect(lambda tb: self.ctx.bus.warn(
            tr("Doctor (enlace ENET): fallo el informe — ", "Doctor (ENET link): the report failed — ") + _last_line(tb)))
        self._retried = False
        self._reeval()   # el boton nace bloqueado hasta aceptar la lista

    def _reeval(self) -> None:
        d = self.ctx.sm.can_run_diagnostic()
        self.btn_run.setEnabled(bool(d) and self.accept.accepted and not self._ctl.running)
        self.btn_run.setToolTip("" if d else d.reason)

    def _adapter_info(self, adapters) -> None:
        if self.ctx.demo:
            self.adapter_lbl.setText(tr("Adaptador ENET (demo): Ethernet 2 · 169.254.10.20",
                                        "ENET adapter (demo): Ethernet 2 · 169.254.10.20"))
            return
        enet = [a for a in (adapters or []) if a.looks_enet]
        if enet:
            a = enet[0]
            self.adapter_lbl.setText(tr(f"✓ Adaptador ENET: {a.name} ({a.description}) · {', '.join(a.link_local)}",
                                        f"✓ ENET adapter: {a.name} ({a.description}) · {', '.join(a.link_local)}"))
            self.adapter_lbl.setStyleSheet("color:#2fbf71;")
        else:
            self.adapter_lbl.setText(tr("! Ningun adaptador cableado con 169.254.x.x todavia. Conecte el ENET con el contacto "
                                        "encendido y espere ~30-60 s; luego pulse 'Ejecutar'.",
                                        "! No wired adapter with a 169.254.x.x address yet. Connect the ENET cable with the "
                                        "ignition on and wait ~30-60 s; then press 'Run diagnostics'."))
            self.adapter_lbl.setStyleSheet("color:#f2b134;")

    def run(self, gateway: str | None) -> None:
        d = self.ctx.sm.can_run_diagnostic()
        if not d:
            self.ctx.bus.warn(d.reason)
            return
        self._clear_hints()
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        gw = gateway or (self.gateway.text().strip() or None)
        self._ctl.start(self.ctx.sshtool.run_status, gateway=gw)

    def _finished(self, result) -> None:
        self.btn_cancel.setEnabled(False)
        if result.error:
            self.ctx.bus.error(result.error)
        st = parse_status(result.lines)
        s = self.ctx.state
        s.diagnostic_done = True
        s.diagnostic_rc = result.returncode
        s.gateway_found, s.is_mgu, s.btld = st.gateway_found, st.is_mgu, st.btld
        s.software_version, s.ssh_port_open = st.software_version, st.ssh_port_open
        s.cafd, s.coding_missing = st.cafd, st.coding_missing
        if st.mgu_ip:   # una IP conocida nunca se borra por un diagnostico fallido (paso en el coche)
            s.mgu_ip, s.mgu_ip_source = st.mgu_ip, "diagnostico de hoy"
        if st.gateway_ip:
            s.gateway_ip = st.gateway_ip
        if st.is_mgu and (st.gateway_ip or st.mgu_ip):
            self.ctx.sshtool.remember_car(st.gateway_ip, st.mgu_ip)   # para reintentar con ESTA pasarela
        s.vin_masked = st.vin_masked or getattr(result, "vin_masked", "") or s.vin_masked
        if getattr(result, "vin", ""):
            s.vin = result.vin   # solo en memoria: evita pedirlo a mano para `enable --vin`

        self.kv_gw.set(tr("encontrada", "found") if st.gateway_found else tr("NO respondio", "did NOT respond"),
                       "ok" if st.gateway_found else "err")
        if st.nbt_rejected:
            self.kv_mgu.set(tr("NBT/EVO (fuera de alcance)", "NBT/EVO (out of scope)"), "err")
        elif st.btld_unsupported:
            self.kv_mgu.set(tr("MGU, pero BTLD fuera del catalogo soportado (el tool se niega)",
                               "MGU, but the BTLD is not in the supported catalog (the tool refuses)"), "err")
        elif st.is_mgu:
            self.kv_mgu.set("MGU (iDrive 7/8)", "ok")
        else:
            self.kv_mgu.set("—")
        self.kv_btld.set((st.btld or "—") + (tr("  ✓ soportado", "  ✓ supported") if st.btld_supported
                                             else (tr(f"  ✗ no es {SUPPORTED_BTLD}", f"  ✗ not {SUPPORTED_BTLD}")
                                                   if st.btld else "")),
                         "ok" if st.btld_supported else ("err" if st.btld else ""))
        self.kv_sw.set(st.software_version or "—")
        if st.coding_missing:
            self.kv_cafd.set(tr(f"BORRADA ({st.cafd}) — recodificar HU_MGU por VO (E-Sys) antes del Store",
                                f"WIPED ({st.cafd}) — recode HU_MGU to the VO (E-Sys) before the Store"), "err")
        elif st.cafd:
            self.kv_cafd.set(tr(f"{st.cafd}  ✓ presente", f"{st.cafd}  ✓ present"), "ok")
        else:
            self.kv_cafd.set("—")
        if st.mgu_ip:
            self.kv_ip.set(st.mgu_ip, "ok")
        elif s.mgu_ip:
            src = _ip_source_label(s.mgu_ip_source) or tr("anterior", "previous")
            self.kv_ip.set(tr(f"{s.mgu_ip} ({src}; hoy la unidad no respondio)",
                              f"{s.mgu_ip} ({src}; the unit did not respond today)"), "warn")
        else:
            self.kv_ip.set("—")
        if st.ssh_persistent:
            self.kv_p22.set(tr("abierto · SSH persistente (modo debug OFF, sin DTC B7F8E5)",
                               "open · persistent SSH (debug mode OFF, no DTC B7F8E5)"), "ok")
        elif st.ssh_port_open:
            self.kv_p22.set(tr("abierto (SSH activo)", "open (SSH active)"), "ok")
        elif st.ssh_port_open is False:
            self.kv_p22.set(tr("cerrado (normal antes de habilitar)", "closed (normal before enabling)"))
        else:
            self.kv_p22.set("—")
        self.kv_vin.set(s.vin_masked or "—")

        # Doctor: pistas + auto-correccion (un reintento con pasarela fija).
        hints = hints_for_output(result.lines)
        for h in hints:
            if h.fix_id == "RETRY_FIXED_GATEWAY" and not self._retried and not self.gateway.text().strip():
                self._retried = True
                gw = self.ctx.sshtool.retry_gateway(s.gateway_ip)
                self.ctx.bus.warn(tr(f"Doctor: sin respuesta por difusion UDP; reintento con la ultima pasarela conocida {gw}…",
                                     f"Doctor: no answer to the UDP broadcast; retrying with the last known gateway {gw}…"))
                self.run(gw)
                return
            self._show_hint(h)
        self._retried = False
        if not st.gateway_found or any(h.id == "GATEWAY_TIMEOUT" for h in hints):
            # Sin tocar el coche: adaptador con 169.254.x.x, vecinos ARP y puerto 22 de las IPs candidatas.
            self.ctx.bus.info(tr("Doctor: revisando el enlace ENET (adaptador, vecinos ARP y puerto 22)…",
                                 "Doctor: checking the ENET link (adapter, ARP neighbors and port 22)…"))
            self._link.run(self._link_report)
        if st.coding_missing:
            f = finding_by_id("CODING_DEFAULT")
            if f:
                self._show_hint(f)
                self.ctx.bus.warn(f"Doctor: {f.title} — {f.detail}")
        if s.id7_confirmed and s.btld_supported:
            if st.coding_missing:
                self.ctx.bus.warn(tr("Diagnostico: unidad MGU con BTLD soportado, pero la codificacion esta borrada "
                                     "(CAFD FFFFFFFF). El Store se bloquea hasta recodificar HU_MGU y repetir este diagnostico.",
                                     "Diagnostics: MGU unit with a supported BTLD, but the coding is wiped "
                                     "(CAFD FFFFFFFF). The Store stays blocked until HU_MGU is recoded and these "
                                     "diagnostics are run again."))
            else:
                self.ctx.bus.ok(tr("Diagnostico: unidad MGU confirmada con BTLD soportado. Puede continuar al respaldo.",
                                   "Diagnostics: MGU unit confirmed with a supported BTLD. You can continue to the backup."))
        self._reeval()
        self.changed.emit()

    def _relaunch_admin(self) -> None:
        """Relanza elevado y cierra esta instancia (sin propagar SystemExit en un slot Qt)."""
        try:
            self.ctx.doctor.fix("RELAUNCH_ADMIN")
        except SystemExit:
            from PySide6.QtWidgets import QApplication
            QApplication.instance().quit()

    def _clear_hints(self) -> None:
        while self._hints_box.count():
            it = self._hints_box.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

    def _show_hint(self, h) -> None:
        card = Card()
        row = QHBoxLayout()
        color = {"warn": "#f2b134", "error": "#ff5c5c"}.get(h.severity, "#9aa3ad")
        lbl = QLabel(f"<span style='color:{color}'><b>{h.title}</b></span> — {h.detail}")
        lbl.setWordWrap(True)
        row.addWidget(lbl, 1)
        if h.fix_id == "RELAUNCH_ADMIN" or (h.id == "ENET_NO_GATEWAY" and not netinfo.is_admin() and not self.ctx.demo):
            b = QPushButton(tr("Reiniciar como administrador", "Restart as administrator"))
            b.clicked.connect(self._relaunch_admin)
            row.addWidget(b)
        if h.fix_id == "RETRY_FIXED_GATEWAY":
            gw = self.ctx.sshtool.retry_gateway(self.ctx.state.gateway_ip)
            b = QPushButton(tr(f"Reintentar con pasarela {gw}", f"Retry with gateway {gw}"))
            b.clicked.connect(lambda _c=False, g=gw: self.run(g))
            row.addWidget(b)
        if h.fix_id == "OPEN_PREFLIGHT_FOLDER":
            b = QPushButton(h.fix_label or tr("Abrir respaldo preflight", "Open preflight backup"))
            b.clicked.connect(lambda: self.ctx.doctor.fix("OPEN_PREFLIGHT_FOLDER"))
            row.addWidget(b)
        card.lay.addLayout(row)
        self._hints_box.addWidget(card)

    def _link_report(self) -> dict:
        """(Hilo) Estado del enlace ENET sin tocar el coche."""
        if self.ctx.demo:
            return {"demo": True}
        s = self.ctx.state
        adapters = netinfo.list_adapters()
        exclude = {s.gateway_ip} if s.gateway_ip else set()
        probes = self.ctx.sshtool.locate_unit([s.mgu_ip] if s.mgu_ip else [], exclude=exclude)
        return {"demo": False, "enet": [a for a in adapters if a.looks_enet],
                "wired_up": [a for a in adapters if a.is_up and not a.looks_enet], "probes": probes}

    def _link_done(self, rep) -> None:
        if not rep or rep.get("demo"):
            return
        s = self.ctx.state
        parts: list[str] = []
        if rep["enet"]:
            a = rep["enet"][0]
            parts.append(tr(f"Adaptador ENET: {a.name} con {', '.join(a.link_local)} (enlace activo).",
                            f"ENET adapter: {a.name} with {', '.join(a.link_local)} (link up)."))
        else:
            wired = ", ".join(a.name for a in rep.get("wired_up") or [])
            parts.append(tr("Ningun adaptador cableado tiene direccion 169.254.x.x: cable/adaptador sin enlace, o Windows "
                            "aun no la asigno (tarda 30-60 s tras conectar).",
                            "No wired adapter has a 169.254.x.x address: the cable/adapter has no link, or Windows "
                            "has not assigned it yet (it takes 30-60 s after connecting).")
                         + (tr(f" Cableados activos: {wired}.", f" Active wired adapters: {wired}.") if rep.get("wired_up") else ""))
        probes = rep.get("probes") or []
        open_ips = [ip for ip, r in probes if r == "open"]
        refused = [ip for ip, r in probes if r == "refused"]
        if probes:
            parts.append(tr("Sondeo del puerto 22: ", "Port 22 probe: ") + ", ".join(f"{ip}={r}" for ip, r in probes) + ".")
        if len(open_ips) == 1:
            s.mgu_ip, s.mgu_ip_source = open_ips[0], "sondeo ENET"   # valor interno: Habilitar SSH lo compara
            self.kv_ip.set(tr(f"{open_ips[0]} (sondeo ENET: SSH abierto)", f"{open_ips[0]} (ENET probe: SSH open)"), "ok")
            parts.append(tr(f"Unidad localizada en {open_ips[0]} con SSH abierto: puede ir a 'Habilitar SSH' → 'Probar SSH' "
                            "aunque la pasarela no haya respondido.",
                            f"Unit found at {open_ips[0]} with SSH open: you can go to 'Enable SSH' → 'Test SSH' "
                            "even though the gateway did not respond."))
        elif open_ips:
            parts.append(tr(f"Varias IPs con el puerto 22 abierto ({', '.join(open_ips)}): elija la de la unidad en el Store "
                            "('Otra direccion').",
                            f"Several IPs have port 22 open ({', '.join(open_ips)}): pick the head unit's one in the Store "
                            "('Other address')."))
        elif refused:
            parts.append(tr(f"Host vivo con el puerto 22 cerrado en {', '.join(refused)}: si es la unidad, SSH no esta activo "
                            "(Enable, sin flasheo; necesita que la pasarela responda).",
                            f"Live host with port 22 closed at {', '.join(refused)}: if it is the head unit, SSH is not "
                            "active (Enable, no flash; the gateway must respond)."))
        elif rep["enet"]:
            parts.append(tr("Nadie responde en el enlace: el coche esta dormido o la unidad aun arranca. Contacto encendido "
                            "(Start sin pisar el freno), espere 1 min y repita.",
                            "Nothing responds on the link: the car is asleep or the unit is still booting. Ignition on "
                            "(Start without pressing the brake), wait 1 min and try again."))
        msg = " ".join(parts)
        self.ctx.bus.warn(tr("Doctor (enlace ENET): ", "Doctor (ENET link): ") + msg)
        self._show_hint(Finding("ENET_LINK", "warn", tr("Estado del enlace ENET", "ENET link status"), msg))
        self.changed.emit()

    def status(self):
        s = self.ctx.state
        if s.id7_confirmed and s.btld_supported:
            if s.coding_missing:
                return ("warn", tr(f"MGU · BTLD {s.btld} · ⚠ codificacion BORRADA: recodificar HU_MGU",
                                   f"MGU · BTLD {s.btld} · ⚠ coding WIPED: recode HU_MGU"))
            return ("ok", tr(f"MGU confirmada · BTLD {s.btld} · IP {s.mgu_ip or '?'}",
                             f"MGU confirmed · BTLD {s.btld} · IP {s.mgu_ip or '?'}"))
        if s.diagnostic_done:
            return ("err", tr("La unidad no respondio o no es MGU", "The unit did not respond or is not an MGU"))
        return ("pending", tr("Pendiente (solo lectura)", "Pending (read-only)"))

    def is_unlocked(self) -> bool:
        return bool(self.ctx.sm.can_run_diagnostic())

    def on_enter(self) -> None:
        self._reeval()
        self._net.run(lambda: [] if self.ctx.demo else netinfo.list_adapters())
