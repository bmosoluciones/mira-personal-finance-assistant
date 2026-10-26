# Solución de Problemas

## La app no inicia

Checklist:

1. Verifica que PySide6 esté instalado.
2. Ejecuta `mira-cli --debug` para ver trazas.
3. Si usas entorno virtual, confirma que esté activado.

## No reconoce comandos en lenguaje natural

Causas comunes:

- Frase demasiado ambigua.
- Falta monto numérico en gasto/ingreso.

Acciones:

1. Usa frases más directas (ver ejemplos del manual).
2. Revisa que exista categoría/cuenta o deja que MIRA cree según contexto.

## Error al importar CSV

Causas típicas:

- `type` distinto de income/expense.
- `amount` no numérico o menor/igual a cero.
- Formato de columnas incompleto.

Solución:

1. Valida archivo con encabezados correctos.
2. Corrige filas inválidas y reintenta.

## Los reportes no muestran lo esperado

1. Revisa filtros activos.
2. Verifica rango de fechas.
3. Confirma que transacciones estén en la cuenta/categoría correcta.

## Restauré backup y perdí cambios recientes

Comportamiento esperado: restore reemplaza el contenido actual.

Mitigación:

1. Mantén backups versionados.
2. Haz backup antes de restaurar otro archivo.
