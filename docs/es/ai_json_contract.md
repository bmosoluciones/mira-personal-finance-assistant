# Contrato JSON IA ↔ Backend ↔ Frontend

Este documento define el **formato JSON oficial** aceptado por el sistema para interpretar instrucciones en lenguaje natural y convertirlas en acciones financieras.

> Este esquema es el **contrato de integración** entre backend y frontend. Cualquier cambio debe actualizar este documento y versionarse.

## 1) Esquema JSON aceptado

```json
{
  "action": "add_income | add_expense | report | data_analysis | none",
  "amount": 1000.0,
  "description": "Salary",
  "category": "salary",
  "account": "General",
  "base_currency": "USD",
  "exchange_rate": 1.0,
  "converted_amount": 1000.0,
  "report_type": "expenses | incomes | balance | cashflow | summary | null",
  "period": {
    "preset": "this_month | last_month | last_3_months | this_year | custom",
    "from": "2025-01-01",
    "to": "2025-03-31"
  },
  "filters": {
    "categories": ["restaurant"],
    "accounts": ["General"],
    "min_amount": null,
    "max_amount": null,
    "text": null
  },
  "message": "Income recorded: 1000.00 USD (base USD) in General"
}
```

## 2) Definición de campos

- `action` *(string, requerido)*
  - Acción que debe ejecutar el sistema.
  - Valores permitidos:
    - `add_income`: Registrar un ingreso
    - `add_expense`: Registrar un gasto
    - `report`: Solicitar reporte
    - `data_analysis`: Solicitar análisis de datos del usuario (hallazgos principales/secundarios)
    - `none`: No hay acción ejecutable

- `amount` *(number, opcional según acción)*
  - Monto original detectado en el prompt.
  - Para `add_income` y `add_expense` es requerido.
  - Desde `0.0.1a2`, el backend normaliza los montos monetarios como valores exactos de dos decimales antes de persistirlos.

- `description` *(string, opcional)*
  - Descripción libre de la operación (ej. `Salary`, `Coffee`).

- `category` *(string, opcional)*
  - Categoría semántica (ej. `salary`, `food`, `transport`).

Regla especial para ahorro:

- Si la IA o el parser determinístico interpretan una frase de ahorro, la acción sigue siendo `add_expense`.
- En ese caso la `category` puede resolverse a una categoría técnica de ahorro como `savings` o su equivalente canónico interno.
- Las categorías marcadas internamente como ahorro sí actualizan metas, pero no se computan como gasto real en reportes, análisis ni presupuestos.

- `account` *(string, opcional)*
  - Cuenta destino/origen (ej. `General`, `Savings`, `Cash`).

- `base_currency` *(string, requerido para flujos monetarios)*
  - Moneda base del sistema sobre la que se consolida el libro.
  - Formato recomendado: código ISO 4217 (ej. `USD`, `EUR`, `MXN`).

- `exchange_rate` *(number, requerido para flujos monetarios)*
  - Tipo de cambio aplicado para convertir `amount` a `base_currency`.
  - Regla: `converted_amount = amount * exchange_rate`.
  - Una acción soporta solo un tramo de conversión hacia `base_currency`. Si el flujo real cruza más de dos monedas, el cliente debe enviar la tasa efectiva final hacia `base_currency` o dividir el flujo en múltiples operaciones.

- `converted_amount` *(number, requerido para flujos monetarios)*
  - Monto convertido a la moneda base.
  - Debe ser consistente con `amount` y `exchange_rate`.
  - Debe coincidir con la fórmula luego de aplicar la regla canónica de redondeo.

### Campos específicos para `report` y `data_analysis`

Estos campos responden explícitamente a:
1) ¿Qué vista/acción analítica? 2) ¿Qué período? 3) ¿Algún filtro?

- `report_type` *(string, requerido cuando `action=report`)*
  - Tipo de reporte solicitado.
  - Valores permitidos: `expenses`, `incomes`, `balance`, `cashflow`, `summary`.

- `period` *(object, requerido cuando `action=report` o `action=data_analysis`)*
  - Define el período de consulta.
  - Estructura:
    - `preset` *(string, requerido)*: `this_month`, `last_month`, `last_3_months`, `this_year`, `custom`.
    - `from` *(string, opcional)*: fecha ISO `YYYY-MM-DD` (requerido si `preset=custom`).
    - `to` *(string, opcional)*: fecha ISO `YYYY-MM-DD` (requerido si `preset=custom`).

