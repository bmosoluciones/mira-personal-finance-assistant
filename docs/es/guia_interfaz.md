# Guía de la Interfaz

La ventana principal de MIRA está compuesta por:

- Barra de menú superior.
- Barra lateral de navegación.
- Área central de vistas.
- Panel inferior de chat/comandos.

## Navegación lateral

Secciones principales:

- Dashboard
- Transactions
- Accounts
- Presupuestos
- Categories
- Recurring
- Reports
- Goals
- Settings

## Menú principal

Acciones frecuentes:

- File: importar CSV, exportar CSV, backup, restore, salir.
- Accounts: agregar cuenta.
- Transactions: agregar transacción.
- Budget: crear presupuesto anual.
- Categories: agregar categorías de ingreso o gasto.
- Recurring: agregar y aplicar recurrentes.
- Reports: abrir reportes y analizar datos.
- Goals: crear meta y aportar.
- View: mostrar/ocultar sidebar y panel de prompt.
- Settings: abrir configuración principal.

## Atajos útiles

- `Ctrl+Q`: salir.
- `Ctrl+B`: mostrar/ocultar barra lateral.
- `Ctrl+P`: mostrar/ocultar panel de prompt.
- `Ctrl+,`: abrir configuración.

## Vista Transactions

Permite:

- Crear, editar, eliminar y duplicar transacciones.
- Filtrar por fecha, categoría, cuenta y texto.
- Ver total del conjunto filtrado.

Indicadores visuales especiales:

- `+ income` en verde para ingresos.
- `- expense` en rojo para gasto operativo.
- `@ savings` en azul neutral para egresos técnicos de ahorro.

Resumen inferior (totales):

- Muestra 4 tarjetas: Ingreso, Gasto, Balance y Ahorro.
- Los movimientos `@ savings` se acumulan en Ahorro y no se suman al total de Gasto.

Campos relevantes:

- Fecha
- Tipo (income/expense)
- Monto
- Cuenta
- Categoría y subcategoría
- Método de pago
- Nota
- Comprobante (ruta de archivo)

## Vista Accounts

Gestiona cuentas financieras:

- Alta, edición y eliminación.
- Balance actual por cuenta.
- Moneda asociada.

También admite transferencias entre cuentas con soporte de conversión si aplica.

## Vista Presupuestos

La vista Presupuestos permite trabajar con presupuestos anuales persistidos en base de datos.

Elementos principales:

- Selector de presupuesto por código.
- Alta de presupuesto con código, año y moneda.
- Tabla anual por categoría con los 12 meses y total anual.
- Tarjetas con total de ingresos, total de gastos y balance presupuestado.
- Advertencia visible cuando los gastos superan los ingresos esperados, sin bloquear el presupuesto.

Acciones disponibles:

- Nuevo presupuesto.
- Eliminar presupuesto.
- Proponer presupuesto.
- Comparar con real.
- Seguimiento mensual presupuestario.

Proponer presupuesto:

- Usa el último año con datos suficientes.
- Calcula un promedio mensual inicial por categoría.
- Si no hay historial suficiente, MIRA informa al usuario y no genera propuesta.

Comparar con real:

- Permite vista anual, semestral, trimestral y mensual.
- La vista trimestral es la predeterminada.
- Muestra Real, PPTO y Variación por período y total anual.
- Diferencia visualmente ingresos y egresos cuando el real está mejor o peor que lo esperado.

Seguimiento mensual presupuestario:

- Permite consultar cualquier mes del año del presupuesto seleccionado (meses pasados, mes actual y meses futuros).
- Presenta KPI globales de Total Asignado, Total Ejecutado y Total Disponible.
- Muestra por categoría de gasto: Asignado, Ejecutado, Disponible y estado visual:
  - Sobregiro (rojo) cuando Ejecutado > Asignado.
  - Ejecutado exacto (neutral) cuando Ejecutado = Asignado.
  - Saldo disponible (verde) cuando Asignado > Ejecutado.
