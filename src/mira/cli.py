# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Command-line utilities for MIRA maintenance tasks."""

from __future__ import annotations

import argparse
import importlib
from importlib import metadata
from pathlib import Path
import sys

from mira.db.database import Database
from mira.db.errors import DatabaseSchemaError
from mira.db.helpers import default_db_path_for_display


def _build_parser() -> argparse.ArgumentParser:
    """Return build parser."""
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
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the installed MIRA package version.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run a dependency import check for headless/package verification.",
    )

    subparsers = parser.add_subparsers(dest="command")

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


def _resolve_installed_version() -> str:
    """Return resolve installed version."""
    for package_name in ("mira-personal-finance-assistant", "mira"):
        try:
            return metadata.version(package_name)
        except metadata.PackageNotFoundError:
            continue
    return "unknown"


def _run_import_check() -> int:
    """Return run import check."""
    modules_to_probe = (
        "mira",
        "mira.db.database",
        "PySide6",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "qt_material",
    )
    open_gl_modules = ("PySide6.QtWidgets", "PySide6.QtCharts")
    failures: list[tuple[str, str]] = []
    opengl_failures: list[tuple[str, str]] = []

    for module_name in modules_to_probe:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - exercised through CLI tests
            failures.append((module_name, str(exc)))

    for module_name in open_gl_modules:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - exercised through CLI tests
            opengl_failures.append((module_name, str(exc)))

    if not failures and not opengl_failures:
        print("Check OK: all required modules imported correctly.")
        return 0

    if failures:
        for module_name, error in failures:
            print(f"Check FAIL: cannot import {module_name}: {error}", file=sys.stderr)

    if opengl_failures:
        for module_name, error in opengl_failures:
            print(f"Check FAIL: OpenGL/Qt import failed in {module_name}: {error}", file=sys.stderr)
        print(
            "Recommendation: verify graphics dependencies (Qt/PySide6/OpenGL/EGL) in the target environment.",
            file=sys.stderr,
        )

    return 1


def _open_database(path: str | None) -> Database:
    """Return open database."""
    db = Database(path=path)
    try:
        db.connect()
    except DatabaseSchemaError as exc:
        raise SystemExit(f"Error: {exc}") from exc
    return db


def main(argv: list[str] | None = None) -> int:
    """Return main."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(_resolve_installed_version())
        return 0

    if args.check:
        return _run_import_check()

    if args.command is None:
        parser.error("A command is required unless --version or --check is used.")
        return 2

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