- `filters` *(object, opcional cuando `action=report` o `action=data_analysis`)*
  - Filtros de segmentación del reporte.
  - Estructura:
    - `categories` *(array<string>, opcional)*: categorías incluidas.
    - `accounts` *(array<string>, opcional)*: cuentas incluidas.
    - `min_amount` *(number|null, opcional)*: umbral mínimo.
    - `max_amount` *(number|null, opcional)*: umbral máximo.
    - `text` *(string|null, opcional)*: búsqueda textual libre.

- `message` *(string, opcional pero recomendado)*
  - Mensaje amigable para UI/logs con resultado o intención.

## 3) Reglas de validación del contrato

1. Si `action` es `add_income` o `add_expense`:
   - Deben venir `amount`, `base_currency`, `exchange_rate`, `converted_amount`.
   - `report_type`, `period`, `filters` deben venir como `null` o no incluirse.
2. Si `action` es `report`:
   - `report_type` y `period` son obligatorios.
   - `filters` es opcional (puede ser `{}` o `null`).
   - `amount`, `exchange_rate`, `converted_amount` deben venir como `null` o no incluirse.
3. Si `action` es `data_analysis`:
   - `period` es obligatorio.
   - `filters` es opcional (puede ser `{}` o `null`).
   - `report_type` debe ser `null`.
   - `amount`, `exchange_rate`, `converted_amount` deben venir como `null` o no incluirse.
4. Si `action` es `none`:
   - Campos monetarios y de reporte pueden omitirse y `message` debe explicar por qué no se ejecuta acción.
5. `exchange_rate` debe ser mayor a 0 en operaciones monetarias.
6. `converted_amount` debe respetar la fórmula de conversión.
7. Los valores monetarios (`amount`, `converted_amount`, `filters.min_amount`, `filters.max_amount`) se normalizan a dos decimales usando `ROUND_HALF_UP`.
8. Si `period.preset = custom`, entonces `period.from` y `period.to` son obligatorios.
9. Si `action = add_expense` y la categoría queda marcada internamente como ahorro, el backend debe tratar la operación como un egreso técnico para metas y excluirla de gasto real reportable.

## 4) Semántica monetaria

- El JSON sigue transportando dinero como números JSON.
- En la validación, el backend convierte esos campos monetarios a semántica decimal exacta con dos decimales.
- La persistencia SQLite guarda el resultado como centavos enteros.
- La UI, los charts y algunos adaptadores de export pueden renderizar strings decimales o `float` de presentación, pero la aritmética y la persistencia ya no dependen de `float` binario.
- Regla canónica de redondeo: `ROUND_HALF_UP` a dos decimales.

## 5) Ejemplos válidos

### Ejemplo A: Ingreso en moneda base

**Prompt IA:**

> "Registra un ingreso de 1000 USD en la cuenta General por salario"

**JSON esperado:**

```json
{
  "action": "add_income",
  "amount": 1000.0,
  "description": "Salary",
  "category": "salary",
  "account": "General",
  "base_currency": "USD",
  "exchange_rate": 1.0,
  "converted_amount": 1000.0,
  "report_type": null,
  "period": null,
  "filters": null,
  "message": "Income recorded: 1000.00 USD (base USD) in General"
}
```

### Ejemplo B: Gasto en moneda distinta a la base

**Prompt IA:**

> "Anota un gasto de 500 MXN en comida desde General. Moneda base USD con tipo de cambio 0.058"

**JSON esperado:**

```json
{
  "action": "add_expense",
  "amount": 500.0,
  "description": "Food expense",
  "category": "food",
  "account": "General",
  "base_currency": "USD",
  "exchange_rate": 0.058,
  "converted_amount": 29.0,
  "report_type": null,
  "period": null,
  "filters": null,
  "message": "Expense recorded: 500.00 (converted to 29.00 USD) in General"
}
```

### Ejemplo C: Reporte con tipo, período y filtro

**Prompt IA:**

> "Quiero ver el reporte de gastos en restaurantes de los últimos 3 meses"

**JSON esperado:**

