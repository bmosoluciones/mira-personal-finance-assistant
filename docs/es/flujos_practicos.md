# Flujos Prácticos

## Flujo 1: Registrar gasto diario

1. Ir a Transactions.
2. Crear transacción tipo gasto.
3. Elegir cuenta y categoría.
4. Guardar.
5. Confirmar impacto en Dashboard.

## Flujo 2: Registrar ingreso mensual

1. Crear transacción tipo ingreso.
2. Asignar categoría de ingreso (por ejemplo salario).
3. Validar cuenta destino.
4. Guardar y revisar balance actualizado.

## Flujo 3: Transferir entre cuentas

1. Ir a Accounts.
2. Usar acción de transferencia.
3. Definir origen, destino y monto.
4. Si hay monedas distintas, definir tasa de cambio.

Resultado esperado:

- Se registra salida en cuenta origen y entrada en cuenta destino.

## Flujo 4: Crear presupuesto anual y cargar propuesta inicial

1. Ir a Presupuestos.
2. Crear un nuevo presupuesto indicando código, año y moneda.
3. Usar Proponer presupuesto para cargar una base inicial desde el último año con datos suficientes.
4. Revisar y ajustar los 12 meses por categoría.
5. Confirmar totales anuales de ingresos, gastos y balance.

Resultado esperado:

- Queda un presupuesto anual editable para ingresos y gastos.
- Si gastos superan ingresos, MIRA advierte pero no bloquea el presupuesto.
- Las categorías de ahorro internas no aparecen como líneas presupuestables.

## Flujo 5: Recurrentes de inicio de mes

1. Configurar reglas recurrentes (ingresos fijos y gastos fijos).
2. Al iniciar mes, ejecutar Apply recurring.
3. Confirmar que no se dupliquen al reintentar dentro del mismo período.

## Flujo 6: Revisión quincenal

1. Abrir Reports y revisar totales.
2. Abrir Presupuestos y usar Comparar con real.
3. Revisar variaciones por categoría en vista trimestral o mensual.
4. Ajustar presupuesto o categorías según hallazgos.
5. Exportar CSV para respaldo analítico externo.

## Flujo 7: Cierre mensual

1. Ejecutar reportes principales.
2. Comparar real vs presupuesto para el período.
3. Verificar progreso de metas.
4. Generar backup de base de datos.
5. Guardar CSV de transacciones del mes.

Nota operativa:

- Si registraste ahorro desde lenguaje natural, esos movimientos sí empujan las metas.
- No deben leerse como gasto real de consumo en reportes ni como desviación presupuestaria.

## Flujo 8: Registrar ahorro sin distorsionar gastos

1. Usar una frase como "ahorré 200 córdobas" o "set aside 50 dollars for emergencies".
2. Confirmar que la transacción quede registrada como egreso técnico de ahorro.
3. Abrir Goals y verificar que la meta vinculada aumentó su progreso.
4. Abrir Reports o Presupuestos y confirmar que ese movimiento no aparece como gasto real ni como línea presupuestaria.

Resultado esperado:

- La salida a ahorro queda trazable en transacciones.
- La meta se actualiza correctamente.
- El gasto operativo y el presupuesto no quedan inflados por ahorro interno.

## Flujo 9: Conciliar una tarjeta de credito

1. Registrar compras en la cuenta de tipo `credit`.
2. Registrar el pago usando `Credit Card Payment`, no como gasto normal.
3. Abrir el reporte de balance de cuentas y tarjetas.
4. Comparar el saldo de MIRA con el saldo del banco para la misma fecha.
5. Revisar cargos automaticos, intereses, comisiones y reembolsos faltantes.

Resultado esperado:

- La deuda de la tarjeta coincide con el estado de cuenta.
- Los pagos no inflan el KPI de gasto.
- Los cargos financieros quedan trazables en la misma tarjeta.

Referencia:

- Consulta `Tarjetas de Credito` para una guia detallada de conciliacion.
