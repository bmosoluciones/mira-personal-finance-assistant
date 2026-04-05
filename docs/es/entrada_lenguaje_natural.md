# Lenguaje Natural

MIRA permite capturar acciones desde texto libre en el panel inferior.

## Cómo funciona

Pipeline general:

1. Normalización del texto.
2. Interpretación por motor (determinístico o LLM local).
3. Validación de esquema.
4. Ejecución de acción.

Si falla la interpretación, MIRA no detiene la app y muestra un mensaje de ayuda con ejemplos.

## Acciones soportadas

- `add_income`
- `add_expense`
- `report`
- `data_analysis`
- `none`

## Ejemplos recomendados

Ingresos:

- "recibi 1200 de salario"
- "ingreso de 300 por ventas"

Gastos:

- "gaste 25 en transporte"
- "pague 80 de servicios"

Ahorro técnico para metas:

- "ahorré 100 córdobas del vuelto"
- "transferí a ahorro 300 dólares de mi salario"
- "saved 50 dollars from my paycheck"

Nota importante:

- Estas frases se registran como un egreso técnico en una categoría de ahorro interna para poder actualizar metas de ahorro.
- Ese egreso no se considera gasto real de consumo en reportes, análisis ni presupuestos.
- Las categorías marcadas como ahorro no aparecen como categorías presupuestables.

Reportes:

- "reporte"
- "reporte de gastos"
- "analiza mis datos del ultimo mes"

## Botones rápidos

Cuando el sistema responde con acción `none`, se muestran accesos rápidos para:

- Add Income
- Add Expense
- View Report

Estos botones precargan una plantilla en la caja de texto.

## Historial de comandos

En la caja de entrada puedes usar:

- Flecha arriba: comando anterior.
- Flecha abajo: siguiente comando o borrador actual.

## Modo Assistant vs Chat

- Assistant: interpreta y ejecuta acciones financieras.
- Chat: conversación libre con modelo local.

Nota:

- Chat sólo está disponible cuando hay LLM local listo.
- Si no hay modelo activo, MIRA usa el parser determinístico del asistente.
