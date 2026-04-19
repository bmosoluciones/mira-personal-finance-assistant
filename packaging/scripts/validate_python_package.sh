#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)

cd "$REPO_ROOT"

resolve_python_bin() {
  if [ "${1:-}" != "" ]; then
    printf '%s\n' "$1"
    return 0
  fi

  if [ "${PYTHON_BIN:-}" != "" ]; then
    printf '%s\n' "$PYTHON_BIN"
    return 0
  fi

  if [ -x "$REPO_ROOT/venv/Scripts/python.exe" ]; then
    printf '%s\n' "$REPO_ROOT/venv/Scripts/python.exe"
    return 0
  fi

  if [ -x "$REPO_ROOT/venv/bin/python" ]; then
    printf '%s\n' "$REPO_ROOT/venv/bin/python"
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "python3"
    return 0
  fi

  if command -v python >/dev/null 2>&1; then
    printf '%s\n' "python"
    return 0
  fi

  printf '%s\n' "Error: could not find a Python interpreter (tried PYTHON_BIN, first argument, python3, python)." >&2
  return 1
}

run_step() {
  local title="$1"
  shift
  printf '\n==> %s\n' "$title"
  "$@"
}

run_python_module_step() {
  local title="$1"
  local module_name="$2"
  shift 2
  run_step "$title" "$PYTHON_BIN" -m "$module_name" "$@"
}

PYTHON_BIN=$(resolve_python_bin "${1:-}")

printf '%s\n' "Using Python: $PYTHON_BIN"

run_step "Upgrade pip" "$PYTHON_BIN" -m pip install --upgrade pip
run_step "Install dependencies" "$PYTHON_BIN" -m pip install '.[dev]'
run_python_module_step "Lint with flake8" flake8 src/
run_python_module_step "Lint with ruff" ruff check src/
run_python_module_step "Type-check with mypy" mypy --no-color-output src/mira/
run_python_module_step "Test with pytest" pytest
run_python_module_step "Test with pytest -m full" pytest -m full

printf '\n%s\n' "All CI validation steps completed successfully."
