# Asociación de Categorías de Ingresos y Gastos

## Descripción General

MIRA permite a usuarios avanzados **vincular categorías de ingresos con una o
más categorías de gastos** para que el Reporte Maestro MIRA muestre un desglose
por fuente de ingreso de cómo se distribuyen los gastos.

### Ejemplo

Juan recibe un *Salario* y un ingreso por *Alquiler*.  Utiliza el salario para
Vivienda, Alimentación, Transporte y Educación, mientras que el ingreso por
alquiler cubre Mantenimiento e Impuestos sobre la propiedad.  Al vincular estas
categorías, Juan puede ver en el reporte exactamente cuánto de cada fuente de
ingreso es consumido por sus gastos asociados.

## Reglas de Negocio

| Regla | Descripción |
|-------|-------------|
| 1 → N | Una categoría de ingreso puede vincularse a **varias** categorías de gasto. |
| N → 1 | Cada categoría de gasto solo puede vincularse a **una** categoría de ingreso. |
| Solo nivel 1 | Solo categorías padre (nivel 1) pueden participar. |
| Basado en ID | Las relaciones se guardan por ID de categoría — renombrar una categoría no rompe el vínculo. |
| Eliminación en cascada | Eliminar una categoría elimina automáticamente sus relaciones. |

## Uso de la Funcionalidad

### Acceso al Diálogo

1. Navegue a **Categorías** en la barra lateral.
2. Haga clic en el botón **🔗 Vincular** ubicado entre las columnas de ingresos y gastos.

### Ver Relaciones Existentes

El diálogo muestra una tabla con dos columnas:

| Categoría Ingreso | Categoría Gasto |
|--------------------|-----------------|
| Salario            | Vivienda        |
| Salario            | Alimentación    |
| Alquileres         | Mantenimiento   |

Las filas se ordenan alfabéticamente por categoría de ingreso y luego por
categoría de gasto.

### Agregar una Relación

1. Haga clic en **Agregar Relación**.
2. Seleccione una categoría de ingreso del primer menú desplegable (solo nivel 1).
3. Seleccione una categoría de gasto del segundo menú desplegable (solo nivel 1;
   las categorías ya vinculadas se excluyen).
4. Haga clic en **Guardar**.

### Eliminar una Relación

1. Seleccione una fila en la tabla.
2. Haga clic en **Eliminar Relación**.
3. Confirme en el diálogo.

## Sección del Reporte Maestro MIRA

Cuando existe al menos una relación, el Reporte Maestro MIRA incluye una nueva
sección al final:

**Ingresos vs Gastos por Categoría de Ingreso**

Para cada categoría de ingreso con gastos vinculados el reporte muestra:

| Categoría Ingreso | Monto     | Categoría Gasto | Monto    |
|-------------------|-----------|-----------------|----------|
| Salarios      | 2,000.00  | Vivienda        | 300.00   |
|               |           | Alimentación    | 400.00   |
|               |           | Transporte      | 400.00   |
|               |           | Educación       | 300.00   |
| **Total**     | 2,000.00  |                 | 1,400.00 |
| Alquileres    | 500.00    | Mantenimiento   | 200.00   |
|               |           | Impuestos       | 100.00   |
| **Total**     | 500.00    |                 | 300.00   |

- Los montos se filtran por el **mismo mes y año** seleccionado en el reporte.
- Si no existen relaciones, la sección se omite por completo.

## Base de Datos

La funcionalidad agrega una tabla `income_expense_relations`:

| Columna              | Tipo      | Restricción             |
|----------------------|-----------|-------------------------|
| id                   | PK        | auto-incremento         |
| income_category_id   | FK → categories | NOT NULL, CASCADE  |
| expense_category_id  | FK → categories | NOT NULL, UNIQUE, CASCADE |
| created_at           | timestamp | NOT NULL                |

La tabla se crea como parte del esquema versión 3 vía `initialize_schema` (para
bases de datos nuevas) y la migración idempotente v2 → v3 (para bases de datos
existentes).

## Referencia API

### CategoryFacade (vía `db.category`)

```python
db.category.list_relations() -> list[dict]
db.category.create_relation(income_category_id, expense_category_id) -> dict
db.category.delete_relation(relation_id) -> None
db.category.linked_expense_ids() -> set[int]
```

### CategoriesViewService

```python
service.list_relations() -> list[dict]
service.create_relation(income_id, expense_id) -> dict
service.delete_relation(relation_id) -> None
service.parent_income_categories() -> list[dict]
service.available_parent_expense_categories() -> list[dict]
```

### Payload del Reporte

La nueva clave `income_vs_expense_by_income` es `None` (sin relaciones) o una
lista de objetos:

```json
[
  {
    "income_category": "Salarios",
    "income_amount": 2000.00,
    "expenses": [
      {"category": "Vivienda", "amount": 300.00},
      {"category": "Alimentación", "amount": 400.00}
    ],
    "expense_total": 700.00
  }
]
```
