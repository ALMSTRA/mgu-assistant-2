"""Rutas de datos por usuario (nunca la carpeta de instalacion).

Windows: %LOCALAPPDATA%\\MGU Assistant 2\\   macOS: ~/Library/Application Support/MGU Assistant 2/
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .. import APP_NAME


def base_data_dir() -> Path:
    if sys.platform.startswith("win"):
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return Path(root) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    root = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(root) / APP_NAME


@dataclass(frozen=True)
class DataPaths:
    base: Path

    @property
    def tools(self) -> Path:      # binarios prebuilt descargados (MGU-SSH, mgu-install)
        return self.base / "tools"

    @property
    def repos(self) -> Path:      # codigo/manifiestos descargados (zip, sin git)
        return self.base / "repos"

    @property
    def logs(self) -> Path:
        return self.base / "logs"

    @property
    def backups(self) -> Path:    # copias de respaldos (preflight) que el usuario elija
        return self.base / "backups"

    @property
    def downloads(self) -> Path:  # archivos descargados antes de extraer
        return self.base / "downloads"

    @property
    def state(self) -> Path:      # estado no secreto (versiones instaladas, etc.)
        return self.base / "state"

    @property
    def usb(self) -> Path:        # staging para repos USB
        return self.base / "usb"

    def all(self) -> list[Path]:
        return [self.base, self.tools, self.repos, self.logs, self.backups,
                self.downloads, self.state, self.usb]

    def ensure(self) -> "DataPaths":
        for p in self.all():
            p.mkdir(parents=True, exist_ok=True)
        return self


def data_paths(base: Path | str | None = None) -> DataPaths:
    return DataPaths(base=Path(base) if base is not None else base_data_dir())
