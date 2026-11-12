#!/bin/sh
# Build de MGU Assistant 2 en macOS (arm64 nativo en Apple Silicon).
# Uso (raiz de v2): sh packaging/macos/build.sh
# Nota: la GUI oficial MGU-SSH solo tiene prebuilt para Windows; en macOS el
# tool se ejecuta con nuestro interprete (mgua2-cli) a partir del codigo.
set -eu
ROOT=$(cd "$(dirname "$0")/../.." && pwd); cd "$ROOT"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m PyInstaller --noconfirm --clean packaging/mgua2.spec
echo "LISTO: dist/MGU-Assistant-2/  (abrir con clic secundario -> Abrir si no esta notarizado)"
