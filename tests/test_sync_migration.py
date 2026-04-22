# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from mira.db import migrations as db_migrations
from mira.db.database import Database
from mira.db.errors import DatabaseSchemaError


def _create_minimal_v2_database(path: Path, *, transactions: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                balance_cents INTEGER DEFAULT 0,
                account_type TEXT DEFAULT 'bank',
                currency TEXT DEFAULT 'USD',
                is_default INTEGER DEFAULT 0,
                created_at TEXT
            );
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                type TEXT,
                amount_cents INTEGER,
                description TEXT,
                category TEXT,
                category_id INTEGER,
                subcategory TEXT,
                note TEXT,
                payment_method TEXT DEFAULT 'cash',
                receipt_path TEXT,
                to_account_id INTEGER,
                is_transfer INTEGER DEFAULT 0,
                exchange_rate REAL,
                converted_amount_cents INTEGER,
                date TEXT,
                created_at TEXT
            );
            CREATE TABLE buckets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                budget_amount_cents INTEGER,
                spent_amount_cents INTEGER,
                period TEXT,
                start_day INTEGER,
                end_day INTEGER,
                alert_threshold REAL
            );
            CREATE TABLE settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE currencies (
                code TEXT PRIMARY KEY,
                name TEXT,
                region TEXT
            );
            CREATE TABLE categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                type TEXT,
                color TEXT,
                icon TEXT,
                is_savings INTEGER,
                parent_id INTEGER
            );
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                icon TEXT,
                color TEXT,
                created_at TEXT
            );
            CREATE TABLE transaction_tags (
                transaction_id INTEGER,
                tag_id INTEGER,
                PRIMARY KEY(transaction_id, tag_id)
            );
            CREATE TABLE savings_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                target_amount_cents INTEGER,
                current_amount_cents INTEGER,
                currency TEXT,
                category_id INTEGER,
                target_date TEXT,
                created_at TEXT
            );
            CREATE TABLE recurring_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                type TEXT,
                amount_cents INTEGER,
                description TEXT,
                category TEXT,
                category_id INTEGER,
                note TEXT,
                day_of_month INTEGER
            );
            CREATE TABLE recurring_transaction_tags (
                recurring_id INTEGER,
                tag_id INTEGER,
                PRIMARY KEY(recurring_id, tag_id)
            );
            CREATE TABLE budget_master (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                year INTEGER,
                is_default_year INTEGER,
                currency TEXT,
                created_at TEXT
            );
            CREATE TABLE budget_detail (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                budget_id INTEGER,
                category_id INTEGER,
                year INTEGER,
                month INTEGER,
                amount_cents INTEGER
            );
            CREATE TABLE insight_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                transaction_id INTEGER,
                insight_code TEXT,
                message TEXT,
                priority INTEGER,
                created_at TEXT,
                period_key TEXT,
                extra_context TEXT
            );
            CREATE TABLE achievement_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                transaction_id INTEGER,
                achievement_code TEXT,
                message TEXT,
                priority INTEGER,
                created_at TEXT,
                period_key TEXT,
                extra_context TEXT
            );
            CREATE TABLE achievement_counters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                counter_key TEXT,
                counter_value INTEGER,
                updated_at TEXT
            );
            CREATE TABLE message_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message_code TEXT,
                message_type TEXT,
                source_event_type TEXT,
                source_event_id INTEGER,
                period_key TEXT,
                reference_date TEXT,
                context_category_id INTEGER,
                context_amount_cents INTEGER,
                context_source TEXT,
                shown_at TEXT,
                priority INTEGER,
                message_text TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO accounts (name, balance_cents, account_type, currency, is_default, created_at)
            VALUES ('General', 10000, 'bank', 'USD', 1, '2026-04-08 10:00:00')
            """
        )
        for index in range(transactions):
            conn.execute(
                """
                INSERT INTO transactions (
                    account_id,
                    type,
                    amount_cents,
                    description,
                    category,
                    category_id,
                    subcategory,
                    note,
                    payment_method,
                    receipt_path,
                    to_account_id,
                    is_transfer,
                    exchange_rate,
                    converted_amount_cents,
                    date,
                    created_at
                )
                VALUES (?, 'expense', ?, ?, 'Food', NULL, NULL, NULL, 'cash', NULL, NULL, 0, NULL, NULL, '2026-04-08', ?)
                """,
                (
                    1,
                    2500 + (index * 100),
                    f"legacy expense {index}",
                    None if index == 0 else f"2026-04-08 10:{index % 60:02d}:00",
                ),
            )
        conn.execute("PRAGMA user_version = 2")
        conn.commit()


def _create_minimal_v4_database_missing_sync_schema(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                balance_cents INTEGER DEFAULT 0,
                account_type TEXT DEFAULT 'bank',
                currency TEXT DEFAULT 'USD',
                is_default INTEGER DEFAULT 1,
                created_at TEXT,
                global_id TEXT,
                updated_at TEXT,
                sync_version INTEGER NOT NULL DEFAULT 1,
                last_modified_by_device_id TEXT
            );
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                type TEXT,
                amount_cents INTEGER,
                description TEXT,
                category TEXT,
                category_id INTEGER,
                subcategory TEXT,
                note TEXT,
                payment_method TEXT DEFAULT 'cash',
                receipt_path TEXT,
                to_account_id INTEGER,
                is_transfer INTEGER DEFAULT 0,
                exchange_rate REAL,
                converted_amount_cents INTEGER,
                is_reconciled INTEGER NOT NULL DEFAULT 0,
                reconciled_at TEXT,
                date TEXT,
                created_at TEXT
            );
            CREATE TABLE settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                type TEXT,
                color TEXT,
                icon TEXT,
                is_savings INTEGER,
                parent_id INTEGER,
                global_id TEXT,
                updated_at TEXT,
                sync_version INTEGER NOT NULL DEFAULT 1,
                last_modified_by_device_id TEXT
            );
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                icon TEXT,
                color TEXT,
                created_at TEXT,
                global_id TEXT,
                updated_at TEXT,
                sync_version INTEGER NOT NULL DEFAULT 1,
                last_modified_by_device_id TEXT
            );
            CREATE TABLE savings_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                target_amount_cents INTEGER,
                current_amount_cents INTEGER,
                currency TEXT,
                category_id INTEGER,
                target_date TEXT,
                created_at TEXT,
                global_id TEXT,
                updated_at TEXT,
                sync_version INTEGER NOT NULL DEFAULT 1,
                last_modified_by_device_id TEXT
            );
            CREATE TABLE buckets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                budget_amount_cents INTEGER,
                spent_amount_cents INTEGER,
                period TEXT,
                start_day INTEGER,
                end_day INTEGER,
                alert_threshold REAL
            );
            CREATE TABLE currencies (
                code TEXT PRIMARY KEY,
                name TEXT,
                region TEXT
            );
            CREATE TABLE transaction_tags (
                transaction_id INTEGER,
                tag_id INTEGER,
                PRIMARY KEY(transaction_id, tag_id)
            );
            CREATE TABLE recurring_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                type TEXT,
                amount_cents INTEGER,
                description TEXT,
                category TEXT,
                category_id INTEGER,
                note TEXT,
                day_of_month INTEGER
            );
            CREATE TABLE recurring_transaction_tags (
                recurring_id INTEGER,
                tag_id INTEGER,
                PRIMARY KEY(recurring_id, tag_id)
            );
            CREATE TABLE budget_master (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                year INTEGER,
                is_default_year INTEGER,
                currency TEXT,
                created_at TEXT
            );
            CREATE TABLE budget_detail (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                budget_id INTEGER,
                category_id INTEGER,
                year INTEGER,
                month INTEGER,
                amount_cents INTEGER
            );
            CREATE TABLE insight_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                transaction_id INTEGER,
                insight_code TEXT,
                message TEXT,
                priority INTEGER,
                created_at TEXT,
                period_key TEXT,
                extra_context TEXT
            );
            CREATE TABLE achievement_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                transaction_id INTEGER,
                achievement_code TEXT,
                message TEXT,
                priority INTEGER,
                created_at TEXT,
                period_key TEXT,
                extra_context TEXT
            );
            CREATE TABLE achievement_counters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                counter_key TEXT,
                counter_value INTEGER,
                updated_at TEXT
            );
            CREATE TABLE message_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message_code TEXT,
                message_type TEXT,
                source_event_type TEXT,
                source_event_id INTEGER,
                period_key TEXT,
                reference_date TEXT,
                context_category_id INTEGER,
                context_amount_cents INTEGER,
                context_source TEXT,
                shown_at TEXT,
                priority INTEGER,
                message_text TEXT
            );
            CREATE TABLE reconciliation_groups (
                id TEXT PRIMARY KEY,
                account_id INTEGER NOT NULL,
                date_from DATE NOT NULL,
                date_to DATE NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE reconciliation_matches (
                id TEXT PRIMARY KEY,
                reconciliation_group_id TEXT NOT NULL,
                system_transaction_id INTEGER NOT NULL,
                external_reference TEXT,
                external_date DATE NOT NULL,
                external_description TEXT,
                external_amount_cents INTEGER NOT NULL,
                external_item_key TEXT NOT NULL
            );
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL,
                status TEXT NOT NULL
            );
        """
        )
        conn.execute(
            """
            INSERT INTO accounts (
                name, balance_cents, account_type, currency, is_default, created_at, global_id, updated_at, sync_version,
                last_modified_by_device_id
            ) VALUES ('General', 10000, 'bank', 'USD', 1, '2026-04-08 10:00:00', '01ARZ3NDEKTSV4RRFFQ69G5FAA',
                '2026-04-08T10:00:00Z', 1, 'desktop-local')
            """
        )
        conn.execute(
            """
            INSERT INTO transactions (
                account_id, type, amount_cents, description, category, payment_method, is_transfer,
                is_reconciled, date, created_at
            ) VALUES (1, 'expense', 2500, 'legacy v4 expense', 'Food', 'cash', 0, 0, '2026-04-08', '2026-04-08 10:00:00')
            """
        )
        conn.execute(
            "INSERT INTO schema_version(version, applied_at, status) VALUES (4, '2026-04-18 10:00:00', 'applied')"
        )
        conn.execute("PRAGMA user_version = 4")
        conn.commit()


