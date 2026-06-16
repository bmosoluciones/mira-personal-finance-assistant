# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Module documentation."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from mira.db import model as db_model
from mira.db.errors import DatabaseSchemaError
from mira.db.master_sync import MASTER_DATA_UPDATED_AT_SETTING
from mira.sync_utils import generate_ulid, normalize_utc_iso, utc_now_iso

MigrationFn = Callable[[sqlite3.Connection], None]

MIN_MIGRATABLE_SCHEMA_VERSION = 1

_CENT = Decimal("0.01")


def _table_columns(conn: sqlite3.Connection, table: str) -> frozenset[str]:
    """Return table columns."""
    return frozenset(str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column_name: str, column_sql: str) -> None:
    """Return add column if missing."""
    if column_name not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_sql}")


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Return whether a table exists in the database."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _create_index_if_missing(conn: sqlite3.Connection, sql: str) -> None:
    """Execute an idempotent CREATE INDEX IF NOT EXISTS statement."""
    conn.execute(sql)


def _next_unique_ulid(
    existing_identifier: str,
    seen_identifiers: set[str],
    *,
    record_label: str,
    max_attempts: int,
) -> str:
    """Return a unique ULID, reusing an existing valid one if possible."""
    normalized_existing = existing_identifier.strip()
    if normalized_existing and normalized_existing not in seen_identifiers:
        return normalized_existing

    for _ in range(max_attempts):
        if (candidate := generate_ulid().strip()) and candidate not in seen_identifiers:
            return candidate

    raise DatabaseSchemaError(
        "Migration v2 -> v3 failed: duplicated ULID values were found."
        f" Could not generate a unique identifier for {record_label}."
    )


def _backfill_master_table_sync_fields(
    conn: sqlite3.Connection,
    table_name: str,
    *,
    created_at_column: str | None,
) -> None:
    """Backfill global_id, updated_at, sync_version and last_modified_by_device_id."""
    columns = _table_columns(conn, table_name)
    created_at_expr = created_at_column if created_at_column and created_at_column in columns else "NULL"
    rows = conn.execute(f"""
        SELECT id, global_id, {created_at_expr} AS created_at, updated_at, sync_version, last_modified_by_device_id
        FROM {table_name}
        ORDER BY id
        """).fetchall()
    seen_global_ids: set[str] = set()
    fallback_timestamp = utc_now_iso()
    max_attempts = max(16, len(rows) * 4)
    updates: list[tuple[str, str, int]] = []

    for row in rows:
        row_id = int(row[0])
        existing_global_id = str(row[1]).strip() if row[1] is not None else ""
        global_id = _next_unique_ulid(
            existing_global_id,
            seen_global_ids,
            record_label=f"{table_name} row {row_id}",
            max_attempts=max_attempts,
        )
        seen_global_ids.add(global_id)
        created_at = normalize_utc_iso(row[2] or fallback_timestamp)
        updated_at = normalize_utc_iso(row[3] or created_at)
        updates.append((global_id, updated_at, row_id))

    if updates:
        conn.executemany(
            f"""
            UPDATE {table_name}
            SET global_id = ?,
                sync_version = COALESCE(sync_version, 1),
                updated_at = ?,
                last_modified_by_device_id = COALESCE(NULLIF(last_modified_by_device_id, ''), 'desktop-local')
            WHERE id = ?
            """,
            updates,
        )


def _ensure_backfilled_transaction_sync_fields(conn: sqlite3.Connection) -> None:
    """Backfill sync_id, sync_version, updated_at and last_modified_by_device_id for transactions."""
    rows = conn.execute("SELECT id, sync_id, created_at, updated_at FROM transactions ORDER BY id").fetchall()
    seen_sync_ids: set[str] = set()
    fallback_timestamp = utc_now_iso()
    max_attempts = max(16, len(rows) * 4)
    updates: list[tuple[str, str, int]] = []

    for row in rows:
        tx_id = int(row[0])
        existing_sync_id = str(row[1]).strip() if row[1] is not None else ""
        sync_id = _next_unique_ulid(
            existing_sync_id,
            seen_sync_ids,
            record_label=f"transaction {tx_id}",
            max_attempts=max_attempts,
        )
        seen_sync_ids.add(sync_id)
        created_at = normalize_utc_iso(row[2] or fallback_timestamp)
        updated_at = normalize_utc_iso(row[3] or created_at)
        updates.append((sync_id, updated_at, tx_id))

    if updates:
        conn.executemany(
            """
            UPDATE transactions
            SET sync_id = ?,
                sync_version = COALESCE(sync_version, 1),
                updated_at = ?,
                last_modified_by_device_id = COALESCE(NULLIF(last_modified_by_device_id, ''), 'desktop-local')
            WHERE id = ?
            """,
            updates,
        )


