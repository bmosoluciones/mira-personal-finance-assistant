# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from itertools import count
from pathlib import Path
from typing import Any

import pytest

from mira import cli as cli_module
from mira.db import migrations as db_migrations
from mira.db.database import Database
from tests.db_inspection import fetch_all_dicts, fetch_one_dict


@dataclass(frozen=True)
class SeedSnapshot:
    db_path: Path
    result: dict[str, Any]


def _set_user_version(path: Path, version: int) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()


def _create_legacy_float_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                balance REAL DEFAULT 0.0,
                account_type TEXT DEFAULT 'bank',
                currency TEXT DEFAULT 'USD',
                is_default INTEGER DEFAULT 0,
                created_at TEXT
            )
            """
        )
        conn.commit()


def _build_seed_ready_snapshot(path: Path, *, language: str) -> Path:
    db = Database(path=path)
    db.connect()
    try:
        db.setting.set("language", language)
        db.setting.seed_initial_data(include_default_categories=True, account_names=[], language=language)
    finally:
        db.close()
    return path


def _build_seed_demo_snapshot(
    path: Path,
    *,
    language: str,
    reference_date: date,
    prepare_seed_ready: bool = False,
    before_seed: Callable[[Database], None] | None = None,
) -> SeedSnapshot:
    db = Database(path=path)
    db.connect()
    try:
        db.setting.set("language", language)
        if prepare_seed_ready:
            db.setting.seed_initial_data(include_default_categories=True, account_names=[], language=language)
        if before_seed is not None:
            before_seed(db)
        result = db.setting.seed_demo_data(reference_date=reference_date)
    finally:
        db.close()
    return SeedSnapshot(db_path=path, result=result)


def _database_from_template(template_path: Path, path: Path) -> Database:
    shutil.copy2(template_path, path)
    db = Database(path=path)
    db.connect()
    return db


@pytest.fixture(scope="module")
def seed_ready_en_snapshot(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("cli-ready-en") / "seed_ready_en.db"
    return _build_seed_ready_snapshot(path, language="en")


@pytest.fixture(scope="module")
def seeded_demo_en_snapshot(tmp_path_factory: pytest.TempPathFactory) -> SeedSnapshot:
    path = tmp_path_factory.mktemp("cli-seed-en") / "seed_demo_en.db"
    return _build_seed_demo_snapshot(
        path,
        language="en",
        reference_date=date(2026, 3, 17),
        prepare_seed_ready=True,
    )


@pytest.mark.full
def test_seed_demo_data_populates_current_year_budget_and_transactions(
    tmp_path: Path,
    seeded_demo_en_snapshot: SeedSnapshot,
) -> None:
    db = _database_from_template(seeded_demo_en_snapshot.db_path, tmp_path / "seed.db")
    try:
        result = seeded_demo_en_snapshot.result

        assert result["year"] == 2026
        assert result["budget_code"] == "mira_cli_seed_2026"
        assert result["transactions_created"] > 100
        assert db.setting.get("active_budget_code") == "mira_cli_seed_2026"

        budget = db.budget.find_by_code("mira_cli_seed_2026")
        assert budget is not None

        periods = [
            str(row["period"])
            for row in fetch_all_dicts(
                db,
                """
                SELECT DISTINCT substr(date, 1, 7) AS period
                FROM transactions
                WHERE note = ?
                ORDER BY period
                """,
                ("mira_cli_seed:2026",),
            )
        ]
        monthly_counts = {
            str(row["period"]): int(row["total"])
            for row in fetch_all_dicts(
                db,
                """
                SELECT substr(date, 1, 7) AS period, COUNT(*) AS total
                FROM transactions
                WHERE note = ?
                GROUP BY period
                ORDER BY period
                """,
                ("mira_cli_seed:2026",),
            )
        }

        assert periods == [f"2026-{month:02d}" for month in range(1, 13)]
        assert all(monthly_counts[f"2026-{month:02d}"] >= 20 for month in range(1, 13))

        june_payload = db.report.get_mira_master_report(year=2026, month=6)
        deficit_payload = db.report.get_mira_master_report(year=2026, month=2)
        assert june_payload["budget"]["has_budget"] is True
        assert june_payload["kpis"]["income"] > 0
        assert june_payload["kpis"]["expense_operational"] > 0
        assert june_payload["kpis"]["net"] > 0
        assert june_payload["allocation"]["top_tags"]
        assert deficit_payload["kpis"]["net"] < 0
        goals = db.savings_goal.list()
        assert len(goals) >= 3
        assert any(float(goal["current_amount"]) > 0 for goal in goals)
    finally:
        db.close()


@pytest.mark.full
def test_seed_demo_data_replaces_previous_seed_artifacts_without_duplicate_budget(
    tmp_path: Path,
    seed_ready_en_snapshot: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _database_from_template(seed_ready_en_snapshot, tmp_path / "repeatable.db")
    try:
        original_add_transaction = db._backend.add_transaction
        fake_tx_ids = count(10_000)

        def _fast_add_transaction(**_: Any) -> dict[str, Any]:
            return {"id": next(fake_tx_ids)}

        monkeypatch.setattr(db._backend, "add_transaction", _fast_add_transaction)
        monkeypatch.setattr(db._backend, "upsert_budget_amount", lambda *args, **kwargs: None)
        monkeypatch.setattr(db._backend, "add_transaction_tag", lambda *args, **kwargs: None)
        monkeypatch.setattr(db._backend, "transfer_between_accounts", lambda *args, **kwargs: None)

        first = db.setting.seed_demo_data(reference_date=date(2026, 1, 5))

        account = db.account.get_default()
        salary = db.category.find_by_name("Net Salary (Payroll)", "income")
        assert account is not None
        assert salary is not None

        original_add_transaction(
            account_id=int(account["id"]),
            tx_type="income",
            amount=1.0,
            category=str(salary["name"]),
            category_id=int(salary["id"]),
            description="legacy seed tx a",
            tx_date="2026-01-02",
            note="mira_cli_seed:2026",
        )
        original_add_transaction(
            account_id=int(account["id"]),
            tx_type="income",
            amount=2.0,
            category=str(salary["name"]),
            category_id=int(salary["id"]),
            description="legacy seed tx b",
            tx_date="2026-01-03",
            note="mira_cli_seed:2026",
        )

        tx_total_before = int(
            fetch_one_dict(db, "SELECT COUNT(*) AS total FROM transactions WHERE note = ?", ("mira_cli_seed:2026",))[
                "total"
            ]
        )
        assert tx_total_before == 2

        second = db.setting.seed_demo_data(reference_date=date(2026, 8, 9))

        tx_total_after = int(
            fetch_one_dict(db, "SELECT COUNT(*) AS total FROM transactions WHERE note = ?", ("mira_cli_seed:2026",))[
                "total"
            ]
        )
        budget_total = int(
            fetch_one_dict(db, "SELECT COUNT(*) AS total FROM budget_master WHERE code = ?", ("mira_cli_seed_2026",))[
                "total"
            ]
        )
        goals_total = int(fetch_one_dict(db, "SELECT COUNT(*) AS total FROM savings_goals")["total"])

        assert first["transactions_created"] > 100
        assert second["transactions_created"] == first["transactions_created"]
        assert tx_total_after == 0
        assert budget_total == 1
        assert goals_total >= 3
    finally:
        db.close()


@pytest.mark.full
def test_cli_seed_command_reports_completion_summary(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "cli_seed.db"
    calls: list[date | None] = []

    def _fake_seed_demo_data(self, *, reference_date: date | None = None) -> dict[str, Any]:
        calls.append(reference_date)
        return {
            "year": 2026,
            "budget_code": "mira_cli_seed_2026",
            "transactions_created": 123,
            "tag_links_created": 456,
        }

    monkeypatch.setattr("mira.db.database.SettingFacade.seed_demo_data", _fake_seed_demo_data)

    exit_code = cli_module.main(["--db", str(db_path), "seed"])

    assert calls == [None]
    assert exit_code == 0
    assert db_path.is_file()
    assert capsys.readouterr().out.strip() == (
        "Seed completed: year=2026, budget=mira_cli_seed_2026, transactions=123, tag_links=456"
    )


@pytest.mark.full
def test_seed_initial_data_backfills_new_catalog_on_legacy_database(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_seed.db"
    db = Database(path=db_path)
    db.connect()
    try:
        db.setting.set("language", "en")
        db.category.create("Primary salary", "income")
        db.category.create("Freelance / Business", "income")
        db.category.create("Savings", "expense", is_savings=True)

        db.setting.seed_initial_data(
            include_default_categories=True,
            language="en",
            update_existing_category_metadata=False,
        )

        assert db.category.find_by_name("Net Salary (Payroll)", "income") is not None
        assert db.category.find_by_name("Freelance Fees", "income") is not None
        assert db.category.find_by_name("Emergency Fund", "expense") is not None
    finally:
        db.close()


@pytest.mark.full
def test_seed_initial_data_does_not_overwrite_existing_category_customizations(tmp_path: Path) -> None:
    db_path = tmp_path / "customized_seed.db"
    db = Database(path=db_path)
    db.connect()
    try:
        db.setting.set("language", "en")
        savings = db.category.create("Savings", "expense", color="#123456", icon="diamond", is_savings=True)

        db.setting.seed_initial_data(
            include_default_categories=True,
            language="en",
            update_existing_category_metadata=False,
        )

        refreshed = db.category.get(int(savings["id"]))
        assert refreshed is not None
        assert refreshed["color"] == "#123456"
        assert refreshed["icon"] == "diamond"
        assert refreshed["parent_id"] is None
    finally:
        db.close()


@pytest.mark.full
def test_seed_demo_data_clamps_february_savings_date_and_uses_emergency_description(
    tmp_path: Path,
    seeded_demo_en_snapshot: SeedSnapshot,
) -> None:
    db = _database_from_template(seeded_demo_en_snapshot.db_path, tmp_path / "february_seed.db")
    try:
        savings_rows = fetch_all_dicts(
            db,
            """
            SELECT date, description
            FROM transactions
            WHERE note = ? AND category = ?
            ORDER BY date
            """,
            ("mira_cli_seed:2026", "Savings"),
        )
        emergency_descriptions = [
            str(row["description"])
            for row in fetch_all_dicts(
                db,
                """
                SELECT description
                FROM transactions
                WHERE note = ? AND category = ?
                ORDER BY date
                """,
                ("mira_cli_seed:2026", "Emergency Fund"),
            )
        ]

        assert "2026-02-28" in {str(row["date"]) for row in savings_rows}
        assert "2026-02-29" not in {str(row["date"]) for row in savings_rows}
        assert emergency_descriptions
        assert all(description == "Emergency fund contribution" for description in emergency_descriptions)
    finally:
        db.close()


def test_cli_backup_and_restore_commands(tmp_path: Path) -> None:
    db_path = tmp_path / "cli_backup.db"
    backup_path = tmp_path / "cli_backup_copy.db"

    db = Database(path=db_path)
    db.connect()
    account = db.account.get_or_create("General")
    db.transaction.create(account_id=int(account["id"]), tx_type="income", amount=500.0, description="Original income")
    db.close()

    backup_exit = cli_module.main(["--db", str(db_path), "backup", "--output-file", str(backup_path)])
    assert backup_exit == 0
    assert backup_path.is_file()

    db = Database(path=db_path)
    db.connect()
    account = db.account.get_or_create("General")
    db.transaction.create(account_id=int(account["id"]), tx_type="expense", amount=50.0, description="Post backup")
    db.close()

    restore_exit = cli_module.main(["--db", str(db_path), "restore", "--input-file", str(backup_path)])
    assert restore_exit == 0

    db = Database(path=db_path)
    db.connect()
    transactions = db.transaction.list(limit=10)
    db.close()

    assert len(transactions) == 1
    assert transactions[0]["description"] == "Original income"


def test_cli_restore_reports_schema_upgrade(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "cli_restore_target.db"
    backup_path = tmp_path / "cli_restore_migratable.db"

    backup_db = Database(path=backup_path)
    backup_db.connect()
    try:
        account = backup_db.account.get_or_create("General")
        backup_db.transaction.create(
            account_id=int(account["id"]),
            tx_type="income",
            amount=700.0,
            description="Migrated CLI income",
        )
    finally:
        backup_db.close()
    _set_user_version(backup_path, 1)

    applied: list[int] = []

    def _migration(conn: sqlite3.Connection) -> None:
        applied.append(1)
        conn.execute("CREATE TABLE IF NOT EXISTS cli_restore_probe (id INTEGER PRIMARY KEY AUTOINCREMENT)")

    monkeypatch.setattr(db_migrations, "MIN_MIGRATABLE_SCHEMA_VERSION", 1)
    monkeypatch.setattr(db_migrations, "MIGRATIONS", {1: _migration})

    restore_exit = cli_module.main(["--db", str(db_path), "restore", "--input-file", str(backup_path)])
    captured = capsys.readouterr()

    assert restore_exit == 0
    assert "schema upgraded v1 -> v2" in captured.out
    assert applied == [1]

    db = Database(path=db_path)
    db.connect()
    try:
        transactions = db.transaction.list(limit=10)
    finally:
        db.close()

    assert len(transactions) == 1
    assert transactions[0]["description"] == "Migrated CLI income"


def test_cli_restore_rejects_legacy_backup(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "cli_restore_target_legacy.db"
    legacy_backup = tmp_path / "legacy_restore_backup.db"
    _create_legacy_float_database(legacy_backup)

    restore_exit = cli_module.main(["--db", str(db_path), "restore", "--input-file", str(legacy_backup)])
    captured = capsys.readouterr()

    assert restore_exit == 2
    assert "Pre-0.0.1a2 backups remain unsupported" in captured.err


def test_cli_version_uses_importlib_metadata(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli_module.metadata, "version", lambda _name: "9.9.9")

    exit_code = cli_module.main(["--version"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == "9.9.9"


def test_cli_check_reports_success(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli_module.importlib, "import_module", lambda _name: object())

    exit_code = cli_module.main(["--check"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Check OK: all required modules imported correctly." in captured.out
    assert captured.err == ""


def test_cli_check_reports_qt_opengl_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failing_modules = {"PySide6.QtWidgets", "PySide6.QtCharts"}
    original_import = cli_module.importlib.import_module

    def _fake_import(name: str) -> Any:
        if name in failing_modules:
            raise ImportError(f"{name} missing graphics backend")
        return original_import("sys")

    monkeypatch.setattr(cli_module.importlib, "import_module", _fake_import)

    exit_code = cli_module.main(["--check"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "OpenGL/Qt import failed" in captured.err
    assert "verify graphics dependencies" in captured.err
