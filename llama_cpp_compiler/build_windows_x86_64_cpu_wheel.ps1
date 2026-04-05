<#
.SYNOPSIS
Build llama-cpp-python wheel on Windows x86_64 (CPU-only).

.DESCRIPTION
Builds a wheel from source with all GPU backends disabled:
- CUDA: OFF
- HIP/ROCm: OFF
- Vulkan: OFF
- OpenCL: OFF
- SYCL: OFF
- Metal: OFF (Metal is Apple-only and not available on Windows)

.PARAMETER Version
llama-cpp-python version to build. Default: 0.3.16

.PARAMETER PythonExe
Python executable to use. Default: python

.EXAMPLE
./llama_cpp_compiler/build_windows_x86_64_cpu_wheel.ps1 -Version 0.3.16
#>

param(
    [string]$Version = "0.3.16",
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir "..")
$DistDir = Join-Path $RootDir "dist"
$BuildDir = Join-Path $env:TEMP "llama_cpp_build_$Version"

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
if (Test-Path $BuildDir) {
    Remove-Item -Recurse -Force $BuildDir
}
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null

Write-Host "=== Windows wheel build: llama-cpp-python==$Version ==="
Write-Host "Profile: CPU-only (all GPU backends disabled)"

& $PythonExe -m pip install --upgrade pip setuptools wheel
& $PythonExe -m pip install "scikit-build-core[pyproject]>=0.9.2" cmake ninja

Push-Location $BuildDir
try {
    Write-Host "--- Downloading source ---"
    & $PythonExe -m pip download --no-binary :all: --no-deps "llama-cpp-python==$Version" -d .

    Write-Host "--- Extracting source ---"
    $Tarball = Get-ChildItem -Path . -Filter "llama_cpp_python-$Version.tar.gz" | Select-Object -First 1
    if (-not $Tarball) {
        throw "Source tarball not found for version $Version"
    }

    tar -xzf $Tarball.FullName
    $SrcDir = Join-Path $BuildDir "llama_cpp_python-$Version"
    if (-not (Test-Path $SrcDir)) {
        throw "Extracted source folder not found: $SrcDir"
    }

    Push-Location $SrcDir
    try {
        Write-Host "--- Building wheel (CPU-only) ---"
        $env:CMAKE_ARGS = "-DGGML_CUDA=OFF -DGGML_METAL=OFF -DGGML_VULKAN=OFF -DGGML_OPENCL=OFF -DGGML_SYCL=OFF -DGGML_HIP=OFF"

        & $PythonExe -m pip wheel . --no-deps --no-build-isolation --wheel-dir $DistDir
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Wheel(s) generated in: $DistDir"
Get-ChildItem -Path $DistDir -Filter "llama_cpp_python-*.whl" | Format-Table Name, Length, LastWriteTime

Write-Host ""
Write-Host "CPU recommendation for this wheel:"
Write-Host "  - Prefer small quantized models (1B-3B, Q4_K_M/Q5_K_M)"
Write-Host "  - Typical examples: SmolLM2, Qwen2.5 1.5B/3B, TinyLlama"
