# Uso del archivo portable `.zip` de MIRA en Windows (sin instalador)

Esta guía es para usuarios avanzados de Windows que **no pueden instalar programas** con un instalador `.exe` y necesitan ejecutar MIRA desde el paquete portable `.zip`.

## Resultado esperado

Al final de esta guía tendrás:

- Los archivos portables de MIRA extraídos en un directorio estable que no sea probable que se borre por accidente.
- Un acceso directo en el escritorio para abrir MIRA rápidamente.
- (Opcional) Una entrada en el Menú Inicio para un inicio más fácil.

## 1) Descargar el `.zip` portable

1. Abre: `https://mira.bmogroup.solutions/releases/`
2. Descarga el archivo portable más reciente para Windows (el artefacto `.zip`).
3. **No** ejecutes el archivo directamente desde Descargas.

## 2) Elegir una carpeta de extracción segura

Evita directorios temporales o de limpieza automática como:

- `Descargas` (Downloads)
- `Escritorio` (si tu organización limpia perfiles automáticamente)
- `%TEMP%`

Ubicación estable recomendada:

- `%LOCALAPPDATA%\Programs\MIRA\`

Crea la carpeta si es necesario y extrae el contenido del `.zip` allí.

Ejemplo de ruta final del ejecutable:

- `%LOCALAPPDATA%\Programs\MIRA\MIRA.exe`

## 3) Ejecutar una vez para validar

Haz doble clic en `MIRA.exe` desde el directorio extraído.

Si aparece Windows SmartScreen:

1. Haz clic en **Más información**.
2. Haz clic en **Ejecutar de todas formas**.

## 4) Crear un acceso directo en el escritorio

1. Abre la carpeta de extracción.
2. Haz clic derecho en `MIRA.exe` -> **Enviar a** -> **Escritorio (crear acceso directo)**.
3. Cambia el nombre del acceso directo a `MIRA` si lo deseas.

Esto proporciona a los usuarios sin permisos de administrador un lanzador conveniente sin instalar software a nivel de sistema.

## 5) Opcional: añadir una entrada al Menú Inicio

Puedes añadir un acceso directo al Menú Inicio por usuario (no requiere permisos de administrador):

1. Presiona `Win + R`, escribe:

   ```text
   shell:programs
   ```

2. En la carpeta abierta, crea un acceso directo que apunte a:

   ```text
   %LOCALAPPDATA%\Programs\MIRA\MIRA.exe
   ```

3. Nómbralo `MIRA`.

MIRA debería aparecer ahora en la búsqueda del Menú Inicio del usuario.

## 6) Flujo de trabajo para actualización de versiones

Dado que esta es una instalación portable:

1. Descarga el nuevo lanzamiento `.zip`.
2. Cierra MIRA.
3. Reemplaza los archivos en `%LOCALAPPDATA%\Programs\MIRA\`.
4. Vuelve a abrir desde el acceso directo existente (los accesos directos del escritorio y del Menú Inicio seguirán funcionando si la ruta de `MIRA.exe` sigue siendo la misma).

## Solución de problemas

- **El acceso directo no abre MIRA:** verifica que el `Destino` apunte a la ruta actual de `MIRA.exe`.
- **La aplicación desaparece después de una limpieza:** mueve la instalación desde carpetas volátiles (Descargas/Escritorio/temp) a `%LOCALAPPDATA%\Programs\MIRA\`.
- **Bloqueado por política:** algunas organizaciones bloquean binarios sin firmar; solicita a TI que incluyan a MIRA en la lista de permitidos.
