#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)

cd "$REPO_ROOT"

PYTHON_BIN="python"
if [ -x "$REPO_ROOT/venv/Scripts/python.exe" ]; then
  PYTHON_BIN="$REPO_ROOT/venv/Scripts/python.exe"
elif [ -x "$REPO_ROOT/venv/bin/python" ]; then
  PYTHON_BIN="$REPO_ROOT/venv/bin/python"
fi

printf '%s\n' "Usando Python: $PYTHON_BIN"

if ! "$PYTHON_BIN" -c "import build" >/dev/null 2>&1; then
  printf '%s\n' "Instalando dependencia de build..."
  "$PYTHON_BIN" -m pip install build
fi

printf '%s\n' "Limpiando artefactos previos de dist/"
rm -rf dist

printf '%s\n' "Generando sdist (.tar.gz) y wheel (.whl)"
"$PYTHON_BIN" -m build --sdist --wheel

printf '%s\n' "Artefactos generados en dist/:"
find dist -maxdepth 1 -type f | sort