```json
{
  "action": "report",
  "amount": null,
  "description": "Expense report",
  "category": null,
  "account": null,
  "base_currency": "USD",
  "exchange_rate": null,
  "converted_amount": null,
  "report_type": "expenses",
  "period": {
    "preset": "last_3_months",
    "from": null,
    "to": null
  },
  "filters": {
    "categories": ["restaurant"],
    "accounts": null,
    "min_amount": null,
    "max_amount": null,
    "text": null
  },
  "message": "Requested expenses report for restaurants in last 3 months"
}
```

### Ejemplo D: Reporte personalizado con rango de fechas

**Prompt IA:**

> "Dame un balance del 2025-01-01 al 2025-01-31 para la cuenta General"

**JSON esperado:**

```json
{
  "action": "report",
  "amount": null,
  "description": "Balance report",
  "category": null,
  "account": null,
  "base_currency": "USD",
  "exchange_rate": null,
  "converted_amount": null,
  "report_type": "balance",
  "period": {
    "preset": "custom",
    "from": "2025-01-01",
    "to": "2025-01-31"
  },
  "filters": {
    "categories": null,
    "accounts": ["General"],
    "min_amount": null,
    "max_amount": null,
    "text": null
  },
  "message": "Requested balance report for General from 2025-01-01 to 2025-01-31"
}
```


### Ejemplo E: Análisis de datos por categoría y período

**Prompt IA:**

> "Analiza mis datos de gastos de educación de los últimos 3 meses"

**JSON esperado:**

```json
{
  "action": "data_analysis",
  "amount": null,
  "description": null,
  "category": "education",
  "account": null,
  "base_currency": "USD",
  "exchange_rate": null,
  "converted_amount": null,
  "report_type": null,
  "period": {
    "preset": "last_3_months",
    "from": null,
    "to": null
  },
  "filters": {
    "categories": ["education"],
    "accounts": null,
    "min_amount": null,
    "max_amount": null,
    "text": null
  },
  "message": null
}
```

### Ejemplo F: Sin acción ejecutable

**Prompt IA:**

> "Hola, ¿cómo estás?"

**JSON esperado:**

```json
{
  "action": "none",
  "amount": null,
  "description": null,
  "category": null,
  "account": null,
  "base_currency": "USD",
  "exchange_rate": null,
  "converted_amount": null,
  "report_type": null,
  "period": null,
  "filters": null,
  "message": "No actionable finance intent found"
}
```

## 6) Plantilla recomendada para entrenar/promptear la IA

Usar esta instrucción de sistema para forzar una salida consistente:

```text
Eres un parser financiero. Debes convertir el prompt del usuario a JSON válido.
Responde únicamente JSON con las claves:
action, amount, description, category, account, base_currency, exchange_rate, converted_amount, report_type, period, filters, message.

Reglas:
- action ∈ {add_income, add_expense, report, data_analysis, none}
- Para add_income/add_expense:
  - amount, base_currency, exchange_rate y converted_amount son obligatorios
  - converted_amount = amount * exchange_rate redondeado a 2 decimales con ROUND_HALF_UP
  - report_type, period y filters deben ser null
- Para report:
  - report_type obligatorio ∈ {expenses, incomes, balance, cashflow, summary}
  - period obligatorio con preset ∈ {this_month,last_month,last_3_months,this_year,custom}
  - si period.preset=custom, from y to son obligatorios
  - filters opcional
- Para data_analysis:
  - period obligatorio con preset ∈ {this_month,last_month,last_3_months,this_year,custom}
  - si period.preset=custom, from y to son obligatorios
  - filters opcional
  - report_type debe ser null
- Para none:
  - campos monetarios y de reporte pueden ir en null
- No agregues texto fuera del JSON
```

## 7) Compatibilidad

- Este documento reemplaza el formato previo que no incluía campos de multimoneda, estructura explícita para reportes ni la acción `data_analysis`.
- Backend y frontend deben validar presencia y consistencia de:
  - `base_currency`
  - `exchange_rate`
  - `converted_amount`
  - `report_type`
  - `period`
- Desde `0.0.1a2`, las integraciones también deben respetar el contrato monetario exacto:
  - los campos monetarios se normalizan a dos decimales exactos
  - `converted_amount` se valida contra la fórmula de conversión ya redondeada
  - una sola acción no representa conversiones multi-tramo
  - `filters`
