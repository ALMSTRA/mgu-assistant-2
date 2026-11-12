# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: MGU Assistant 2 (onedir) con DOS ejecutables en una carpeta.

  dist/MGU-Assistant-2/MGU-Assistant-2.exe   GUI (windowed)
  dist/MGU-Assistant-2/mgua2-cli.exe         consola: interprete del tool upstream

Build:  pyinstaller --noconfirm --clean packaging/mgua2.spec
No incluye repos, SDK, VIN ni llaves: todo se descarga al primer uso.
"""
import os

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [(os.path.join(ROOT, "mgua2", "resources"), "mgua2/resources")]
datas += collect_data_files("cryptography")

# La herramienta upstream (ssh_enable.py + mgu7) se ejecuta con NUESTRO
# interprete, asi que todos los modulos de la stdlib que ella importa deben ir
# en el paquete aunque mgua2 no los use. Lista tomada de sus imports.
UPSTREAM_STDLIB = [
    "argparse", "base64", "binascii", "contextlib", "csv", "ctypes", "ctypes.util",
    "datetime", "errno", "fnmatch", "getpass", "glob", "hashlib", "hmac", "io",
    "ipaddress", "json", "locale", "logging", "os", "pathlib", "platform", "queue",
    "re", "secrets", "select", "shutil", "signal", "socket", "ssl", "stat", "string",
    "struct", "subprocess", "sys", "tempfile", "textwrap", "threading", "time",
    "traceback", "uuid", "zlib", "zipfile", "gzip", "tarfile", "email", "http",
    "urllib", "urllib.request", "html", "xml", "decimal", "random", "math",
    "collections", "itertools", "functools", "operator", "codecs", "encodings",
    "unicodedata", "copy", "pprint", "enum", "dataclasses", "typing", "runpy",
    "bz2", "lzma", "pickle", "shlex", "difflib", "heapq", "bisect", "array",
    "mmap", "weakref", "types", "inspect", "abc", "numbers", "fractions", "statistics",
    "concurrent", "concurrent.futures", "asyncio", "multiprocessing", "sqlite3",
]
hiddenimports = (collect_submodules("mgua2") + collect_submodules("cryptography")
                 + ["cffi", "_cffi_backend"] + UPSTREAM_STDLIB)

a = Analysis(
    [os.path.join(SPECPATH, "main.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe_gui = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="MGU-Assistant-2",
    console=False,
    strip=False, upx=False,
    icon=None,
)
exe_cli = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="mgua2-cli",
    console=True,
    strip=False, upx=False,
    icon=None,
)
coll = COLLECT(
    exe_gui, exe_cli,
    a.binaries, a.datas,
    strip=False, upx=False,
    name="MGU-Assistant-2",
)
