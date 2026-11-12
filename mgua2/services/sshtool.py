"""Envoltura de la herramienta oficial `idrive7-8-ssh-root` (ID7).

- `status` y `preflight`: SOLO lectura, con nuestro interprete (sin Python en
  la laptop). `enable`/`persist`: reparacion sin flasheo.
- Flasheo: se abre la GUI oficial prebuilt (MGU-SSH.exe) como administrador;
  nunca se pasa --force ni --yes desde aqui.
- Detecta enrollments y respaldos preflight sin leer llaves privadas.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..core.logbus import LogBus
from ..core.models import SSH_ARCH, SUPPORTED_BTLD
from ..core.paths import DataPaths
from ..i18n import tr
from ..security.redaction import mask_vin, redact
from . import netinfo, upstream_cli
from .runner import ProcessRunner
from .tools import ToolsManager

_TS_RE = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]\s*")
_IP_RE = re.compile(r"\b(169\.254\.\d{1,3}\.\d{1,3})\b")
# Solo las carpetas con nombre de VIN (17 alfanumericos, como las crea upstream) son enrollments;
# "<VIN> backup" (copia del usuario) no lo es. Alfabeto laxo a proposito: el VIN de la demo lleva 'O'.
_VIN_DIR_RE = re.compile(r"^[A-Za-z0-9]{17}$")
# Ultimo recurso si nunca se vio una pasarela (la de cada coche se guarda en state/last_car.json).
FALLBACK_GATEWAY = "169.254.254.36"
# Formato real del tool: "SVK: BTLD 00003F36_030.016.006 SWFL 00003F37_030.016.002 ..."
_SVK_REC_RE = re.compile(r"\b(BTLD|SWFL|CAFD|HWEL|SWFK)\s*[:=]?\s*([0-9A-Fa-f]{8})(?:[_\s-]+([0-9]{3}\.[0-9]{3}\.[0-9]{3}))?", re.IGNORECASE)
_VER_RE = re.compile(r"\b([0-9]{3}\.[0-9]{3}\.[0-9]{3})\b")
_VIN_RE = re.compile(r"\bVIN[:=\s]+\[?([A-HJ-NPR-Z0-9]{17})\]?", re.IGNORECASE)
_GATEWAY_FOUND_RE = re.compile(r"found \d+ enet gateway|connecting to enet gateway|enet gateway\S* found", re.IGNORECASE)
# Linea de known_hosts: "[marcador] host[,host2] tipo-de-llave base64 [comentario]"
_KNOWN_HOSTS_LINE_RE = re.compile(
    r"^(@\S+\s+)?\S+\s+(ssh-(rsa|ed25519|dss)|ecdsa-sha2-\S+|sk-\S+)\s+[A-Za-z0-9+/=]+", re.IGNORECASE)
# CAFD que deja un flasheo: la unidad queda sin codificacion (valores por defecto). Visto en un X4 M F98 (2026-11-08).
CAFD_WIPED = "FFFFFFFF"
UPSTREAM_ISSUE_SETTINGS_RESET = "https://github.com/cauliflowermossgrape/idrive7-8-ssh-root/issues/10"


@dataclass
class StatusResult:
    gateway_found: bool = False
    is_mgu: bool = False
    nbt_rejected: bool = False
    btld_unsupported: bool = False   # el tool rechazo la unidad por BTLD distinto de 00003F36
    btld: str = ""
    software_version: str = ""
    cafd: str = ""                   # id CAFD del SVK; FFFFFFFF = codificacion borrada
    coding_missing: bool = False     # la unidad esta con valores por defecto (tipico tras el flash)
    gateway_ip: str = ""             # pasarela ENET que respondio (p. ej. 169.254.1.21)
    mgu_ip: str = ""
    ssh_port_open: Optional[bool] = None
    ssh_ok_root: Optional[bool] = None
    debug_active: Optional[bool] = None
    vin_masked: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    raw: list[str] = field(default_factory=list)

    @property
    def btld_supported(self) -> bool:
        return self.btld.upper() == SUPPORTED_BTLD

    @property
    def ssh_persistent(self) -> bool:
        """Puerto 22 abierto con el modo debug apagado: el estado final deseado (sin DTC B7F8E5)."""
        return bool(self.ssh_port_open) and self.debug_active is False


def parse_status(lines: list[str]) -> StatusResult:
    r = StatusResult(raw=list(lines))
    gateway_timeout = False
    for raw in lines:
        ln = _TS_RE.sub("", raw).strip()
        low = ln.lower()
        if "no enet gateway responded" in low:
            r.gateway_found = False
            r.errors.append(ln)
            continue
        if _GATEWAY_FOUND_RE.search(ln) or ("gateway" in low and _IP_RE.search(ln)):
            r.gateway_found = True
            gm = _IP_RE.search(ln)
            if gm and "gateway" in low and not r.gateway_ip:
                r.gateway_ip = gm.group(1)
        if "nbt/evo" in low or "this tool only speaks mgu" in low:
            r.nbt_rejected = True
            r.errors.append(ln)
        if "refusing to flash" in low and "btld is not" in low:
            # MGU real pero fuera del catalogo soportado: el propio tool se niega (no se fuerza).
            r.gateway_found = True
            r.btld_unsupported = True
            r.errors.append(ln)
        # Registros SVK (BTLD/SWFL/...): BTLD decide el soporte; SWFL da la version de software.
        for m in _SVK_REC_RE.finditer(ln):
            kind, hexid, ver = m.group(1).upper(), m.group(2).upper(), (m.group(3) or "")
            r.gateway_found = True
            if kind == "BTLD" and not r.btld:
                r.btld = hexid
                if ver and not r.software_version:
                    r.software_version = ver
            if kind == "SWFL" and ver:
                r.software_version = ver
            if kind == "CAFD":
                r.cafd = r.cafd or hexid
                if hexid == CAFD_WIPED:
                    r.coding_missing = True
        if low.startswith("svk:") and not r.software_version:
            m = _VER_RE.search(ln)
            if m:
                r.software_version = m.group(1)
        m = _IP_RE.search(ln)
        if m and ("mgu ip" in low or "mgu unit" in low or "head unit" in low) and not r.mgu_ip and not m.group(1).startswith("169.254.254."):
            r.mgu_ip = m.group(1)
        if "port 22" in low:
            r.ssh_port_open = "open" in low and "not open" not in low and "closed" not in low
            r.gateway_found = True
        if "ssh ok as root" in low:
            r.ssh_ok_root = True
        # "DTC B7F8E5 (Debugging active / SSH is active!!!): PRESENT|absent"  /  "Status: ... state is ON|OFF"
        if "b7f8e5" in low:
            r.debug_active = low.rstrip(".").endswith("present")
        elif low.startswith("status:") and "state is" in low:
            tail = low.split("state is", 1)[1].strip()
            # "OFF (or not reported)" = el tool no pudo leer los DTC: estado desconocido, no "apagado".
            r.debug_active = None if "not reported" in tail else tail.startswith("on")
        m = _VIN_RE.search(ln)
        if m and not r.vin_masked:
            r.vin_masked = mask_vin(m.group(1))
        if "timeouterror" in low or "winerror 10060" in low or "error del tool upstream" in low:
            gateway_timeout = True
        if re.search(r"\b(warn|warning)\b", low):
            r.warnings.append(ln)
        if re.search(r"\b(error|refused|denied|failed|traceback)\b", low):
            r.errors.append(ln)
    # "Connecting to ENET gateway X" seguido de un timeout NO es una pasarela encontrada.
    if gateway_timeout and not r.btld and not r.btld_unsupported:
        r.gateway_found = False
        r.gateway_ip = ""
    # MGU confirmada si la unidad respondio, el tool no la rechazo como NBT/EVO y se leyo su SVK.
    r.is_mgu = r.gateway_found and not r.nbt_rejected and (bool(r.btld) or bool(r.software_version) or r.btld_unsupported)
    return r


@dataclass
class Enrollment:
    folder: str
    vin_masked: str
    key_path: str = ""
    connect_txt: str = ""
    fingerprints: str = ""
    mgu_ip: str = ""
    arch: str = ""
    timestamp: str = ""
    source: str = ""   # "gui" (MGU-SSH.exe) o "cli" (codigo)


@dataclass
class PreflightBackup:
    folder: str
    vin_masked: str
    taken: str = ""
    complete: bool = True
    has_sums: bool = False


class SshTool:
    def __init__(self, tools: ToolsManager, runner: ProcessRunner, paths: DataPaths,
                 bus: Optional[LogBus] = None) -> None:
        self.tools = tools
        self.runner = runner
        self.paths = paths
        self.bus = bus
        self._ignored_dirs: set = set()   # carpetas no-VIN ya avisadas (un aviso por sesion)

    def _log(self, lvl: str, msg: str) -> None:
        if self.bus:
            self.bus.log(lvl, msg)

    def available(self) -> bool:
        return self.tools.ssh_script.exists()

    def commit(self) -> str:
        return self.tools.commit_of("idrive7-8-ssh-root")[:10]

    # -- argv ----------------------------------------------------------------
    def _argv(self, action: str, extra: list[str]) -> list[str]:
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        log = self.paths.logs / f"upstream-{action}-{stamp}.log"
        return upstream_cli.build_argv(self.tools.ssh_script, [action, *extra, "--log", str(log)])

    def _run(self, action: str, extra: list[str], *, cancelable: bool, timeout: float | None,
             on_output=None, on_finished=None, label: str = ""):
        argv = self._argv(action, extra)
        return self.runner.run(argv, cwd=str(self.tools.ssh_script.parent), env=upstream_cli.child_env(),
                               on_output=on_output, on_finished=on_finished, cancelable=cancelable,
                               timeout=timeout, label=label or f"ssh-tool {action}")

    # -- solo lectura --------------------------------------------------------
    def run_status(self, *, gateway: str | None = None, mgu_ip: str | None = None, verbose: bool = False,
                   on_output=None, on_finished=None):
        extra: list[str] = ["--arch", SSH_ARCH]
        if gateway:
            extra += ["--gateway", gateway]
        if mgu_ip:
            extra += ["--mgu-ip", mgu_ip]
        if verbose:
            extra += ["--verbose"]
        return self._run("status", extra, cancelable=True, timeout=300, on_output=on_output,
                         on_finished=on_finished, label=tr("diagnostico (solo lectura)", "diagnostic (read-only)"))

    def run_preflight(self, *, gateway: str | None = None, on_output=None, on_finished=None):
        extra: list[str] = ["--arch", SSH_ARCH]
        if gateway:
            extra += ["--gateway", gateway]
        return self._run("preflight", extra, cancelable=True, timeout=None, on_output=on_output,
                         on_finished=on_finished,
                         label=tr("respaldo de codificacion (solo lectura)", "coding backup (read-only)"))

    # -- reparacion sin flasheo --------------------------------------------
    def run_enable(self, vin: str, *, persist: bool = True, gateway: str | None = None,
                   on_output=None, on_finished=None):
        """Re-abre SSH en una unidad YA flasheada (no flashea). Requiere VIN."""
        extra: list[str] = ["--arch", SSH_ARCH, "--vin", vin]
        if persist:
            extra.append("--persist")
        if gateway:
            extra += ["--gateway", gateway]
        if self.bus:
            self.bus.add_vin(vin)
        return self._run("enable", extra, cancelable=False, timeout=None, on_output=on_output,
                         on_finished=on_finished, label=tr("enable (reparacion, sin flasheo)", "enable (repair, no flashing)"))

    def run_persist(self, *, gateway: str | None = None, on_output=None, on_finished=None):
        extra: list[str] = ["--arch", SSH_ARCH]
        if gateway:
            extra += ["--gateway", gateway]
        return self._run("persist", extra, cancelable=False, timeout=None, on_output=on_output,
                         on_finished=on_finished,
                         label=tr("persist (SSH permanente, sin flasheo)", "persist (permanent SSH, no flashing)"))

    # -- flasheo: GUI oficial -----------------------------------------------
    def launch_official_gui(self) -> bool:
        """Abre MGU-SSH.exe como administrador (UAC). El flasheo lo conduce el usuario."""
        exe = self.tools.ssh_prebuilt_exe
        if not exe.exists():
            self._log("ERROR", tr("La GUI oficial MGU-SSH.exe no esta descargada.",
                                  "The official MGU-SSH.exe GUI is not downloaded."))
            return False
        self._log("CMD", tr(f"abrir GUI oficial (administrador): {exe}", f"open official GUI (administrator): {exe}"))
        if sys.platform.startswith("win"):
            try:
                import ctypes
                rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(exe), None, str(exe.parent), 1)
                ok = int(rc) > 32
            except Exception as e:
                self._log("ERROR", tr(f"No se pudo abrir la GUI oficial: {e}", f"Could not open the official GUI: {e}"))
                return False
        else:
            ok = False
        self._log("OK" if ok else "ERROR", tr("GUI oficial abierta.", "Official GUI opened.") if ok
                  else tr("UAC cancelado o fallo al abrir.", "UAC cancelled or it failed to open."))
        return ok

    # -- enrollments / respaldos --------------------------------------------
    def _enrollment_roots(self) -> list[tuple[Path, str]]:
        return [(self.tools.ssh_prebuilt_dir / "data" / "enrollments", "gui"),
                (self.tools.ssh_script.parent / "data" / "enrollments", "cli")]

    def find_enrollments(self) -> list[Enrollment]:
        """Enrollments reales: carpetas con nombre de VIN, primero las que tienen id_rsa, mas recientes
        antes. Las copias del usuario ("<VIN> backup") se ignoran: en el coche una de ellas sin id_rsa
        y con una IP vieja se tomo como enrollment y 'Probar SSH' fue a la IP equivocada (2026-11-09)."""
        out: list[Enrollment] = []
        for root, source in self._enrollment_roots():
            if not root.exists():
                continue
            for d in root.iterdir():
                if not d.is_dir():
                    continue
                if self.bus and _VIN_DIR_RE.match(d.name[:17]):
                    self.bus.add_vin(d.name[:17])  # la carpeta empieza por el VIN: censurarlo en todo el log
                if not _VIN_DIR_RE.match(d.name):
                    key = (root, d.name)
                    if key not in self._ignored_dirs:
                        self._ignored_dirs.add(key)
                        self._log("INFO", tr(f"Carpeta ignorada en enrollments (no es un VIN): {redact(d.name)} — "
                                             "guarde las copias fuera de esa carpeta.",
                                             f"Folder ignored in enrollments (not a VIN): {redact(d.name)} — "
                                             "keep copies outside that folder."))
                    continue
                e = Enrollment(folder=str(d), vin_masked=mask_vin(d.name), source=source)
                key = d / "id_rsa"
                if key.exists():
                    e.key_path = str(key)
                if (d / "connect.txt").exists():
                    e.connect_txt = str(d / "connect.txt")
                fp = d / "fingerprints.txt"
                if fp.exists():
                    try:
                        e.fingerprints = redact(fp.read_text(encoding="utf-8", errors="replace")).strip()
                    except Exception:
                        pass
                meta = d / "metadata.json"
                if meta.exists():
                    try:
                        m = json.loads(meta.read_text(encoding="utf-8", errors="replace"))
                        if isinstance(m, dict):
                            e.mgu_ip = str(m.get("mgu_ip", "") or "")
                            e.arch = str(m.get("arch", "") or "")
                            e.timestamp = str(m.get("timestamp", "") or "")
                    except Exception:
                        pass
                out.append(e)
        out.sort(key=lambda e: (bool(e.key_path),
                                Path(e.folder).stat().st_mtime if Path(e.folder).exists() else 0), reverse=True)
        return out

    # -- memoria del coche (IPs, no secretos) ---------------------------------
    def last_car_file(self) -> Path:
        return self.paths.state / "last_car.json"

    def last_car(self) -> dict:
        try:
            d = json.loads(self.last_car_file().read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def remember_car(self, gateway_ip: str = "", mgu_ip: str = "") -> None:
        """Guarda la ultima pasarela e IP de la unidad vistas: el reintento del diagnostico usa ESA
        pasarela (la fija 169.254.254.36 no era la de este coche: era 169.254.1.21)."""
        d = self.last_car()
        if gateway_ip:
            d["gateway"] = gateway_ip
        if mgu_ip:
            d["mgu_ip"] = mgu_ip
            seen = [ip for ip in d.get("mgu_ips", []) if ip != mgu_ip]
            d["mgu_ips"] = ([mgu_ip] + seen)[:6]
        d["when"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.last_car_file().write_text(json.dumps(d, indent=2), encoding="utf-8")
        except OSError:
            pass

    def retry_gateway(self, current: str = "") -> str:
        """Pasarela para el reintento: la del diagnostico actual, la ultima guardada o la fija."""
        return current or str(self.last_car().get("gateway", "")) or FALLBACK_GATEWAY

    # -- localizar la unidad en el enlace ENET (sin UDP 6811) ---------------------
    def candidate_unit_ips(self, extra: list[str] | None = None, exclude: set[str] | None = None) -> list[str]:
        """IPs donde puede estar la unidad: las conocidas (estado, enrollments, memoria) y los vecinos
        link-local de la tabla ARP, sin esta maquina ni la pasarela (`exclude`)."""
        skip = set(netinfo.own_ipv4()) | set(exclude or set()) | {str(self.last_car().get("gateway", ""))}
        order: list[str] = []
        for ip in list(extra or []) + [e.mgu_ip for e in self.find_enrollments()] + \
                [str(self.last_car().get("mgu_ip", ""))] + list(self.last_car().get("mgu_ips", [])) + \
                netinfo.arp_neighbors(exclude=skip):
            if ip and ip not in skip and ip not in order:
                order.append(ip)
        return order

    def locate_unit(self, extra: list[str] | None = None, exclude: set[str] | None = None,
                    timeout: float = 2.5) -> list[tuple[str, str]]:
        """Sondea el puerto 22 en las candidatas: [(ip, 'open'|'refused'|'timeout'|'error')]."""
        return [(ip, netinfo.probe_tcp(ip, 22, timeout)) for ip in self.candidate_unit_ips(extra, exclude)]

    def find_preflight_backups(self) -> list[PreflightBackup]:
        root = self.tools.ssh_script.parent / "data" / "preflight"
        out: list[PreflightBackup] = []
        if root.exists():
            for d in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if not d.is_dir():
                    continue
                vin = d.name.split("-", 2)[-1] if "-" in d.name else d.name
                b = PreflightBackup(folder=str(d), vin_masked=mask_vin(vin),
                                    has_sums=(d / "SHA256SUMS").exists())
                try:
                    data = json.loads((d / "backup.json").read_text(encoding="utf-8", errors="replace"))
                    b.taken = str(data.get("taken", ""))
                    b.complete = bool(data.get("verified", data.get("complete", True)))
                except Exception:
                    pass
                out.append(b)
        return out

    def copy_backup(self, folder: str) -> Path:
        """Copia un respaldo preflight a backups/ del usuario (solo metadatos de codificacion)."""
        src = Path(folder)
        dest = self.paths.backups / f"preflight-{src.name}"
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest)
        self._log("OK", tr(f"Respaldo copiado a {dest}", f"Backup copied to {dest}"))
        return dest

    # -- verificacion SSH ------------------------------------------------------
    def known_hosts_file(self) -> Path:
        return self.paths.state / "known_hosts"

    def known_hosts_option(self) -> str:
        """Valor de -o UserKnownHostsFile. Las comillas son OBLIGATORIAS: ssh separa el valor por
        espacios, asi que "...\\MGU Assistant 2\\state\\known_hosts" se convertia en TRES archivos y la
        huella acababa en %LOCALAPPDATA%\\MGU (visto en el coche el 2026-11-08: el Doctor "limpiaba" un
        archivo que ssh nunca leia)."""
        return f'UserKnownHostsFile="{self.known_hosts_file()}"'

    def test_ssh_argv(self, key_path: str, host: str) -> list[str]:
        ssh = shutil.which("ssh") or "ssh"
        return [ssh, "-i", key_path, "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
                "-o", "StrictHostKeyChecking=accept-new",
                "-o", self.known_hosts_option(),
                "-o", "IdentitiesOnly=yes", f"root@{host}", "id"]

    def test_ssh(self, key_path: str, host: str, on_output=None, on_finished=None):
        return self.runner.run(self.test_ssh_argv(key_path, host), on_output=on_output,
                               on_finished=on_finished, cancelable=True, timeout=40, label=tr("prueba SSH", "SSH test"))

    def cleanup_legacy_known_hosts(self) -> bool:
        """Borra el archivo huerfano que ssh creaba al partir la ruta sin comillas en el primer
        espacio (p. ej. %LOCALAPPDATA%\\MGU). Solo si su contenido son huellas de host."""
        full = str(self.known_hosts_file())
        if " " not in full:
            return False
        stray = Path(full.split(" ", 1)[0])
        if not stray.is_file():
            return False
        try:
            lines = [l for l in stray.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
        except OSError:
            return False
        if not lines or not all(_KNOWN_HOSTS_LINE_RE.match(l) for l in lines):
            return False
        try:
            stray.unlink()
        except OSError:
            return False
        self._log("OK", tr(f"known_hosts: eliminado el archivo huerfano {stray} (ruta partida por un espacio).",
                           f"known_hosts: removed the orphan file {stray} (path split at a space)."))
        return True

    def forget_host_key(self, host: str) -> bool:
        """Elimina la huella de `host` de known_hosts (auto-correccion). La unidad regenera su llave
        de host al reiniciarse, asi que esto es rutinario tras un flash o un reinicio."""
        removed = self.cleanup_legacy_known_hosts()
        kh = self.known_hosts_file()
        if not kh.exists():
            return removed
        lines = kh.read_text(encoding="utf-8", errors="replace").splitlines()
        keep = [l for l in lines if not _known_hosts_line_matches(l, host)]
        if len(keep) != len(lines):
            kh.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
            self._log("OK", tr(f"known_hosts: entrada de {host} eliminada.", f"known_hosts: entry for {host} removed."))
            removed = True
        return removed


def _known_hosts_line_matches(line: str, host: str) -> bool:
    parts = line.strip().split()
    if not parts:
        return False
    if parts[0].startswith("@"):      # marcador @cert-authority / @revoked
        parts = parts[1:]
    if not parts:
        return False
    hosts = parts[0].split(",")
    return any(h == host or h.startswith(f"[{host}]:") for h in hosts)
