# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Command-line utilities for MIRA maintenance tasks."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from mira.db.database import Database
from mira.db.errors import DatabaseSchemaError
from mira.db.helpers import default_db_path_for_display


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mira-cli",
        description="Maintenance commands for MIRA databases.",
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        default=None,
        help=f"Path to the SQLite database file. Defaults to {default_db_path_for_display()}.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup", help="Create a SQLite backup of the current database.")
    backup_parser.add_argument(
        "--output-file",
        "--outpu-file",
        dest="output_file",
        required=True,
        metavar="PATH",
        help="Destination path for the backup database file.",
    )

    restore_parser = subparsers.add_parser("restore", help="Restore the current database from a backup file.")
    restore_parser.add_argument(
        "--input-file",
        dest="input_file",
        required=True,
        metavar="PATH",
        help="Source path for the backup database file.",
    )

    subparsers.add_parser(
        "seed",
        help="Populate the current-year database with demo budget and transactions.",
    )
    return parser


def _open_database(path: str | None) -> Database:
    db = Database(path=path)
    try:
        db.connect()
    except DatabaseSchemaError as exc:
        raise SystemExit(f"Error: {exc}") from exc
    return db


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    db = _open_database(args.db)
    try:
        if args.command == "backup":
            backup_path = db.backup.create(Path(args.output_file))
            print(f"Backup created: {backup_path}")
            return 0

        if args.command == "restore":
            try:
                restored = db.backup.restore(Path(args.input_file))
            except (DatabaseSchemaError, FileNotFoundError) as exc:
                print(f"Restore error: {exc}", file=sys.stderr)
                return 2
            if restored.migration_applied:
                print(
                    "Backup restored from: "
                    f"{restored.restored_from} "
                    f"(schema upgraded v{restored.source_schema_version} -> v{restored.target_schema_version})"
                )
            else:
                print(f"Backup restored from: {restored.restored_from}")
            return 0

        if args.command == "seed":
            seed_result = db.setting.seed_demo_data()
            print(
                "Seed completed: "
                f"year={seed_result['year']}, "
                f"budget={seed_result['budget_code']}, "
                f"transactions={seed_result['transactions_created']}, "
                f"tag_links={seed_result['tag_links_created']}"
            )
            return 0

        parser.error(f"Unsupported command: {args.command}")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
