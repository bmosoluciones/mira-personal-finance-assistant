# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from peewee import SqliteDatabase

from mira.db import migrations as db_migrations
from mira.db import bootstrap as db_bootstrap
from mira.db.errors import DatabaseSchemaError
from mira.db.helpers import get_default_db_path
from mira.db.model import bind_database, create_peewee_database, initialize_schema, inspect_database_schema_details
from mira.db.money import cents_to_decimal, cents_to_money, money_to_cents, money_to_decimal, round_money


class _ActiveDatabaseGuard:
    """Process-wide guard for the globally bound Peewee proxy."""

    _active_owner_id: int | None = None

    @classmethod
    def acquire(cls, owner: object) -> None:
        owner_id = id(owner)
        if cls._active_owner_id is not None and cls._active_owner_id != owner_id:
            raise RuntimeError("Only one Database instance can be connected at a time in this process.")
        cls._active_owner_id = owner_id

    @classmethod
    def release(cls, owner: object) -> None:
        if cls._active_owner_id == id(owner):
            cls._active_owner_id = None

    @classmethod
    def reset_for_tests(cls) -> None:
        cls._active_owner_id = None


def reset_active_database_guard_for_tests() -> None:
    """Reset the process-wide database guard for test isolation."""
    _ActiveDatabaseGuard.reset_for_tests()


class DatabaseRuntime:
    """Owns the shared Peewee/sqlite runtime for repository mixins."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else get_default_db_path()
        self._database: SqliteDatabase | None = None
        self._connection: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Open the database connection and initialise the schema."""
        _ActiveDatabaseGuard.acquire(self)
        if self._database is not None and not self._database.is_closed():
            return
        target_version = db_migrations.get_current_schema_version()
        inspection = inspect_database_schema_details(
            self.path,
            current_version=target_version,
            min_migratable_version=db_migrations.MIN_MIGRATABLE_SCHEMA_VERSION,
        )
        if inspection.status == "legacy":
            version = inspection.user_version if inspection.user_version is not None else "unknown"
            raise DatabaseSchemaError(
                f"Database schema version {version} is not supported for in-place migration. "
                "Pre-0.0.1a2 databases remain unsupported."
            )
        if inspection.status == "invalid":
            detail = f" {inspection.error}" if inspection.error else ""
            raise DatabaseSchemaError(f"The selected database file is not a valid MIRA database.{detail}")
        self._database = create_peewee_database(str(self.path))
        bind_database(self._database)
        try:
            self._database.connect(reuse_if_open=True)
            self._connection = self._database.connection()
            self._connection.row_factory = sqlite3.Row
            if inspection.status == "migratable":
                db_migrations.migrate_database(self._connection, int(inspection.user_version or 0), target_version)
            self._init_schema()
        except Exception:
            self._close_handles()
            _ActiveDatabaseGuard.release(self)
            raise

    def close(self) -> None:
        """Close the database connection."""
        try:
            self._close_handles()
        finally:
            _ActiveDatabaseGuard.release(self)

    def _close_handles(self) -> None:
        database = self._database
        connection = self._connection
        try:
            if database is not None and not database.is_closed():
                database.close()
        finally:
            if connection is not None:
                try:
                    connection.close()
                except sqlite3.Error:
                    pass
            self._database = None
            self._connection = None

    @contextmanager
    def _atomic(self) -> Generator[SqliteDatabase, None, None]:
        database = self._require_db()
        with database.atomic():
            yield database

    def _require_db(self) -> SqliteDatabase:
        database = self._database
        if database is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        return database

    def _require_connection(self) -> sqlite3.Connection:
        connection = self._connection
        if connection is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        return connection

    @staticmethod
    def _money_to_cents(value: object, *, allow_none: bool = False) -> int | None:
        return money_to_cents(value, allow_none=allow_none)

    @staticmethod
    def _money_to_decimal(value: object, *, allow_none: bool = False):
        return money_to_decimal(value, allow_none=allow_none)

    @staticmethod
    def _round_money(value: object):
        return round_money(value)

    @staticmethod
    def _cents_to_decimal(value: object, *, allow_none: bool = False):
        return cents_to_decimal(value, allow_none=allow_none)

    @staticmethod
    def _cents_to_money(value: object, *, allow_none: bool = False):
        # Compatibility shim for older repository code; prefer `_cents_to_decimal`.
        return cents_to_decimal(value, allow_none=allow_none)

    @staticmethod
    def _money_to_display_float(value: object, *, allow_none: bool = False) -> float | None:
        return cents_to_money(money_to_cents(value, allow_none=allow_none), allow_none=allow_none)

    def _init_schema(self) -> None:
        database = self._require_db()
        initialize_schema(database)
        db_bootstrap.seed_currencies()
        db_bootstrap.seed_default_settings()
        db_bootstrap.seed_default_account()
