"""Estado del entorno: administrador, OpenSSH, adaptadores de red / ENET,
internet. Sin instalar nada oculto: ofrece acciones explicitas (relanzar como
administrador, instalar el Cliente OpenSSH) que el usuario dispara.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

# "169.254.1.21   00-1a-2b-3c-4d-5e   dinámico"  (arp -a; cabeceras en cualquier idioma se ignoran)
_ARP_RE = re.compile(r"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})\s+(\S+)")


@dataclass
class Adapter:
    name: str
    description: str
    status: str            # Up / Disconnected / ...
    ipv4: list[str] = field(default_factory=list)

    @property
    def link_local(self) -> list[str]:
        return [ip for ip in self.ipv4 if ip.startswith("169.254.")]

    @property
    def is_up(self) -> bool:
        return self.status.lower() == "up"

    @property
    def looks_enet(self) -> bool:
        """Cableado, con enlace y con direccion link-local (sin DHCP): tipico ENET."""
        d = self.description.lower()
        wired = not any(k in d for k in ("wi-fi", "wifi", "wireless", "bluetooth", "vmware", "virtual", "hyper-v", "loopback", "tap", "tunnel"))
        return wired and self.is_up and bool(self.link_local)


def is_admin() -> bool:
    if sys.platform.startswith("win"):
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    try:
        return os.geteuid() == 0  # type: ignore[attr-defined]
    except Exception:
        return False


def openssh_path() -> Optional[str]:
    return shutil.which("ssh")


def ssh_version() -> str:
    p = openssh_path()
    if not p:
        return ""
    try:
        out = subprocess.run([p, "-V"], capture_output=True, text=True, timeout=15,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return (out.stderr or out.stdout or "").strip().splitlines()[0]
    except Exception:
        return ""


def internet_ok(host: str = "github.com", port: int = 443, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def list_adapters() -> list[Adapter]:
    """Windows: PowerShell Get-NetAdapter + Get-NetIPAddress (JSON). Otros: psutil-free fallback minimo."""
    if sys.platform.startswith("win"):
        ps = (
            "$a = Get-NetAdapter | Select-Object Name,InterfaceDescription,Status,ifIndex; "
            "$ip = Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceIndex,IPAddress; "
            "@{adapters=$a; ips=$ip} | ConvertTo-Json -Depth 4 -Compress"
        )
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                                 capture_output=True, text=True, timeout=30,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            data = json.loads(out.stdout or "{}")
        except Exception:
            return []
        adapters = data.get("adapters") or []
        ips = data.get("ips") or []
        if isinstance(adapters, dict):
            adapters = [adapters]
        if isinstance(ips, dict):
            ips = [ips]
        by_idx: dict[int, list[str]] = {}
        for e in ips:
            try:
                by_idx.setdefault(int(e.get("InterfaceIndex")), []).append(str(e.get("IPAddress")))
            except Exception:
                pass
        result: list[Adapter] = []
        for a in adapters:
            try:
                idx = int(a.get("ifIndex"))
            except Exception:
                idx = -1
            status = a.get("Status")
            if isinstance(status, int):  # algunos builds devuelven enum numerico
                status = {1: "Up", 2: "Disconnected"}.get(status, str(status))
            result.append(Adapter(
                name=str(a.get("Name", "")), description=str(a.get("InterfaceDescription", "")),
                status=str(status or ""), ipv4=by_idx.get(idx, []),
            ))
        return result
    # macOS/Linux: minimo con `ifconfig`/`ip` seria mas trabajo; devolvemos vacio.
    return []


def own_ipv4() -> set[str]:
    """Direcciones IPv4 de esta maquina (para no confundirlas con la unidad)."""
    out: set[str] = set()
    for a in list_adapters():
        out.update(a.ipv4)
    return out


def probe_tcp(host: str, port: int = 22, timeout: float = 3.0) -> str:
    """Sondea un puerto TCP: 'open' | 'refused' (host vivo, puerto cerrado) | 'timeout' | 'error'."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return "open"
    except ConnectionRefusedError:
        return "refused"
    except (socket.timeout, TimeoutError):
        return "timeout"
    except OSError as e:
        win = getattr(e, "winerror", None)
        if win == 10061:
            return "refused"
        if win in (10060, 10065):   # WSAETIMEDOUT / WSAEHOSTUNREACH
            return "timeout"
        return "error"
    finally:
        try:
            s.close()
        except Exception:
            pass


def parse_arp(text: str, prefix: str = "169.254.", exclude: Optional[set[str]] = None) -> list[str]:
    """IPs (con `prefix`) presentes en la salida de `arp -a`, sin difusion ni direcciones propias."""
    out: list[str] = []
    for line in (text or "").splitlines():
        m = _ARP_RE.match(line)
        if not m:
            continue
        ip, mac = m.group(1), m.group(2).lower().replace(":", "-")
        if not ip.startswith(prefix) or ip.endswith(".255") or mac == "ff-ff-ff-ff-ff-ff":
            continue
        if ip in (exclude or set()) or ip in out:
            continue
        out.append(ip)
    return out


def arp_neighbors(prefix: str = "169.254.", exclude: Optional[set[str]] = None) -> list[str]:
    """Hosts link-local con los que ya hubo trafico (tabla ARP): la unidad y la pasarela aparecen aqui
    aunque el descubrimiento UDP 6811 no responda."""
    try:
        res = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=15,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return []
    return parse_arp(res.stdout, prefix, exclude)


def relaunch_as_admin(argv: Optional[list[str]] = None) -> bool:
    """Windows: relanza el ejecutable actual con UAC (runas). Devuelve True si se lanzo."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        exe = sys.executable
        params = " ".join(f'"{a}"' for a in (argv if argv is not None else sys.argv[1:]))
        if not getattr(sys, "frozen", False):
            # En desarrollo: python -m mgua2 ...
            params = f'-m mgua2 {params}'
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        return int(rc) > 32
    except Exception:
        return False


def install_openssh_client_argv() -> list[str]:
    """Comando (elevado) para anadir el Cliente OpenSSH en Windows."""
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command",
            "Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0"]


def run_elevated(argv: list[str]) -> bool:
    """Ejecuta un comando con UAC (sin capturar salida)."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        exe, params = argv[0], " ".join(f'"{a}"' if " " in a else a for a in argv[1:])
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        return int(rc) > 32
    except Exception:
        return False
