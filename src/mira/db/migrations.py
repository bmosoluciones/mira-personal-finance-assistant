# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from mira.db import model as db_model
from mira.db.errors import DatabaseSchemaError

MigrationFn = Callable[[sqlite3.Connection], None]

MIN_MIGRATABLE_SCHEMA_VERSION = 1

_CENT = Decimal("0.01")


def _table_columns(conn: sqlite3.Connection, table: str) -> frozenset[str]:
    return frozenset(str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column_name: str, column_sql: str) -> None:
    if column_name not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_sql}")


def _money_to_cents(value: object | None) -> int | None:
    if value is None:
        return None
    amount = Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _populate_money_column(
    conn: sqlite3.Connection,
    *,
    table: str,
    legacy_column: str,
    cents_column: str,
    nullable: bool = False,
) -> None:
    rows = conn.execute(f"SELECT id, {legacy_column} FROM {table}").fetchall()
    for row in rows:
        cents_value = _money_to_cents(row[1])
        if cents_value is None and not nullable:
            cents_value = 0
        conn.execute(
            f"UPDATE {table} SET {cents_column} = ? WHERE id = ?",
            (cents_value, row[0]),
        )


def _ensure_schema_version_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL,
            status TEXT NOT NULL
        )
        """)


def _record_schema_version(conn: sqlite3.Connection, version: int, *, status: str = "applied") -> None:
    _ensure_schema_version_table(conn)
    conn.execute(
        "INSERT OR REPLACE INTO schema_version(version, applied_at, status) VALUES (?, ?, ?)",
        (version, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status),
    )


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Migrate legacy float-backed money columns into exact integer cents columns."""
    _add_column_if_missing(conn, "accounts", "balance_cents", "balance_cents INTEGER NOT NULL DEFAULT 0")
    _populate_money_column(conn, table="accounts", legacy_column="balance", cents_column="balance_cents")

    _add_column_if_missing(conn, "transactions", "amount_cents", "amount_cents INTEGER NOT NULL DEFAULT 0")
    _populate_money_column(conn, table="transactions", legacy_column="amount", cents_column="amount_cents")
    _add_column_if_missing(conn, "transactions", "converted_amount_cents", "converted_amount_cents INTEGER")
    _populate_money_column(
        conn,
        table="transactions",
        legacy_column="converted_amount",
        cents_column="converted_amount_cents",
        nullable=True,
    )

    _add_column_if_missing(conn, "buckets", "budget_amount_cents", "budget_amount_cents INTEGER NOT NULL DEFAULT 0")
    _populate_money_column(conn, table="buckets", legacy_column="budget_amount", cents_column="budget_amount_cents")
    _add_column_if_missing(conn, "buckets", "spent_amount_cents", "spent_amount_cents INTEGER NOT NULL DEFAULT 0")
    _populate_money_column(conn, table="buckets", legacy_column="spent_amount", cents_column="spent_amount_cents")

    _add_column_if_missing(
        conn,
        "recurring_transactions",
        "amount_cents",
        "amount_cents INTEGER NOT NULL DEFAULT 0",
    )
    _populate_money_column(
        conn,
        table="recurring_transactions",
        legacy_column="amount",
        cents_column="amount_cents",
    )

    _add_column_if_missing(conn, "budget_detail", "amount_cents", "amount_cents INTEGER NOT NULL DEFAULT 0")
    _populate_money_column(conn, table="budget_detail", legacy_column="amount", cents_column="amount_cents")

    _add_column_if_missing(
        conn,
        "savings_goals",
        "target_amount_cents",
        "target_amount_cents INTEGER NOT NULL DEFAULT 0",
    )
    _populate_money_column(
        conn,
        table="savings_goals",
        legacy_column="target_amount",
        cents_column="target_amount_cents",
    )
    _add_column_if_missing(
        conn,
        "savings_goals",
        "current_amount_cents",
        "current_amount_cents INTEGER NOT NULL DEFAULT 0",
    )
    _populate_money_column(
        conn,
        table="savings_goals",
        legacy_column="current_amount",
        cents_column="current_amount_cents",
    )

    _add_column_if_missing(
        conn,
        "message_events",
        "context_amount_cents",
        "context_amount_cents INTEGER",
    )
    _populate_money_column(
        conn,
        table="message_events",
        legacy_column="context_amount",
        cents_column="context_amount_cents",
        nullable=True,
    )


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    """Migrate schema v2 → v3.

    1. Sanitize duplicate default accounts so the uniqueness index can be
       created without conflicts.
    2. Create the ``income_expense_relations`` table for associating
       income categories with expense categories (idempotent).
    """
    # -- Fix duplicate default accounts ------------------------------------
    rows = conn.execute("SELECT id FROM accounts WHERE is_default = 1 ORDER BY id").fetchall()
    if len(rows) > 1:
        keep_id = rows[0][0]
        conn.execute("UPDATE accounts SET is_default = 0 WHERE is_default = 1 AND id != ?", (keep_id,))

    # -- Create income_expense_relations table -----------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS income_expense_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            income_category_id INTEGER NOT NULL
                REFERENCES categories(id) ON DELETE CASCADE,
            expense_category_id INTEGER NOT NULL
                REFERENCES categories(id) ON DELETE CASCADE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_income_expense_relations_expense "
        "ON income_expense_relations(expense_category_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_income_expense_relations_income "
        "ON income_expense_relations(income_category_id)"
    )