def test_migrate_v2_to_v3_backfills_sync_metadata_and_indices(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-v2.db"
    _create_minimal_v2_database(db_path, transactions=2)

    with sqlite3.connect(db_path) as conn:
        migrated = db_migrations.migrate_database(conn, 2, 3)
        assert migrated is True

        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(transactions)").fetchall()}
        assert {"sync_id", "sync_version", "updated_at", "last_modified_by_device_id"}.issubset(columns)
        account_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(accounts)").fetchall()}
        category_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(categories)").fetchall()}
        tag_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(tags)").fetchall()}
        goal_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(savings_goals)").fetchall()}
        expected_master_columns = {"global_id", "updated_at", "sync_version", "last_modified_by_device_id"}
        assert expected_master_columns.issubset(account_columns)
        assert expected_master_columns.issubset(category_columns)
        assert expected_master_columns.issubset(tag_columns)
        assert expected_master_columns.issubset(goal_columns)

        rows = conn.execute(
            """
            SELECT sync_id, sync_version, updated_at, last_modified_by_device_id
            FROM transactions
            ORDER BY id
            """
        ).fetchall()
        assert len(rows) == 2
        assert all(row[0] and len(str(row[0])) == 26 for row in rows)
        assert all(int(row[1]) == 1 for row in rows)
        assert all(str(row[2]).strip() for row in rows)
        assert all(str(row[3]) == "desktop-local" for row in rows)
        assert str(rows[0][2]).endswith("Z")

        master_data_setting = conn.execute("SELECT value FROM settings WHERE key = 'master_data_updated_at'").fetchone()
        assert master_data_setting is not None
        assert str(master_data_setting[0]).strip().endswith("Z")

        account_global_ids = conn.execute("SELECT global_id FROM accounts").fetchall()
        assert all(row[0] and len(str(row[0])) == 26 for row in account_global_ids)

        index_names = {
            str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
        }
        assert "idx_transactions_sync_id" in index_names
        assert "idx_transactions_updated_at" in index_names
        assert "idx_events_transaction_sync_id" in index_names
        assert "idx_events_event_id" in index_names
        event_total = int(conn.execute("SELECT COUNT(*) FROM transaction_sync_events").fetchone()[0] or 0)
        assert event_total == 2
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 3


def test_migrate_v2_to_v3_backfills_moderate_volume_with_unique_sync_values(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-v2-volume.db"
    _create_minimal_v2_database(db_path, transactions=40)

    with sqlite3.connect(db_path) as conn:
        migrated = db_migrations.migrate_database(conn, 2, 3)
        assert migrated is True

        rows = conn.execute(
            """
            SELECT sync_id, updated_at, last_modified_by_device_id
            FROM transactions
            ORDER BY id
            """
        ).fetchall()
        sync_ids = [str(row[0]) for row in rows]
        updated_values = [str(row[1]) for row in rows]

        assert len(rows) == 40
        assert len(set(sync_ids)) == 40
        assert all(len(sync_id) == 26 for sync_id in sync_ids)
        assert all("T" in updated_at and updated_at.endswith("Z") for updated_at in updated_values)
        assert all(str(row[2]) == "desktop-local" for row in rows)

        event_total = int(conn.execute("SELECT COUNT(*) FROM transaction_sync_events").fetchone()[0] or 0)
        event_sync_ids = {
            str(row[0]) for row in conn.execute("SELECT transaction_sync_id FROM transaction_sync_events").fetchall()
        }
        master_data_setting = conn.execute("SELECT value FROM settings WHERE key = 'master_data_updated_at'").fetchone()

        assert event_total == 40
        assert event_sync_ids == set(sync_ids)
        assert master_data_setting is not None
        assert "T" in str(master_data_setting[0])
        assert str(master_data_setting[0]).endswith("Z")


def test_migrate_v2_to_v3_rolls_back_when_sync_id_backfill_is_not_unique(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy-v2-rollback.db"
    _create_minimal_v2_database(db_path, transactions=2)
    monkeypatch.setattr(db_migrations, "generate_ulid", lambda: "01ARZ3NDEKTSV4RRFFQ69G5FAV")

    with sqlite3.connect(db_path) as conn:
        with pytest.raises(DatabaseSchemaError, match="duplicated ULID values"):
            db_migrations.migrate_database(conn, 2, 3)
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 2
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(transactions)").fetchall()}
        assert "sync_id" not in columns


def test_database_connect_migrates_v2_database_to_v3_without_data_loss(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-v2-open.db"
    _create_minimal_v2_database(db_path, transactions=1)

    db = Database(path=db_path)
    db.connect()
    try:
        transactions = db.transaction.list(limit=10)
        assert len(transactions) == 1
        assert transactions[0]["description"] == "legacy expense 0"
        assert transactions[0]["sync_id"]
        assert int(transactions[0]["sync_version"]) >= 1
        with sqlite3.connect(db_path) as conn:
            tombstone_tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'transaction_tombstones'"
                ).fetchall()
            }
        assert tombstone_tables == {"transaction_tombstones"}
    finally:
        db.close()


def test_database_connect_creates_backup_and_preserves_v2_database_when_migration_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy-v2-fail.db"
    _create_minimal_v2_database(db_path, transactions=1)

    def _fail_migration(_conn: sqlite3.Connection, _from_version: int, _to_version: int | None = None) -> bool:
        raise DatabaseSchemaError("simulated disk-full failure")

    monkeypatch.setattr("mira.db.runtime.db_migrations.migrate_database", _fail_migration)

    db = Database(path=db_path)
    with pytest.raises(DatabaseSchemaError, match="backup was created"):
        db.connect()

    with sqlite3.connect(db_path) as conn:
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 2
        tx_rows = conn.execute("SELECT description, created_at FROM transactions ORDER BY id").fetchall()
        assert tx_rows == [("legacy expense 0", None)]

    backups = list(tmp_path.glob("legacy-v2-fail.pre-v2-migration-*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 2


def test_database_connect_migrates_v4_database_missing_sync_tables_to_v5(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-v4-missing-sync.db"
    _create_minimal_v4_database_missing_sync_schema(db_path)

    db = Database(path=db_path)
    db.connect()
    try:
        transactions = db.transaction.list(limit=10)
        assert len(transactions) == 1
        assert transactions[0]["description"] == "legacy v4 expense"
        assert transactions[0]["sync_id"]
        assert int(transactions[0]["sync_version"]) >= 1
        with sqlite3.connect(db_path) as conn:
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('sync_devices', 'transaction_sync_events', 'transaction_tombstones')"
                ).fetchall()
            }
            assert tables == {"sync_devices", "transaction_sync_events", "transaction_tombstones"}
            assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 5
            event_total = int(conn.execute("SELECT COUNT(*) FROM transaction_sync_events").fetchone()[0] or 0)
            assert event_total == 1
    finally:
        db.close()
