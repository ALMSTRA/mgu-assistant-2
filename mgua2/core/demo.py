"""Modo demostracion: todo simulado, sin coche/ENET/VIN/llaves ni descargas.

El DemoRunner responde con salida guionizada en vez de lanzar procesos; las
herramientas se declaran listas apuntando a los fixtures incluidos; los
respaldos/enrollments se crean en el directorio temporal de la demo.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..i18n import tr
from ..security.redaction import mask_vin
from ..services.runner import ProcessHandle, ProcessResult, ProcessRunner
from ..services.sshtool import SshTool
from ..services.tools import ToolInfo, ToolsManager, ToolsStatus

DEMO_VIN = "WBSDEMO00000DEMO1"

DEMO_STATUS = [
    "[demo] === MGU-SSH session | action=status ===",
    "[demo] Scanning active adapters for an ENET gateway (UDP 6811 broadcast)...",
    "[demo] Gateway 169.254.254.36:6801 (ZGW) found on adapter 'Ethernet 2' 169.254.10.20",
    f"[demo] VIN: {DEMO_VIN}",
    "[demo] SVK: BTLD 00003F36 030.016.006 | SWFL 030.016.002 | CAFD 00003F3A",
    "[demo] MGU unit IP: 169.254.36.47",
    "[demo] Debug state (DTC B7F8E5): inactive",
    "[demo] MGU SSH port 22 is not open",
    "[demo] status done (read-only).",
]
DEMO_PREFLIGHT = [
    "[demo] === MGU-SSH session | action=preflight ===",
    "[demo] Gateway 169.254.254.36:6801 found",
    "[demo] SVK: BTLD 00003F36 030.016.006",
    "[demo] reading the MGU coding (DID 0x3000-0x3FFF)... 128 blocks",
    "[demo]   verifying the coding (second read)... identical",
    "[demo] Coding backup written to {folder}",
]
DEMO_STORE = [
    "[demo] mgu-install first-install",
    "[demo] head unit reached at {host} (ssh root)",
    "[demo] installing app-privacy, mgu-deploy, mgu-python, mgu-render, mgu-updater, robertn_store ...",
    "[demo] seeding updater sources: mgu-store, idrive7-apps, idrive-apps, car-apps",
    "[demo] done. Restart the head unit to see the Store tile.",
]
DEMO_USB = [
    "[demo] mgu-install usb-repo {stick}",
    "[demo] fetching github:cauliflowermossgrape/idrive7-apps ...",
    "[demo] catalog written to {stick}/mgu-repo/",
    "[demo] done. Plug the stick into the car and open Store > USB.",
]


def fixtures_root() -> Path:
    return Path(__file__).resolve().parent.parent / "resources" / "fixtures"


class DemoRunner(ProcessRunner):
    def __init__(self, bus, demo_dir: Path) -> None:
        super().__init__(bus)
        self.demo_dir = demo_dir

    def _script(self, argv: list[str]) -> tuple[int, list[str]]:
        j = " ".join(argv).lower()
        if "ssh_enable.py" in j and " status" in j:
            return 0, DEMO_STATUS
        if "ssh_enable.py" in j and "preflight" in j:
            folder = self.demo_dir / "repos" / "idrive7-8-ssh-root" / "data" / "preflight" / f"20261108-120000-{DEMO_VIN}"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "backup.json").write_text(json.dumps({"vin": DEMO_VIN, "taken": "2026-11-08 12:00:00", "verified": True}), encoding="utf-8")
            (folder / "coding_MGU.txt").write_text("# demo coding\n", encoding="utf-8")
            (folder / "RESTORE.txt").write_text("demo\n", encoding="utf-8")
            (folder / "SHA256SUMS").write_text("demo\n", encoding="utf-8")
            return 0, [l.replace("{folder}", str(folder)) for l in DEMO_PREFLIGHT]
        if "ssh_enable.py" in j and (" enable" in j or " persist" in j):
            return 0, ["[demo] enrolling ...", "[demo] MGU SSH port 22 is open", "[demo] SSH OK as root: uid=0(root)"]
        if "first-install" in j:
            host = argv[argv.index("--host") + 1] if "--host" in argv else "172.16.222.97"
            return 0, [l.replace("{host}", host) for l in DEMO_STORE]
        if "usb-repo" in j:
            stick = argv[argv.index("usb-repo") + 1] if "usb-repo" in argv else "E:\\"
            return 0, [l.replace("{stick}", stick) for l in DEMO_USB]
        if "uninstall" in j:
            return 0, ["[demo] uninstalling ...", "[demo] done."]
        if argv and os.path.basename(argv[0]).lower().startswith("ssh"):
            return 0, ["uid=0(root) gid=0(root) groups=0(root)"]
        return 0, [tr(f"[demo] (simulado) {j}", f"[demo] (simulated) {j}")]

    def run(self, argv, *, cwd=None, env=None, on_output=None, on_finished=None,
            cancelable=True, timeout=None, label=""):
        argv = [str(a) for a in argv]
        self._log("CMD", (label + ": " if label else "") + "[demo] " + " ".join(argv[:4]) + " …")
        rc, lines = self._script(argv)
        res = ProcessResult(returncode=rc, lines=list(lines))
        if any(DEMO_VIN in l for l in lines):
            res.vin_masked = mask_vin(DEMO_VIN)
        for ln in lines:
            self._log("OUT", ln)
            if on_output:
                on_output(ln)
        self._log("OK", tr(f"codigo de salida: {rc}", f"exit code: {rc}"))
        if on_finished:
            on_finished(res)
        return ProcessHandle(cancelable=cancelable)

    def run_blocking(self, argv, *, cwd=None, env=None, timeout=None, label=""):
        rc, lines = self._script([str(a) for a in argv])
        return ProcessResult(returncode=rc, lines=list(lines))


class DemoTools(ToolsManager):
    """Herramientas 'listas' apuntando a los fixtures; sin descargas."""

    def __init__(self, paths, bus, demo_dir: Path) -> None:
        super().__init__(paths, bus)
        self.demo_dir = demo_dir
        self._commits = {}
        try:
            self._commits = json.loads((fixtures_root() / "commits.json").read_text(encoding="utf-8"))
        except Exception:
            pass
        # Script y exe "existentes" en el temporal de la demo. Se escriben stubs, asi que NUNCA
        # sobre una herramienta real: si alguien apunta la demo a datos reales, mejor fallar que
        # destruir (paso el 2026-11-08 con el boton 'Modo demo').
        script = self.paths.repos / "idrive7-8-ssh-root" / "ssh_enable.py"
        for real in (script, self.ssh_prebuilt_exe, self.mgu_install_exe):
            if real.exists() and real.stat().st_size > 64:
                raise RuntimeError(tr(f"Demo: me niego a sobrescribir una herramienta real en {real}. "
                                      "El modo demo debe usar una carpeta temporal.",
                                      f"Demo: refusing to overwrite a real tool at {real}. "
                                      "Demo mode must use a temporary folder."))
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("# demo\n", encoding="utf-8")
        self.ssh_prebuilt_dir.mkdir(parents=True, exist_ok=True)
        self.ssh_prebuilt_exe.write_bytes(b"demo")
        self.mgu_install_exe.write_bytes(b"demo")

    def repo_dir(self, name: str) -> Path:
        if name == "idrive7-8-ssh-root":
            return self.paths.repos / name
        return fixtures_root() / "repos" / name

    @property
    def paths_repos_for_catalog(self) -> Path:
        return fixtures_root() / "repos"

    def commit_of(self, name: str) -> str:
        return str((self._commits.get(name) or {}).get("commit", "demo"))

    def status(self) -> ToolsStatus:
        s = ToolsStatus()
        s.ssh_source = ToolInfo(tr("Codigo SSH tool", "SSH tool source code"), True,
                                self.commit_of("idrive7-8-ssh-root")[:10], "demo", str(self.ssh_script))
        s.ssh_prebuilt = ToolInfo(tr("GUI oficial MGU-SSH.exe", "Official MGU-SSH.exe GUI"), True, "v1.3.1 (demo)",
                                  "demo", str(self.ssh_prebuilt_exe))
        s.mgu_install = ToolInfo(tr("Instalador mgu-install", "mgu-install installer"), True, "demo", "demo",
                                 str(self.mgu_install_exe))
        for n in ("idrive7-apps", "idrive-apps", "car-apps", "mgu-store"):
            s.repos[n] = ToolInfo(n, True, self.commit_of(n)[:10], "demo", str(self.repo_dir(n)))
        return s

    def install_all(self, progress=None, force=False) -> ToolsStatus:
        self._log("OK", tr("[demo] herramientas simuladas: nada que descargar.",
                           "[demo] simulated tools: nothing to download."))
        return self.status()


class DemoSshTool(SshTool):
    def launch_official_gui(self) -> bool:
        self._log("OK", tr("[demo] Aqui se abriria MGU-SSH.exe como administrador (no se lanza nada en demo).",
                           "[demo] MGU-SSH.exe would open here as administrator (nothing is launched in demo)."))
        # Simula que el usuario completo Flash+Enable: crea un enrollment ficticio.
        d = self.tools.ssh_prebuilt_dir / "data" / "enrollments" / DEMO_VIN
        d.mkdir(parents=True, exist_ok=True)
        (d / "id_rsa").write_text("demo-key-not-real\n", encoding="utf-8")
        (d / "connect.txt").write_text("ssh -i id_rsa root@169.254.36.47\n", encoding="utf-8")
        (d / "fingerprints.txt").write_text("SHA256:demo+fingerprint\n", encoding="utf-8")
        (d / "metadata.json").write_text(json.dumps({"vin": DEMO_VIN, "arch": "id7", "mgu_ip": "169.254.36.47",
                                                      "timestamp": "2026-11-08T12:05:00Z"}), encoding="utf-8")
        self._log("OK", tr("[demo] enrollment simulado creado.", "[demo] simulated enrollment created."))
        return True


def install_demo(ctx) -> None:
    demo_dir = ctx.paths.base
    ctx.bus.add_vin(DEMO_VIN)  # el VIN demo lleva 'O' (no es VIN valido): censurarlo igual
    ctx.runner = DemoRunner(ctx.bus, demo_dir)
    ctx.tools = DemoTools(ctx.paths, ctx.bus, demo_dir)
    ctx.sshtool = DemoSshTool(ctx.tools, ctx.runner, ctx.paths, ctx.bus)
    from ..services.store import StoreInstaller
    ctx.store = StoreInstaller(ctx.tools, ctx.runner, ctx.bus)
    ctx.catalog_repos_dir = lambda: fixtures_root() / "repos"  # type: ignore[assignment]
