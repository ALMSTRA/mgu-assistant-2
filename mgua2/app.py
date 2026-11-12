"""Punto de entrada de MGU Assistant 2.

Modos:
  mgua2                      GUI normal
  mgua2 --demo               GUI con fixtures (sin coche/ENET/VIN/llaves)
  mgua2 --upstream-cli SCRIPT [ARGS...]
                             Ejecuta un script upstream (ssh_enable.py) usando
                             NUESTRO interprete empaquetado. Lo usa el .exe de
                             consola como "python" para la herramienta oficial.

La importacion de Qt es perezosa: el modo --upstream-cli y --help no la
necesitan (el .exe de consola nunca carga la GUI).
"""
from __future__ import annotations

import sys

from . import APP_NAME, __version__


def _usage() -> str:
    return (
        f"{APP_NAME} {__version__}\n"
        "Uso / Usage:\n"
        "  --demo                       GUI en modo demostracion / demo mode (no car)\n"
        "  --lang es|en                 idioma de la interfaz / interface language\n"
        "  --upstream-cli SCRIPT [ARGS] ejecutar un script upstream / run an upstream script\n"
        "  --version                    mostrar version / show version\n"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] == "--upstream-cli":
        from .services.upstream_cli import run_upstream_entry
        if len(args) < 2:
            sys.stderr.write("--upstream-cli requiere la ruta del script\n")
            return 2
        return run_upstream_entry(args[1], args[2:])

    if args and args[0] in ("--version", "-V"):
        print(f"{APP_NAME} {__version__}")
        return 0

    if args and args[0] in ("--help", "-h"):
        print(_usage())
        return 0

    demo = "--demo" in args

    # Idioma ANTES de importar la UI (sus textos de modulo se evaluan al importar).
    # Prioridad: --lang es|en > preferencia guardada > idioma del sistema.
    from . import i18n
    from .core.paths import data_paths
    lang = None
    if "--lang" in args:
        i = args.index("--lang")
        lang = args[i + 1] if i + 1 < len(args) else None
    i18n.set_language(lang or i18n.load_saved(data_paths().state) or i18n.system_language())

    # --- GUI ---
    from PySide6.QtWidgets import QApplication

    from .core.context import AppContext
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    ctx = AppContext(demo=demo)
    win = MainWindow(ctx)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
