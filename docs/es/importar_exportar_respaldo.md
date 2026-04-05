# Importación, Exportación y Respaldo

## Importar CSV

Ruta en menú:

- File -> Import CSV...

Reglas de importación:

- Cada fila válida se inserta como transacción.
- Filas inválidas se omiten y se contabilizan como error.
- Si una cuenta no existe, se crea automáticamente.

Campos CSV esperados:

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

## Exportar CSV

Ruta en menú:

- File -> Export CSV...

Contenido exportado:

- Incluye transacciones con columnas estándar del sistema.
- Puede usarse para análisis externo o control histórico.

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
2. Export CSV mensual para auditoría.
3. Backup adicional antes de actualizar versión de MIRA.
