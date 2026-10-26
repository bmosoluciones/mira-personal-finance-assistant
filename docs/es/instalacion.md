# Instalación y arranque

## Dependencias base

MIRA funciona con:

- `openpyxl>=3.1.5`
- `PySide6>=6.10.2`
- `qt-material>=2.14`

## Descargas oficiales

Las distribuciones publicadas de MIRA están disponibles en GitHub Releases:

- https://github.com/bmosoluciones/mira-personal-finance-assistant/releases/latest

MIRA no se publicará en PyPI, así que no se recomienda instalarla con `pip` como flujo de usuario final.

Artefactos del release:

- `.whl`: paquete Python para instalación y empaquetado.
- `.tar.gz`: distribución de código fuente que incluye el código y la licencia.

## Arranque

- Desde una copia del código fuente, instala la aplicación de escritorio con `pip install '.[gui]'`.
- La CLI y el servidor MCP no necesitan la opción GUI.

## Parámetros útiles

- `--db PATH`: ruta personalizada de la base SQLite.
- `--debug`: activa logging detallado.

## Notas importantes

- Las transacciones en lenguaje natural siempre usan el parser determinista.
- Si vas a trabajar desde el repositorio como desarrollador, usa el flujo de desarrollo descrito en el `README`.
