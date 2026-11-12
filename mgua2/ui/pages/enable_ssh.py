"""Habilitar SSH (GUI oficial, una sola vez) y verificar la conexion."""
from __future__ import annotations

import webbrowser
from pathlib import Path

from PySide6.QtWidgets import (QComboBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout)

from ...core.models import HOTSPOT_HOST
from ...i18n import tr
from ...services.doctor import hints_for_output
from ..qt_bridge import ProcessController, Worker
from ..widgets import KV, Card, hline, muted, section
from . import BasePage

STEPS = [
    tr("1. Se abre MGU-SSH.exe (oficial, prebuilt) como administrador.",
       "1. MGU-SSH.exe (official, prebuilt) opens as administrator."),
    tr("2. Pulse <b>Detect VIN</b> y compruebe que coincide con el coche.",
       "2. Click <b>Detect VIN</b> and check that it matches the car."),
    tr("3. Variante: <b>id7</b>. Deje marcado 'Turn debug mode off after enabling'. NO marque 'unique key'.",
       "3. Variant: <b>id7</b>. Leave 'Turn debug mode off after enabling' checked. Do NOT check 'unique key'."),
    tr("4. Pulse <b>Flash + Enable</b> una sola vez y espere sin desconectar nada hasta 'SSH OK as root' (en un X4 M F98 tardo ~3 min).",
       "4. Click <b>Flash + Enable</b> only once and wait, without disconnecting anything, until 'SSH OK as root' "
       "(it took ~3 min on an X4 M F98)."),
    tr("5. <b>El flasheo borra la codificacion del HU (CAFD)</b>: la pantalla queda de fabrica y el Store NO se instalara hasta "
       "recodificar HU_MGU por orden de vehiculo (E-Sys) y reiniciar la unidad. Repita despues el diagnostico: debe volver un CAFD real.",
       "5. <b>Flashing wipes the head unit coding (CAFD)</b>: the screen is left at factory defaults and the Store will NOT "
       "install until you recode HU_MGU from the vehicle order (E-Sys) and restart the unit. Then run the diagnostics again: "
       "they must return a real CAFD."),
    tr("6. Vuelva aqui: 'Buscar enrollment' y 'Probar SSH'. Si la unidad se reinicio, su huella SSH cambia: el Doctor limpia "
       "known_hosts y reintenta solo.",
       "6. Come back here: 'Find enrollment' and 'Test SSH'. If the unit restarted, its SSH fingerprint changes: the Doctor "
       "clears known_hosts and retries on its own."),
]

# `state.mgu_ip_source` guarda el origen en espanol porque se compara (ver _show_ip); solo se traduce al mostrarlo.
IP_SOURCE_EN = {
    "diagnostico de hoy": "today's diagnostics",
    "sondeo ENET": "ENET probe",
    "enrollment (fecha del flash; puede haber cambiado)": "enrollment (as of the flash; may have changed)",
}


def ip_source_label(src: str) -> str:
    """Texto visible del origen de la IP de la unidad."""
    if not src:
        return tr("origen desconocido", "unknown source")
    return tr(src, IP_SOURCE_EN.get(src, src))


