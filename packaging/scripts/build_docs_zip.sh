#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)

cd "$REPO_ROOT"

PYTHON_BIN="python"
if [ -x "$REPO_ROOT/venv/Scripts/python.exe" ]; then
  PYTHON_BIN="$REPO_ROOT/venv/Scripts/python.exe"
elif [ -x "$REPO_ROOT/venv/bin/python" ]; then
  PYTHON_BIN="$REPO_ROOT/venv/bin/python"
fi

printf '%s\n' "Using Python: $PYTHON_BIN"

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import importlib.util
modules = ("mkdocs", "material", "mkdocs_static_i18n")
missing = [name for name in modules if importlib.util.find_spec(name) is None]
raise SystemExit(1 if missing else 0)
PY
then
  printf '%s\n' "Installing documentation dependencies..."
  "$PYTHON_BIN" -m pip install ".[docs]"
fi

DIST_INFO=$("$PYTHON_BIN" - <<'PY'
from pathlib import Path
import tomllib

data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
project = data["project"]
version = str(project["version"]).strip()
print(version)
PY
)

RELEASE=$(printf '%s\n' "$DIST_INFO" | sed -n '1p')
ARCHIVE_PATH="dist/mira-site-${RELEASE}.zip"

printf '%s\n' "Cleaning previous documentation build"
rm -rf site

printf '%s\n' "Building MkDocs site"
"$PYTHON_BIN" -m mkdocs build --strict

printf '%s\n' "Creating deploy archive ${ARCHIVE_PATH}"
mkdir -p dist
"$PYTHON_BIN" - "$ARCHIVE_PATH" <<'PY'
from pathlib import Path
import sys
import zipfile

archive_path = Path(sys.argv[1])
site_dir = Path("site")

if not site_dir.is_dir():
    raise SystemExit("MkDocs output directory 'site' was not created")

with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(site_dir.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(site_dir))

print(archive_path)
PY

printf '%s\n' "Archive ready to upload:"
printf '  %s\n' "$ARCHIVE_PATH"
printf '%s\n' "The ZIP contains the contents of site/ at the archive root."
