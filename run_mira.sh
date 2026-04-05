#!/usr/bin/env bash
# Sets up required library paths for PySide6/Qt on NixOS

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Convert NIX_LDFLAGS to LD_LIBRARY_PATH so PySide6 can find xcb libs
if [ -n "$NIX_LDFLAGS" ]; then
    NIX_LIB_PATH=$(echo "$NIX_LDFLAGS" | tr ' ' '\n' | grep "^-L" | sed 's/^-L//' | tr '\n' ':')
    export LD_LIBRARY_PATH="${NIX_LIB_PATH}${LD_LIBRARY_PATH}"
fi

export PYTHONPATH="$SCRIPT_DIR/src"

exec xvfb-run -a -s '-screen 0 1280x800x24' python3 "$SCRIPT_DIR/mira_launcher.py" "$@"
