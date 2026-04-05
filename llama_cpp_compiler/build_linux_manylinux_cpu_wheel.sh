#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

# Build a manylinux wheel for llama-cpp-python on Linux x86_64.
#
# Target profile: CPU-only.
# All GPU backends are explicitly disabled (CUDA, HIP/ROCm, Vulkan, OpenCL,
# SYCL). Metal is not available on Linux.
#
# Usage:
#   ./llama_cpp_compiler/build_linux_manylinux_cpu_wheel.sh [version]
#
# Example:
#   ./llama_cpp_compiler/build_linux_manylinux_cpu_wheel.sh 0.3.16

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"

VERSION="${1:-0.3.16}"
PYTHON_TAG="cp312"
MANYLINUX_IMAGE="quay.io/pypa/manylinux_2_28_x86_64:latest"

mkdir -p "$DIST_DIR"

if command -v docker >/dev/null 2>&1; then
  CONTAINER_CMD="docker"
elif command -v podman >/dev/null 2>&1; then
  CONTAINER_CMD="podman"
else
  echo "Error: Docker or Podman is required." >&2
  exit 1
fi

echo "=== Linux manylinux wheel build: llama-cpp-python==${VERSION} ==="
echo "Runtime: ${CONTAINER_CMD}"
echo "Profile: CPU-only (all GPU backends disabled)"
echo ""

"$CONTAINER_CMD" run --rm \
  -v "$DIST_DIR:/output:z" \
  "$MANYLINUX_IMAGE" \
  bash -c "
    set -euo pipefail

    PYTHON=/opt/python/${PYTHON_TAG}-${PYTHON_TAG}/bin/python

    echo '--- Installing build tooling ---'
    \$PYTHON -m pip install --upgrade pip setuptools wheel
    \$PYTHON -m pip install 'scikit-build-core[pyproject]>=0.9.2' cmake ninja auditwheel

    echo '--- Downloading source ---'
    \$PYTHON -m pip download --no-binary :all: --no-deps \
      \"llama-cpp-python==${VERSION}\" -d /tmp/src

    echo '--- Extracting source ---'
    cd /tmp/src
    tar xzf llama_cpp_python-${VERSION}.tar.gz
    cd llama_cpp_python-${VERSION}

    echo '--- Building wheel (CPU-only) ---'
    export CMAKE_ARGS='-DGGML_CUDA=OFF -DGGML_METAL=OFF -DGGML_VULKAN=OFF -DGGML_OPENCL=OFF -DGGML_SYCL=OFF -DGGML_HIP=OFF'

    \$PYTHON -m pip wheel . \
      --no-deps \
      --no-build-isolation \
      --wheel-dir /tmp/wheelhouse

    echo '--- Repairing wheel with auditwheel ---'
    auditwheel repair /tmp/wheelhouse/llama_cpp_python-*.whl \
      --plat manylinux_2_28_x86_64 \
      -w /output

    echo ''
    echo '=== Build complete ==='
    ls -lh /output/llama_cpp_python-*.whl
  "

echo ""
echo "Wheel(s) generated in $DIST_DIR:"
ls -lh "$DIST_DIR"/llama_cpp_python-*.whl

echo ""
echo "SHA-256:"
sha256sum "$DIST_DIR"/llama_cpp_python-*.whl

echo ""
echo "CPU recommendation for this wheel:"
echo "  - Prefer small quantized models (1B-3B, Q4_K_M/Q5_K_M)"
echo "  - Typical examples: SmolLM2, Qwen2.5 1.5B/3B, TinyLlama"
