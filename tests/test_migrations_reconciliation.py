# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import sqlite3

import pytest

from mira.db import migrations as db_migrations
from mira.db.errors import DatabaseSchemaError


def _create_minimum_v3_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY,
            name TEXT,
            balance_cents INTEGER NOT NULL DEFAULT 0,
            account_type TEXT,
            currency TEXT,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP
        )
        """)
    conn.execute("""
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY,
            account_id INTEGER,
            type TEXT,
            amount_cents INTEGER NOT NULL DEFAULT 0,
            category TEXT,
            category_id INTEGER,
            date DATE
        )
        """)


def test_migrate_v3_to_v4_creates_reconciliation_tables_and_columns() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        _create_minimum_v3_schema(conn)

        db_migrations._migrate_v3_to_v4(conn)

        transaction_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(transactions)").fetchall()}
        tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        indexes = {
            str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
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


def _create_minimum_v1_schema(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, balance REAL, currency TEXT)")
    conn.execute("CREATE TABLE transactions (id INTEGER PRIMARY KEY, amount REAL, converted_amount REAL)")
    conn.execute("CREATE TABLE buckets (id INTEGER PRIMARY KEY, budget_amount REAL, spent_amount REAL)")
    conn.execute("CREATE TABLE recurring_transactions (id INTEGER PRIMARY KEY, amount REAL)")
    conn.execute("CREATE TABLE budget_detail (id INTEGER PRIMARY KEY, amount REAL)")
    conn.execute("CREATE TABLE savings_goals (id INTEGER PRIMARY KEY, target_amount REAL, current_amount REAL)")
    conn.execute("CREATE TABLE message_events (id INTEGER PRIMARY KEY, context_amount REAL)")
    conn.commit()


def test_migrate_v1_to_v2_converts_legacy_cents_columns() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        _create_minimum_v1_schema(conn)
        conn.execute("INSERT INTO accounts (balance, currency) VALUES (?, ?)", (123.45, "USD"))
        conn.execute(
            "INSERT INTO transactions (amount, converted_amount) VALUES (?, ?)",
            (10.0, None),
        )
        conn.execute(
            "INSERT INTO buckets (budget_amount, spent_amount) VALUES (?, ?)",
            (40.25, 15.75),
        )
        conn.execute("INSERT INTO recurring_transactions (amount) VALUES (?)", (12.5,))
        conn.execute("INSERT INTO budget_detail (amount) VALUES (?)", (8.25,))
        conn.execute(
            "INSERT INTO savings_goals (target_amount, current_amount) VALUES (?, ?)",
            (500.0, 125.25),
        )
        conn.execute("INSERT INTO message_events (context_amount) VALUES (?)", (None,))
        conn.commit()

        db_migrations._migrate_v1_to_v2(conn)

        assert conn.execute("PRAGMA table_info(accounts)").fetchone()[1] == "id"
        account_row = conn.execute("SELECT balance_cents FROM accounts WHERE id = 1").fetchone()
        assert account_row[0] == 12345

        tx_row = conn.execute("SELECT amount_cents, converted_amount_cents FROM transactions WHERE id = 1").fetchone()
        assert tx_row[0] == 1000
        assert tx_row[1] is None

        bucket_row = conn.execute("SELECT budget_amount_cents, spent_amount_cents FROM buckets WHERE id = 1").fetchone()
        assert bucket_row == (4025, 1575)

        savings_goal_row = conn.execute(
            "SELECT target_amount_cents, current_amount_cents FROM savings_goals WHERE id = 1"
        ).fetchone()
        assert savings_goal_row == (50000, 12525)

        message_event_row = conn.execute("SELECT context_amount_cents FROM message_events WHERE id = 1").fetchone()
        assert message_event_row[0] is None
    finally:
        conn.close()


def test_migrate_v2_to_v3_sanitizes_duplicate_default_accounts_and_creates_relations() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(
            "CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT, balance_cents INTEGER NOT NULL DEFAULT 0, account_type TEXT, currency TEXT, is_default INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMP)"
        )
        conn.execute("CREATE TABLE categories (id INTEGER PRIMARY KEY)")
        conn.execute(
            "INSERT INTO accounts (name, balance_cents, account_type, currency, is_default) VALUES (?, ?, ?, ?, ?)",
            ("General", 0, "bank", "USD", 1),
        )
        conn.execute(
            "INSERT INTO accounts (name, balance_cents, account_type, currency, is_default) VALUES (?, ?, ?, ?, ?)",
            ("Second Default", 0, "bank", "USD", 1),
        )
        conn.commit()

        db_migrations._migrate_v2_to_v3(conn)

        defaults = [row[0] for row in conn.execute("SELECT is_default FROM accounts ORDER BY id").fetchall()]
        assert defaults == [1, 0]

        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        assert "income_expense_relations" in tables

        indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()}
        assert "uq_income_expense_relations_expense" in indexes
        assert "idx_income_expense_relations_income" in indexes
    finally:
        conn.close()


def test_migrate_database_rejects_unsupported_version() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(DatabaseSchemaError, match="Pre-0.0.1a2 databases remain unsupported"):
            db_migrations.migrate_database(conn, 0, 4)
    finally:
        conn.close()


def test_migrate_database_returns_false_for_current_version() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        assert db_migrations.migrate_database(conn, 4, 4) is False
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
            int(row[0]) for row in conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
        ]
        user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])

        assert migration_applied is True
        assert schema_versions == [3, 4]
        assert user_version == 4
    finally:
        conn.close()
