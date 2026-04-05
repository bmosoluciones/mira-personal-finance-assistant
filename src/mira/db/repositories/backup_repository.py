# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING

from mira.db import migrations as db_migrations
from mira.db.errors import DatabaseSchemaError
from mira.db.model import inspect_database_schema_details


@dataclass(frozen=True)
class RestoreResult:
    restored_from: Path
    source_schema_version: int | None
    target_schema_version: int
    migration_applied: bool = False


def _cleanup_sqlite_sidecars(path: Path) -> None:
    for candidate in (
        path.with_name(f"{path.name}-wal"),
        path.with_name(f"{path.name}-shm"),
    ):
        if candidate.exists():
            candidate.unlink()


class BackupRepository:
    if TYPE_CHECKING:
        path: Path

        def _require_connection(self) -> sqlite3.Connection: ...
        def close(self) -> None: ...
        def connect(self) -> None: ...

    def create_backup(self, filepath: str | Path) -> Path:
        """Create a full SQLite backup of the current database file."""
        conn = self._require_connection()
        target = Path(filepath).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.resolve() == self.path.resolve():
            raise ValueError("Select a different file path for the backup.")

        conn.commit()
        dest = sqlite3.connect(str(target))
        try:
            conn.backup(dest)
            dest.commit()
        finally:
            dest.close()
        return target

    def restore(self, filepath: str | Path) -> RestoreResult:
        """Restore database content from another SQLite file."""
        self._require_connection()
        source = Path(filepath).expanduser()
        if not source.exists():
            raise FileNotFoundError(f"Backup file not found: {source}")

        target_version = db_migrations.get_current_schema_version()
        inspection = inspect_database_schema_details(
            source,
            current_version=target_version,
            min_migratable_version=db_migrations.MIN_MIGRATABLE_SCHEMA_VERSION,
        )
        if inspection.status == "legacy":
            version = inspection.user_version if inspection.user_version is not None else "unknown"
            raise DatabaseSchemaError(
                f"The selected backup uses unsupported schema version {version} and cannot be restored in place. "
                "Pre-0.0.1a2 backups remain unsupported."
            )
        if inspection.status != "current" and inspection.status != "migratable":
            detail = f" {inspection.error}" if inspection.error else ""
            raise DatabaseSchemaError(f"The selected backup is not a valid MIRA backup for this version.{detail}")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, staging_name = tempfile.mkstemp(
            prefix=f"{self.path.stem}.restore-", suffix=".db", dir=str(self.path.parent)
        )
        os.close(fd)
        staging_path = Path(staging_name)
        migration_applied = False

        try:
            src = sqlite3.connect(str(source))
            staging = sqlite3.connect(str(staging_path))
            try:
                src.backup(staging)
                staging.commit()
            finally:
                staging.close()
                src.close()

            staging = sqlite3.connect(str(staging_path))
            try:
                if inspection.status == "migratable":
                    migration_applied = db_migrations.migrate_database(
                        staging,
                        int(inspection.user_version or 0),
                        target_version,
                    )
                # Normalize the staged file into a self-contained main database
                # before swapping it into place so reconnect does not depend on
                # staging-side WAL/SHM artifacts.
                staging.execute("PRAGMA wal_checkpoint(FULL)")
                staging.execute("PRAGMA journal_mode=DELETE")
                staging.commit()
            finally:
                staging.close()

            staged_inspection = inspect_database_schema_details(
                staging_path,
                current_version=target_version,
                min_migratable_version=db_migrations.MIN_MIGRATABLE_SCHEMA_VERSION,
            )
            if staged_inspection.status != "current":
                raise DatabaseSchemaError("The selected backup could not be upgraded to the current MIRA schema.")

            self.close()
            _cleanup_sqlite_sidecars(self.path)
            os.replace(staging_path, self.path)
            self.connect()
            return RestoreResult(
                restored_from=source,
                source_schema_version=inspection.user_version,
                target_schema_version=target_version,
                migration_applied=migration_applied,
            )
        finally:
            _cleanup_sqlite_sidecars(staging_path)
            if staging_path.exists():
                staging_path.unlink()
