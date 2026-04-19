# Tarjetas de Credito

## Que soporta MIRA

MIRA maneja una tarjeta de credito como una cuenta de tipo `credit`.

Esto significa:

- Cada compra con tarjeta se registra como un gasto normal en esa cuenta.
- Cada pago de tarjeta se registra como un traslado interno desde una cuenta `bank` o `cash` hacia la cuenta `credit`.
- Los pagos de tarjeta no deben inflar los KPI de ingresos ni de gastos.
- Reembolsos, cashback aplicados como credito y ajustes a favor del usuario pueden registrarse como ingresos en la cuenta `credit`.

## Como registrar movimientos

### Compras con tarjeta

Registra la compra como gasto y selecciona la cuenta de tipo `credit`.

Resultado esperado:

- El saldo de la tarjeta se vuelve mas negativo si aumenta la deuda.
- El gasto si aparece en reportes operativos y KPI de gasto.

### Pago de tarjeta

Usa la opcion `Credit Card Payment` en Transacciones.

Reglas:

- Origen: solo cuentas `bank` o `cash`.
- Destino: solo cuentas `credit`.
- El movimiento se guarda como transferencia interna.

Resultado esperado:

- Baja el saldo de la cuenta origen.
- La deuda de la tarjeta se acerca a cero.
- No se altera el KPI de gasto ni de ingreso.

### Reembolso, cashback o ajuste a favor

Si el banco aplica un credito monetario a la tarjeta, registralo como ingreso en la cuenta `credit`.

Resultado esperado:

- La deuda disminuye o la cuenta queda con saldo positivo si el credito supera lo adeudado.
- El ingreso si cuenta en KPI de ingresos.

## Reporte recomendado

Usa el reporte `Account and Credit Card Balance` para revisar:

- nombre de cuenta
- tipo
- moneda
- balance actual
- total consolidado

Este reporte sirve para validar rapidamente si la suma de bancos, efectivo y tarjetas coincide con tu posicion financiera actual.

## Conciliacion con el saldo del banco

MIRA no hace conciliacion automatica de tarjetas de credito. La conciliacion es manual y debe hacerse comparando tus registros con el estado de cuenta o con el saldo publicado por el banco.

Si cargas el estado de cuenta desde Excel, MIRA acepta archivos `.xlsx` con encabezados en ingles o espanol, incluso mezclados, por ejemplo `Date`, `Referencia`, `Description`, `Income` y `Gastos`.

### Regla base de conciliacion

Si el banco muestra una deuda de corte de `12,350.00`, en MIRA la cuenta `credit` deberia mostrar aproximadamente `-12,350.00` para esa misma fecha, salvo que exista un credito a favor del usuario.

Si el banco muestra un saldo a favor, en MIRA la cuenta puede quedar positiva.

### Paso a paso recomendado

1. Identifica la fecha de corte o la fecha exacta del saldo que vas a conciliar.
2. Revisa la cuenta `credit` correcta dentro de MIRA.
3. Compara el saldo de la tarjeta en MIRA contra el saldo del banco para la misma fecha.
4. Si no coincide, revisa primero movimientos pendientes o registrados despues del corte.
5. Luego busca cargos faltantes, cargos duplicados, pagos mal fechados, intereses, comisiones y reembolsos no capturados.
6. Corrige los faltantes y vuelve a comparar hasta que la diferencia sea cero o explicable.

### Orden practico para conciliar

Usa este orden porque reduce errores:

1. Compras del periodo.
2. Pagos aplicados antes o en la fecha de corte.
3. Cargos automaticos.
4. Intereses.
5. Comisiones y cargos similares.
6. Reembolsos, cashback y notas de credito.

### Diferencias tipicas entre banco y sistema

Las diferencias mas comunes son:

- Una compra si fue registrada en MIRA pero el banco aun no la postea.
- El banco ya cargo una compra o ajuste que aun no fue registrado.
- El pago se registro con fecha distinta a la fecha real de aplicacion.
- El pago se registro en la cuenta equivocada.
- Un mismo cargo fue capturado dos veces.
- Falta registrar un reembolso o una nota de credito.
- Faltan intereses o comisiones del cierre.

## Como identificar cargos automaticos

Los cargos automaticos suelen ser el primer origen de diferencias pequenas pero recurrentes.

Busca estos patrones:

- mismo comercio cada mes
- monto identico o muy parecido
- fecha cercana en cada ciclo
- descripciones como streaming, suscripcion, membresia, seguro, telefono, internet, nube, app store, gimnasio o plataforma

Ejemplos comunes:

- streaming y plataformas
- membresias
- seguros
- telefonia e internet
- herramientas de trabajo o servicios cloud

Como registrarlos:

- Siempre como gasto en la cuenta `credit`.
- Idealmente con una descripcion clara del comercio.
- Si son recurrentes, usa categoria consistente y, si te ayuda, una etiqueta como `automatico`.

Si un cargo automatico aparece todos los meses y siempre debe registrarse, puedes apoyarte en recurrentes. Si el banco lo mueve de fecha con frecuencia, conviene registrarlo cuando realmente aparezca en el estado de cuenta.

## Intereses

Los intereses no son pagos de tarjeta. Son un costo financiero y deben registrarse como gasto en la cuenta `credit`.

Buenas practicas:

- Usa una categoria dedicada como `intereses`, `finance_charges` o similar.
- Registra el monto exacto que el banco cargo.
- Usa la fecha de aplicacion del estado de cuenta o del movimiento bancario.

No lo registres como transferencia ni como pago.

## Comisiones y cargos similares

Las comisiones tambien deben registrarse como gasto en la cuenta `credit`.

Incluye en este grupo:

- membresia anual
- cargo por mora
- cargo por retiro de efectivo
- comision por conversion o compra internacional
- cargo administrativo
- seguro agregado por el banco
- SMS, alertas o servicios anexos si el banco los cobra en la tarjeta

Recomendacion:

- Usa una categoria separada como `comisiones_tarjeta` o `bank_fees`.
- Si quieres distinguirlas mas, usa subcategoria o nota.

## Rutina de cierre mensual sugerida

1. Espera a tener el estado de cuenta o el saldo de corte.
2. Abre la tarjeta correcta en MIRA.
3. Revisa compras grandes primero.
4. Revisa cargos automaticos.
5. Registra intereses.
6. Registra comisiones.
7. Verifica reembolsos o cashback.
8. Ejecuta el pago de tarjeta si ya fue realizado.
9. Confirma que el saldo de la cuenta `credit` coincida con el saldo del banco.

## Senales de alerta

Conviene revisar inmediatamente si ves alguna de estas situaciones:

- saldo del banco y saldo de MIRA divergen todos los meses
- la diferencia es siempre el mismo monto
- el pago de tarjeta reduce KPI de gasto o ingreso
- la tarjeta aparece con saldo positivo sin que exista credito a favor
- hay cargos del banco que no logras ubicar en el audit trail

Cuando eso ocurra, revisa primero cargos automaticos, intereses, comisiones, reembolsos y fechas de pago.
