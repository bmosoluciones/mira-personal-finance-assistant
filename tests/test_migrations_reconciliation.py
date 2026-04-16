# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import sqlite3

from mira.db import migrations as db_migrations


def _create_minimum_v3_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY,
            name TEXT,
            balance_cents INTEGER NOT NULL DEFAULT 0,
            account_type TEXT,
            currency TEXT,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY,
            account_id INTEGER,
            type TEXT,
            amount_cents INTEGER NOT NULL DEFAULT 0,
            category TEXT,
            category_id INTEGER,
            date DATE
        )
        """
    )


def test_migrate_v3_to_v4_creates_reconciliation_tables_and_columns() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        _create_minimum_v3_schema(conn)

        db_migrations._migrate_v3_to_v4(conn)

        transaction_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(transactions)").fetchall()
        }
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        indexes = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
        }
        schema_rows = conn.execute("SELECT version, status FROM schema_version").fetchall()

        assert "is_reconciled" in transaction_columns
        assert "reconciled_at" in transaction_columns
        assert "reconciliation_groups" in tables
        assert "reconciliation_matches" in tables
        assert "idx_reconciliation_groups_account_range" in indexes
        assert "idx_reconciliation_matches_group" in indexes
        assert "idx_reconciliation_matches_transaction" in indexes
        assert "uq_reconciliation_matches_group_tx_external" in indexes
        assert schema_rows == [(4, "applied")]
    finally:
        conn.close()


def test_migrate_v3_to_v4_is_idempotent() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        _create_minimum_v3_schema(conn)

        db_migrations._migrate_v3_to_v4(conn)
        db_migrations._migrate_v3_to_v4(conn)

        schema_rows = conn.execute("SELECT version, status FROM schema_version ORDER BY version").fetchall()
        assert schema_rows == [(4, "applied")]
    finally:
        conn.close()


def test_migrate_database_records_from_and_target_versions_in_schema_audit() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        _create_minimum_v3_schema(conn)

        migration_applied = db_migrations.migrate_database(conn, 3, 4)

        schema_versions = [
            int(row[0])
            for row in conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
        ]
        user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])

        assert migration_applied is True
        assert schema_versions == [3, 4]
        assert user_version == 4
    finally:
        conn.close()