def _migrate_v3_to_v4(conn: sqlite3.Connection) -> None:
    """Create reconciliation structures and reconciliation flags in transactions."""
    _add_column_if_missing(conn, "transactions", "is_reconciled", "is_reconciled INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "transactions", "reconciled_at", "reconciled_at TIMESTAMP")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS reconciliation_groups (
            id TEXT PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            date_from DATE NOT NULL,
            date_to DATE NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reconciliation_matches (
            id TEXT PRIMARY KEY,
            reconciliation_group_id TEXT NOT NULL
                REFERENCES reconciliation_groups(id) ON DELETE CASCADE,
            system_transaction_id INTEGER NOT NULL
                REFERENCES transactions(id) ON DELETE CASCADE,
            external_reference TEXT,
            external_date DATE NOT NULL,
            external_description TEXT,
            external_amount_cents INTEGER NOT NULL,
            external_item_key TEXT NOT NULL
        )
        """)
    _record_schema_version(conn, 4)

    for index_spec in db_model.SCHEMA_INDEX_SPECS:
        if index_spec.table in {"transactions", "reconciliation_groups", "reconciliation_matches", "schema_version"}:
            conn.execute(db_model._build_create_index_sql(index_spec))


MIGRATIONS: dict[int, MigrationFn] = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
}


def get_current_schema_version() -> int:
    return db_model.SCHEMA_VERSION


def migrate_database(conn: sqlite3.Connection, from_version: int, to_version: int | None = None) -> bool:
    """Apply sequential schema migrations up to the requested target version."""
    target_version = get_current_schema_version() if to_version is None else to_version
    if from_version >= target_version:
        return False
    if from_version < MIN_MIGRATABLE_SCHEMA_VERSION:
        raise DatabaseSchemaError(
            f"Schema version {from_version} is not supported for in-place migration. "
            "Pre-0.0.1a2 databases remain unsupported."
        )

    current_version = from_version
    migration_applied = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        _record_schema_version(conn, from_version)
        while current_version < target_version:
            migration = MIGRATIONS.get(current_version)
            if migration is None:
                raise DatabaseSchemaError(
                    f"No migration path exists from schema version {current_version} to {target_version}."
                )
            migration(conn)
            current_version += 1
            conn.execute(f"PRAGMA user_version = {current_version}")
            _record_schema_version(conn, current_version)
            migration_applied = True
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return migration_applied
