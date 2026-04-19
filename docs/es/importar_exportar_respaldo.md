# Importación, Exportación y Respaldo

## Importar transacciones

Ruta en menú:

- Archivo -> Importar transacciones...

Reglas de importación:

- Cada fila válida se inserta como transacción.
- Filas inválidas se omiten y se contabilizan como error.
- Si una cuenta no existe, se crea automáticamente.
- El selector de archivos acepta `.csv` y `.xlsx`.
- `.xls` y cualquier otra extensión se rechazan de forma explícita.
- Los encabezados pueden venir en inglés o en español, incluso mezclados.

Campos esperados para transacciones:

- `date`
- `type` (income o expense)
- `amount`
- `account_name`
- `category`
- `subcategory`
- `payment_method`
- `description`
- `note`
- `receipt_path`

Aliases de encabezados aceptados:

- `date` / `fecha`
- `type` / `tipo`
- `amount` / `monto`
- `account_name` / `account` / `cuenta` / `nombre_cuenta`
- `category` / `categoria`
- `subcategory` / `subcategoria`
- `payment_method` / `metodo_pago` / `medio_pago`
- `description` / `descripcion`
- `note` / `nota`
- `receipt_path` / `ruta_recibo` / `ruta_comprobante` / `comprobante`
- `tags` / `etiquetas`

Notas:

- `type` y `amount` son las únicas columnas obligatorias.
- Si falta `account_name`, MIRA usa `General`.
- La importación de Excel trabaja solo con archivos `.xlsx`.

## Exportar transacciones

Ruta en menú:

- Archivo -> Exportar transacciones...

Contenido exportado:

- Incluye transacciones con columnas estándar del sistema.
- Puede usarse para análisis externo o control histórico.
- El cuadro de guardado acepta `.csv` y `.xlsx`.
- Si no se indica extensión, MIRA guarda `.csv` por defecto.
- Si se elige el filtro de Excel y no se indica extensión, MIRA guarda `.xlsx`.
- Las exportaciones Excel se escriben en una hoja llamada `Transactions`.

## Backup de base de datos

Ruta en menú:

- File -> Backup Database...

Comportamiento:

- Crea una copia completa SQLite.
- No permite sobrescribir el mismo archivo activo de DB.

Buenas prácticas:

1. Mantener backup semanal.
2. Conservar al menos las últimas 4 versiones.
3. Guardar copia fuera del equipo principal cuando sea posible.

## Restaurar base de datos

Ruta en menú:

- File -> Restore Database...

Comportamiento:

- Valida que el archivo seleccionado sea un backup MIRA compatible antes de reemplazar la base activa.
- Restaura mediante una base de staging y reconecta el runtime al finalizar.
- Informa cuando durante la restauración se aplicó una actualización soportada del schema.
- Recomendado cerrar flujos de trabajo pendientes antes de restaurar.

## Estrategia recomendada de continuidad

1. Backup antes de importaciones grandes.
2. Exportar CSV o XLSX mensual para auditoría.
3. Backup adicional antes de actualizar versión de MIRA.