- Permite reasignar fondos entre categorías sin alterar el total mensual:
  - Origen: solo categorías con disponible mayor a cero.
  - Destino: categorías disponibles en el reporte mensual.
  - Asignación: monto positivo no mayor al disponible en origen.
- La reasignación actualiza directamente los montos presupuestados del mes y refresca el reporte.

Regla especial para ahorro:

- Las categorías marcadas internamente como ahorro no se muestran en la grilla del presupuesto.
- Los movimientos registrados hacia ahorro para alimentar metas no cuentan como gasto real en la comparación real vs presupuesto.
- Esto evita distorsionar el consumo operativo aunque el sistema use un egreso técnico para actualizar metas.

Moneda:

- Cada presupuesto tiene su propia moneda.
- Si una transacción real no puede reconciliarse con la moneda del presupuesto, se excluye de la comparación y se informa en pantalla.

## Vista Categories

Organiza categorías:

- Tipo ingreso o gasto.
- Color.
- Jerarquía (categoría padre e hijas).
- Posibilidad de consolidar categorías en flujos de limpieza.

### Jerarquía y emoji/icono en categorías

- MIRA permite organizar categorías en jerarquía de dos niveles: cada categoría puede tener un padre (opcional), pero no nietos ni más profundidad en la interfaz. El backend soporta jerarquía recursiva, pero la UI solo permite padre/hijo.
- Al crear o editar una categoría, puedes elegir un emoji o icono Unicode (campo "Icon"). Este emoji se muestra junto al nombre en las tablas y selectores.
- El selector de padre solo muestra categorías del mismo tipo (ingreso/gasto) y excluye la propia categoría.
- En las tablas de categorías y en los selectores de transacción, se muestra el emoji y la relación padre/hijo.
- Esta restricción de dos niveles facilita la navegación y evita confusión visual, pero permite suficiente flexibilidad para la mayoría de los casos de uso.

## Vista Recurring

Plantillas para movimientos mensuales.

- Día del mes.
- Tipo de transacción.
- Cuenta, monto y categoría.

Acción clave:

- Apply recurring: aplica reglas del mes actual una sola vez por período.

## Vista Reports

Incluye:

- Total income vs expenses.
- Breakdown por categoría.
- Tendencia por cuenta.
- Flujo de caja.
- Análisis de datos del usuario (cuando aplica).

Regla especial para ahorro:

- Los movimientos en categorías marcadas como ahorro no se suman al total de gastos reales.
- Tampoco aparecen en los desgloses analíticos de gasto pensados para consumo.
- Su objetivo es actualizar metas de ahorro sin inflar artificialmente el gasto del período.

## Vista Dashboard

Tarjetas KPI:

- Ingreso
- Gasto
- Balance
- Ahorro

Regla de cálculo:

- Ahorro se calcula por separado usando categorías marcadas internamente como ahorro.
- Gasto representa consumo operativo y no incorpora egresos técnicos de ahorro.

## Vista Goals

Metas de ahorro:

- Crear meta con monto objetivo y fecha.
- Registrar aportes.
- Ver progreso y monto restante.

Implementación funcional:

- Cuando una meta usa lenguaje natural de ahorro, MIRA registra un egreso técnico en una categoría marcada como ahorro.
- Ese movimiento sí actualiza el avance de la meta.
- Ese mismo movimiento no entra en reportes de gasto real ni en presupuestos.

## Herramientas financieras

Desde el menú **Herramientas** se pueden abrir simuladores que calculan en memoria (sin guardar datos automáticamente):

- **Calculadora de Interés Compuesto** para proyectar crecimiento de capital.
- **Calculadora de Préstamos** para amortización con método francés y alemán.
- **Simulador de Metas de Ahorro** para probar escenarios y proponer abrir el formulario de creación de meta con monto/plazo prellenados (sin guardado automático).

## Vista Settings

Configuraciones principales:

- Usuario.
- Idioma.
- Tema.
- Moneda por defecto.
- Separadores numéricos.
- Modelo preferido para IA local.
- Modo de interacción (Assistant o Chat cuando hay LLM activo).
