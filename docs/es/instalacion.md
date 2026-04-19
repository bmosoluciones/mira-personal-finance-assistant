# Instalación y arranque

## Dependencias base

MIRA funciona con:

- `openpyxl>=3.1.5`
- `PySide6>=6.10.2`
- `qt-material>=2.14`

## Descargas oficiales

Las distribuciones publicadas para MIRA están disponibles en:

- https://mira.bmogroup.solutions/releases/

MIRA no se publicará en PyPI, así que no se recomienda instalarla con `pip` como flujo de usuario final.

Artefactos publicados:

- `.exe`: instalador recomendado para Windows.
- `.zip`: distribución portable para Windows.
- `.whl`: paquete publicado para construir la versión Flatpak.
- `.tar.gz`: código fuente publicado para cumplir con la licencia GPL.

## Arranque

- Si instalaste el `.exe`, abre MIRA desde el menú Inicio.
- Si descargaste el `.zip`, extrae el contenido y ejecuta `MIRA.exe`.
- Si usas Flatpak, ejecuta `flatpak run solutions.bmogroup.MIRA`.

## Parámetros útiles

- `--db PATH`: ruta personalizada de la base SQLite.
- `--model PATH`: modelo GGUF opcional para modo chat.
- `--debug`: activa logging detallado.

## Notas importantes

- El modo asistente siempre usa el parser determinista.
- El modelo local no se usa para registrar transacciones.
- La descarga y selección de modelos se hace desde `Ajustes`.
- Si vas a trabajar desde el repositorio como desarrollador, usa el flujo de desarrollo descrito en el `README`.