def _validate_backfilled_sync_state(conn: sqlite3.Connection) -> None:
    """Raise if any transaction is missing or has a duplicate sync_id."""
    null_sync_ids = int(
        conn.execute("SELECT COUNT(*) FROM transactions WHERE sync_id IS NULL OR TRIM(sync_id) = ''").fetchone()[0] or 0
    )
    if null_sync_ids:
        raise DatabaseSchemaError("Migration v2 -> v3 failed: one or more transactions have an empty sync_id.")

    duplicated_sync_ids = int(conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT sync_id
                FROM transactions
                GROUP BY sync_id
                HAVING COUNT(*) > 1
            )
            """).fetchone()[0] or 0)
    if duplicated_sync_ids:
        raise DatabaseSchemaError("Migration v2 -> v3 failed: duplicated transaction sync_id values were found.")


def _validate_master_table_sync_state(conn: sqlite3.Connection, table_name: str) -> None:
    """Raise if any row in the given master table is missing or has a duplicate global_id."""
    empty_global_ids = int(
        conn.execute(f"SELECT COUNT(*) FROM {table_name} WHERE global_id IS NULL OR TRIM(global_id) = ''").fetchone()[0]
        or 0
    )
    if empty_global_ids:
        raise DatabaseSchemaError(
            f"Migration v2 -> v3 failed: one or more rows in '{table_name}' have an empty global_id."
        )
    duplicated_global_ids = int(conn.execute(f"""
            SELECT COUNT(*) FROM (
                SELECT global_id
                FROM {table_name}
                GROUP BY global_id
                HAVING COUNT(*) > 1
            )
            """).fetchone()[0] or 0)
    if duplicated_global_ids:
        raise DatabaseSchemaError(
            f"Migration v2 -> v3 failed: duplicated global_id values were found in '{table_name}'."
        )


def _upsert_master_data_updated_at(conn: sqlite3.Connection) -> None:
    """Insert or update the master_data_updated_at setting."""
    latest_candidates: list[str] = []
    for table_name in ("accounts", "categories", "tags", "savings_goals"):
        row = conn.execute(f"SELECT MAX(updated_at) FROM {table_name}").fetchone()
        if row and row[0]:
            latest_candidates.append(normalize_utc_iso(row[0]))
    master_data_updated_at = max(latest_candidates) if latest_candidates else utc_now_iso()
    conn.execute(
        """
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (MASTER_DATA_UPDATED_AT_SETTING, master_data_updated_at),
    )