class EnableSshPage(BasePage):
    title = tr("Habilitar SSH (una sola vez)", "Enable SSH (one time only)")
    subtitle = tr("Este es el unico paso que se hace a mano, en la GUI oficial. Tras un Flash + Enable correcto, SSH queda "
                  "permanente (sin DTC B7F8E5). No lo repita 'por si acaso'. Aqui se detecta la llave creada y se prueba "
                  "la conexion sin leer la llave privada. Si SSH ya estaba habilitado de antes, basta con 'Buscar "
                  "enrollment' y 'Probar SSH': no hay que repetir respaldo ni flasheo.",
                  "This is the only step done by hand, in the official GUI. After a successful Flash + Enable, SSH stays "
                  "permanent (no DTC B7F8E5). Do not repeat it 'just in case'. This page detects the key that was created "
                  "and tests the connection without reading the private key. If SSH was already enabled before, 'Find "
                  "enrollment' and 'Test SSH' are enough: no need to repeat the backup or the flash.")
    key = "Habilitar SSH"
    nav = tr("Habilitar SSH", "Enable SSH")

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        self.block = QLabel("")
        self.block.setWordWrap(True)
        self.block.setStyleSheet("color:#ff9f6b;")
        self.body().addWidget(self.block)
        g = QGroupBox(tr("Pasos en la GUI oficial", "Steps in the official GUI"))
        gl = QVBoxLayout(g)
        for s in STEPS:
            l = QLabel(s)
            l.setWordWrap(True)
            gl.addWidget(l)
        self.body().addWidget(g)
        row = QHBoxLayout()
        self.btn_gui = QPushButton(tr("🛠 Abrir GUI oficial MGU-SSH (administrador)", "🛠 Open official MGU-SSH GUI (administrator)"))
        self.btn_gui.setObjectName("Primary")
        self.btn_gui.clicked.connect(self._open_gui)
        row.addWidget(self.btn_gui)
        row.addStretch(1)
        self.body().addLayout(row)
        self.ver = muted("")
        self.body().addWidget(self.ver)
        self.body().addWidget(hline())

        self.body().addWidget(section(tr("Verificacion", "Verification")))
        card = Card()
        self.kv_enr = KV("Enrollment")
        self.kv_key = KV(tr("Llave (id_rsa)", "Key (id_rsa)"))
        self.kv_fp = KV(tr("Huella publica", "Public fingerprint"))
        self.kv_ip = KV(tr("IP registrada", "Recorded IP"))
        self.kv_test = KV(tr("Prueba SSH", "SSH test"))
        for kv in (self.kv_enr, self.kv_key, self.kv_fp, self.kv_ip, self.kv_test):
            card.lay.addWidget(kv)
        self.body().addWidget(card)
        vrow = QHBoxLayout()
        self.btn_find = QPushButton(tr("Buscar enrollment", "Find enrollment"))
        self.btn_find.clicked.connect(self.find)
        self.btn_open = QPushButton(tr("Abrir carpeta", "Open folder"))
        self.btn_open.clicked.connect(self._open_folder)
        vrow.addWidget(self.btn_find)
        vrow.addWidget(self.btn_open)
        vrow.addWidget(QLabel(tr("Probar por:", "Test via:")))
        self.host = QComboBox()
        self.host.addItem(tr("IP ENET de la unidad", "Unit ENET IP"), "enet")
        self.host.addItem(tr(f"Hotspot Wi-Fi del coche ({HOTSPOT_HOST})", f"Car Wi-Fi hotspot ({HOTSPOT_HOST})"), "hotspot")
        vrow.addWidget(self.host)
        self.btn_test = QPushButton(tr("🔑 Probar SSH", "🔑 Test SSH"))
        self.btn_test.setObjectName("Primary")
        self.btn_test.clicked.connect(self.test)
        vrow.addWidget(self.btn_test)
        self.btn_locate = QPushButton(tr("🔎 Localizar unidad", "🔎 Locate unit"))
        self.btn_locate.setToolTip(tr("Sondea el puerto 22 en las IPs conocidas y en los vecinos ARP del enlace ENET: "
                                      "encuentra la unidad aunque haya cambiado de IP o la pasarela no responda.",
                                      "Probes port 22 on the known IPs and on the ARP neighbors of the ENET link: "
                                      "finds the unit even if its IP changed or the gateway does not respond."))
        self.btn_locate.clicked.connect(lambda: self._locate(then_test=False))
        vrow.addWidget(self.btn_locate)
        vrow.addStretch(1)
        self.body().addLayout(vrow)
        self.body().addWidget(muted(tr("Guarde una copia CIFRADA de la carpeta de enrollment: contiene su llave privada.",
                                       "Keep an ENCRYPTED copy of the enrollment folder: it contains your private key.")))
        self.body().addWidget(hline())

        self.body().addWidget(section(tr("Reparacion sin flasheo (solo si SSH dejo de responder)",
                                         "Repair without flashing (only if SSH stopped responding)")))
        self.body().addWidget(muted(tr("⚠ 'Enable' NO flashea ni toca la codificacion, pero reactiva el modo debug y eso "
                                       "resetea el perfil de conductor, la memoria del asiento y la sesion BMW ID (reportado "
                                       "en el issue #10 de upstream). Uselo solo si el puerto 22 esta cerrado; 'Persist' no "
                                       "reactiva nada.",
                                       "⚠ 'Enable' does NOT flash or touch the coding, but it turns debug mode back on, which "
                                       "resets the driver profile, the seat memory and the BMW ID session (reported in "
                                       "upstream issue #10). Use it only if port 22 is closed; 'Persist' turns nothing back on.")))
        rrow = QHBoxLayout()
        rrow.addWidget(QLabel("VIN:"))
        self.vin = QLineEdit()
        self.vin.setPlaceholderText(tr("vacio = usar el VIN del diagnostico/enrollment (siempre censurado en el log)",
                                       "empty = use the VIN from the diagnostics/enrollment (always masked in the log)"))
        self.vin.setEchoMode(QLineEdit.Password)
        rrow.addWidget(self.vin, 1)
        self.btn_enable = QPushButton(tr("Enable (re-abrir SSH)", "Enable (reopen SSH)"))
        self.btn_enable.setToolTip(tr("Re-enrola sin flashear. Reactiva el modo debug: resetea perfil, asiento y sesion BMW ID.",
                                      "Re-enrolls without flashing. Turns debug mode back on: resets profile, seat and BMW ID "
                                      "session."))
        self.btn_enable.clicked.connect(self._enable)
        self.btn_persist = QPushButton(tr("Persist (SSH permanente)", "Persist (permanent SSH)"))
        self.btn_persist.clicked.connect(self._persist)
        rrow.addWidget(self.btn_enable)
        rrow.addWidget(self.btn_persist)
        self.body().addLayout(rrow)
        self.body().addStretch(1)
        self._ctl = ProcessController()
        self._ctl.finished.connect(self._test_done)
        self._rctl = ProcessController()
        self._rctl.finished.connect(self._repair_done)
        self._loc = Worker()                      # sondeo del enlace (hilo)
        self._loc.done.connect(self._locate_done)
        self._loc.failed.connect(self._locate_failed)
        self._test_host = ""                      # host realmente probado (no recalcular tras el cambio del combo)
        self._enr = None
        self._hk_retried = False     # un solo reintento automatico tras limpiar known_hosts
        self._located_once = False   # un solo sondeo automatico por fallo de conexion
        self._loc_then_test = False
        self._last_repair = None     # (nombre, funcion, kwargs) para reintentar con pasarela
        self._repair_retried = False

    def _open_gui(self) -> None:
        d = self.ctx.sm.can_enable_ssh()
        if not d:
            self.ctx.bus.warn(d.reason)
            return
        if self.ctx.sshtool.launch_official_gui():
            self.ctx.state.ssh_enabled = True
            self.find()

    def find(self) -> None:
        enrs = self.ctx.sshtool.find_enrollments()
        self._enr = enrs[0] if enrs else None
        if not self._enr:
            self.kv_enr.set(tr("no encontrado todavia", "not found yet"), "warn")
            self.kv_key.set("—"); self.kv_fp.set("—"); self.kv_ip.set("—")
            self.changed.emit()
            return
        e = self._enr
        s = self.ctx.state
        self.kv_enr.set(f"{e.folder}  (VIN {e.vin_masked}, {e.source})", "ok")
        self.kv_key.set(e.key_path or tr("— (sin id_rsa)", "— (no id_rsa)"), "ok" if e.key_path else "err")
        self.kv_fp.set(e.fingerprints.splitlines()[0] if e.fingerprints else "—")
        s.enrollment_dir = e.folder
        s.key_path = e.key_path
        if e.mgu_ip and not s.mgu_ip:
            s.mgu_ip, s.mgu_ip_source = e.mgu_ip, "enrollment (fecha del flash; puede haber cambiado)"
        self._show_ip()
        self.changed.emit()

    def _show_ip(self) -> None:
        s = self.ctx.state
        if s.mgu_ip:
            fresh = s.mgu_ip_source in ("diagnostico de hoy", "sondeo ENET")
            self.kv_ip.set(f"{s.mgu_ip} — {ip_source_label(s.mgu_ip_source)}", "ok" if fresh else "warn")
        else:
            self.kv_ip.set(tr("— (ejecute el diagnostico o 'Localizar unidad')", "— (run the diagnostics or 'Locate unit')"), "warn")

    def _open_folder(self) -> None:
        if self._enr and Path(self._enr.folder).exists():
            webbrowser.open(Path(self._enr.folder).as_uri())

    def _target_host(self) -> str:
        if self.host.currentData() == "hotspot":
            return HOTSPOT_HOST
        # Sin IP inventada: si no se conoce, primero se localiza la unidad.
        return self.ctx.state.mgu_ip or (self._enr.mgu_ip if self._enr else "")

    def test(self) -> None:
        if not self.ctx.state.key_path:
            self.find()
        if not self.ctx.state.key_path:
            self.ctx.bus.warn(tr("No hay llave: complete Flash + Enable en la GUI oficial primero.",
                                 "No key: complete Flash + Enable in the official GUI first."))
            return
        if self._ctl.running:
            return
        host = self._target_host()
        if not host:
            self.ctx.bus.warn(tr("No se conoce la IP de la unidad: sondeando el enlace ENET antes de probar…",
                                 "The unit's IP is unknown: probing the ENET link before testing…"))
            self.btn_test.setEnabled(False)
            self._locate(then_test=True)
            return
        self._test_host = host
        self.kv_test.set(tr(f"probando root@{host}…", f"testing root@{host}…"))
        self.btn_test.setEnabled(False)
        self._ctl.start(self.ctx.sshtool.test_ssh, key_path=self.ctx.state.key_path, host=host)

    # -- localizar la unidad (ARP + puerto 22), sin pasarela ------------------------
    def _locate(self, then_test: bool = False) -> None:
        if self.ctx.demo:
            self.ctx.bus.info(tr("[demo] sondeo del enlace omitido.", "[demo] link probe skipped."))
            if then_test and self.ctx.state.mgu_ip:
                self.test()
            return
        self._loc_then_test = then_test
        self.btn_locate.setEnabled(False)
        s = self.ctx.state
        self.ctx.bus.info(tr("Localizando la unidad: puerto 22 en las IPs conocidas y en los vecinos ARP del enlace ENET…",
                             "Locating the unit: port 22 on the known IPs and on the ARP neighbors of the ENET link…"))
        exclude = {s.gateway_ip} if s.gateway_ip else set()
        self._loc.run(self.ctx.sshtool.locate_unit, [s.mgu_ip] if s.mgu_ip else [], exclude)

    def _locate_failed(self, tb: str) -> None:
        self.btn_locate.setEnabled(True)
        self.btn_test.setEnabled(True)
        self._loc_then_test = False
        last = (tb or "").strip().splitlines()
        self.ctx.bus.warn(tr("Sondeo del enlace: fallo interno — ", "Link probe: internal error — ")
                          + (last[-1] if last else tr("sin detalle", "no details")))

    def _locate_done(self, probes) -> None:
        self.btn_locate.setEnabled(True)
        self.btn_test.setEnabled(True)
        s = self.ctx.state
        probes = probes or []
        open_ips = [ip for ip, r in probes if r == "open"]
        refused = [ip for ip, r in probes if r == "refused"]
        if probes:
            self.ctx.bus.info(tr("Sondeo del puerto 22: ", "Port 22 probe: ") + ", ".join(f"{ip}={r}" for ip, r in probes))
        else:
            self.ctx.bus.warn(tr("Sondeo: ninguna IP candidata (sin diagnostico, sin enrollment y sin vecinos ARP). "
                                 "Compruebe el adaptador ENET (169.254.x.x) y que el coche este despierto.",
                                 "Probe: no candidate IP (no diagnostics, no enrollment and no ARP neighbors). "
                                 "Check the ENET adapter (169.254.x.x) and that the car is awake."))
        if len(open_ips) == 1:
            changed = open_ips[0] != s.mgu_ip
            s.mgu_ip, s.mgu_ip_source = open_ips[0], "sondeo ENET"
            self._show_ip()
            self.ctx.bus.ok(tr(f"Unidad localizada en {open_ips[0]} (SSH abierto)", f"Unit found at {open_ips[0]} (SSH open)")
                            + (tr(" — la IP habia cambiado.", " — the IP had changed.") if changed else "."))
            if self._loc_then_test:
                self._loc_then_test = False
                self.test()
                return
        elif open_ips:
            self.ctx.bus.warn(tr(f"Varias IPs con SSH abierto: {', '.join(open_ips)}. Elija la de la unidad ('Otra direccion' en el Store).",
                                 f"Several IPs have SSH open: {', '.join(open_ips)}. Pick the unit's IP ('Other address' "
                                 "in Install Store)."))
        elif refused:
            self.ctx.bus.warn(tr(f"Host vivo con el puerto 22 cerrado en {', '.join(refused)}: si es la unidad, SSH no esta activo → "
                                 "'Enable (re-abrir SSH)' (requiere que la pasarela ENET responda).",
                                 f"Live host with port 22 closed at {', '.join(refused)}: if it is the unit, SSH is not active → "
                                 "'Enable (reopen SSH)' (needs the ENET gateway to respond)."))
        elif probes:
            self.ctx.bus.warn(tr("Ninguna candidata responde: coche dormido, cable/adaptador sin enlace o la unidad aun arranca.",
                                 "No candidate responds: car asleep, cable/adapter without link, or the unit is still booting."))
        self._loc_then_test = False
        self.changed.emit()

    def _test_done(self, result) -> None:
        self.btn_test.setEnabled(True)
        if result.error:
            self.ctx.bus.error(result.error)
        ok = result.ok and any("uid=0(root)" in l for l in result.lines)
        self.ctx.state.ssh_verified = ok
        if ok:
            self._hk_retried = False
            self._located_once = False
            self.kv_test.set("✓ SSH OK as root", "ok")
            self.ctx.bus.ok(tr("SSH verificado como root. Ya puede instalar MGU Store.",
                               "SSH verified as root. You can now install MGU Store."))
            if self.ctx.state.mgu_ip and self.host.currentData() != "hotspot":
                self.ctx.sshtool.remember_car("", self.ctx.state.mgu_ip)
            self.changed.emit()
            return
        self.kv_test.set(tr("✗ fallo (ver consola)", "✗ failed (see console)"), "err")
        hints = hints_for_output(result.lines)
        host = self._test_host or self._target_host()   # el host que de verdad se probo
        # La IP puede ser vieja (enrollment) o la unidad pudo cambiarla: un sondeo automatico, una vez.
        if host != HOTSPOT_HOST and not self._located_once and any(h.id in ("UNIT_UNREACHABLE", "SSH_CLOSED") for h in hints):
            self._located_once = True
            for h in hints:
                self.ctx.bus.warn(f"Doctor: {h.title} — {h.detail}")
            self.ctx.bus.info(tr("Doctor: ¿cambio la IP de la unidad? Sondeando el enlace ENET…",
                                 "Doctor: did the unit's IP change? Probing the ENET link…"))
            self._locate(then_test=True)
            self.changed.emit()
            return
        if any(h.fix_id == "FORGET_HOST_KEY" for h in hints):
            # La unidad regenera su llave de host al reiniciarse (visto en el coche): limpiar y reintentar UNA vez.
            cleaned = self.ctx.sshtool.forget_host_key(host)
            if cleaned and not self._hk_retried:
                self._hk_retried = True
                self.ctx.bus.warn(tr("Doctor: la unidad cambio su huella SSH (la regenera al reiniciarse). known_hosts "
                                     "limpiado; reintentando la prueba…",
                                     "Doctor: the unit changed its SSH fingerprint (it regenerates it on restart). known_hosts "
                                     "cleared; retrying the test…"))
                self.test()
                return
            if not cleaned:
                kh = self.ctx.sshtool.known_hosts_file()
                self.ctx.bus.warn(tr(f"Doctor: huella cambiada pero no habia entrada de {host} en "
                                     f"{kh}; borre ese archivo a mano y reintente.",
                                     f"Doctor: fingerprint changed but there was no entry for {host} in "
                                     f"{kh}; delete that file by hand and retry."))
            else:
                self.ctx.bus.warn(tr("Doctor: la huella volvio a cambiar en el reintento (¿la unidad se reinicio otra vez?). "
                                     "known_hosts limpiado de nuevo; pulse 'Probar SSH'.",
                                     "Doctor: the fingerprint changed again on the retry (did the unit restart again?). "
                                     "known_hosts cleared again; click 'Test SSH'."))
        self._hk_retried = False
        self._located_once = False   # el siguiente fallo manual vuelve a poder sondear una vez
        for h in hints:
            if h.fix_id == "FORGET_HOST_KEY":
                continue
            self.ctx.bus.warn(f"Doctor: {h.title} — {h.detail}")
        if host == HOTSPOT_HOST and any(h.id == "UNIT_UNREACHABLE" for h in hints):
            self.ctx.bus.info(tr("Doctor: para probar por hotspot la laptop debe estar conectada al Wi-Fi del coche; "
                                 "con el cable ENET elija 'IP ENET de la unidad'.",
                                 "Doctor: to test via the hotspot the laptop must be connected to the car's Wi-Fi; "
                                 "with the ENET cable choose 'Unit ENET IP'."))
        self.changed.emit()

    def _enable(self) -> None:
        if self.ctx.state.ssh_port_open:
            self.ctx.bus.warn(tr("Enable: el ultimo diagnostico vio el puerto 22 ABIERTO. Enable reactivaria el modo debug "
                                 "(resetea perfil/asiento/BMW ID) sin necesidad; pruebe 'Probar SSH' o 'Localizar unidad' primero.",
                                 "Enable: the last diagnostics saw port 22 OPEN. Enable would turn debug mode back on "
                                 "(resets profile/seat/BMW ID) for no reason; try 'Test SSH' or 'Locate unit' first."))
            return
        typed = self.vin.text().strip().upper()
        from_enr = Path(self._enr.folder).name.upper() if self._enr else ""
        vin = typed or self.ctx.state.vin or from_enr
        if len(vin) != 17:
            self.ctx.bus.warn(tr("Enable requiere el VIN (17 caracteres): no se detecto en el diagnostico ni en el "
                                 "enrollment; escribalo en la casilla.",
                                 "Enable needs the VIN (17 characters): it was not found in the diagnostics or the "
                                 "enrollment; type it in the box."))
            return
        self.ctx.bus.info(tr("Enable: VIN tomado ", "Enable: VIN taken ")
                          + (tr("de la casilla.", "from the box.") if typed else
                             tr("del diagnostico/enrollment (censurado en el log).",
                                "from the diagnostics/enrollment (masked in the log).")))
        self._start_repair("enable", self.ctx.sshtool.run_enable, {"vin": vin, "persist": True})

    def _persist(self) -> None:
        self._start_repair("persist", self.ctx.sshtool.run_persist, {})

    def _start_repair(self, name: str, fn, kwargs: dict) -> None:
        # Nunca dos reparaciones a la vez contra la unidad (escriben y no son cancelables).
        if self._rctl.running:
            self.ctx.bus.warn(tr("Ya hay una reparacion en curso; espere a que termine.",
                                 "A repair is already running; wait for it to finish."))
            return
        self._last_repair = (name, fn, kwargs)
        self._repair_retried = False
        self._set_repair_buttons(False)
        self._rctl.start(fn, **kwargs)

    def _set_repair_buttons(self, enabled: bool) -> None:
        self.btn_enable.setEnabled(enabled)
        self.btn_persist.setEnabled(enabled)

    def _repair_done(self, r) -> None:
        if r.error:
            self.ctx.bus.error(r.error)
        self._set_repair_buttons(True)
        if r.ok:
            self._repair_retried = False
            self.ctx.bus.ok(tr("Reparacion terminada.", "Repair finished."))
            self.find()
            return
        lines_low = [l.lower() for l in r.lines]
        no_gw = any("no enet gateway responded" in l for l in lines_low)
        if no_gw and self._last_repair and not self._repair_retried:
            self._repair_retried = True
            name, fn, kwargs = self._last_repair
            gw = self.ctx.sshtool.retry_gateway(self.ctx.state.gateway_ip)
            self.ctx.bus.warn(tr(f"Doctor: la unidad no respondio por difusion UDP; reintento de '{name}' con la ultima "
                                 f"pasarela conocida {gw}…",
                                 f"Doctor: the unit did not answer the UDP broadcast; retrying '{name}' with the last "
                                 f"known gateway {gw}…"))
            self._set_repair_buttons(False)
            self._rctl.start(fn, gateway=gw, **kwargs)
            return
        self._repair_retried = False
        self.ctx.bus.warn(tr(f"Reparacion fallida (codigo {r.returncode}). Requisitos: contacto encendido, adaptador con "
                             "169.254.x.x y la pasarela ENET respondiendo; revise la consola.",
                             f"Repair failed (code {r.returncode}). Requirements: ignition on, adapter with "
                             "169.254.x.x and the ENET gateway responding; check the console."))
        for h in hints_for_output(r.lines):
            self.ctx.bus.warn(f"Doctor: {h.title} — {h.detail}")
        self.find()

    def _reeval(self) -> None:
        d = self.ctx.sm.can_enable_ssh()
        self.btn_gui.setEnabled(bool(d))
        self.block.setText("" if d else "⚠ " + d.reason)
        na = tr("n/d", "n/a")
        commit = self.ctx.sshtool.commit() or na
        gui = self.ctx.tools.status().ssh_prebuilt.version or na
        self.ver.setText(tr(f"Herramienta oficial: codigo @ {commit} · GUI prebuilt {gui}",
                            f"Official tool: code @ {commit} · prebuilt GUI {gui}"))

    def status(self):
        s = self.ctx.state
        if s.ssh_verified:
            return ("ok", tr("SSH verificado como root", "SSH verified as root"))
        if s.key_path:
            return ("warn", tr("Llave encontrada; falta 'Probar SSH'", "Key found; 'Test SSH' still pending"))
        if self.ctx.sshtool.find_enrollments():
            # SSH ya habilitado en una sesion anterior: se retoma desde aqui, sin respaldo ni flasheo.
            return ("warn", tr("Enrollment previo detectado: entre y pulse 'Probar SSH'",
                               "Earlier enrollment found: open this page and click 'Test SSH'"))
        return ("pending", tr("Pendiente (GUI oficial)", "Pending (official GUI)"))

    def is_unlocked(self) -> bool:
        return self.ctx.state.backup_confirmed or self.ctx.state.ssh_verified or bool(self.ctx.sshtool.find_enrollments())

    def on_enter(self) -> None:
        self._reeval()
        self.find()
