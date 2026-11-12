"""Validacion de archivos de llave SSH sin leer su contenido."""
from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

from ..i18n import tr


@dataclass(frozen=True)
class KeyCheck:
    ok: bool
    reason: str = ""
    warning: str = ""


def validate_key_path(path: str | Path) -> KeyCheck:
    if not path:
        return KeyCheck(False, tr("No se indico ninguna llave.", "No key was given."))
    p = Path(path).expanduser()
    if p.is_symlink() and not p.exists():
        return KeyCheck(False, tr("La llave es un enlace simbolico roto.", "The key is a broken symbolic link."))
    if not p.exists():
        return KeyCheck(False, tr(f"La llave no existe: {p}", f"The key does not exist: {p}"))
    if p.is_dir():
        return KeyCheck(False, tr("La ruta es un directorio, no una llave.", "The path is a directory, not a key."))
    if not p.is_file():
        return KeyCheck(False, tr("La ruta no es un archivo regular.", "The path is not a regular file."))
    if not os.access(p, os.R_OK):
        return KeyCheck(False, tr("La llave no es legible por el usuario actual.",
                                  "The key is not readable by the current user."))
    if not sys.platform.startswith("win"):
        mode = p.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            return KeyCheck(False, tr(f"Permisos inseguros (grupo/otros). Ejecute: chmod 600 \"{p}\".",
                                      f"Insecure permissions (group/others). Run: chmod 600 \"{p}\"."))
        return KeyCheck(True)
    return KeyCheck(True, warning=tr("En Windows no se verifica la ACL; asegure que solo su usuario acceda al archivo.",
                                     "On Windows the ACL is not checked; make sure only your user can access the file."))
