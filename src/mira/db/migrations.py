# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from mira.db import model as db_model
from mira.db.errors import DatabaseSchemaError

MigrationFn = Callable[[sqlite3.Connection], None]

# No in-place migrations are enabled yet. Future releases can lower this floor
# and register sequential migrations without changing the restore/runtime flow.
MIN_MIGRATABLE_SCHEMA_VERSION = 2


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


MIGRATIONS: dict[int, MigrationFn] = {
    2: _migrate_v2_to_v3,
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
        conn.execute("BEGIN")
        while current_version < target_version:
            migration = MIGRATIONS.get(current_version)
            if migration is None:
                raise DatabaseSchemaError(
                    f"No migration path exists from schema version {current_version} to {target_version}."
                )
            migration(conn)
            current_version += 1
            conn.execute(f"PRAGMA user_version = {current_version}")
            migration_applied = True
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return migration_applied
