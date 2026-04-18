# Instalación manual en Linux desde el código fuente

Esta guía explica cómo instalar manualmente **MIRA** en Linux utilizando un entorno virtual de Python bajo `$HOME`, y luego integrar la aplicación con el menú del escritorio.

## Resultado esperado

Al final de esta guía tendrás:

- MIRA instalado en `~/.mira` (entorno virtual de Python).
- El icono de MIRA instalado como `~/.local/share/icons/hicolor/256x256/apps/solutions.bmogroup.mira.png`.
- Una entrada de escritorio en `~/.local/share/applications/solutions.bmogroup.mira.desktop`.

## Requisitos previos

- Sistema Linux con un entorno de escritorio.
- Python disponible como `python3` (python3.12+) con soporte para `pip` y `venv`.

## Tutorial

### Crear el entorno virtual

Desde tu directorio personal:

```bash
python3 -m venv ~/.mira
```

Actualiza las herramientas de empaquetado:

```bash
~/.mira/bin/pip install --upgrade pip setuptools wheel
```

### Instalar MIRA desde el repositorio

```bash
~/.mira/bin/pip install https://github.com/bmosoluciones/mira-personal-finance-assistant/archive/refs/heads/main.zip
```

Validación:

```bash
~/.mira/bin/mira-cli --check
```

### Reutilizar el icono existente de `packaging/snap`

Copia el icono del repositorio (`packaging/snap/256x256.png`) a la ubicación estándar de iconos locales con el nombre de aplicación requerido:

```bash
wget -O ~/.local/share/icons/hicolor/256x256/apps/solutions.bmogroup.mira.png https://github.com/bmosoluciones/mira-personal-finance-assistant/blob/main/packaging/snap/256x256.png?raw=true
```

Actualización opcional del caché:

```bash
gtk-update-icon-cache ~/.local/share/icons/hicolor || true
```

### Reutilizar el archivo `.desktop` existente y actualizar `Exec`

Comienza desde el archivo de escritorio del repositorio y parchea solo la ruta del ejecutable:

```bash
wget -O ~/.local/share/applications/solutions.bmogroup.mira.desktop https://raw.githubusercontent.com/bmosoluciones/mira-personal-finance-assistant/refs/heads/main/packaging/snap/solutions.bmogroup.mira.desktop
```

Reemplaza `Exec=mira` con la ruta del lanzador específica del usuario:

Los campos clave deberían verse así:

```ini
[Desktop Entry]
Type=Application
Name=MIRA
Comment=Asistente de Finanzas Personales
Exec=/home/<usuario>/.mira/bin/mira
Icon=solutions.bmogroup.mira
Categories=Office;Finance;
StartupNotify=true
Terminal=false
```

Reemplaza <usuario> con tu usuario de unix.

### Verificar la integración con el escritorio

Comprueba la validez del archivo de escritorio:

```bash
desktop-file-validate ~/.local/share/applications/solutions.bmogroup.mira.desktop
```

Ejecuta MIRA desde la terminal:

```bash
~/.mira/bin/mira
```

Luego busca **MIRA** en tu lanzador de escritorio o menú de aplicaciones.
