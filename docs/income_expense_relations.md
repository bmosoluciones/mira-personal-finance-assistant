# Income–Expense Category Associations

## Overview

MIRA allows advanced users to **link income categories to one or more expense
categories** so that the MIRA Master Report can show a per-income-source
breakdown of where money goes.

### Example

John receives a *Salary* and a *Rental* income.  He uses salary earnings for
Housing, Food, Transport and Education, while rental income covers Maintenance
and Taxes on the property.  By linking these categories John can see in the
report exactly how much of each income source is consumed by its associated
expenses.

## Business Rules

| Rule | Description |
|------|-------------|
| 1 → N | One income category can be linked to **many** expense categories. |
| N → 1 | Each expense category can be linked to **at most one** income category. |
| Level 1 only | Only top-level (parent) categories can participate. |
| ID-based | Relations are stored by category ID — renaming a category does not break the link. |
| Cascade delete | Deleting a category automatically removes its relations. |

## Using the Feature

### Accessing the Dialog

1. Navigate to **Categories** in the side bar.
2. Click the **🔗 Link** button located between the income and expense columns.

### Viewing Existing Relations

The dialog shows a table with two columns:

| Income Category | Expense Category |
|-----------------|------------------|
| Salary          | Housing          |
| Salary          | Food             |
| Rental          | Maintenance      |

Rows are sorted alphabetically by income category name, then by expense
category name.

### Adding a Relation

1. Click **Add Relation**.
2. Select an income category from the first dropdown (level-1 only).
3. Select an expense category from the second dropdown (level-1 only;
   already-linked categories are excluded).
4. Click **Save**.

### Deleting a Relation

1. Select a row in the table.
2. Click **Delete Relation**.
3. Confirm in the dialog.

## MIRA Master Report Section

When at least one relation exists, the MIRA Master Report includes a new
section at the end:

**Income vs Expenses by Income Category**

For each income category that has linked expenses the report shows:

| Income Category | Amount   | Expense Category | Amount   |
|-----------------|----------|------------------|----------|
| Salary          | 2,000.00 | Housing          | 300.00   |
|                 |          | Food             | 400.00   |
|                 |          | Transport        | 400.00   |
|                 |          | Education        | 300.00   |
| **Total**       | 2,000.00 |                  | 1,400.00 |
| Rental          | 500.00   | Maintenance      | 200.00   |
|                 |          | Taxes            | 100.00   |
| **Total**       | 500.00   |                  | 300.00   |

- Amounts are filtered by the **same month and year** selected for the report.
- If no relations exist, the section is omitted entirely.

## Database

The feature adds a single table `income_expense_relations`:

| Column               | Type      | Constraint              |
|----------------------|-----------|-------------------------|
| id                   | PK        | auto-increment          |
| income_category_id   | FK → categories | NOT NULL, CASCADE  |
| expense_category_id  | FK → categories | NOT NULL, UNIQUE, CASCADE |
| created_at           | timestamp | NOT NULL                |

The table is created as part of schema version 3 via `initialize_schema` (for
new databases) and the idempotent v2 → v3 migration (for existing databases).

## API Reference

### CategoryFacade (via `db.category`)

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

### Report Payload

The new key `income_vs_expense_by_income` is either `None` (no relations) or a
list of objects:

```json
[
  {
    "income_category": "Salary",
    "income_amount": 2000.00,
    "expenses": [
      {"category": "Housing", "amount": 300.00},
      {"category": "Food", "amount": 400.00}
    ],
    "expense_total": 700.00
  }
]
```
