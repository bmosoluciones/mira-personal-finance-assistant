# Conciliación de Cuentas

## Resumen

La conciliación de cuentas en MIRA permite comparar tus registros internos contra un estado de cuenta bancario externo (Excel) para asegurar que tu saldo sea exacto y no falten transacciones.

## Acceso a la Conciliación

Puedes abrir la herramienta de conciliación de dos maneras:

1. **Barra lateral de Cuentas**: Ve a la sección de **Cuentas**, haz clic derecho en la cuenta que deseas conciliar y selecciona **✓ Conciliar**.
2. **Menú Principal**: Ve a **Cuentas** -> **Conciliar cuenta**.

## Flujo de Trabajo de Conciliación

### 1. Cargar el Estado de Cuenta Externo

1. Haz clic en **Cargar Excel**.
2. Selecciona tu archivo de estado de cuenta bancario (`.xlsx`).
3. MIRA extraerá las transacciones y las mostrará en la tabla de **Transacciones Externas** (izquierda).

### 2. Revisar Coincidencias Automáticas

MIRA sugiere coincidencias automáticamente cuando encuentra una transacción del sistema y una externa con:
- El mismo monto exacto.
- Una fecha cercana (dentro de unos pocos días).

Las coincidencias sugeridas se resaltan, permitiéndote verificarlas rápidamente.

### 3. Conciliación Manual

Si una transacción no se emparejó automáticamente:
1. Selecciona una o más filas de la tabla de **Transacciones Externas**.
2. Selecciona la(s) transacción(es) correspondiente(s) de la tabla de **Transacciones del Sistema** (derecha).
3. Verifica que la **Diferencia conciliada** sea cero.
4. Haz clic en **Conciliar**.

### 4. Manejo de Diferencias

Si los montos seleccionados no coinciden, MIRA mostrará una advertencia con la diferencia calculada. Aún puedes proceder si la diferencia está explicada (por ejemplo, pequeñas comisiones bancarias aún no registradas).

### 5. Finalización

Una vez que todos los elementos estén conciliados, las **Transacciones del Sistema** se marcarán como "conciliadas" en la vista principal de transacciones, y el saldo de la cuenta debería coincidir con tu estado de cuenta bancario.

## Quitar Conciliación

Si cometiste un error:
1. Selecciona las transacciones del sistema conciliadas.
2. Haz clic en **Quitar conciliación**.

## Tarjetas de Resumen

La parte superior de la ventana de conciliación muestra:
- **Resumen Externo**: Saldo inicial, total de ingresos, total de gastos y saldo final del archivo Excel.
- **Resumen del Sistema**: Totales correspondientes de tus registros en MIRA para el mismo período.
- **Diferencia**: La brecha actual entre tus registros del sistema y el estado de cuenta externo.
