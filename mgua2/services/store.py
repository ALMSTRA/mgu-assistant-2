"""Instalador oficial del Store (`mgu-install`, binario standalone verificado).

first-install por ENET (IP de la unidad) o por el hotspot Wi-Fi del coche
(172.16.222.97). Tambien `usb-repo` para preparar una memoria USB con apps
(instalacion offline desde la pantalla del coche) y `uninstall`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..core.logbus import LogBus
from ..core.models import HOTSPOT_HOST
from ..i18n import tr
from ..security.keyfile import validate_key_path
from ..security.redaction import redact_args
from .runner import ProcessRunner
from .tools import ToolsManager


@dataclass
class InstallPlan:
    argv: list[str]
    display: str
    host: str
    note: str


class StoreInstaller:
    def __init__(self, tools: ToolsManager, runner: ProcessRunner, bus: Optional[LogBus] = None) -> None:
        self.tools = tools
        self.runner = runner
        self.bus = bus

    def available(self) -> bool:
        return self.tools.mgu_install_exe.exists()

    @property
    def exe(self) -> Path:
        return self.tools.mgu_install_exe

    def plan_first_install(self, key_path: str, *, host: str | None = None, no_renderer: bool = False,
                           no_uplink: bool = False, extra_ssh_opts: Optional[list[str]] = None,
                           no_restart_prompt: bool = True) -> InstallPlan:
        if host is not None and not host.strip():
            # nunca caer al hotspot en silencio
            raise ValueError(tr("Falta la IP de la unidad (host vacio).", "The unit's IP is missing (empty host)."))
        host = (host or HOTSPOT_HOST).strip()
        argv = [str(self.exe), "first-install", "--identity", key_path, "--host", host]
        if no_renderer:
            argv.append("--no-renderer")
        if no_uplink:
            argv.append("--no-uplink")
        for o in extra_ssh_opts or []:
            argv += ["--ssh-opt", o]
        if no_restart_prompt:
            argv.append("--no-restart-prompt")
        note = (tr("por hotspot Wi-Fi del coche", "via the car's Wi-Fi hotspot") if host == HOTSPOT_HOST
                else tr("por ENET / direccion indicada", "via ENET / the given address"))
        return InstallPlan(argv=argv, display=" ".join(redact_args(argv)), host=host, note=note)

    def run_first_install(self, plan: InstallPlan, on_output=None, on_finished=None):
        chk = validate_key_path(plan.argv[plan.argv.index("--identity") + 1])
        if not chk.ok:
            raise ValueError(tr(f"Llave invalida: {chk.reason}", f"Invalid key: {chk.reason}"))
        # Modifica la unidad: no cancelable, sin timeout.
        return self.runner.run(plan.argv, on_output=on_output, on_finished=on_finished,
                               cancelable=False, timeout=None, label=tr("instalar MGU Store", "install MGU Store"))

    def plan_uninstall(self, key_path: str, host: str | None = None) -> InstallPlan:
        if host is not None and not host.strip():
            raise ValueError(tr("Falta la IP de la unidad (host vacio).", "The unit's IP is missing (empty host)."))
        host = (host or HOTSPOT_HOST).strip()
        argv = [str(self.exe), "uninstall", "--yes", "--no-restart-prompt", "--identity", key_path, "--host", host]
        return InstallPlan(argv=argv, display=" ".join(redact_args(argv)), host=host,
                           note=tr("desinstalar", "uninstall"))

    def run_uninstall(self, plan: InstallPlan, on_output=None, on_finished=None):
        return self.runner.run(plan.argv, on_output=on_output, on_finished=on_finished,
                               cancelable=False, timeout=None, label=tr("desinstalar MGU Store", "uninstall MGU Store"))

    # -- USB offline -----------------------------------------------------------
    def plan_usb_repo(self, stick_dir: str, inputs: list[str]) -> InstallPlan:
        argv = [str(self.exe), "usb-repo", stick_dir, *inputs]
        return InstallPlan(argv=argv, display=" ".join(redact_args(argv)), host="",
                           note=tr("repositorio USB", "USB repository"))

    def run_usb_repo(self, plan: InstallPlan, on_output=None, on_finished=None):
        return self.runner.run(plan.argv, on_output=on_output, on_finished=on_finished,
                               cancelable=True, timeout=None, label=tr("preparar USB", "prepare USB"))


def github_input(owner_repo: str) -> str:
    """Entrada `github:owner/repo` para usb-repo."""
    return f"github:{owner_repo}"
