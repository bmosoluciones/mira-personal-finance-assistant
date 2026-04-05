# llama_cpp_compiler

Scripts para compilar `llama-cpp-python` en formato wheel con perfil **solo CPU**.

Objetivo:
- Generar wheels reproducibles para `x86_64` sin dependencias de CUDA, ROCm/HIP, Vulkan, OpenCL o SYCL.
- Priorizar ejecución local con modelos pequeños cuantizados que funcionen bien en CPU.

## Scripts disponibles

- `build_linux_manylinux_cpu_wheel.sh`: compila wheel manylinux en Linux `x86_64` (CPU-only).
- `build_windows_x86_64_cpu_wheel.ps1`: compila wheel en Windows `x86_64` (CPU-only).
- `build_llama_cpp_wheel.sh`: script base/compatibilidad para manylinux CPU-only.

## 1) Linux manylinux x86_64 (solo CPU)

Script:
- `./llama_cpp_compiler/build_linux_manylinux_cpu_wheel.sh [version]`

Ejemplo:

```bash
./llama_cpp_compiler/build_linux_manylinux_cpu_wheel.sh 0.3.16
```

Requisitos:
- Docker o Podman

Resultado esperado:
- Wheel en `dist/` con nombre similar a:
	- `llama_cpp_python-<version>-cp312-cp312-manylinux_2_28_x86_64.whl`

Notas:
- El script desactiva explícitamente backends GPU:
	- `GGML_CUDA=OFF`
	- `GGML_METAL=OFF`
	- `GGML_VULKAN=OFF`
	- `GGML_OPENCL=OFF`
	- `GGML_SYCL=OFF`
	- `GGML_HIP=OFF`

## 2) Windows x86_64 (solo CPU)

Script:
- `./llama_cpp_compiler/build_windows_x86_64_cpu_wheel.ps1 -Version <version>`

Ejemplo:

```powershell
./llama_cpp_compiler/build_windows_x86_64_cpu_wheel.ps1 -Version 0.3.16
```

Requisitos:
- Python 3.12 recomendado
- Toolchain de compilacion C/C++ para Windows (por ejemplo MSVC Build Tools)

Resultado esperado:
- Wheel en `dist/` con nombre similar a:
	- `llama_cpp_python-<version>-cp312-cp312-win_amd64.whl`

Notas:
- En Windows, `Metal` no aplica (Apple). El script deja igualmente `GGML_METAL=OFF` para evitar ambiguedad.

## Verificacion rapida

Linux/macOS:

```bash
ls -lh dist/llama_cpp_python-*.whl
sha256sum dist/llama_cpp_python-*.whl
```

Windows PowerShell:

```powershell
Get-ChildItem dist/llama_cpp_python-*.whl
Get-FileHash dist/llama_cpp_python-*.whl -Algorithm SHA256
```

## Recomendacion de modelos para CPU

Para este perfil (solo CPU), usar modelos pequenos cuantizados:

- Tamano sugerido: `1B` a `3B`
- Cuantizacion sugerida: `Q4_K_M` o `Q5_K_M`
- Ejemplos: `SmolLM2`, `Qwen2.5 1.5B/3B`, `TinyLlama`

Esto ayuda a mantener latencia y uso de RAM en rangos razonables sin GPU.

