# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Command-line utilities for MIRA maintenance tasks."""

from __future__ import annotations

import argparse
import importlib
import sys
from importlib import metadata
from pathlib import Path

from mira.ai.llm_config import mcp_enabled
from mira.cli_commands import add_movement, dump, list_transactions, record_text, report_summary, transfer
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
        help="Run a headless dependency import check. Does not import Qt.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )
    parser.add_argument("--require-mcp-consent", action="store_true", help=argparse.SUPPRESS)

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

    def _movement(name: str, help_text: str) -> None:
        movement = subparsers.add_parser(name, help=help_text)
        movement_sub = movement.add_subparsers(dest="movement_command")
        add = movement_sub.add_parser("add", help=f"Record a {name}.")
        add.add_argument("--amount", required=True)
        add.add_argument("--account", required=True)
        add.add_argument("--description", default=None)
        add.add_argument("--category", default=None)
        add.add_argument("--date", dest="tx_date", default=None)
        add.add_argument("--note", default=None)

    _movement("income", "Record income.")
    _movement("expense", "Record an expense.")

    transfer_parser = subparsers.add_parser("transfer", help="Transfer money between accounts.")
    transfer_parser.add_argument("--from", dest="source", required=True)
    transfer_parser.add_argument("--to", dest="target", required=True)
    transfer_parser.add_argument("--amount", required=True)
    transfer_parser.add_argument("--date", dest="tx_date", default=None)
    transfer_parser.add_argument("--note", default=None)

    transactions = subparsers.add_parser("transactions", help="List transactions.")
    transactions_sub = transactions.add_subparsers(dest="transactions_command")
    listing = transactions_sub.add_parser("list", help="List transactions.")
    listing.add_argument("--limit", type=int, default=50)
    listing.add_argument("--account", default=None)
    listing.add_argument("--since", default=None)
    listing.add_argument("--until", default=None)

    report_parser = subparsers.add_parser("report", help="Print a local summary.")
    report_parser.add_argument("--since", default=None)

    record_parser = subparsers.add_parser("record", help="Record a transaction with the local parser.")
    record_parser.add_argument("text")

    subparsers.add_parser("mcp", help="Expose finance commands over MCP stdio. Requires prior consent.")
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
    """Probe headless modules. Qt is not a mira-cli dependency."""
    modules_to_probe = (
        "mira",
        "mira.db.database",
        "mira.i18n",
        "openpyxl",
        "peewee",
    )
    failures: list[tuple[str, str]] = []

    for module_name in modules_to_probe:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - exercised through CLI tests
            failures.append((module_name, str(exc)))

    if not failures:
        print("Check OK: headless modules imported correctly.")
        return 0

    for module_name, error in failures:
        print(f"Check FAIL: cannot import {module_name}: {error}", file=sys.stderr)
    return 1


def _open_database(path: str | None) -> Database:
    """Return open database."""
    db = Database(path=path)
    try:
        db.connect()
    except DatabaseSchemaError as exc:
        raise SystemExit(f"Error: {exc}") from exc
    return db


def _dispatch_finance_command(args: argparse.Namespace, db: Database) -> int | None:
    """Run finance commands. Return None when the command is not one of them."""
    if args.command in {"income", "expense"}:
        if getattr(args, "movement_command", None) != "add":
            raise ValueError(f"{args.command} requires the add subcommand.")
        payload = add_movement(
            db,
            kind="add_income" if args.command == "income" else "add_expense",
            amount=args.amount,
            account=args.account,
            description=args.description,
            category=args.category,
            tx_date=args.tx_date,
            note=args.note,
        )
        print(dump(payload, as_json=args.json))
        return 0

    if args.command == "transfer":
        payload = transfer(
            db,
            source=args.source,
            target=args.target,
            amount=args.amount,
            tx_date=args.tx_date,
            note=args.note,
        )
        print(dump(payload, as_json=args.json))
        return 0

    if args.command == "transactions":
        if getattr(args, "transactions_command", None) != "list":
            raise ValueError("transactions requires the list subcommand.")
        payload = list_transactions(
            db,
            limit=args.limit,
            account=args.account,
            since=args.since,
            until=args.until,
        )
        print(dump(payload, as_json=args.json))
        return 0

    if args.command == "report":
        print(dump(report_summary(db, since=args.since), as_json=args.json))
        return 0

    if args.command == "record":
        print(dump(record_text(db, args.text), as_json=args.json))
        return 0

    if args.command == "mcp":
        if not mcp_enabled(db):
            print(
                "MCP is off. Enable it in Settings and accept that a client can read, "
                "modify, and forward your finances to a third party.",
                file=sys.stderr,
            )
            return 2
        db_path = str(db.path)
        db.close()
        from mira.mcp_server import serve_stdio

        return serve_stdio(db_path)
    return None


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
        if args.require_mcp_consent and not mcp_enabled(db):
            print(
                "MCP is disabled or its consent has been revoked. Enable it in Settings and accept the notice.",
                file=sys.stderr,
            )
            return 2

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

        try:
            handled = _dispatch_finance_command(args, db)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if handled is not None:
            return handled

        parser.error(f"Unsupported command: {args.command}")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
