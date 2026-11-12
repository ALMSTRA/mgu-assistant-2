"""Puente de interprete: ejecutar scripts upstream con NUESTRO Python.

Problema que resuelve (visto en la v1 en un coche real): un .exe de PyInstaller
no es un interprete de Python, asi que `sys.executable script.py` no sirve, y
la laptop del usuario puede no tener Python. Aqui:

- En desarrollo: se usa el interprete real (`sys.executable`).
- Empaquetado: se invoca el ejecutable de CONSOLA hermano (`mgua2-cli.exe`)
  con `--upstream-cli <script> [args]`; dentro, `run_upstream_entry` pone el
  directorio del script en `sys.path` y lo ejecuta con `runpy` como
  `__main__`. El script upstream NO se modifica: resuelve sus `data/` relativo a
  su propio `__file__` y encuentra `mgu7` y `cryptography` (empaquetada).

Se usa un .exe de consola (no la GUI "windowed") para que stdout/stderr sean
tuberias reales al capturarlas como subproceso.
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

from .. import CLI_EXE_NAME
from ..i18n import get_language, set_language, tr

# El .exe de consola es otro proceso y no pasa por la eleccion de idioma de la GUI: se lo hereda por entorno.
LANG_ENV = "MGUA2_LANG"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def cli_executable() -> str:
    """Ruta del ejecutable que actua como interprete.

    Empaquetado: el .exe de consola hermano. Desarrollo: el Python actual.
    """
    if is_frozen():
        sibling = Path(sys.executable).with_name(CLI_EXE_NAME)
        if sibling.exists():
            return str(sibling)
        # Respaldo: el propio ejecutable (puede carecer de stdout si es GUI).
        return sys.executable
    return sys.executable


def build_argv(script_path: str | Path, args: list[str]) -> list[str]:
    """argv para ejecutar `script_path` con nuestro interprete."""
    script = str(Path(script_path))
    if is_frozen():
        return [cli_executable(), "--upstream-cli", script, *args]
    # -I: aislado (ignora PYTHON* del entorno y el cwd en sys.path), pero el
    # script upstream necesita su propio directorio -> lo anadimos nosotros no
    # aqui sino via el propio script (HERE en sys.path). Usamos -u para salida
    # sin buffer.
    return [sys.executable, "-u", script, *args]


def child_env() -> dict:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env[LANG_ENV] = get_language()
    return env


def run_upstream_entry(script_path: str, args: list[str]) -> int:
    """Se ejecuta DENTRO del .exe: corre el script upstream como __main__."""
    if os.environ.get(LANG_ENV):
        set_language(os.environ[LANG_ENV])
    script = Path(script_path).resolve()
    if not script.exists():
        sys.stderr.write(tr(f"script no encontrado: {script}\n", f"script not found: {script}\n"))
        return 2
    script_dir = str(script.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    os.chdir(script_dir)
    # El tool upstream, si ve `sys.frozen`, cree ser su propio MGU-SSH.exe y
    # resuelve `data/` junto al EJECUTABLE (el nuestro). Lo quitamos para que
    # use su `__file__` real: assets, enrollments, preflight y logs quedan en
    # el directorio del codigo descargado. Los imports ya estan inicializados,
    # asi que es seguro.
    if hasattr(sys, "frozen"):
        try:
            del sys.frozen  # type: ignore[attr-defined]
        except Exception:
            pass
    # El tool upstream usa datetime.utcnow(): en Python 3.12 imprime DeprecationWarning en cada
    # accion y ensucia la consola del usuario sin aportar nada. Se silencia solo esa categoria.
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    # Salida en linea para que el log fluya en vivo.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
        except Exception:
            pass
    sys.argv = [str(script), *args]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as e:
        code = e.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        sys.stderr.write(f"{code}\n")
        return 1
    except Exception as e:
        # El tool upstream no captura, p. ej., el TimeoutError al conectar con una pasarela que no
        # responde; sin esto PyInstaller imprimia un traceback y "Failed to execute script".
        # Texto fijo en ambos idiomas (no se traduce): sshtool.parse_status lo reconoce.
        sys.stderr.write(f"ERROR del tool upstream: {type(e).__name__}: {e}\n")
        return 1
    return 0