def _ensure_sync_schema(conn: sqlite3.Connection) -> None:
    """Ensure sync metadata, tables, seed rows, and indexes exist."""
    for tbl in ("accounts", "categories", "tags", "savings_goals"):
        if not _table_exists(conn, tbl):
            continue
        _add_column_if_missing(conn, tbl, "global_id", "global_id TEXT")
        _add_column_if_missing(conn, tbl, "updated_at", "updated_at TEXT")
        _add_column_if_missing(conn, tbl, "sync_version", "sync_version INTEGER NOT NULL DEFAULT 1")
        _add_column_if_missing(conn, tbl, "last_modified_by_device_id", "last_modified_by_device_id TEXT")

    if _table_exists(conn, "transactions"):
        _add_column_if_missing(conn, "transactions", "sync_id", "sync_id TEXT")
        _add_column_if_missing(conn, "transactions", "sync_version", "sync_version INTEGER NOT NULL DEFAULT 1")
        _add_column_if_missing(conn, "transactions", "updated_at", "updated_at TEXT")
        _add_column_if_missing(conn, "transactions", "last_modified_by_device_id", "last_modified_by_device_id TEXT")

    for _tbl, _created_at in (
        ("accounts", "created_at"),
        ("categories", None),
        ("tags", "created_at"),
        ("savings_goals", "created_at"),
    ):
        if _table_exists(conn, _tbl):
            _backfill_master_table_sync_fields(conn, _tbl, created_at_column=_created_at)
    if _table_exists(conn, "transactions"):
        _ensure_backfilled_transaction_sync_fields(conn)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_devices (
            device_id TEXT PRIMARY KEY,
            device_name TEXT NOT NULL,
            platform TEXT NOT NULL,
            app_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_acked_event_id INTEGER NOT NULL DEFAULT 0
        )
        """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transaction_sync_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_sync_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            transaction_version INTEGER NOT NULL,
            device_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transaction_tombstones (
            transaction_sync_id TEXT PRIMARY KEY,
            last_deleted_version INTEGER NOT NULL,
            deleted_by_device_id TEXT NOT NULL,
            deleted_at TEXT NOT NULL
        )
        """)

    if _table_exists(conn, "transactions"):
        transaction_rows = conn.execute("""
            SELECT sync_id, sync_version, updated_at
            FROM transactions
            ORDER BY id
            """).fetchall()
        if transaction_rows:
            conn.executemany(
                """
                INSERT INTO transaction_sync_events (
                    transaction_sync_id,
                    operation,
                    transaction_version,
                    device_id,
                    created_at
                )
                SELECT ?, 'create', ?, 'desktop-local', ?
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM transaction_sync_events
                    WHERE transaction_sync_id = ? AND transaction_version = ?
                    LIMIT 1
                )
                """,
                [
                    (sync_id, sync_version, normalize_utc_iso(updated_at), sync_id, sync_version)
                    for sync_id, sync_version, updated_at in transaction_rows
                ],
            )

    if _table_exists(conn, "transactions"):
        _validate_backfilled_sync_state(conn)
    for _tbl in ("accounts", "categories", "tags", "savings_goals"):
        if _table_exists(conn, _tbl):
            _validate_master_table_sync_state(conn, _tbl)
    if _table_exists(conn, "settings"):
        _upsert_master_data_updated_at(conn)

    if _table_exists(conn, "transactions"):
        _create_index_if_missing(
            conn,
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_sync_id ON transactions(sync_id)",
        )
        _create_index_if_missing(
            conn,
            "CREATE INDEX IF NOT EXISTS idx_transactions_updated_at ON transactions(updated_at)",
        )
    _create_index_if_missing(
        conn,
        "CREATE INDEX IF NOT EXISTS idx_events_transaction_sync_id ON transaction_sync_events(transaction_sync_id)",
    )
    _create_index_if_missing(
        conn,
        "CREATE INDEX IF NOT EXISTS idx_events_event_id ON transaction_sync_events(event_id)",
    )


def _money_to_cents(value: object | None) -> int | None:
    """Return money to cents."""
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
    """Return populate money column."""
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
    """Return ensure schema version table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL,
            status TEXT NOT NULL
        )
        """)


def _record_schema_version(conn: sqlite3.Connection, version: int, *, status: str = "applied") -> None:
    """Return record schema version."""
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
    3. Add sync metadata columns to transactions, accounts, categories, tags
       and savings_goals, and create the sync event/device/tombstone tables.
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

    _ensure_sync_schema(conn)


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
    for index_spec in db_model.SCHEMA_INDEX_SPECS:
        if index_spec.table in {"transactions", "reconciliation_groups", "reconciliation_matches"}:
            conn.execute(db_model._build_create_index_sql(index_spec))
    _record_schema_version(conn, 4)


def _migrate_v4_to_v5(conn: sqlite3.Connection) -> None:
    """Backfill mobile sync schema for databases already marked as v4."""
    _ensure_sync_schema(conn)
    _record_schema_version(conn, 5)

    for index_spec in db_model.SCHEMA_INDEX_SPECS:
        if index_spec.table in {"transactions", "reconciliation_groups", "reconciliation_matches", "schema_version"}:
            conn.execute(db_model._build_create_index_sql(index_spec))


MIGRATIONS: dict[int, MigrationFn] = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
    4: _migrate_v4_to_v5,
}


def get_current_schema_version() -> int:
    """Return get current schema version."""
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
