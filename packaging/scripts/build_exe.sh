#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)

cd "$REPO_ROOT"

PYTHON_BIN="python"
if [ -x "$REPO_ROOT/venv/Scripts/python.exe" ]; then
  PYTHON_BIN="$REPO_ROOT/venv/Scripts/python.exe"
fi

find_makensis() {
  if command -v makensis >/dev/null 2>&1; then
    command -v makensis
    return 0
  fi

  for candidate in \
    "/c/Program Files (x86)/NSIS/makensis.exe" \
    "/c/Program Files/NSIS/makensis.exe" \
    "C:/Program Files (x86)/NSIS/makensis.exe" \
    "C:/Program Files/NSIS/makensis.exe"
  do
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

to_windows_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1"
    return 0
  fi

  printf '%s' "$1" | sed 's|/|\\|g'
}

DIST_INFO=$("$PYTHON_BIN" - <<'PY'
from pathlib import Path
import re
import tomllib

data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
project = data["project"]
name = re.sub(r"[-_.]+", "_", str(project["name"]).strip()).lower()
version = str(project["version"]).strip()

try:
    from packaging.version import Version
except ImportError:
    normalized_version = version.replace("-", "")
else:
    normalized_version = str(Version(version))

print(name)
print(normalized_version)
PY
)

DIST_NAME=$(printf '%s\n' "$DIST_INFO" | sed -n '1p')
RELEASE=$(printf '%s\n' "$DIST_INFO" | sed -n '2p')

INSTALLER_NAME="${DIST_NAME}-${RELEASE}.exe"
INSTALLER_PATH="dist/${INSTALLER_NAME}"
PORTABLE_BASE="dist/${DIST_NAME}-${RELEASE}"
PORTABLE_PATH="${PORTABLE_BASE}.zip"

printf '%s\n' "Paso 0: eliminando dist/"
rm -rf dist

printf '%s\n' "Paso 1: generando build PyInstaller"

"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --onedir \
  --name MIRA \
  --icon src/mira/ui/icons/mira.ico \
  --paths src \
  --add-data "src/mira/ui/icons;mira/ui/icons" \
  --copy-metadata mira-personal-finance-assistant \
  packaging/windows/mira_launcher.pyw

printf '%s\n' "Paso 2: generando instalador ${INSTALLER_NAME}"
MAKENSIS_BIN=$(find_makensis || true)
if [ -z "${MAKENSIS_BIN:-}" ]; then
  printf '%s\n' "Error: no se encontro makensis. Instala NSIS o agrega makensis al PATH." >&2
  exit 1
fi

NSIS_OUTFILE=$(to_windows_path "$REPO_ROOT/$INSTALLER_PATH")
NSIS_BUILD_DIR=$(to_windows_path "$REPO_ROOT/dist/MIRA")
MSYS2_ARG_CONV_EXCL='*' "$MAKENSIS_BIN" "/DSETUP_OUTFILE=${NSIS_OUTFILE}" "/DBUILD_DIR=${NSIS_BUILD_DIR}" "packaging/windows/setup.nsi"

printf '%s\n' "Paso 3: generando portable ${PORTABLE_PATH}"
"$PYTHON_BIN" - "$PORTABLE_BASE" <<'PY'
from pathlib import Path
import sys
import zipfile

base_name = sys.argv[1]
source_dir = Path("dist") / "MIRA"
archive_path = Path(f"{base_name}.zip")

with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(source_dir.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(source_dir))

print(archive_path)
PY

printf '%s\n' "Artefactos generados:"
printf '  %s\n' "$INSTALLER_PATH"
printf '  %s\n' "$PORTABLE_PATH"
