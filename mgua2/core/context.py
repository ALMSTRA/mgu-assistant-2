"""Contexto de la aplicacion: rutas, bus de log, estado y servicios."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..i18n import tr
from .logbus import LogBus
from .paths import DataPaths, data_paths
from .state import SessionState, StateMachine


class AppContext:
    def __init__(self, *, demo: bool = False, data_base: Optional[str | Path] = None) -> None:
        self.demo = demo
        if demo and data_base is None:
            from tempfile import mkdtemp
            data_base = mkdtemp(prefix="mgua2-demo-")
        self.paths: DataPaths = data_paths(data_base).ensure()
        self.bus = LogBus(self.paths.logs)
        self.state = SessionState(demo=demo)
        self.sm = StateMachine(self.state)

        from ..services.doctor import Doctor
        from ..services.runner import ProcessRunner
        from ..services.sshtool import SshTool
        from ..services.store import StoreInstaller
        from ..services.tools import ToolsManager

        from ..services.sources import SourcesManager

        self.runner = ProcessRunner(self.bus)
        self.tools = ToolsManager(self.paths, self.bus)
        self.sources = SourcesManager(self.paths, self.bus)
        self.sshtool = SshTool(self.tools, self.runner, self.paths, self.bus)
        self.store = StoreInstaller(self.tools, self.runner, self.bus)
        self.doctor = Doctor(self)

        if demo:
            from .demo import install_demo
            install_demo(self)
        else:
            # Archivo huerfano que dejaba la ruta de known_hosts sin comillas (bug corregido 2026-11-08).
            self.sshtool.cleanup_legacy_known_hosts()

        self.state.tools_ready = self.tools.all_ready()
        from ..services import netinfo
        self.state.admin = demo or netinfo.is_admin()
        self.state.openssh_ok = demo or bool(netinfo.openssh_path())
        self.bus.info(tr(f"Datos en {self.paths.base}", f"Data folder: {self.paths.base}") + ("  [DEMO]" if demo else ""))

    # -- demo desde la app ----------------------------------------------------
    def switch_to_demo(self) -> None:
        """Activa el modo demo en caliente: TODO lo simulado va a una carpeta temporal nueva.

        Nunca sobre los datos reales: el 2026-11-08 el boton 'Modo demo' sembro los stubs de la
        demo en %LOCALAPPDATA% y sobrescribio el ssh_enable.py descargado con '# demo'.
        """
        from tempfile import mkdtemp

        from ..services.runner import ProcessRunner
        from ..services.sources import SourcesManager
        from ..services.sshtool import SshTool
        from ..services.store import StoreInstaller
        from ..services.tools import ToolsManager
        from .demo import install_demo

        self.demo = True
        self.state.demo = True
        self.paths = data_paths(mkdtemp(prefix="mgua2-demo-")).ensure()
        self.runner = ProcessRunner(self.bus)
        self.tools = ToolsManager(self.paths, self.bus)
        self.sources = SourcesManager(self.paths, self.bus)
        self.sshtool = SshTool(self.tools, self.runner, self.paths, self.bus)
        self.store = StoreInstaller(self.tools, self.runner, self.bus)
        install_demo(self)
        self.state.tools_ready = True
        self.state.admin = True
        self.state.openssh_ok = True
        self.bus.warn(tr(f"Modo demo activado: todo simulado en {self.paths.base}. Los datos reales no se tocan.",
                         f"Demo mode on: everything is simulated in {self.paths.base}. Real data is not touched."))

    # -- catalogo ------------------------------------------------------------
    def catalog_repos_dir(self) -> Path:
        return self.tools.paths.repos

    def build_catalog(self):
        from ..catalog.scanner import CatalogScanner
        commits: dict = {}
        if self.demo:
            try:
                commits = json.loads((self.catalog_repos_dir().parent / "commits.json").read_text(encoding="utf-8"))
            except Exception:
                commits = {}

        def lookup(name: str) -> str:
            if self.demo:
                return str((commits.get(name) or {}).get("commit", ""))
            if "/" in name:
                return self.tools.source_commit(name)
            return self.tools.commit_of(name)

        from ..catalog.scanner import APP_REPOS
        entries: list = list(APP_REPOS)
        if not self.demo:
            for repo in self.sources.enabled():
                d = self.tools.source_dir(repo)
                if d.exists():
                    entries.append((repo, d.name))
        return CatalogScanner(self.catalog_repos_dir(), commit_lookup=lookup).scan(entries)

    def close(self) -> None:
        self.bus.close()
