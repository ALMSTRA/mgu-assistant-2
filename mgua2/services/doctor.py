"""Doctor: deteccion de problemas y auto-correccion.

Dos fuentes de hallazgos:
1. Comprobaciones del entorno (administrador, OpenSSH, internet, herramientas,
   adaptador ENET con direccion link-local).
2. Patrones en la salida de los procesos (p. ej. "No ENET gateway responded",
   "Permission denied (publickey)", "REMOTE HOST IDENTIFICATION HAS CHANGED").

Cada hallazgo lleva, cuando existe, un `fix_id` que la app puede ejecutar.
Las correcciones automaticas nunca escriben en el coche: descargan, elevan,
instalan OpenSSH, reintentan con otra pasarela, limpian known_hosts, etc.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ..core.models import HOTSPOT_HOST
from ..i18n import tr
from . import netinfo

Severity = str  # "ok" | "info" | "warn" | "error"


@dataclass
class Finding:
    id: str
    severity: Severity
    title: str
    detail: str = ""
    fix_id: str = ""        # accion que la app sabe ejecutar
    fix_label: str = ""
    auto: bool = False      # se puede aplicar sin preguntar


# Lo emite nuestra propia descarga (download.verify_sha256), en espanol o en ingles: dos claves, un hallazgo.
_BAD_CHECKSUM = ("BAD_CHECKSUM", "error", tr("Descarga corrupta (SHA256)", "Corrupted download (SHA256)"),
                 tr("Se vuelve a descargar el archivo.", "The file is downloaded again."),
                 "REDOWNLOAD_TOOLS", tr("Volver a descargar", "Download again"), True)

# Patrones de salida -> hallazgo (id, severidad, titulo, detalle, fix_id, fix_label, auto)
# Las claves (primer elemento) son texto de la salida upstream: NUNCA se traducen.
OUTPUT_PATTERNS: list[tuple[str, tuple]] = [
    ("no enet gateway responded",
     ("ENET_NO_GATEWAY", "error", tr("La unidad no respondio por ENET", "The unit did not respond over ENET"),
      tr("Revise: contacto encendido y unidad despierta, cable ENET en el OBD-II, adaptador con "
         "direccion 169.254.x.x y la app ejecutada como administrador.",
         "Check: ignition on and unit awake, ENET cable in the OBD-II port, adapter with a "
         "169.254.x.x address and the app running as administrator."),
      "RETRY_FIXED_GATEWAY", tr("Reintentar con pasarela fija 169.254.254.36", "Retry with fixed gateway 169.254.254.36"),
      True)),
    ("nbt/evo head unit",
     ("NOT_MGU", "error", tr("La unidad es NBT/EVO, no MGU", "The unit is NBT/EVO, not MGU"),
      tr("Este ecosistema solo aplica a iDrive 7/8 (MGU). Fuera de alcance.",
         "This ecosystem only applies to iDrive 7/8 (MGU). Out of scope."), "", "", False)),
    ("this tool only speaks mgu",
     ("NOT_MGU", "error", tr("La unidad no es MGU", "The unit is not MGU"),
      tr("Fuera de alcance de esta herramienta.", "Out of scope for this tool."), "", "", False)),
    ("refusing to flash: this unit's btld is not",
     ("BTLD_UNSUPPORTED", "error", tr("Unidad MGU con BTLD fuera del catalogo soportado",
                                      "MGU unit with a BTLD outside the supported catalog"),
      tr("La herramienta oficial se niega a flashear esta unidad (BTLD distinto de 00003F36). No se fuerza "
         "(--force) bajo ninguna circunstancia: consulte los issues del proyecto upstream.",
         "The official tool refuses to flash this unit (BTLD other than 00003F36). It is never forced "
         "(--force) under any circumstances: check the upstream project's issues."), "", "", False)),
    ("permission denied (publickey)",
     ("KEY_REFUSED", "error", tr("La unidad rechaza la llave SSH", "The unit rejects the SSH key"),
      tr("Caso conocido: el sshd confia en otra llave. Use 'Fix refusing SSH key' en la GUI oficial "
         "(re-flash que solo cambia la region sin firmar).",
         "Known case: the sshd trusts a different key. Use 'Fix refusing SSH key' in the official GUI "
         "(a re-flash that only changes the unsigned region)."),
      "OPEN_OFFICIAL_GUI", tr("Abrir GUI oficial", "Open official GUI"), False)),
    ("remote host identification has changed",
     ("KNOWN_HOSTS_STALE", "warn", tr("Huella del host cambiada (known_hosts)", "Host fingerprint changed (known_hosts)"),
      tr("La unidad cambio de huella (p. ej. tras un flash). Se puede limpiar la entrada y reintentar.",
         "The unit's fingerprint changed (e.g. after a flash). The entry can be cleared and the step retried."),
      "FORGET_HOST_KEY", tr("Limpiar known_hosts y reintentar", "Clear known_hosts and retry"), True)),
    ("connection timed out",
     ("UNIT_UNREACHABLE", "error", tr("Tiempo de espera agotado al conectar", "Connection timed out"),
      tr("Compruebe la IP de la unidad, el enlace ENET o el hotspot Wi-Fi del coche.",
         "Check the unit's IP, the ENET link or the car's Wi-Fi hotspot."), "", "", False)),
    ("port 22: unknown error",
     ("UNIT_UNREACHABLE", "error", tr("La unidad no responde (error de red desconocido)",
                                      "The unit does not respond (unknown network error)"),
      tr("Suele ocurrir mientras la unidad se reinicia o si el cable ENET se desconecto. Espere ~1 min y reintente.",
         "It usually happens while the unit restarts or if the ENET cable came loose. Wait ~1 min and retry."),
      "", "", False)),
    # Visto en un X4 M F98 (2026-11-08): el flash deja CAFD FFFFFFFF y mgu-install se niega con codigo 2.
    ("coding is missing",
     ("CODING_DEFAULT", "error", tr("La codificacion del HU esta borrada (valores por defecto)",
                                    "The HU coding is wiped (default values)"),
      tr("El flasheo borra el CAFD (en el SVK aparece CAFD FFFFFFFF) y el instalador oficial se niega (codigo 2): sin "
         "codificacion valida oapcontroller no arranca MainApp. Reconfigurar la pantalla a mano NO basta y los ajustes "
         "se pierden al reiniciar. Recodifique HU_MGU por orden de vehiculo (VO) con E-Sys —lo que recomienda upstream y "
         "lo que funciono en su issue #10; 'restaurar respaldo' de BimmerCode se reporto insuficiente— o en un taller con "
         "E-Sys/ISTA. Luego reinicie la unidad, repita el diagnostico (debe volver un CAFD real) y reinstale el Store. "
         "El respaldo preflight (RESTORE.txt) sirve para comparar; esta app nunca escribe codificacion.",
         "Flashing wipes the CAFD (the SVK shows CAFD FFFFFFFF) and the official installer refuses (code 2): without "
         "valid coding, oapcontroller does not start MainApp. Reconfiguring the screen by hand is NOT enough and the "
         "settings are lost on restart. Recode HU_MGU from the vehicle order (VO) with E-Sys —what upstream recommends "
         "and what worked in its issue #10; BimmerCode's 'restore backup' was reported as insufficient— or at a workshop "
         "with E-Sys/ISTA. Then restart the unit, repeat the diagnostic (a real CAFD must come back) and reinstall the "
         "Store. The preflight backup (RESTORE.txt) is for comparison; this app never writes coding."),
      "OPEN_PREFLIGHT_FOLDER", tr("Abrir respaldo preflight (RESTORE.txt)", "Open preflight backup (RESTORE.txt)"),
      False)),
    ("no route to host",
     ("UNIT_UNREACHABLE", "error", tr("Sin ruta hacia la unidad", "No route to the unit"),
      tr("El adaptador no esta en la misma red (169.254.x.x) o el hotspot no esta conectado.",
         "The adapter is not on the same network (169.254.x.x) or the hotspot is not connected."), "", "", False)),
    ("connection refused",
     ("SSH_CLOSED", "error", tr("Algo responde en esa IP pero con el puerto 22 cerrado",
                                "Something answers at that IP but port 22 is closed"),
      tr("O SSH no esta activo en la unidad (use 'Enable', reparacion sin flasheo), o esa IP ya no es la de la "
         "unidad (puede cambiar tras un reinicio). Se sondea el enlace ENET para localizarla.",
         "Either SSH is not active on the unit (use 'Enable', a repair without flashing), or that IP no longer "
         "belongs to the unit (it can change after a restart). The ENET link is probed to locate it."),
      "RUN_ENABLE", tr("Ejecutar enable (sin flasheo)", "Run enable (no flashing)"), False)),
    ("timeouterror",
     ("GATEWAY_TIMEOUT", "error", tr("La pasarela ENET no respondio por TCP (6801)",
                                     "The ENET gateway did not respond over TCP (6801)"),
      tr("La IP de pasarela usada no es la de este coche o el coche esta dormido. Encienda el contacto, espere "
         "a que el adaptador tenga 169.254.x.x y repita; la app reintenta con la ultima pasarela conocida.",
         "The gateway IP used is not this car's, or the car is asleep. Turn the ignition on, wait until "
         "the adapter has 169.254.x.x and repeat; the app retries with the last known gateway."),
      "", "", False)),
    ("winerror 10060",
     ("GATEWAY_TIMEOUT", "error", tr("La pasarela ENET no respondio por TCP (6801)",
                                     "The ENET gateway did not respond over TCP (6801)"),
      tr("La IP de pasarela usada no es la de este coche o el coche esta dormido. Encienda el contacto, espere "
         "a que el adaptador tenga 169.254.x.x y repita.",
         "The gateway IP used is not this car's, or the car is asleep. Turn the ignition on, wait until "
         "the adapter has 169.254.x.x and repeat."), "", "", False)),
    ("not accessible: no such file",
     ("KEY_MISSING", "error", tr("La llave del enrollment no existe en esa ruta",
                                 "The enrollment key does not exist at that path"),
      tr("La carpeta se movio, renombro o es una copia incompleta. Pulse 'Buscar enrollment' (solo se aceptan "
         "carpetas con nombre de VIN que contengan id_rsa).",
         "The folder was moved, renamed or is an incomplete copy. Press 'Find enrollment' (only folders "
         "named after a VIN that contain id_rsa are accepted)."), "", "", False)),
    ("the coding read is incomplete",
     ("PREFLIGHT_INCOMPLETE", "warn", tr("Respaldo de codificacion incompleto", "Incomplete coding backup"),
      tr("Upstream avisa que la lectura no se verifico. Repita el preflight y NO lo use como unico respaldo "
         "(haga tambien BimmerCode/E-Sys).",
         "Upstream warns that the read was not verified. Repeat the preflight and do NOT use it as your only backup "
         "(also make one with BimmerCode/E-Sys)."),
      "RERUN_PREFLIGHT", tr("Repetir preflight", "Repeat preflight"), False)),
    ("unrecognized arguments: --no-restart-prompt",
     ("FLAG_UNSUPPORTED", "warn", tr("El instalador no acepta --no-restart-prompt",
                                     "The installer does not accept --no-restart-prompt"),
      tr("Se reintenta sin esa opcion.", "Retrying without that option."),
      "RETRY_WITHOUT_RESTART_FLAG", tr("Reintentar sin la opcion", "Retry without the option"), True)),
    ("sha256 no coincide", _BAD_CHECKSUM),
    ("sha256 does not match", _BAD_CHECKSUM),
    ("rate limit",
     ("GH_RATE_LIMIT", "warn", tr("Limite de la API de GitHub", "GitHub API rate limit"),
      tr("Espere unos minutos y reintente; mientras, se usan las copias locales.",
         "Wait a few minutes and retry; meanwhile the local copies are used."), "", "", False)),
    ("could not download",
     ("DOWNLOAD_FAILED", "error", tr("Fallo una descarga", "A download failed"),
      tr("Revise internet / proxy y reintente.", "Check the internet connection / proxy and retry."),
      "REDOWNLOAD_TOOLS", tr("Reintentar descargas", "Retry downloads"), True)),
    ("ssh: command not found",
     ("NO_OPENSSH", "error", tr("No hay cliente OpenSSH", "No OpenSSH client"),
      tr("Instale el Cliente OpenSSH de Windows.", "Install the Windows OpenSSH Client."),
      "INSTALL_OPENSSH", tr("Instalar OpenSSH", "Install OpenSSH"), True)),
    ("is not recognized as",
     ("NO_OPENSSH", "error", tr("No hay cliente OpenSSH", "No OpenSSH client"),
      tr("Instale el Cliente OpenSSH.", "Install the OpenSSH Client."), "INSTALL_OPENSSH",
      tr("Instalar OpenSSH", "Install OpenSSH"), True)),
]


def hints_for_output(lines: list[str]) -> list[Finding]:
    found: dict[str, Finding] = {}
    for raw in lines:
        low = raw.lower()
        for pat, (fid, sev, title, detail, fix, fix_label, auto) in OUTPUT_PATTERNS:
            if pat in low and fid not in found:
                found[fid] = Finding(fid, sev, title, detail, fix, fix_label, auto)
    return list(found.values())


def finding_by_id(fid: str) -> Optional[Finding]:
    """El mismo hallazgo que daria la salida, pero deducido de otro dato (p. ej. CAFD FFFFFFFF en el SVK)."""
    for _pat, spec in OUTPUT_PATTERNS:
        if spec[0] == fid:
            return Finding(*spec)
    return None


class Doctor:
    """Comprobaciones del entorno y ejecucion de correcciones."""

    def __init__(self, ctx) -> None:
        self.ctx = ctx

    def check_environment(self) -> list[Finding]:
        out: list[Finding] = []
        demo = self.ctx.demo

        admin = netinfo.is_admin() or demo
        out.append(Finding("ADMIN", "ok" if admin else "warn", tr("Administrador", "Administrator"),
                           tr("Necesario en Windows para la direccion link-local del ENET.",
                              "Required on Windows for the ENET link-local address.") if not admin
                           else tr("Con privilegios.", "Running elevated."),
                           "" if admin else "RELAUNCH_ADMIN",
                           "" if admin else tr("Reiniciar como administrador", "Restart as administrator"), auto=False))

        ssh = netinfo.openssh_path() or demo
        out.append(Finding("OPENSSH", "ok" if ssh else "error", tr("Cliente OpenSSH", "OpenSSH client"),
                           (netinfo.ssh_version() or tr("presente", "present")) if ssh
                           else tr("No encontrado (ssh).", "Not found (ssh)."),
                           "" if ssh else "INSTALL_OPENSSH",
                           "" if ssh else tr("Instalar Cliente OpenSSH", "Install OpenSSH client"), auto=True))

        net = demo or netinfo.internet_ok()
        out.append(Finding("INTERNET", "ok" if net else "warn", "Internet (GitHub)",
                           tr("Conectividad OK.", "Connectivity OK.") if net
                           else tr("Sin conexion: las descargas fallaran; se usan copias locales.",
                                   "No connection: downloads will fail; local copies are used.")))

        ready = self.ctx.tools.all_ready()
        out.append(Finding("TOOLS", "ok" if ready else "warn", tr("Herramientas descargadas", "Tools downloaded"),
                           tr("Todo descargado y verificado.", "Everything downloaded and verified.") if ready
                           else tr("Faltan herramientas.", "Some tools are missing."),
                           "" if ready else "DOWNLOAD_TOOLS",
                           "" if ready else tr("Descargar todo", "Download all"), auto=True))

        if demo:
            out.append(Finding("ENET", "ok", tr("Adaptador ENET (demo)", "ENET adapter (demo)"),
                               tr("Simulado: 169.254.10.20", "Simulated: 169.254.10.20")))
        else:
            adapters = netinfo.list_adapters()
            enet = [a for a in adapters if a.looks_enet]
            up_wired = [a for a in adapters if a.is_up and not a.looks_enet]
            if enet:
                a = enet[0]
                out.append(Finding("ENET", "ok", tr("Adaptador ENET con enlace", "ENET adapter with link"),
                                   f"{a.name} ({a.description}) {', '.join(a.link_local)}"))
            else:
                active = ", ".join(a.name for a in up_wired)
                out.append(Finding("ENET", "warn", tr("Sin adaptador ENET con direccion 169.254.x.x",
                                                      "No ENET adapter with a 169.254.x.x address"),
                                   tr("Conecte el cable ENET al OBD-II con el contacto encendido; Windows asigna "
                                      "169.254.x.x en ~30-60 s si no hay DHCP. ",
                                      "Connect the ENET cable to the OBD-II port with the ignition on; Windows assigns "
                                      "169.254.x.x within ~30-60 s if there is no DHCP. ")
                                   + (tr(f"Adaptadores activos: {active}.", f"Active adapters: {active}.")
                                      if up_wired else ""),
                                   "RECHECK_ENET", tr("Volver a comprobar", "Check again"), auto=False))
        return out

    # -- correcciones ------------------------------------------------------------
    def fix(self, fix_id: str, done: Optional[Callable[[bool, str], None]] = None) -> None:
        """Aplica una correccion. Las que lanzan procesos largos avisan por `done`."""
        bus = self.ctx.bus

        def finish(ok: bool, msg: str) -> None:
            bus.log("OK" if ok else "WARN", msg)
            if done:
                done(ok, msg)

        if fix_id == "RELAUNCH_ADMIN":
            ok = netinfo.relaunch_as_admin()
            finish(ok, tr("Relanzando como administrador…", "Relaunching as administrator…") if ok
                   else tr("No se pudo relanzar (UAC cancelado).", "Could not relaunch (UAC cancelled)."))
            if ok:
                raise SystemExit(0)
        elif fix_id == "INSTALL_OPENSSH":
            ok = netinfo.run_elevated(netinfo.install_openssh_client_argv())
            finish(ok, tr("Instalacion del Cliente OpenSSH lanzada (ventana elevada).",
                          "OpenSSH Client installation launched (elevated window).") if ok
                   else tr("No se pudo lanzar (UAC).", "Could not launch it (UAC)."))
        elif fix_id in ("DOWNLOAD_TOOLS", "REDOWNLOAD_TOOLS"):
            import threading

            def worker() -> None:
                st = self.ctx.tools.install_all(force=(fix_id == "REDOWNLOAD_TOOLS"))
                self.ctx.state.tools_ready = st.all_ready
                finish(st.all_ready, tr("Herramientas listas.", "Tools ready.") if st.all_ready
                       else tr("Algunas herramientas no se descargaron.", "Some tools were not downloaded."))

            threading.Thread(target=worker, daemon=True).start()
        elif fix_id == "FORGET_HOST_KEY":
            host = self.ctx.state.mgu_ip or HOTSPOT_HOST
            ok = self.ctx.sshtool.forget_host_key(host)
            finish(ok, tr("known_hosts limpiado.", "known_hosts cleared.") if ok
                   else tr("No habia entrada que limpiar.", "There was no entry to clear."))
        elif fix_id == "OPEN_PREFLIGHT_FOLDER":
            import webbrowser
            from pathlib import Path
            folder = self.ctx.state.preflight_folder
            if not folder or not Path(folder).exists():
                bk = self.ctx.sshtool.find_preflight_backups()
                folder = bk[0].folder if bk else ""
            ok = bool(folder) and Path(folder).exists()
            if ok:
                webbrowser.open(Path(folder).as_uri())
            finish(ok, tr(f"Respaldo preflight abierto: {folder}", f"Preflight backup opened: {folder}") if ok
                   else tr("No hay respaldo preflight en este equipo (¿se hizo en otra laptop?).",
                           "There is no preflight backup on this computer (was it made on another laptop?)."))
        elif fix_id == "RECHECK_ENET":
            finish(True, tr("Comprobacion de red repetida.", "Network check repeated."))
        else:
            finish(False, tr(f"Correccion no automatica: {fix_id}", f"Not an automatic fix: {fix_id}"))
