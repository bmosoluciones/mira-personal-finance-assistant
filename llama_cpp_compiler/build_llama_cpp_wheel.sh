#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

# Build a CPU-only manylinux wheel for llama-cpp-python.
#
# llama-cpp-python does not publish prebuilt wheels on PyPI, so the Flatpak
# build fails because the SDK lacks cmake / scikit-build-core / a C++ compiler.
#
# This script compiles llama-cpp-python from source with GPU support disabled
# (CPU-only) so the resulting wheel works on any x86_64 Linux host regardless
# of whether a GPU is available.
#
# Prerequisites (installed automatically inside the build container):
#   - Docker or Podman (for the manylinux build container)
#
# Usage:
#   ./scripts/build_llama_cpp_wheel.sh [version]
#
# Arguments:
#   version   llama-cpp-python version to build (default: 0.3.16)
#
# Output:
#   dist/llama_cpp_python-<version>-cp312-cp312-manylinux_2_28_x86_64.whl
#
# Once built, upload the wheel to a public URL and update packaging/flatpak/pypi-dependencies.json:
#   1. Replace the llama_cpp_python-*.tar.gz source entry with the wheel URL
#   2. Update the sha256 hash (use: sha256sum dist/*.whl)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VERSION="${1:-0.3.16}"
PYTHON_VERSION="3.12"
PYTHON_TAG="cp312"
MANYLINUX_IMAGE="quay.io/pypa/manylinux_2_28_x86_64:latest"
DIST_DIR="$ROOT_DIR/dist"

mkdir -p "$DIST_DIR"

# ── Detect container runtime ─────────────────────────────────────────────
if command -v docker >/dev/null 2>&1; then
  CONTAINER_CMD="docker"
elif command -v podman >/dev/null 2>&1; then
  CONTAINER_CMD="podman"
else
  echo "Error: Docker or Podman is required to build the manylinux wheel." >&2
  exit 1
fi

echo "=== Building llama-cpp-python==${VERSION} CPU-only wheel ==="
echo "Container runtime: ${CONTAINER_CMD}"
echo "Target: ${PYTHON_TAG}-${PYTHON_TAG}-manylinux_2_28_x86_64"
echo ""

# ── Build inside manylinux container ──────────────────────────────────────
$CONTAINER_CMD run --rm \
  -v "$DIST_DIR:/output:z" \
  "$MANYLINUX_IMAGE" \
  bash -c "
    set -euo pipefail

    PYTHON=/opt/python/${PYTHON_TAG}-${PYTHON_TAG}/bin/python

    echo '--- Installing build dependencies ---'
    \$PYTHON -m pip install --upgrade pip setuptools wheel
    \$PYTHON -m pip install 'scikit-build-core[pyproject]>=0.9.2' cmake ninja

    echo '--- Downloading llama-cpp-python source ---'
    \$PYTHON -m pip download --no-binary :all: --no-deps \
      \"llama-cpp-python==${VERSION}\" -d /tmp/src

    echo '--- Extracting source ---'
    cd /tmp/src
    tar xzf llama_cpp_python-${VERSION}.tar.gz
    cd llama_cpp_python-${VERSION}

    echo '--- Building CPU-only wheel (GPU disabled) ---'
    # Disable all GPU backends so the build is CPU-only.
    export CMAKE_ARGS='-DGGML_CUDA=OFF -DGGML_METAL=OFF -DGGML_VULKAN=OFF -DGGML_OPENCL=OFF -DGGML_SYCL=OFF -DGGML_HIP=OFF'

    \$PYTHON -m pip wheel . \
      --no-deps \
      --no-build-isolation \
      --wheel-dir /tmp/wheelhouse

    echo '--- Repairing wheel with auditwheel ---'
    \$PYTHON -m pip install auditwheel
    auditwheel repair /tmp/wheelhouse/llama_cpp_python-*.whl \
      --plat manylinux_2_28_x86_64 \
      -w /output

    echo ''
    echo '=== Build complete ==='
    ls -lh /output/llama_cpp_python-*.whl
  "

echo ""
echo "Wheel written to:"
ls -lh "$DIST_DIR"/llama_cpp_python-*.whl
echo ""
echo "SHA-256:"
sha256sum "$DIST_DIR"/llama_cpp_python-*.whl
echo ""
echo "Next steps:"
echo "  1. Upload the wheel to a public URL (e.g. GitHub Release asset)"
echo "  2. Update packaging/flatpak/pypi-dependencies.json:"
echo "     - In the python3-llama_cpp_python module, replace the .tar.gz source"
echo "       entry with the wheel URL and its SHA-256 hash"
echo "  3. Run ./scripts/generate_flatpak_deps.sh to regenerate if needed"
