# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tests for the database layer."""

from __future__ import annotations

import csv
import sqlite3
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

import pytest
from openpyxl import load_workbook

from mira.db import migrations as db_migrations
from mira.db.database import Database
from mira.db.errors import (
    BudgetValidationError,
    DatabaseSchemaError,
    DuplicateBudgetCodeError,
    DuplicateCategoryNameError,
    DuplicateTagNameError,
)
from mira.db.model import SCHEMA_VERSION, Setting, inspect_database_schema
from mira.db.repositories import tag_repository as tag_repository_module
from tests.db_inspection import (
    backend_connection_state,
    break_backend_connection_for_test,
    fetch_all_dicts,
    fetch_scalar,
)


@pytest.fixture
def db(tmp_path):
    """Return an in-memory (tmp file) database for isolated testing."""
    d = Database(path=tmp_path / "test.db")
    d.connect()
    yield d
    d.close()


_CENT = Decimal("0.01")


def _money(value: object) -> Decimal:
    if isinstance(value, Decimal):
        amount = value
    else:
        amount = Decimal(str(value))
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)


def _assert_money(actual: object, expected: object) -> None:
    assert _money(actual) == _money(expected)


def test_default_db_path_is_resolved_before_connect_attempt(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    expected_path = tmp_path / "resolved-before-connect.db"

    def _fake_get_default_db_path():
        calls.append("resolved")
        return expected_path

    def _fake_create_peewee_database(_path: str):
        calls.append("connect")
        raise RuntimeError("stop")

    monkeypatch.setattr("mira.db.runtime.get_default_db_path", _fake_get_default_db_path)
    monkeypatch.setattr("mira.db.runtime.create_peewee_database", _fake_create_peewee_database)

    database = Database()

    assert database.path == expected_path
    assert calls == ["resolved"]

    with pytest.raises(RuntimeError, match="stop"):
        database.connect()

    assert calls == ["resolved", "connect"]


def test_init_schema_requires_connected_database(tmp_path) -> None:
    database = Database(path=tmp_path / "not-connected.db")
    with pytest.raises(RuntimeError, match="Database is not connected"):
        database._backend._init_schema()


def test_connect_cleans_internal_state_on_unexpected_init_failure(monkeypatch, tmp_path) -> None:
    database = Database(path=tmp_path / "init-fails.db")

    def _fail_init_schema() -> None:
        raise TypeError("unexpected init failure")

    monkeypatch.setattr(database._backend, "_init_schema", _fail_init_schema)

    with pytest.raises(TypeError, match="unexpected init failure"):
        database.connect()

    assert backend_connection_state(database) == (True, True)


def test_atomic_rolls_back_on_unexpected_exception(db) -> None:
    assert not hasattr(db._backend, "_cursor")

    with pytest.raises(TypeError, match="force rollback"):
        with db._backend._atomic():
            Setting.insert(key="__rollback_test_key__", value="temp").execute()
            raise TypeError("force rollback")

    assert db.setting.get("__rollback_test_key__") is None


def _create_legacy_float_database(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                balance REAL DEFAULT 0.0,
                account_type TEXT DEFAULT 'bank',
                currency TEXT DEFAULT 'USD',
                is_default INTEGER DEFAULT 0,
                created_at TEXT
            )
            """)
        conn.commit()


def _create_non_mira_sqlite_database(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL)")
        conn.execute("INSERT INTO notes (body) VALUES ('not a mira backup')")
        conn.commit()


def _create_current_schema_database(path) -> None:
    database = Database(path=path)
    database.connect()
    database.close()


def _set_user_version(path, version: int) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()


def test_connect_rejects_explicit_legacy_float_database_without_replacing_file(tmp_path) -> None:
    path = tmp_path / "legacy-money.db"
    _create_legacy_float_database(path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO accounts (name, balance, account_type, currency, is_default, created_at) "
            "VALUES ('legacy account', 123.45, 'bank', 'USD', 0, '2026-04-02T00:00:00')"
        )
        conn.commit()

    database = Database(path=path)
    with pytest.raises(DatabaseSchemaError, match="Pre-0.0.1a2 databases remain unsupported"):
        database.connect()

    assert inspect_database_schema(path) == "legacy"
    with sqlite3.connect(path) as conn:
        rows = conn.execute("SELECT name FROM accounts").fetchall()
    assert {str(row[0]) for row in rows} == {"legacy account"}


def test_default_path_rejects_legacy_float_database_without_archiving(monkeypatch, tmp_path) -> None:
    path = tmp_path / "xdg-data" / "mira" / "mira.db"
    _create_legacy_float_database(path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO accounts (name, balance, account_type, currency, is_default, created_at) "
            "VALUES ('legacy account', 123.45, 'bank', 'USD', 0, '2026-04-02T00:00:00')"
        )
        conn.commit()
    monkeypatch.setattr("mira.db.runtime.get_default_db_path", lambda: path)

    database = Database()
    with pytest.raises(DatabaseSchemaError, match="Pre-0.0.1a2 databases remain unsupported"):
        database.connect()

    assert inspect_database_schema(path) == "legacy"
    assert not (path.parent / "legacy").exists()
    with sqlite3.connect(path) as conn:
        rows = conn.execute("SELECT name FROM accounts").fetchall()
    assert {str(row[0]) for row in rows} == {"legacy account"}


def test_connect_current_schema_does_not_invoke_migrations(monkeypatch, tmp_path) -> None:
    path = tmp_path / "current.db"
    _create_current_schema_database(path)

    def _unexpected_migration(_conn: sqlite3.Connection, _from_version: int, _to_version: int | None = None) -> bool:
        raise AssertionError("migrate_database should not run for the current schema")

    monkeypatch.setattr(db_migrations, "migrate_database", _unexpected_migration)

    database = Database(path=path)
    database.connect()
    try:
        assert fetch_scalar(database, "PRAGMA user_version") == SCHEMA_VERSION
    finally:
        database.close()


def test_connect_runs_registered_migrations_for_supported_schema(monkeypatch, tmp_path) -> None:
    path = tmp_path / "migratable.db"
    _create_current_schema_database(path)
    _set_user_version(path, SCHEMA_VERSION - 1)
    applied: list[int] = []

    def _migration(conn: sqlite3.Connection) -> None:
        applied.append(1)
        conn.execute("CREATE TABLE IF NOT EXISTS migration_probe (id INTEGER PRIMARY KEY AUTOINCREMENT)")

    monkeypatch.setattr(db_migrations, "MIN_MIGRATABLE_SCHEMA_VERSION", SCHEMA_VERSION - 1)
    monkeypatch.setattr(db_migrations, "MIGRATIONS", {SCHEMA_VERSION - 1: _migration})

    database = Database(path=path)
    database.connect()
    try:
        assert applied == [1]
        assert fetch_scalar(database, "PRAGMA user_version") == SCHEMA_VERSION
        with sqlite3.connect(path) as conn:
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'migration_probe'"
                ).fetchall()
            }
        assert tables == {"migration_probe"}
    finally:
        database.close()


def test_connect_rejects_supported_schema_when_migration_step_is_missing(monkeypatch, tmp_path) -> None:
    path = tmp_path / "missing-migration.db"
    _create_current_schema_database(path)
    _set_user_version(path, SCHEMA_VERSION - 1)

    monkeypatch.setattr(db_migrations, "MIN_MIGRATABLE_SCHEMA_VERSION", SCHEMA_VERSION - 1)
    monkeypatch.setattr(db_migrations, "MIGRATIONS", {})

    database = Database(path=path)
    with pytest.raises(DatabaseSchemaError, match="No migration path exists"):
        database.connect()

    assert inspect_database_schema(path, min_migratable_version=SCHEMA_VERSION - 1) == "migratable"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class TestCurrencies:
    def test_americas_currencies_seeded(self, db):
        currencies = {c["code"] for c in db.setting.list_currencies(region="americas")}
        assert {"USD", "NIO", "MXN", "CAD", "ARS", "BRL", "CLP", "COP", "PEN"}.issubset(currencies)


class TestSettings:
    def test_default_username(self, db):
        assert db.setting.get("username") == "Usuario"

    def test_default_language(self, db):
        assert db.setting.get("language") == "en"

    def test_default_theme(self, db):
        assert db.setting.get("theme") == "dark_teal.xml"

    def test_set_and_get_setting(self, db):
        db.setting.set("username", "Alice")
        assert db.setting.get("username") == "Alice"

    def test_default_preferred_model_empty(self, db):
        assert db.setting.get("preferred_model") == ""

    def test_missing_key_returns_none(self, db):
        assert db.setting.get("nonexistent") is None


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


class TestAccounts:
    def test_add_account_canonicalizes_card_type_to_credit(self, db):
        acc = db.account.create("Visa", account_type="card", opening_balance=-250.0, currency="USD")
        assert acc["account_type"] == "credit"
        _assert_money(acc["balance"], -250.0)

    def test_reconnect_canonicalizes_legacy_card_accounts(self, tmp_path):
        path = tmp_path / "legacy_card.db"
        first = Database(path=path)
        first.connect()
        legacy = first.account.create("Legacy Visa", account_type="credit", opening_balance=-100.0, currency="USD")
        with sqlite3.connect(path) as conn:
            conn.execute(
                "UPDATE accounts SET account_type = 'card' WHERE id = ?",
                (legacy["id"],),
            )
            conn.commit()
        first.close()

        reopened = Database(path=path)
        reopened.connect()
        try:
            refreshed = reopened.account.find_by_name("Legacy Visa")
            assert refreshed is not None
            assert refreshed["account_type"] == "credit"
        finally:
            reopened.close()

    def test_add_account_raises_runtime_error_when_created_row_cannot_be_read(self, db, monkeypatch):
        original = db._backend.get_account_by_name

        def _missing_after_create(name: str):
            if name == "Cuenta inconsistente":
                return None
            return original(name)

        monkeypatch.setattr(db._backend, "get_account_by_name", _missing_after_create)

        with pytest.raises(RuntimeError, match="Failed to create account"):
            db.account.create(
                "Cuenta inconsistente",
                account_type="bank",
                opening_balance=1.0,
                currency="NIO",
            )

    def test_find_account_mentions_matches_real_accounts(self, db):
        bac = db.account.create("BAC Principal", account_type="bank", opening_balance=0.0, currency="NIO")
        visa = db.account.create(
            "Visa Platinum",
            account_type="credit",
            opening_balance=-50.0,
            currency="USD",
        )

        mentions = db.account.find_mentions("pague la visa platinum desde bac principal")

        assert [item["id"] for item in mentions] == [visa["id"], bac["id"]]

    def test_get_credit_accounts_and_is_credit_account(self, db):
        bank = db.account.create("Checking", account_type="bank", opening_balance=0.0, currency="USD")
        credit = db.account.create("Amex", account_type="credit", opening_balance=-10.0, currency="USD")

        credit_accounts = db.account.list_credit()

        assert [row["name"] for row in credit_accounts] == ["Amex"]
        assert db.account.is_credit(credit["id"]) is True
        assert db.account.is_credit(bank["id"]) is False

    def test_default_account_exists(self, db):
        accounts = db.account.list()
        names = [a["name"] for a in accounts]
        assert "General" in names

    def test_get_or_create_new_account(self, db):
        acc = db.account.get_or_create("Savings")
        assert acc["name"] == "Savings"
        _assert_money(acc["balance"], 0.0)

    def test_get_or_create_existing_account(self, db):
        db.account.get_or_create("Checking")
        db.account.get_or_create("Checking")
        accounts = [a for a in db.account.list() if a["name"] == "Checking"]
        assert len(accounts) == 1

    def test_update_account_balance(self, db):
        acc = db.account.get_or_create("Test")
        db.account.update_balance(acc["id"], 100.0)
        updated = db.account.find_by_name("Test")
        _assert_money(updated["balance"], 100.0)

    def test_update_account_balance_negative_delta(self, db):
        acc = db.account.get_or_create("Test2")
        db.account.update_balance(acc["id"], 500.0)
        db.account.update_balance(acc["id"], -200.0)
        updated = db.account.find_by_name("Test2")
        _assert_money(updated["balance"], 300.0)

    def test_account_balance_uses_exact_integer_cents_storage(self, db):
        acc = db.account.create("Cuenta centavos", account_type="bank", opening_balance=0.0, currency="USD")
        db.transaction.create(account_id=acc["id"], tx_type="income", amount=0.10, description="a")
        db.transaction.create(account_id=acc["id"], tx_type="income", amount=0.20, description="b")
        db.transaction.create(account_id=acc["id"], tx_type="income", amount=0.30, description="c")
        db.transaction.create(account_id=acc["id"], tx_type="expense", amount=0.15, description="d")

        updated = db.account.get(acc["id"])

        _assert_money(updated["balance"], 0.45)
        assert fetch_scalar(db, "SELECT balance_cents FROM accounts WHERE id = ?", (acc["id"],)) == 45
        cents = fetch_all_dicts(
            db,
            "SELECT amount_cents FROM transactions WHERE account_id = ? ORDER BY id",
            (acc["id"],),
        )
        assert [int(row["amount_cents"]) for row in cents] == [10, 20, 30, 15]

    def test_add_account_with_currency(self, db):
        acc = db.account.create("Cuenta USD", account_type="bank", opening_balance=10.0, currency="USD")
        assert acc["currency"] == "USD"

    def test_add_account_trims_name(self, db):
        acc = db.account.create(
            "  Cuenta ahorro  ",
            account_type="bank",
            opening_balance=10.0,
            currency="USD",
        )
        assert acc["name"] == "Cuenta ahorro"
        assert db.account.find_by_name("Cuenta ahorro")["id"] == acc["id"]

    def test_seed_initial_data_creates_main_account_in_default_currency(self, db):
        db.setting.set("default_currency", "USD")
        db.setting.seed_initial_data(include_default_categories=False, account_names=[])
        names = {a["name"]: a for a in db.account.list()}
        assert names["Main account"]["currency"] == "USD"
        assert "General" not in names

    def test_get_or_create_account_uses_default_currency(self, db):
        db.setting.set("default_currency", "CRC")
        acc = db.account.get_or_create("Wallet")
        assert acc["currency"] == "CRC"

    # ------------------------------------------------------------------
    # is_default / set_default_account / get_default_account
    # ------------------------------------------------------------------

    def test_schema_includes_is_default_column(self, db):
        acc = db.account.find_by_name("General")
        assert "is_default" in acc

    def test_initial_general_account_is_default(self, db):
        acc = db.account.find_by_name("General")
        assert acc["is_default"] == 1

    def test_get_default_account_returns_general(self, db):
        default = db.account.get_default()
        assert default is not None
        assert default["name"] == "General"

    def test_set_default_account_switches_default(self, db):
        new_acc = db.account.create("Savings", account_type="bank", opening_balance=0.0)
        db.account.set_default(new_acc["id"])
        default = db.account.get_default()
        assert default["id"] == new_acc["id"]
        # Old default must be cleared
        old = db.account.find_by_name("General")
        assert old["is_default"] == 0

    def test_set_default_account_invariant_only_one(self, db):
        a1 = db.account.create("A1")
        a2 = db.account.create("A2")
        db.account.set_default(a1["id"])
        db.account.set_default(a2["id"])
        defaults = [a for a in db.account.list() if a["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["id"] == a2["id"]

    def test_set_default_account_rejects_unknown_account(self, db):
        original_default = db.account.get_default()
        with pytest.raises(ValueError, match="Account 999999 not found"):
            db.account.set_default(999999)
        assert db.account.get_default()["id"] == original_default["id"]

    def test_seed_initial_data_account_names_list(self, db):
        db.setting.set("default_currency", "USD")
        db.setting.seed_initial_data(
            include_default_categories=False,
            account_names=["Main", "Savings"],
        )
        all_accounts = {a["name"]: a for a in db.account.list()}
        assert "Main" in all_accounts
        assert "Savings" in all_accounts
        assert "General" not in all_accounts
        # First named account is the default
        assert all_accounts["Main"]["is_default"] == 1
        assert all_accounts["Savings"]["is_default"] == 0

    def test_seed_initial_data_empty_account_names_creates_default(self, db):
        db.setting.set("default_currency", "EUR")
        db.setting.seed_initial_data(include_default_categories=False, account_names=[])
        names = [a["name"] for a in db.account.list()]
        assert "Main account" in names
        assert "General" not in names
        default = db.account.get_default()
        assert default is not None

    def test_seed_initial_data_without_account_names_keeps_existing_accounts(self, db):
        db.setting.set("default_currency", "COP")
        db.setting.seed_initial_data(
            include_default_categories=False,
            account_names=None,
        )
        names = [a["name"] for a in db.account.list()]
        assert "Main account" not in names
        assert "General" in names

    def test_seed_initial_data_uses_account_specs(self, db):
        db.setting.seed_initial_data(
            include_default_categories=False,
            account_specs=[
                {
                    "name": "Caja",
                    "account_type": "cash",
                    "currency": "NIO",
                    "opening_balance": 25.0,
                },
                {
                    "name": "Visa",
                    "account_type": "credit",
                    "currency": "USD",
                    "opening_balance": -300.0,
                },
            ],
        )

        accounts = {row["name"]: row for row in db.account.list()}

        assert accounts["Caja"]["account_type"] == "cash"
        _assert_money(accounts["Caja"]["balance"], 25.0)
        assert accounts["Caja"]["is_default"] == 1
        assert accounts["Visa"]["account_type"] == "credit"
        _assert_money(accounts["Visa"]["balance"], -300.0)
        assert "General" not in accounts


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


class TestTransactions:
    def test_credit_card_payment_records_transfer_and_updates_balances(self, db):
        source = db.account.create("BAC", "bank", 1200.0, "NIO")
        credit = db.account.create("Visa", "credit", -450.0, "NIO")

        debit_tx, credit_tx = db.transaction.record_credit_card_payment(
            from_account_id=source["id"],
            credit_account_id=credit["id"],
            amount=200.0,
            description="Pago de tarjeta Visa",
        )

        source_after = db.account.get(source["id"])
        credit_after = db.account.get(credit["id"])
        summary = db.report.summary()

        assert debit_tx["is_transfer"] == 1
        assert credit_tx["is_transfer"] == 1
        assert debit_tx["type"] == "expense"
        assert credit_tx["type"] == "income"
        _assert_money(source_after["balance"], 1000.0)
        _assert_money(credit_after["balance"], -250.0)
        assert float(summary["total_income"]) == pytest.approx(0.0)
        assert float(summary["total_expenses"]) == pytest.approx(0.0)

    def test_credit_card_payment_rejects_invalid_account_types(self, db):
        cash = db.account.create("Caja", "cash", 100.0, "NIO")
        bank = db.account.create("Banco", "bank", 100.0, "NIO")
        other_credit = db.account.create("Amex", "credit", -50.0, "NIO")
        credit = db.account.create("Mastercard", "credit", -100.0, "NIO")

        with pytest.raises(ValueError, match="bank or cash"):
            db.transaction.record_credit_card_payment(other_credit["id"], credit["id"], 20.0)

        with pytest.raises(ValueError, match="target an account of type credit"):
            db.transaction.record_credit_card_payment(cash["id"], bank["id"], 20.0)

    def test_credit_card_payment_rejects_same_account(self, db):
        bank = db.account.create("Banco", "bank", 100.0, "NIO")
        with pytest.raises(ValueError, match="different"):
            db.transaction.record_credit_card_payment(bank["id"], bank["id"], 20.0)

    def test_credit_card_payment_rejects_date_before_credit_account_creation(self, db):
        bank = db.account.create("Banco", "bank", 500.0, "NIO")
        credit = db.account.create("Visa", "credit", -50.0, "NIO")

        with pytest.raises(ValueError, match="cannot be dated before"):
            db.transaction.record_credit_card_payment(
                from_account_id=bank["id"],
                credit_account_id=credit["id"],
                amount=20.0,
                tx_date="2000-01-01",
            )

    def test_add_income_updates_balance(self, db):
        acc = db.account.get_or_create("Wallet")
        db.transaction.create(account_id=acc["id"], tx_type="income", amount=1000.0, description="salary")
        updated = db.account.find_by_name("Wallet")
        _assert_money(updated["balance"], 1000.0)

    def test_add_expense_decreases_balance(self, db):
        acc = db.account.get_or_create("Cash")
        db.transaction.create(account_id=acc["id"], tx_type="income", amount=500.0)
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=200.0,
            description="groceries",
        )
        updated = db.account.find_by_name("Cash")
        _assert_money(updated["balance"], 300.0)

    def test_add_transaction_rolls_back_when_balance_update_fails(self, db, monkeypatch):
        acc = db.account.get_or_create("Atomic add")
        original_balance = db.account.get(acc["id"])["balance"]

        def _boom(_account_id: int, _delta: float) -> None:
            raise RuntimeError("balance update failed")

        monkeypatch.setattr(db._backend, "update_account_balance", _boom)

        with pytest.raises(RuntimeError, match="balance update failed"):
            db.transaction.create(account_id=acc["id"], tx_type="income", amount=25.0, description="should rollback")

        assert db.transaction.list() == []
        assert db.account.get(acc["id"])["balance"] == pytest.approx(original_balance)

    def test_get_transactions_returns_list(self, db):
        acc = db.account.get_or_create("General")
        db.transaction.create(account_id=acc["id"], tx_type="income", amount=100.0)
        txs = db.transaction.list()
        assert len(txs) >= 1

    def test_get_transactions_filter_by_type(self, db):
        acc = db.account.get_or_create("General")
        db.transaction.create(account_id=acc["id"], tx_type="income", amount=200.0)
        db.transaction.create(account_id=acc["id"], tx_type="expense", amount=50.0)
        incomes = db.transaction.list(tx_type="income")
        expenses = db.transaction.list(tx_type="expense")
        assert all(t["type"] == "income" for t in incomes)
        assert all(t["type"] == "expense" for t in expenses)

    def test_transaction_has_expected_fields(self, db):
        acc = db.account.get_or_create("General")
        tx = db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=42.0,
            description="coffee",
            category="food",
        )
        _assert_money(tx["amount"], 42.0)
        assert tx["type"] == "expense"
        assert tx["description"] == "coffee"
        assert tx["category"] == "food"

    def test_update_transaction_account_moves_balance_between_accounts(self, db):
        src = db.account.create("Source", "bank", 0.0, "NIO")
        dst = db.account.create("Target", "bank", 0.0, "NIO")
        tx = db.transaction.create(account_id=src["id"], tx_type="expense", amount=25.0, description="taxi")

        db.transaction.update_account(tx["id"], dst["id"])

        src_after = db.account.get(src["id"])
        dst_after = db.account.get(dst["id"])
        _assert_money(src_after["balance"], 0.0)
        _assert_money(dst_after["balance"], -25.0)

    def test_update_transaction_category_changes_only_category(self, db):
        acc = db.account.get_or_create("General")
        tx = db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=12.0,
            description="snack",
            category="food",
        )

        updated = db.transaction.update_category(tx["id"], "coffee")

        assert updated["category"] == "coffee"
        refreshed = db.transaction.get(tx["id"])
        assert refreshed is not None
        assert refreshed["description"] == "snack"


class TestCategories:
    def test_seed_initial_data_creates_robust_default_catalog(self, db):
        db.setting.seed_initial_data(include_default_categories=True, account_names=None)

        categories = {(cat["name"], cat["type"]) for cat in db.category.list()}
        expected = {
            # Original categories
            ("Salary and Compensation", "income"),
            ("Net Salary (Payroll)", "income"),
            ("Services and Sales", "income"),
            ("Freelance Fees", "income"),
            ("Rent and Interest", "income"),
            ("Rent or Mortgage", "expense"),
            ("Housing", "expense"),
            ("Electricity, Gas and Water", "expense"),
            ("Groceries and Pantry", "expense"),
            ("Fuel and Tolls", "expense"),
            ("Savings", "expense"),
            ("Emergency Fund", "expense"),
            # New comprehensive income categories
            ("Other Active Income", "income"),
            ("Business Income", "income"),
            ("Passive Income", "income"),
            ("Transfers and Gifts Received", "income"),
            ("Other Income", "income"),
            ("Overtime and Tips", "income"),
            ("Royalties and Affiliates", "income"),
            ("Reimbursements", "income"),
            # New comprehensive expense categories
            ("Personal Shopping", "expense"),
            ("Family and Social", "expense"),
            ("Pets", "expense"),
            ("Business Expenses", "expense"),
            ("Donations and Charity", "expense"),
            ("Miscellaneous", "expense"),
            ("Travel and Vacations", "expense"),
            ("Clothing and Footwear", "expense"),
            ("Veterinarian", "expense"),
            ("Investment Savings", "expense"),
            ("Specific Savings Goals", "expense"),
        }

        assert expected.issubset(categories)

        category_rows = {c["name"]: c for c in db.category.list()}
        assert category_rows["Salary and Compensation"]["parent_id"] is None
        assert category_rows["Net Salary (Payroll)"]["parent_id"] == category_rows["Salary and Compensation"]["id"]
        assert category_rows["Savings Goals"]["parent_id"] is None
        assert category_rows["Savings"]["parent_id"] == category_rows["Savings Goals"]["id"]
        assert category_rows["Emergency Fund"]["parent_id"] == category_rows["Savings"]["id"]
        assert category_rows["Investment Savings"]["parent_id"] == category_rows["Savings"]["id"]
        assert category_rows["Overtime and Tips"]["parent_id"] == category_rows["Other Active Income"]["id"]

    def test_seed_initial_data_creates_default_tags_by_language(self, db):
        db.setting.seed_initial_data(include_default_categories=True, account_names=None)
        tag_names = {t["name"] for t in db.tag.list()}
        assert {"Fixed", "Variable", "Essential", "Discretionary"}.issubset(tag_names)

    def test_seed_initial_data_in_spanish_localizes_accounts_categories_and_tags(self, db):
        db.setting.seed_initial_data(include_default_categories=True, account_names=[], language="es")

        account_names = {a["name"] for a in db.account.list()}
        assert "Cuenta principal" in account_names

        categories = {c["name"]: c for c in db.category.list()}
        assert "Salario y Remuneración" in categories
        assert "Ahorro" in categories
        assert "Compras Personales" in categories
        assert "Mascotas" in categories
        assert "Donaciones y Caridad" in categories
        assert categories["Metas de ahorro"]["parent_id"] is None
        assert categories["Ahorro"]["parent_id"] == categories["Metas de ahorro"]["id"]
        assert categories["Fondo de Emergencia"]["parent_id"] == categories["Ahorro"]["id"]
        assert categories["Ahorro para Inversión"]["parent_id"] == categories["Ahorro"]["id"]

        tag_names = {t["name"] for t in db.tag.list()}
        assert {"Fijo", "Variable", "Necesario", "Discrecional"}.issubset(tag_names)

    def test_get_or_create_category_reuses_existing_case_insensitive(self, db):
        created = db.category.get_or_create("Cafe", "expense")
        same = db.category.get_or_create(" cafe ", "expense")
        assert created["id"] == same["id"]

    def test_get_category_is_single_lookup_source_by_id_or_name(self, db):
        created = db.category.get_or_create("Supermercado", "expense")

        by_id = db.category.get(int(created["id"]))
        by_name = db.category.find_by_name("  supermercado ", "expense")
        legacy_by_id = db.category.get(int(created["id"]))
        legacy_by_name = db.category.find_by_name("Supermercado", "expense")

        assert by_id is not None and by_name is not None
        assert by_id["id"] == by_name["id"] == int(created["id"])
        assert legacy_by_id == by_id
        assert legacy_by_name == by_name

    def test_create_category_maps_duplicate_name_to_domain_error(self, db):
        db.category.create("Cafe", "expense")

        with pytest.raises(DuplicateCategoryNameError):
            db.category.create("Cafe", "expense")

    def test_update_category_maps_duplicate_name_to_domain_error(self, db):
        db.category.create("Cafe", "expense")
        transport = db.category.create("Transporte", "expense")

        with pytest.raises(DuplicateCategoryNameError):
            db.category.update(int(transport["id"]), "Cafe", "expense")

    def test_merge_categories_propagates_to_related_tables(self, db):
        acc = db.account.get_or_create("Wallet")
        source = db.category.create("cafeteria", "expense")
        target = db.category.create("cafe", "expense")

        db.transaction.create(account_id=acc["id"], tx_type="expense", amount=10.0, category="cafeteria")
        db.recurring.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=25.0,
            description="coffee plan",
            category="cafeteria",
            note=None,
            day_of_month=5,
        )
        db.bucket.upsert("cafeteria", 100.0)
        db.bucket.update_spent("cafeteria", 40.0)
        db.bucket.upsert("cafe", 150.0)
        db.bucket.update_spent("cafe", 20.0)

        merged = db.category.merge(source["id"], target["id"])

        assert merged["id"] == target["id"]
        assert db.category.get(source["id"]) is None

        txs = db.transaction.list(tx_type="expense")
        assert any(tx["category"] == "cafe" for tx in txs)
        assert not any(tx["category"] == "cafeteria" for tx in txs)

        recurring = db.recurring.list()
        assert any(r["category"] == "cafe" for r in recurring)
        assert not any(r["category"] == "cafeteria" for r in recurring)

        bucket = db.bucket.find_by_name("cafe")
        assert bucket is not None
        _assert_money(bucket["spent_amount"], 60.0)
        assert db.bucket.find_by_name("cafeteria") is None


class TestTags:
    def test_create_tag_maps_duplicate_name_to_domain_error(self, db):
        db.tag.create("Monthly", color="#123456")

        with pytest.raises(DuplicateTagNameError):
            db.tag.create("Monthly", color="#654321")

    def test_update_tag_maps_duplicate_name_to_domain_error(self, db):
        db.tag.create("Monthly", color="#123456")
        variable = db.tag.create("Variable", color="#654321")

        with pytest.raises(DuplicateTagNameError):
            db.tag.update(int(variable["id"]), "Monthly", "#654321")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class TestSummary:
    def test_summary_empty(self, db):
        summary = db.report.summary()
        _assert_money(summary["total_income"], 0.0)
        _assert_money(summary["total_expenses"], 0.0)
        _assert_money(summary["savings"], 0.0)
        _assert_money(summary["net"], 0.0)

    def test_summary_with_transactions(self, db):
        acc = db.account.get_or_create("General")
        db.transaction.create(account_id=acc["id"], tx_type="income", amount=1000.0)
        db.transaction.create(account_id=acc["id"], tx_type="expense", amount=300.0)
        summary = db.report.summary()
        _assert_money(summary["total_income"], 1000.0)
        _assert_money(summary["total_expenses"], 300.0)
        _assert_money(summary["savings"], 0.0)
        _assert_money(summary["net"], 700.0)

    def test_summary_excludes_savings_categories_from_reportable_expenses(self, db):
        acc = db.account.get_or_create("General")
        db.category.create("Ahorro Test", "expense", is_savings=True)
        db.transaction.create(account_id=acc["id"], tx_type="income", amount=1000.0)
        db.transaction.create(account_id=acc["id"], tx_type="expense", amount=300.0, category="Comida")
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=100.0,
            category="Ahorro Test",
        )

        summary = db.report.summary()

        _assert_money(summary["total_income"], 1000.0)
        _assert_money(summary["total_expenses"], 300.0)
        _assert_money(summary["savings"], 100.0)
        _assert_money(summary["net"], 700.0)

    def test_category_summary_excludes_savings_rows(self, db):
        acc = db.account.get_or_create("General")
        db.category.create("Comida", "expense")
        db.category.create("Ahorro Test", "expense", is_savings=True)
        db.transaction.create(account_id=acc["id"], tx_type="expense", amount=150.0, category="Comida")
        db.transaction.create(account_id=acc["id"], tx_type="expense", amount=80.0, category="Ahorro Test")

        summary = db.report.category_summary()
        rows = {row["category"]: row for row in summary}

        assert "Comida" in rows
        _assert_money(rows["Comida"]["total_expenses"], 150.0)
        assert "Ahorro Test" not in rows

    def test_category_summary_can_aggregate_child_categories_by_parent(self, db):
        acc = db.account.get_or_create("General")
        food = db.category.create("Comida", "expense")
        dining = db.category.create("Restaurantes", "expense", parent_id=int(food["id"]))
        db.transaction.create(
            account_id=int(acc["id"]),
            tx_type="expense",
            amount=120.0,
            category=str(dining["name"]),
            category_id=int(dining["id"]),
        )
        db.transaction.create(
            account_id=int(acc["id"]),
            tx_type="expense",
            amount=30.0,
            category=str(food["name"]),
            category_id=int(food["id"]),
        )

        rows = {row["category"]: row for row in db.report.category_summary(aggregate_by_parent=True)}

        _assert_money(rows["Comida"]["total_expenses"], 150.0)

    def test_category_summary_uses_category_fk_after_category_rename(self, db):
        acc = db.account.get_or_create("General")
        parent = db.category.create("Food", "expense")
        child = db.category.create("Dining", "expense", parent_id=int(parent["id"]))
        db.transaction.create(
            account_id=int(acc["id"]),
            tx_type="expense",
            amount=120.0,
            category=str(child["name"]),
            category_id=int(child["id"]),
        )

        db.category.update(
            int(child["id"]),
            name="Restaurants",
            cat_type=str(child["type"]),
            color=str(child["color"]),
            is_savings=bool(child.get("is_savings", False)),
            parent_id=int(child["parent_id"]) if child.get("parent_id") is not None else None,
            icon=str(child.get("icon") or ""),
        )

        rows = {row["category"]: row for row in db.report.category_summary()}
        aggregated = {row["category"]: row for row in db.report.category_summary(aggregate_by_parent=True)}

        assert "Dining" not in rows
        assert "Restaurants" in rows
        _assert_money(rows["Restaurants"]["total_expenses"], 120.0)
        _assert_money(aggregated["Food"]["total_expenses"], 120.0)

    def test_summary_and_category_report_keep_fractional_cents_exact(self, db):
        acc = db.account.get_or_create("General")
        food = db.category.create("Food", "expense")
        savings = db.category.create("Savings Fractional", "expense", is_savings=True)

        db.transaction.create(account_id=acc["id"], tx_type="income", amount=1000.10, category="Salary")
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=300.20,
            category=food["name"],
            category_id=food["id"],
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=50.15,
            category=savings["name"],
            category_id=savings["id"],
        )

        summary = db.report.summary()
        rows = {row["category"]: row for row in db.report.category_summary()}

        _assert_money(summary["total_income"], 1000.10)
        _assert_money(summary["total_expenses"], 300.20)
        _assert_money(summary["savings"], 50.15)
        _assert_money(summary["net"], 699.90)
        _assert_money(rows["Food"]["total_expenses"], 300.20)


# ---------------------------------------------------------------------------
# Buckets
# ---------------------------------------------------------------------------


class TestBuckets:
    def test_upsert_and_get_bucket(self, db):
        bucket = db.bucket.upsert("Food", 500.0)
        assert bucket["name"] == "Food"
        _assert_money(bucket["budget_amount"], 500.0)
        _assert_money(bucket["spent_amount"], 0.0)

    def test_upsert_updates_existing(self, db):
        db.bucket.upsert("Travel", 300.0)
        bucket = db.bucket.upsert("Travel", 600.0)
        _assert_money(bucket["budget_amount"], 600.0)

    def test_update_bucket_spent(self, db):
        db.bucket.upsert("Entertainment", 200.0)
        db.bucket.update_spent("Entertainment", 50.0)
        bucket = db.bucket.find_by_name("Entertainment")
        _assert_money(bucket["spent_amount"], 50.0)

    def test_get_buckets_returns_list(self, db):
        db.bucket.upsert("Health", 100.0)
        buckets = db.bucket.list()
        assert any(b["name"] == "Health" for b in buckets)


class TestAnnualBudgets:
    def test_first_budget_in_year_becomes_default(self, db):
        first = db.budget.create("ppto_base_2026", 2026, "NIO")
        default_budget = db.budget.get_default_for_year(2026)

        assert default_budget is not None
        assert int(default_budget["id"]) == int(first["id"])
        assert int(default_budget["is_default_year"]) == 1

    def test_set_default_budget_for_year_enforces_single_default(self, db):
        a = db.budget.create("ppto_optimista_2026", 2026, "NIO")
        b = db.budget.create("ppto_pesimista_2026", 2026, "NIO")

        db.budget.set_default_for_year(int(b["id"]))

        budgets_2026 = db.budget.list(year=2026)
        defaults = [row for row in budgets_2026 if int(row.get("is_default_year") or 0) == 1]

        assert len(defaults) == 1
        assert int(defaults[0]["id"]) == int(b["id"])

        refreshed_a = db.budget.get(int(a["id"]))
        refreshed_b = db.budget.get(int(b["id"]))
        assert refreshed_a is not None and int(refreshed_a["is_default_year"]) == 0
        assert refreshed_b is not None and int(refreshed_b["is_default_year"]) == 1

    def test_deleting_default_budget_promotes_another_default_same_year(self, db):
        a = db.budget.create("ppto_a_2027", 2027, "NIO")
        b = db.budget.create("ppto_b_2027", 2027, "NIO")
        db.budget.set_default_for_year(int(b["id"]))

        db.budget.delete(int(b["id"]))

        default_budget = db.budget.get_default_for_year(2027)
        assert default_budget is not None
        assert int(default_budget["id"]) == int(a["id"])

    def test_get_budget_by_id_uses_direct_query_without_list_budgets(self, db, monkeypatch):
        income = db.category.create("Salario lookup directo", "income")
        expense = db.category.create("Comida lookup directo", "expense")
        budget = db.budget.create("ppto_lookup_directo", 2026, "USD")
        db.budget.upsert_amount(int(budget["id"]), int(income["id"]), 2026, 1, 1200.0)
        db.budget.upsert_amount(int(budget["id"]), int(expense["id"]), 2026, 1, 450.0)

        def _boom(*args, **kwargs):
            raise AssertionError("get_budget_by_id should not call list_budgets()")

        monkeypatch.setattr(db._backend, "list_budgets", _boom)

        loaded = db.budget.get(int(budget["id"]))

        assert loaded is not None
        assert int(loaded["id"]) == int(budget["id"])
        _assert_money(loaded["total_income"], 1200.0)
        _assert_money(loaded["total_expenses"], 450.0)
        _assert_money(loaded["balance"], 750.0)

    def test_create_budget_uses_default_currency_and_creates_12_month_matrix(self, db):
        db.setting.set("default_currency", "USD")
        income = db.category.create("Salario", "income")
        expense = db.category.create("Comida", "expense")

        budget = db.budget.create("ppto_2026", 2026)
        matrix = db.budget.get_matrix(budget["id"])

        assert budget["currency"] == "USD"
        rows = {row["category_id"]: row for row in matrix["rows"]}
        assert len(rows[income["id"]]["months"]) == 12
        assert len(rows[expense["id"]]["months"]) == 12
        _assert_money(matrix["totals"]["income_annual"], 0.0)
        _assert_money(matrix["totals"]["expense_annual"], 0.0)

    def test_budget_matrix_excludes_savings_categories(self, db):
        income = db.category.create("Salario", "income")
        expense = db.category.create("Comida", "expense")
        db.category.create("Ahorro Test", "expense", is_savings=True)

        budget = db.budget.create("ppto_sin_ahorro", 2026, "NIO")
        matrix = db.budget.get_matrix(budget["id"])
        row_names = {row["name"] for row in matrix["rows"]}

        assert income["name"] in row_names
        assert expense["name"] in row_names
        assert "Ahorro Test" not in row_names

    def test_budget_storage_and_tracking_keep_exact_integer_cents(self, db):
        food = db.category.create("Comida exacta", "expense")
        acc = db.account.create("Cuenta exacta presupuesto", currency="USD")
        today = date.today()
        budget = db.budget.create("ppto_exacto", today.year, "USD")

        db.budget.upsert_amount(int(budget["id"]), int(food["id"]), today.year, today.month, 0.30)
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=0.10,
            category=food["name"],
            category_id=food["id"],
            tx_date=f"{today.year:04d}-{today.month:02d}-05",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=0.05,
            category=food["name"],
            category_id=food["id"],
            tx_date=f"{today.year:04d}-{today.month:02d}-06",
        )

        matrix = db.budget.get_matrix(int(budget["id"]))
        tracking = db.budget.get_monthly_tracking(int(budget["id"]), today.year, today.month)
        row = next(item for item in tracking["rows"] if item["name"] == food["name"])

        _assert_money(
            next(item for item in matrix["rows"] if item["name"] == food["name"])["months"][today.month - 1], 0.30
        )
        _assert_money(row["assigned"], 0.30)
        _assert_money(row["executed"], 0.15)
        _assert_money(row["available"], 0.15)
        assert (
            fetch_scalar(
                db,
                "SELECT amount_cents FROM budget_detail WHERE budget_id = ? AND category_id = ? AND year = ? AND month = ?",
                (int(budget["id"]), int(food["id"]), today.year, today.month),
            )
            == 30
        )

    def test_budget_code_is_globally_unique(self, db):
        db.budget.create("ppto_viaje", 2026, "NIO")

        with pytest.raises(DuplicateBudgetCodeError):
            db.budget.create("ppto_viaje", 2027, "USD")

    def test_create_budget_rejects_invalid_year(self, db):
        with pytest.raises(BudgetValidationError):
            db.budget.create("ppto_invalido", 1800, "USD")

    @pytest.mark.full
    def test_propose_budget_uses_average_monthly_amount_from_previous_year(self, db):
        salary = db.category.create("Salario", "income")
        food = db.category.create("Comida", "expense")
        acc = db.account.create("Cuenta NIO", currency="NIO")

        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=1200.0,
            category="Salario",
            tx_date="2025-01-10",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=1200.0,
            category="Salario",
            tx_date="2025-02-10",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=1200.0,
            category="Salario",
            tx_date="2025-03-10",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=600.0,
            category="Comida",
            tx_date="2025-01-12",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=600.0,
            category="Comida",
            tx_date="2025-02-12",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=600.0,
            category="Comida",
            tx_date="2025-03-12",
        )

        budget = db.budget.create("ppto_base", 2026, "NIO")
        result = db.budget.propose(budget["id"])
        matrix = db.budget.get_matrix(budget["id"])
        rows = {row["category_id"]: row for row in matrix["rows"]}

        assert result["applied"] is True
        assert result["source_year"] == 2025
        assert all(_money(month) == _money(300.0) for month in rows[salary["id"]]["months"])
        assert all(_money(month) == _money(150.0) for month in rows[food["id"]]["months"])

    @pytest.mark.full
    def test_propose_budget_requires_sufficient_previous_history(self, db):
        db.category.create("Salario", "income")
        acc = db.account.create("Cuenta base", currency="NIO")
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=500.0,
            category="Salario",
            tx_date="2025-01-15",
        )

        budget = db.budget.create("ppto_sin_base", 2026, "NIO")
        result = db.budget.propose(budget["id"])

        assert result["applied"] is False
        assert "información suficiente" in result["reason"].lower()

    def test_budget_comparison_groups_by_quarter(self, db):
        salary = db.category.create("Salario", "income")
        food = db.category.create("Comida", "expense")
        acc = db.account.create("Cuenta comparación", currency="NIO")
        budget = db.budget.create("ppto_compare", 2026, "NIO")

        for month in [1, 2, 3]:
            db.budget.upsert_amount(budget["id"], salary["id"], 2026, month, 1000.0)
            db.budget.upsert_amount(budget["id"], food["id"], 2026, month, 200.0)

        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=900.0,
            category="Salario",
            tx_date="2026-01-05",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=950.0,
            category="Salario",
            tx_date="2026-02-05",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=1000.0,
            category="Salario",
            tx_date="2026-03-05",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=180.0,
            category="Comida",
            tx_date="2026-01-07",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=250.0,
            category="Comida",
            tx_date="2026-02-07",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=220.0,
            category="Comida",
            tx_date="2026-03-07",
        )

        comparison = db.budget.compare(budget["id"], granularity="quarterly")
        rows = {row["name"]: row for row in comparison["rows"]}
        salary_q1 = rows["Salario"]["periods"][0]
        food_q1 = rows["Comida"]["periods"][0]

        _assert_money(salary_q1["budget"], 3000.0)
        _assert_money(salary_q1["real"], 2850.0)
        _assert_money(salary_q1["variance"], -150.0)
        _assert_money(food_q1["budget"], 600.0)
        _assert_money(food_q1["real"], 650.0)
        _assert_money(food_q1["variance"], 50.0)

    def test_budget_comparison_excludes_savings_transactions_from_real_expenses(self, db):
        food = db.category.create("Comida", "expense")
        savings = db.category.create("Ahorro Test", "expense", is_savings=True)
        acc = db.account.create("Cuenta ahorro hack", currency="NIO")
        budget = db.budget.create("ppto_hack_ahorro", 2026, "NIO")

        db.budget.upsert_amount(budget["id"], food["id"], 2026, 1, 200.0)

        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=180.0,
            category="Comida",
            tx_date="2026-01-07",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=90.0,
            category=savings["name"],
            tx_date="2026-01-08",
        )

        comparison = db.budget.compare(budget["id"], granularity="quarterly")
        rows = {row["name"]: row for row in comparison["rows"]}
        food_q1 = rows["Comida"]["periods"][0]

        assert "Ahorro Test" not in rows
        _assert_money(food_q1["real"], 180.0)
        _assert_money(comparison["totals"]["expense"][0]["real"], 180.0)

    def test_budget_comparison_uses_sql_aggregation_without_loading_full_year_transactions(self, db, monkeypatch):
        salary = db.category.create("Salario SQL", "income")
        food = db.category.create("Comida SQL", "expense")
        acc = db.account.create("Cuenta SQL comparison", currency="NIO")
        budget = db.budget.create("ppto_sql_compare", 2026, "NIO")

        for month in [1, 2, 3]:
            db.budget.upsert_amount(int(budget["id"]), int(salary["id"]), 2026, month, 1000.0)
            db.budget.upsert_amount(int(budget["id"]), int(food["id"]), 2026, month, 250.0)

        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=1200.0,
            category=salary["name"],
            category_id=salary["id"],
            tx_date="2026-01-05",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=300.0,
            category=food["name"],
            category_id=food["id"],
            tx_date="2026-01-08",
        )

        def _boom(*args, **kwargs):
            raise AssertionError("budget comparison should not call _get_budget_transactions()")

        monkeypatch.setattr(db._backend, "_get_budget_transactions", _boom)

        comparison = db.budget.compare(int(budget["id"]), granularity="quarterly")
        rows = {row["name"]: row for row in comparison["rows"]}

        _assert_money(rows["Salario SQL"]["periods"][0]["real"], 1200.0)
        _assert_money(rows["Comida SQL"]["periods"][0]["real"], 300.0)

    def test_export_budget_comparison_excel_creates_workbook_with_expected_headers(self, db, tmp_path):
        salary = db.category.create("Salario", "income")
        food = db.category.create("Comida", "expense")
        acc = db.account.create("Cuenta exportación", currency="NIO")
        budget = db.budget.create("ppto_excel", 2026, "NIO")

        for month in [1, 2, 3]:
            db.budget.upsert_amount(budget["id"], salary["id"], 2026, month, 1000.0)
            db.budget.upsert_amount(budget["id"], food["id"], 2026, month, 200.0)

        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=900.0,
            category="Salario",
            tx_date="2026-01-05",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=210.0,
            category="Comida",
            tx_date="2026-01-07",
        )

        output = tmp_path / "real-vs-ppto.xlsx"
        exported_rows = db.budget.export_comparison_excel(output, budget["id"], granularity="quarterly")

        workbook = load_workbook(output)
        sheet = workbook["Real vs PPTO"]

        assert exported_rows > 0
        assert sheet["A1"].value == "Reporte Real vs Presupuesto | ppto_excel | 2026 | NIO"
        assert sheet["A8"].value == "Categoría"
        assert sheet["B8"].value == "T1 Real"
        assert sheet["C8"].value == "T1 PPTO"
        assert sheet["D8"].value == "T1 Var"
        assert sheet["A9"].value == "Ingresos"
        assert sheet["A10"].value == "Salario"

    def test_monthly_budget_tracking_returns_assigned_executed_and_available(self, db):
        food = db.category.create("Comida", "expense")
        transport = db.category.create("Transporte", "expense")
        acc = db.account.create("Cuenta sobres", currency="NIO")
        today = date.today()
        year = today.year
        month = today.month
        budget = db.budget.create("ppto_sobres", year, "NIO")
        db.budget.upsert_amount(budget["id"], food["id"], year, month, 200.0)
        db.budget.upsert_amount(budget["id"], transport["id"], year, month, 100.0)

        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=90.0,
            category="Comida",
            tx_date=f"{year:04d}-{month:02d}-05",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=150.0,
            category="Transporte",
            tx_date=f"{year:04d}-{month:02d}-06",
        )

        tracking = db.budget.get_monthly_tracking(budget["id"], year, month)
        rows = {row["name"]: row for row in tracking["rows"]}

        _assert_money(tracking["totals"]["assigned"], 300.0)
        _assert_money(tracking["totals"]["executed"], 240.0)
        _assert_money(tracking["totals"]["available"], 60.0)
        _assert_money(rows["Comida"]["available"], 110.0)
        assert rows["Comida"]["status"] == "available"
        _assert_money(rows["Transporte"]["available"], -50.0)
        assert rows["Transporte"]["status"] == "over"

    def test_monthly_budget_tracking_uses_sql_aggregation_without_loading_full_year_transactions(self, db, monkeypatch):
        food = db.category.create("Comida SQL tracking", "expense")
        transport = db.category.create("Transporte SQL tracking", "expense")
        acc = db.account.create("Cuenta SQL tracking", currency="USD")
        year = date.today().year
        month = date.today().month
        budget = db.budget.create("ppto_sql_tracking", year, "USD")
        db.budget.upsert_amount(int(budget["id"]), int(food["id"]), year, month, 200.0)
        db.budget.upsert_amount(int(budget["id"]), int(transport["id"]), year, month, 90.0)

        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=70.0,
            category=food["name"],
            category_id=food["id"],
            tx_date=f"{year:04d}-{month:02d}-03",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=110.0,
            category=transport["name"],
            category_id=transport["id"],
            tx_date=f"{year:04d}-{month:02d}-04",
        )

        def _boom(*args, **kwargs):
            raise AssertionError("monthly tracking should not call _get_budget_transactions()")

        monkeypatch.setattr(db._backend, "_get_budget_transactions", _boom)

        tracking = db.budget.get_monthly_tracking(int(budget["id"]), year, month)
        rows = {row["name"]: row for row in tracking["rows"]}

        _assert_money(tracking["totals"]["executed"], 180.0)
        _assert_money(rows["Comida SQL tracking"]["executed"], 70.0)
        _assert_money(rows["Transporte SQL tracking"]["executed"], 110.0)

    def test_monthly_budget_tracking_allows_past_and_future_months_in_budget_year(self, db):
        food = db.category.create("Comida", "expense")
        year = date.today().year
        budget = db.budget.create("ppto_mes_actual", year, "NIO")
        db.budget.upsert_amount(budget["id"], food["id"], year, 1, 100.0)
        db.budget.upsert_amount(budget["id"], food["id"], year, 12, 200.0)

        jan_tracking = db.budget.get_monthly_tracking(budget["id"], year, 1)
        dec_tracking = db.budget.get_monthly_tracking(budget["id"], year, 12)

        jan_row = next(row for row in jan_tracking["rows"] if row["name"] == "Comida")
        dec_row = next(row for row in dec_tracking["rows"] if row["name"] == "Comida")

        _assert_money(jan_row["assigned"], 100.0)
        _assert_money(dec_row["assigned"], 200.0)

    def test_monthly_budget_tracking_rejects_year_different_from_budget(self, db):
        food = db.category.create("Comida", "expense")
        year = date.today().year
        budget = db.budget.create("ppto_year_guard", year, "NIO")
        db.budget.upsert_amount(budget["id"], food["id"], year, 1, 100.0)

        with pytest.raises(ValueError, match=f"budget year {year}"):
            db.budget.get_monthly_tracking(budget["id"], year + 1, 1)

    def test_reassign_monthly_budget_moves_amount_without_changing_total(self, db):
        food = db.category.create("Comida", "expense")
        transport = db.category.create("Transporte", "expense")
        today = date.today()
        year = today.year
        month = today.month
        budget = db.budget.create("ppto_reasignacion", year, "NIO")
        db.budget.upsert_amount(budget["id"], food["id"], year, month, 200.0)
        db.budget.upsert_amount(budget["id"], transport["id"], year, month, 100.0)

        result = db.budget.reassign_monthly(budget["id"], year, month, food["id"], transport["id"], 50.0)
        rows = {row["name"]: row for row in result["tracking"]["rows"]}

        _assert_money(rows["Comida"]["assigned"], 150.0)
        _assert_money(rows["Transporte"]["assigned"], 150.0)
        _assert_money(result["tracking"]["totals"]["assigned"], 300.0)


# ---------------------------------------------------------------------------
# Transfers
# ---------------------------------------------------------------------------


class TestTransfers:
    def test_transfer_same_currency_between_accounts(self, db):
        a = db.account.create("Origen NIO", "bank", 100.0, "NIO")
        b = db.account.create("Destino NIO", "bank", 50.0, "NIO")

        db.transaction.transfer_between_accounts(a["id"], b["id"], 25.0)

        a2 = db.account.get(a["id"])
        b2 = db.account.get(b["id"])
        _assert_money(a2["balance"], 75.0)
        _assert_money(b2["balance"], 75.0)

    def test_transfer_cross_currency_with_exchange_rate(self, db):
        usd = db.account.create("Ahorro USD", "bank", 100.0, "USD")
        nio = db.account.create("Pago NIO", "bank", 0.0, "NIO")

        db.transaction.transfer_between_accounts(
            usd["id"],
            nio["id"],
            amount=27.29,
            exchange_rate=36.6432,
        )

        usd2 = db.account.get(usd["id"])
        nio2 = db.account.get(nio["id"])
        _assert_money(usd2["balance"], 72.71)
        _assert_money(nio2["balance"], Decimal("27.29") * Decimal("36.6432"))

    def test_transfer_cross_currency_with_converted_amount(self, db):
        usd = db.account.create("Ahorro USD 2", "bank", 100.0, "USD")
        nio = db.account.create("Pago NIO 2", "bank", 0.0, "NIO")

        db.transaction.transfer_between_accounts(
            usd["id"],
            nio["id"],
            amount=20.0,
            converted_amount=730.0,
        )

        usd2 = db.account.get(usd["id"])
        nio2 = db.account.get(nio["id"])
        _assert_money(usd2["balance"], 80.0)
        _assert_money(nio2["balance"], 730.0)

    def test_transfer_cross_currency_with_fractional_converted_amount_uses_exact_cents(self, db):
        usd = db.account.create("FX USD exact", "bank", 10.00, "USD")
        nio = db.account.create("FX NIO exact", "bank", 0.00, "NIO")

        expense_tx, income_tx = db.transaction.transfer_between_accounts(
            usd["id"],
            nio["id"],
            amount=0.10,
            converted_amount=3.66,
        )

        usd2 = db.account.get(usd["id"])
        nio2 = db.account.get(nio["id"])
        tx_rows = fetch_all_dicts(
            db,
            """
            SELECT type, amount_cents, converted_amount_cents
            FROM transactions
            WHERE id IN (?, ?)
            ORDER BY id
            """,
            (expense_tx["id"], income_tx["id"]),
        )

        _assert_money(usd2["balance"], 9.90)
        _assert_money(nio2["balance"], 3.66)
        _assert_money(expense_tx["amount"], 0.10)
        _assert_money(expense_tx["converted_amount"], 3.66)
        _assert_money(income_tx["amount"], 3.66)
        assert [int(row["amount_cents"]) for row in tx_rows] == [10, 366]
        assert [int(row["converted_amount_cents"]) for row in tx_rows] == [366, 366]

    def test_transfer_same_account_raises(self, db):
        a = db.account.create("Solo", "bank", 100.0, "NIO")
        with pytest.raises(ValueError, match="different"):
            db.transaction.transfer_between_accounts(a["id"], a["id"], 50.0)

    def test_transfer_zero_amount_raises(self, db):
        a = db.account.create("A", "bank", 100.0, "NIO")
        b = db.account.create("B", "bank", 50.0, "NIO")
        with pytest.raises(ValueError, match="greater than zero"):
            db.transaction.transfer_between_accounts(a["id"], b["id"], 0.0)

    def test_transfer_negative_amount_raises(self, db):
        a = db.account.create("A2", "bank", 100.0, "NIO")
        b = db.account.create("B2", "bank", 50.0, "NIO")
        with pytest.raises(ValueError, match="greater than zero"):
            db.transaction.transfer_between_accounts(a["id"], b["id"], -10.0)

    def test_transfer_marks_is_transfer(self, db):
        a = db.account.create("Cuenta A", "bank", 500.0, "NIO")
        b = db.account.create("Cuenta B", "bank", 200.0, "NIO")

        expense_tx, income_tx = db.transaction.transfer_between_accounts(a["id"], b["id"], 100.0)

        assert int(expense_tx.get("is_transfer") or 0) == 1
        assert int(income_tx.get("is_transfer") or 0) == 1
        assert expense_tx["type"] == "expense"
        assert income_tx["type"] == "income"

    def test_transfer_description_default(self, db):
        a = db.account.create("Origen", "bank", 500.0, "NIO")
        b = db.account.create("Destino", "bank", 200.0, "NIO")

        expense_tx, income_tx = db.transaction.transfer_between_accounts(a["id"], b["id"], 50.0)

        assert "Transfer to Destino" in expense_tx["description"]
        assert "Transfer from Origen" in income_tx["description"]

    def test_transfer_description_custom(self, db):
        a = db.account.create("CuentaX", "bank", 500.0, "NIO")
        b = db.account.create("CuentaY", "bank", 200.0, "NIO")

        expense_tx, income_tx = db.transaction.transfer_between_accounts(
            a["id"],
            b["id"],
            75.0,
            description="Pago de renta",
        )

        assert expense_tx["description"] == "Pago de renta"
        assert income_tx["description"] == "Pago de renta"

    def test_transfer_date_stored(self, db):
        a = db.account.create("D1", "bank", 500.0, "NIO")
        b = db.account.create("D2", "bank", 200.0, "NIO")

        expense_tx, income_tx = db.transaction.transfer_between_accounts(
            a["id"],
            b["id"],
            30.0,
            tx_date="2025-06-15",
        )

        assert expense_tx["date"] == "2025-06-15"
        assert income_tx["date"] == "2025-06-15"

    def test_transfer_note_persisted(self, db):
        a = db.account.create("N1", "bank", 500.0, "NIO")
        b = db.account.create("N2", "bank", 200.0, "NIO")

        expense_tx, income_tx = db.transaction.transfer_between_accounts(
            a["id"],
            b["id"],
            40.0,
            note="Nota de prueba",
        )

        assert "Nota de prueba" in (expense_tx.get("note") or "")
        assert "Nota de prueba" in (income_tx.get("note") or "")

    def test_transfer_not_in_summary(self, db):
        a = db.account.create("Sum1", "bank", 1000.0, "NIO")
        b = db.account.create("Sum2", "bank", 500.0, "NIO")

        # Add a real income and expense
        db.transaction.create(account_id=a["id"], tx_type="income", amount=200.0)
        db.transaction.create(account_id=a["id"], tx_type="expense", amount=50.0)

        # Transfer should NOT affect summary totals
        db.transaction.transfer_between_accounts(a["id"], b["id"], 100.0)

        summary = db.report.summary()
        assert float(summary["total_income"]) == pytest.approx(200.0)
        assert abs(float(summary["total_expenses"])) == pytest.approx(50.0)

    def test_transfer_cross_currency_balances(self, db):
        usd = db.account.create("USD Acc", "bank", 500.0, "USD")
        eur = db.account.create("EUR Acc", "bank", 100.0, "EUR")

        db.transaction.transfer_between_accounts(
            usd["id"],
            eur["id"],
            amount=100.0,
            exchange_rate=0.92,
        )

        usd2 = db.account.get(usd["id"])
        eur2 = db.account.get(eur["id"])
        _assert_money(usd2["balance"], 400.0)
        _assert_money(eur2["balance"], 192.0)


class TestExtendedPersonalFinanceBasics:
    def test_transaction_supports_payment_method_subcategory_and_receipt(self, db):
        acc = db.account.get_or_create("Daily")
        tx = db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=15.5,
            category="Comida",
            subcategory="Delivery",
            payment_method="credit_card",
            receipt_path="/tmp/ticket.png",
        )

        assert tx["subcategory"] == "Delivery"
        assert tx["payment_method"] == "credit_card"
        assert tx["receipt_path"] == "/tmp/ticket.png"

    def test_get_transactions_supports_advanced_filters(self, db):
        acc = db.account.get_or_create("Filtro")
        db.transaction.create(account_id=acc["id"], tx_type="expense", amount=10, payment_method="cash")
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=80,
            payment_method="transfer",
        )

        txs = db.transaction.list(payment_method="transfer", min_amount=50, max_amount=90)

        assert len(txs) == 1
        assert txs[0]["payment_method"] == "transfer"

    def test_subcategories_are_supported(self, db):
        parent = db.category.create(name="Comida", cat_type="expense")
        child = db.category.create(name="Restaurantes", cat_type="expense", parent_id=parent["id"])

        children = db.category.list_subcategories(parent["id"])

        assert any(c["id"] == child["id"] for c in children)

    def test_budget_alerts_use_active_budget_monthly_progress(self, db):
        current_year = date.today().year
        current_month = date.today().month
        account = db.account.get_or_create("General")
        category = db.category.create("Ocio", "expense")
        budget = db.budget.create("alertas_test", current_year, db.setting.get_default_currency())
        db.budget.set_default_for_year(int(budget["id"]))
        db.setting.set("active_budget_code", "alertas_test")
        db.budget.upsert_amount(int(budget["id"]), int(category["id"]), current_year, current_month, 200.0)
        db.transaction.create(
            account_id=int(account["id"]),
            tx_type="expense",
            amount=160.0,
            description="Consumo ocio",
            category="Ocio",
        )

        alerts = db.report.get_budget_alerts()
        ocio_alert = next(item for item in alerts if item["name"] == "Ocio")

        assert ocio_alert["status"] == "warning"
        assert ocio_alert["progress"] == pytest.approx(0.8)
        assert "start_day" not in ocio_alert
        assert "end_day" not in ocio_alert

    def test_budget_alerts_return_empty_without_active_budget(self, db):
        db.setting.set("active_budget_code", "")
        assert db.report.get_budget_alerts() == []

    def test_budget_alerts_ignore_bucket_threshold_and_shape(self, db):
        current_year = date.today().year
        current_month = date.today().month
        account = db.account.get_or_create("General")
        category = db.category.create("Cafe", "expense")
        budget = db.budget.create("alertas_bucket_ignored", current_year, db.setting.get_default_currency())
        db.budget.set_default_for_year(int(budget["id"]))
        db.setting.set("active_budget_code", "alertas_bucket_ignored")
        db.budget.upsert_amount(int(budget["id"]), int(category["id"]), current_year, current_month, 100.0)
        db.bucket.upsert(
            "Cafe",
            100.0,
            period="custom",
            start_day=15,
            end_day=14,
            alert_threshold=0.01,
        )
        db.bucket.update_spent("Cafe", 20.0)
        db.transaction.create(
            account_id=int(account["id"]),
            tx_type="expense",
            amount=20.0,
            description="Cafe del mes",
            category="Cafe",
        )

        alert = next(item for item in db.report.get_budget_alerts() if item["name"] == "Cafe")

        assert set(alert.keys()) == {
            "name",
            "budget_amount",
            "spent_amount",
            "progress",
            "status",
        }
        assert alert["status"] == "ok"

    def test_savings_goals_track_progress(self, db):
        goal = db.savings_goal.create("Viaje a Europa", 1200.0, "2026-12-31")
        db.savings_goal.contribute(goal["id"], 300.0)

        goals = db.savings_goal.list()
        tracked = next(g for g in goals if g["id"] == goal["id"])

        _assert_money(tracked["remaining_amount"], 900.0)
        assert tracked["progress"] == pytest.approx(0.25)

    def test_savings_goal_creates_and_links_savings_category(self, db):
        goal = db.savings_goal.create("Fondo Emergencia", 1500.0)

        linked = db.savings_goal.get(goal["id"])
        assert linked["category_name"] == "Fondo Emergencia"
        assert int(linked["category_is_savings"] or 0) == 1

        category = db.category.find_by_name("Fondo Emergencia", "expense")
        assert category is not None
        assert int(category["is_savings"] or 0) == 1
        parent = db.category.get(int(category["parent_id"]))
        assert parent is not None
        assert parent["name"] == "Savings Goals"
        assert int(parent["is_savings"] or 0) == 1

    def test_savings_goal_progress_syncs_with_savings_category_transactions(self, db):
        acc = db.account.get_or_create("General")
        goal = db.savings_goal.create("Ahorro Casa", 1000.0)

        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=120.0,
            description="aporte 1",
            category="Ahorro Casa",
        )

        tracked = db.savings_goal.get(goal["id"])
        assert float(tracked["current_amount"]) == pytest.approx(120.0)

        tx = db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=30.0,
            description="aporte 2",
            category="Ahorro Casa",
        )
        tracked = db.savings_goal.get(goal["id"])
        assert float(tracked["current_amount"]) == pytest.approx(150.0)

        db.transaction.update(tx["id"], amount=50.0)
        tracked = db.savings_goal.get(goal["id"])
        assert float(tracked["current_amount"]) == pytest.approx(170.0)

        db.transaction.delete(tx["id"])
        tracked = db.savings_goal.get(goal["id"])
        assert float(tracked["current_amount"]) == pytest.approx(120.0)

    def test_savings_goal_storage_uses_exact_integer_cents(self, db):
        acc = db.account.get_or_create("General")
        goal = db.savings_goal.create("Meta Exacta", 0.30)

        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=0.10,
            description="aporte exacto 1",
            category="Meta Exacta",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=0.20,
            description="aporte exacto 2",
            category="Meta Exacta",
        )

        tracked = db.savings_goal.get(goal["id"])

        _assert_money(tracked["target_amount"], 0.30)
        _assert_money(tracked["current_amount"], 0.30)
        _assert_money(tracked["remaining_amount"], 0.0)
        assert tracked["progress"] == pytest.approx(1.0)
        row = fetch_all_dicts(
            db,
            "SELECT target_amount_cents, current_amount_cents FROM savings_goals WHERE id = ?",
            (goal["id"],),
        )[0]
        assert int(row["target_amount_cents"]) == 30
        assert int(row["current_amount_cents"]) == 30

    def test_update_transaction_rolls_back_when_savings_delta_reapply_fails(self, db, monkeypatch):
        acc = db.account.get_or_create("Atomic update")
        tx = db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=10.0,
            description="before atomic update",
            category="Comida",
        )
        original_balance = db.account.get(acc["id"])["balance"]
        original_tx = db.transaction.get(tx["id"])

        def _boom(_tx: dict | None, sign: int) -> None:
            if sign > 0:
                raise RuntimeError("reapply failed")

        monkeypatch.setattr(db._backend, "_apply_savings_goal_delta_for_transaction", _boom)

        with pytest.raises(RuntimeError, match="reapply failed"):
            db.transaction.update(tx["id"], amount=25.0, description="should rollback")

        assert db.account.get(acc["id"])["balance"] == pytest.approx(original_balance)
        assert db.transaction.get(tx["id"])["amount"] == pytest.approx(original_tx["amount"])
        assert db.transaction.get(tx["id"])["description"] == original_tx["description"]

    def test_delete_transaction_rolls_back_when_goal_delta_fails(self, db, monkeypatch):
        acc = db.account.get_or_create("Atomic delete")
        tx = db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=12.5,
            description="before atomic delete",
            category="Comida",
        )
        original_balance = db.account.get(acc["id"])["balance"]

        def _boom(_tx: dict | None, sign: int) -> None:
            if sign < 0:
                raise RuntimeError("delete delta failed")

        monkeypatch.setattr(db._backend, "_apply_savings_goal_delta_for_transaction", _boom)

        with pytest.raises(RuntimeError, match="delete delta failed"):
            db.transaction.delete(tx["id"])

        assert db.account.get(acc["id"])["balance"] == pytest.approx(original_balance)
        assert db.transaction.get(tx["id"]) is not None

    def test_seed_updates_default_savings_goal_currency_to_default_currency(self, db):
        db.setting.set("default_currency", "USD")
        db.setting.seed_initial_data(include_default_categories=True, account_names=None)

        goal = db.savings_goal.find_by_name("Savings")
        assert goal is not None
        assert goal["currency"] == "USD"
        assert goal["category_name"] == "Savings"
        assert int(goal["category_is_savings"] or 0) == 1
        savings = db.category.find_by_name("Savings", "expense")
        parent = db.category.get(int(savings["parent_id"]))
        assert parent is not None
        assert parent["name"] == "Savings Goals"

    def test_delete_savings_goal(self, db):
        goal = db.savings_goal.create("Delete Me", 500.0)
        db.savings_goal.delete(goal["id"])

        goals = db.savings_goal.list()
        assert not any(g["id"] == goal["id"] for g in goals)
        assert db.category.find_by_name("Delete Me", "expense") is None
        assert db.category.find_by_name("Savings Goals", "expense") is not None

    def test_update_savings_goal_preserves_current_amount(self, db):
        goal = db.savings_goal.create("Old Name", 1000.0, "2026-12-31")
        db.savings_goal.contribute(goal["id"], 150.0)

        updated = db.savings_goal.update(
            goal["id"],
            name="New Name",
            target_amount=1200.0,
            target_date="2027-01-15",
        )

        assert updated["name"] == "New Name"
        _assert_money(updated["target_amount"], 1200.0)
        _assert_money(updated["current_amount"], 150.0)
        assert updated["category_name"] == "New Name"
        assert db.category.find_by_name("Old Name", "expense") is not None
        new_category = db.category.find_by_name("New Name", "expense")
        assert new_category is not None
        parent = db.category.get(int(new_category["parent_id"]))
        assert parent is not None
        assert parent["name"] == "Savings Goals"

        db.close()
        reopened = Database(path=db.path)
        reopened.connect()
        try:
            linked = reopened.savings_goal.get(goal["id"])
            category = reopened.category.find_by_name("New Name", "expense")
            assert linked["category_name"] == "New Name"
            assert category is not None
            parent = reopened.category.get(int(category["parent_id"]))
            assert parent is not None
            assert parent["name"] == "Savings Goals"
        finally:
            reopened.close()

    def test_delete_savings_goal_with_transaction_history_is_blocked(self, db):
        acc = db.account.get_or_create("General")
        goal = db.savings_goal.create("Protected Goal", 700.0)
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=80.0,
            description="aporte protegido",
            category="Protected Goal",
        )

        with pytest.raises(ValueError, match="transaction history"):
            db.savings_goal.delete(goal["id"])

        assert db.savings_goal.get(goal["id"])["name"] == "Protected Goal"
        assert db.category.find_by_name("Protected Goal", "expense") is not None

    def test_savings_goals_parent_category_counts_as_savings(self, db):
        acc = db.account.get_or_create("General")
        goal = db.savings_goal.create("Trip Goal", 1200.0)
        parent_name = db.setting.get_savings_goals_parent_name()

        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=45.0,
            description="grouped savings",
            category=parent_name,
        )

        summary = db.report.summary()

        _assert_money(summary["savings"], 45.0)
        _assert_money(db.savings_goal.get(goal["id"])["current_amount"], 0.0)


# ---------------------------------------------------------------------------
# Recurring
# ---------------------------------------------------------------------------


class TestRecurring:
    def test_apply_recurring_for_selected_period_creates_transactions(self, db):
        acc = db.account.get_or_create("General")
        category = db.category.get_or_create("entertainment", "expense")
        recurring_tag = db.tag.create("Streaming")
        db.recurring.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=35.0,
            description="Netflix",
            category=None,
            category_id=category["id"],
            tag_ids=[int(recurring_tag["id"])],
            note=None,
            day_of_month=31,
        )

        created = db.recurring.apply_for_month(2025, 2)

        assert len(created) == 1
        assert created[0]["date"] == "2025-02-28"
        assert created[0]["category_id"] == category["id"]
        assert {int(tag["id"]) for tag in db.tag.list_for_transaction(int(created[0]["id"]))} == {
            int(recurring_tag["id"])
        }

    def test_apply_recurring_for_selected_period_is_idempotent(self, db):
        acc = db.account.get_or_create("General")
        category = db.category.get_or_create("salary", "income")
        db.recurring.create(
            account_id=acc["id"],
            tx_type="income",
            amount=1000.0,
            description="Salary",
            category=None,
            category_id=category["id"],
            note=None,
            day_of_month=1,
        )

        first = db.recurring.apply_for_month(2025, 3)
        second = db.recurring.apply_for_month(2025, 3)

        assert len(first) == 1
        assert second == []

    def test_apply_recurring_for_month_validates_inputs(self, db):
        with pytest.raises(ValueError):
            db.recurring.apply_for_month(2025, 13)
        with pytest.raises(ValueError):
            db.recurring.apply_for_month(1800, 1)

    def test_apply_recurring_for_month_rolls_back_all_transactions_on_partial_failure(self, db, monkeypatch):
        acc = db.account.get_or_create("General")
        income_category = db.category.get_or_create("salary", "income")
        expense_category = db.category.get_or_create("rent", "expense")
        db.recurring.create(
            account_id=acc["id"],
            tx_type="income",
            amount=1000.0,
            description="Salary",
            category=None,
            category_id=income_category["id"],
            note=None,
            day_of_month=1,
        )
        db.recurring.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=450.0,
            description="Rent",
            category=None,
            category_id=expense_category["id"],
            note=None,
            day_of_month=2,
        )

        original_add_transaction = db._backend.add_transaction
        calls = {"count": 0}

        def _fail_on_second_transaction(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("boom")
            return original_add_transaction(*args, **kwargs)

        monkeypatch.setattr(db._backend, "add_transaction", _fail_on_second_transaction)

        with pytest.raises(RuntimeError, match="boom"):
            db.recurring.apply_for_month(2025, 3)

        assert db.transaction.list() == []
        assert db.setting.get("recurring_applied_2025-03") is None

    def test_update_recurring_changes_rule_fields(self, db):
        acc1 = db.account.get_or_create("Main")
        acc2 = db.account.get_or_create("Savings")
        expense_category = db.category.get_or_create("entertainment", "expense")
        income_category = db.category.get_or_create("salary", "income")
        recurring_tag = db.tag.create("Monthly")
        refund_tag = db.tag.create("Refund")
        rec = db.recurring.create(
            account_id=acc1["id"],
            tx_type="expense",
            amount=20.0,
            description="Streaming",
            category=None,
            category_id=expense_category["id"],
            tag_ids=[int(recurring_tag["id"])],
            note="monthly",
            day_of_month=5,
        )

        updated = db.recurring.update(
            rec["id"],
            account_id=acc2["id"],
            tx_type="income",
            amount=45.0,
            description="Refund",
            category=None,
            category_id=income_category["id"],
            tag_ids=[int(refund_tag["id"])],
            note="updated",
            day_of_month=10,
        )

        assert updated["account_id"] == acc2["id"]
        assert updated["type"] == "income"
        _assert_money(updated["amount"], 45.0)
        assert updated["description"] == "Refund"
        assert updated["category"] == income_category["name"]
        assert updated["category_id"] == income_category["id"]
        assert {int(tag_id) for tag_id in updated["tag_ids"]} == {int(refund_tag["id"])}
        assert updated["day_of_month"] == 10

    def test_set_recurring_tags_rolls_back_on_partial_failure(self, db, monkeypatch):
        acc = db.account.get_or_create("General")
        category = db.category.get_or_create("salary", "income")
        old_tag = db.tag.create("Old Tag")
        keep_tag = db.tag.create("Keep Tag")
        new_tag = db.tag.create("New Tag")
        extra_tag = db.tag.create("Extra Tag")
        recurring = db.recurring.create(
            account_id=acc["id"],
            tx_type="income",
            amount=1000.0,
            description="Salary",
            category=None,
            category_id=category["id"],
            tag_ids=[int(old_tag["id"]), int(keep_tag["id"])],
            note=None,
            day_of_month=1,
        )

        original_insert = tag_repository_module.RecurringTransactionTag.insert
        calls = {"count": 0}

        class _BrokenInsert:
            def on_conflict_ignore(self):
                return self

            def execute(self):
                raise RuntimeError("boom")

        def _insert(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                return _BrokenInsert()
            return original_insert(*args, **kwargs)

        monkeypatch.setattr(tag_repository_module.RecurringTransactionTag, "insert", _insert)

        with pytest.raises(RuntimeError, match="boom"):
            db.tag.set_for_recurring(int(recurring["id"]), [int(new_tag["id"]), int(extra_tag["id"])])

        remaining_tag_ids = {int(tag["id"]) for tag in db.tag.list_for_recurring(int(recurring["id"]))}
        assert remaining_tag_ids == {int(old_tag["id"]), int(keep_tag["id"])}

    def test_recurring_category_link_uses_category_id_after_rename(self, db):
        acc = db.account.get_or_create("General")
        category = db.category.get_or_create("entertainment", "expense")

        rec = db.recurring.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=20.0,
            description="Streaming",
            category=None,
            category_id=category["id"],
            note=None,
            day_of_month=5,
        )

        db.category.update(
            category["id"],
            name="Streaming & Fun",
            cat_type=category["type"],
            color=category["color"],
            icon=category["icon"],
            parent_id=category.get("parent_id"),
        )
        renamed = db.category.get(category["id"])
        assert renamed is not None
        recurring = db.recurring.list()

        assert rec["category_id"] == renamed["id"]
        assert recurring[0]["category_id"] == renamed["id"]
        assert recurring[0]["category_name"] == "Streaming & Fun"

    def test_get_recurring_exposes_tag_metadata(self, db):
        acc = db.account.get_or_create("General")
        category = db.category.get_or_create("entertainment", "expense")
        fixed = db.tag.create("Fixed")
        fun = db.tag.create("Fun")

        db.recurring.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=20.0,
            description="Streaming",
            category=None,
            category_id=category["id"],
            tag_ids=[int(fixed["id"]), int(fun["id"])],
            note=None,
            day_of_month=5,
        )

        recurring = db.recurring.list()

        assert len(recurring) == 1
        assert {int(tag_id) for tag_id in recurring[0]["tag_ids"]} == {
            int(fixed["id"]),
            int(fun["id"]),
        }
        assert {str(tag["name"]) for tag in recurring[0]["tags"]} == {"Fixed", "Fun"}
        assert recurring[0]["tag_names"] == "Fixed, Fun"


# ---------------------------------------------------------------------------
# Database indexes
# ---------------------------------------------------------------------------


class TestDatabaseIndexes:
    def test_indexes_exist_on_transactions(self, db):
        """Verify that performance indexes are present on the transactions table."""
        rows = fetch_all_dicts(db, "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='transactions'")
        index_names = {row["name"] for row in rows}
        assert "idx_transactions_account_id" in index_names
        assert "idx_transactions_date" in index_names
        assert "idx_transactions_type" in index_names
        assert "idx_transactions_category" in index_names
        assert "idx_transactions_date_type" in index_names

    def test_indexes_exist_on_budget_detail(self, db):
        """Verify that performance indexes are present on the budget_detail table."""
        rows = fetch_all_dicts(db, "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='budget_detail'")
        index_names = {row["name"] for row in rows}
        assert "idx_budget_detail_budget_id" in index_names
        assert "idx_budget_detail_category_id" in index_names

    def test_indexes_exist_on_categories(self, db):
        """Verify that performance indexes are present on the categories table."""
        rows = fetch_all_dicts(db, "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='categories'")
        index_names = {row["name"] for row in rows}
        assert "idx_categories_type" in index_names
        assert "idx_categories_is_savings" in index_names


# ---------------------------------------------------------------------------
# Backup and restore
# ---------------------------------------------------------------------------


class TestBackupRestore:
    def test_backup_creates_valid_sqlite_file(self, db, tmp_path):
        """backup_to writes a valid SQLite file that contains all tables."""
        acc = db.account.get_or_create("Cuenta Principal")
        db.transaction.create(account_id=acc["id"], tx_type="income", amount=500.0, description="Salario")
        db.transaction.create(account_id=acc["id"], tx_type="expense", amount=100.0, description="Renta")

        backup_path = tmp_path / "backup.db"
        result = db.backup.create(backup_path)

        assert result == backup_path
        assert backup_path.is_file()

        # Verify the backup is a readable SQLite DB with correct data
        with sqlite3.connect(str(backup_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM transactions ORDER BY id").fetchall()
        assert len(rows) == 2
        assert rows[0]["description"] == "Salario"
        assert rows[1]["description"] == "Renta"

    def test_backup_rejects_same_path(self, db, tmp_path):
        """backup_to raises ValueError when source and destination are the same file."""
        with pytest.raises(ValueError):
            db.backup.create(db.path)

    def test_restore_replaces_database_content(self, db, tmp_path):
        """restore_from overwrites current DB content with backup data."""
        # Populate the original DB with one transaction
        acc = db.account.get_or_create("General")
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=2000.0,
            description="Original",
        )

        # Create a backup
        backup_path = tmp_path / "snapshot.db"
        db.backup.create(backup_path)

        # Add a second transaction AFTER the backup
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=50.0,
            description="Post-backup",
        )

        assert len(db.transaction.list()) == 2

        # Restore from the backup (which only had 1 transaction)
        restored_result = db.backup.restore(backup_path)

        restored = db.transaction.list()
        assert restored_result.restored_from == backup_path
        assert restored_result.migration_applied is False
        assert len(restored) == 1
        assert restored[0]["description"] == "Original"

    def test_restore_raises_for_missing_file(self, db, tmp_path):
        """restore_from raises FileNotFoundError for a non-existent backup."""
        with pytest.raises(FileNotFoundError):
            db.backup.restore(tmp_path / "nonexistent.db")

    def test_restore_rolls_back_when_backup_source_is_invalid(self, db, tmp_path):
        """restore_from rolls back when sqlite backup fails."""
        acc = db.account.get_or_create("General")
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=150.0,
            description="Before restore",
        )
        invalid_backup = tmp_path / "invalid_backup.db"
        invalid_backup.write_text("not a sqlite file", encoding="utf-8")

        with pytest.raises(DatabaseSchemaError, match="not a valid MIRA backup"):
            db.backup.restore(invalid_backup)

        restored = db.transaction.list()
        assert len(restored) == 1
        assert restored[0]["description"] == "Before restore"

    def test_restore_rejects_legacy_float_money_backup(self, db, tmp_path):
        legacy_backup = tmp_path / "legacy_backup.db"
        _create_legacy_float_database(legacy_backup)

        with pytest.raises(DatabaseSchemaError, match="Pre-0.0.1a2 backups remain unsupported"):
            db.backup.restore(legacy_backup)

    def test_backup_restore_round_trip_preserves_all_data(self, db, tmp_path):
        """Full round-trip: backup a fully-seeded DB and restore into a fresh one."""
        db.setting.seed_initial_data(include_default_categories=True, account_names=[])
        acc = db.account.get_or_create("Backup Test")
        goal = db.savings_goal.create("Meta de ahorro", 5000.0, "2027-12-31")
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=3000.0,
            description="Backup income",
        )
        db.savings_goal.contribute(goal["id"], 200.0)

        # Capture the state before backup
        txs_before = db.transaction.list()
        goals_before = db.savings_goal.list()
        categories_before = db.category.list()

        backup_path = tmp_path / "full_backup.db"
        db.backup.create(backup_path)

        # Restore into a fresh database
        db.close()
        fresh_db = Database(path=tmp_path / "restored.db")
        fresh_db.connect()
        fresh_db.backup.restore(backup_path)

        txs_after = fresh_db.transaction.list()
        goals_after = fresh_db.savings_goal.list()
        categories_after = fresh_db.category.list()

        fresh_db.close()

        assert len(txs_after) == len(txs_before)
        assert len(goals_after) == len(goals_before)
        assert len(categories_after) == len(categories_before)

        # Verify goal progress survived
        restored_goal = next(g for g in goals_after if g["name"] == "Meta de ahorro")
        assert float(restored_goal["current_amount"]) == pytest.approx(200.0)

    def test_restore_rejects_sqlite_file_that_is_not_a_mira_backup(self, db, tmp_path):
        backup_path = tmp_path / "not_mira.db"
        _create_non_mira_sqlite_database(backup_path)

        with pytest.raises(DatabaseSchemaError, match="not a valid MIRA backup"):
            db.backup.restore(backup_path)

    def test_restore_runs_registered_migration_for_supported_schema(self, monkeypatch, db, tmp_path):
        source_path = tmp_path / "migratable_source.db"
        account = db.account.get_or_create("General")
        db.transaction.create(
            account_id=account["id"],
            tx_type="income",
            amount=275.0,
            description="Migrated restore",
        )
        db.backup.create(source_path)
        _set_user_version(source_path, SCHEMA_VERSION - 1)

        applied: list[int] = []

        def _migration(conn: sqlite3.Connection) -> None:
            applied.append(1)
            conn.execute("CREATE TABLE IF NOT EXISTS restore_migration_probe (id INTEGER PRIMARY KEY AUTOINCREMENT)")

        monkeypatch.setattr(db_migrations, "MIN_MIGRATABLE_SCHEMA_VERSION", SCHEMA_VERSION - 1)
        monkeypatch.setattr(db_migrations, "MIGRATIONS", {SCHEMA_VERSION - 1: _migration})

        result = db.backup.restore(source_path)

        assert result.restored_from == source_path
        assert result.source_schema_version == SCHEMA_VERSION - 1
        assert result.target_schema_version == SCHEMA_VERSION
        assert result.migration_applied is True
        assert applied == [1]
        restored = db.transaction.list(limit=10)
        assert len(restored) == 1
        assert restored[0]["description"] == "Migrated restore"
        with sqlite3.connect(db.path) as conn:
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'restore_migration_probe'"
                ).fetchall()
            }
        assert tables == {"restore_migration_probe"}

    def test_restore_rejects_supported_schema_when_migration_step_is_missing(self, monkeypatch, db, tmp_path):
        backup_path = tmp_path / "missing-migration-backup.db"
        db.backup.create(backup_path)
        _set_user_version(backup_path, SCHEMA_VERSION - 1)

        existing_account = db.account.get_or_create("General")
        db.transaction.create(
            account_id=existing_account["id"],
            tx_type="income",
            amount=99.0,
            description="Before failed restore",
        )

        monkeypatch.setattr(db_migrations, "MIN_MIGRATABLE_SCHEMA_VERSION", SCHEMA_VERSION - 1)
        monkeypatch.setattr(db_migrations, "MIGRATIONS", {})

        with pytest.raises(DatabaseSchemaError, match="No migration path exists"):
            db.backup.restore(backup_path)

        restored = db.transaction.list(limit=10)
        assert len(restored) == 1
        assert restored[0]["description"] == "Before failed restore"


# ---------------------------------------------------------------------------
# CSV import / export
# ---------------------------------------------------------------------------


class TestCSVImportExport:
    def test_export_creates_csv_with_headers_and_rows(self, db, tmp_path):
        """export_transactions_csv writes a valid CSV with expected columns."""
        acc = db.account.get_or_create("Cuenta Export")
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=1500.0,
            description="Salario mensual",
            category="Ingresos",
            tx_date="2026-01-10",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=300.0,
            description="Supermercado",
            category="Alimentación",
            tx_date="2026-01-15",
        )

        csv_path = tmp_path / "export.csv"
        db.io.export_transactions_csv(str(csv_path))

        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)

        assert len(rows) == 2
        assert set(rows[0].keys()) >= {
            "id",
            "date",
            "type",
            "amount",
            "description",
            "category",
        }
        income_row = next(r for r in rows if r["type"] == "income")
        expense_row = next(r for r in rows if r["type"] == "expense")
        assert float(income_row["amount"]) == pytest.approx(1500.0)
        assert float(expense_row["amount"]) == pytest.approx(300.0)
        assert income_row["description"] == "Salario mensual"

    def test_export_filter_by_type(self, db, tmp_path):
        """export_transactions_csv respects tx_type filter."""
        acc = db.account.get_or_create("Cuenta Filtro")
        db.transaction.create(account_id=acc["id"], tx_type="income", amount=800.0, description="Bonus")
        db.transaction.create(account_id=acc["id"], tx_type="expense", amount=200.0, description="Renta")

        csv_path = tmp_path / "only_expenses.csv"
        db.io.export_transactions_csv(str(csv_path), tx_type="expense")

        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)

        assert all(r["type"] == "expense" for r in rows)
        assert len(rows) == 1
        assert rows[0]["description"] == "Renta"

    def test_import_creates_transactions_from_csv(self, db, tmp_path):
        """import_transactions_csv reads rows and creates transactions in the DB."""
        csv_path = tmp_path / "import.csv"
        fieldnames = [
            "date",
            "type",
            "amount",
            "description",
            "category",
            "account_name",
        ]
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(
                {
                    "date": "2026-02-01",
                    "type": "income",
                    "amount": "2500.0",
                    "description": "Salario Feb",
                    "category": "Salario",
                    "account_name": "General",
                }
            )
            writer.writerow(
                {
                    "date": "2026-02-05",
                    "type": "expense",
                    "amount": "75.0",
                    "description": "Internet",
                    "category": "Telecomunicaciones",
                    "account_name": "General",
                }
            )

        imported, errors = db.io.import_transactions_csv(str(csv_path))

        assert imported == 2
        assert errors == 0
        txs = db.transaction.list()
        assert len(txs) == 2
        amounts = {float(t["amount"]) for t in txs}
        assert amounts == {2500.0, 75.0}

    def test_import_skips_invalid_rows_and_counts_errors(self, db, tmp_path):
        """import_transactions_csv skips rows with bad type or non-positive amount."""
        csv_path = tmp_path / "bad_rows.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["date", "type", "amount", "description"])
            writer.writeheader()
            writer.writerow(
                {
                    "date": "2026-03-01",
                    "type": "income",
                    "amount": "500.0",
                    "description": "OK row",
                }
            )
            writer.writerow(
                {
                    "date": "2026-03-02",
                    "type": "transfer",
                    "amount": "100.0",
                    "description": "Bad type",
                }
            )
            writer.writerow(
                {
                    "date": "2026-03-03",
                    "type": "expense",
                    "amount": "-50",
                    "description": "Negative",
                }
            )
            writer.writerow(
                {
                    "date": "2026-03-04",
                    "type": "expense",
                    "amount": "0",
                    "description": "Zero",
                }
            )

        imported, errors = db.io.import_transactions_csv(str(csv_path))

        assert imported == 1
        assert errors == 3

    def test_export_import_round_trip_preserves_amounts(self, db, tmp_path):
        """Round-trip: export then re-import produces the same transaction amounts."""
        acc = db.account.get_or_create("Round Trip")
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=4000.0,
            description="Sueldo",
            category="Salario",
            tx_date="2026-01-05",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=1200.0,
            description="Alquiler",
            category="Vivienda",
            tx_date="2026-01-10",
        )

        csv_path = tmp_path / "round_trip.csv"
        db.io.export_transactions_csv(str(csv_path))

        # Import into a fresh DB
        db.close()
        fresh_db = Database(path=tmp_path / "fresh.db")
        fresh_db.connect()
        fresh_db.io.import_transactions_csv(str(csv_path))
        txs = fresh_db.transaction.list()
        fresh_db.close()

        assert len(txs) == 2
        amounts = {float(t["amount"]) for t in txs}
        assert amounts == {4000.0, 1200.0}

    def test_export_import_round_trip_preserves_fractional_cents_exactly(self, db, tmp_path):
        acc = db.account.get_or_create("Round Trip Exact")
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=1000.10,
            description="Exact salary",
            category="Salario",
            tx_date="2026-02-05",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=300.20,
            description="Exact rent",
            category="Vivienda",
            tx_date="2026-02-10",
        )

        csv_path = tmp_path / "round_trip_exact.csv"
        db.io.export_transactions_csv(str(csv_path))

        with open(csv_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))

        amounts = {float(row["amount"]) for row in rows}
        assert sorted(amounts) == pytest.approx([300.20, 1000.10])

        db.close()
        fresh_db = Database(path=tmp_path / "fresh_exact.db")
        fresh_db.connect()
        try:
            fresh_db.io.import_transactions_csv(str(csv_path))
            txs = fresh_db.transaction.list()
            assert len(txs) == 2
            tx_amounts = {float(tx["amount"]) for tx in txs}
            assert sorted(tx_amounts) == pytest.approx([300.20, 1000.10])
            stored = fetch_all_dicts(
                fresh_db,
                "SELECT amount_cents FROM transactions ORDER BY amount_cents",
            )
            assert [int(row["amount_cents"]) for row in stored] == [30020, 100010]
        finally:
            fresh_db.close()


# ---------------------------------------------------------------------------
# Savings goal: category change updates goal accumulation
# ---------------------------------------------------------------------------


class TestSavingsGoalCategoryChange:
    def test_changing_category_to_savings_adds_to_goal(self, db):
        """Editing a transaction to a savings category correctly adds to the goal."""
        acc = db.account.get_or_create("General")
        goal = db.savings_goal.create("Meta viaje", 2000.0)

        # Start with a regular expense (non-savings)
        tx = db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=500.0,
            description="Gasto regular",
            category="Alimentación",
        )

        # Goal should not have been touched yet
        g = db.savings_goal.get(goal["id"])
        assert float(g["current_amount"]) == pytest.approx(0.0)

        # Change category to the savings goal's linked savings category
        db.transaction.update(tx["id"], category="Meta viaje")

        g = db.savings_goal.get(goal["id"])
        assert float(g["current_amount"]) == pytest.approx(500.0)

    def test_changing_category_away_from_savings_removes_from_goal(self, db):
        """Editing a transaction's category from savings to regular reverses the goal update."""
        acc = db.account.get_or_create("General")
        goal = db.savings_goal.create("Fondo vivienda", 5000.0)

        # Add a savings transaction
        tx = db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=800.0,
            description="Ahorro casa",
            category="Fondo vivienda",
        )

        g = db.savings_goal.get(goal["id"])
        assert float(g["current_amount"]) == pytest.approx(800.0)

        # Change category to a non-savings category
        db.transaction.update(tx["id"], category="Alimentación")

        g = db.savings_goal.get(goal["id"])
        assert float(g["current_amount"]) == pytest.approx(0.0)

    def test_changing_between_two_savings_categories_updates_both_goals(self, db):
        """Changing from one savings category to another updates both goals correctly."""
        acc = db.account.get_or_create("General")
        goal_a = db.savings_goal.create("Meta A", 1000.0)
        goal_b = db.savings_goal.create("Meta B", 2000.0)

        tx = db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=300.0,
            description="Aporte inicial",
            category="Meta A",
        )

        assert float(db.savings_goal.get(goal_a["id"])["current_amount"]) == pytest.approx(300.0)
        assert float(db.savings_goal.get(goal_b["id"])["current_amount"]) == pytest.approx(0.0)

        # Move contribution from goal A to goal B
        db.transaction.update(tx["id"], category="Meta B")

        assert float(db.savings_goal.get(goal_a["id"])["current_amount"]) == pytest.approx(0.0)
        assert float(db.savings_goal.get(goal_b["id"])["current_amount"]) == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# Savings goal category protections
# ---------------------------------------------------------------------------


class TestSavingsGoalCategoryProtections:
    def test_linked_savings_category_cannot_be_renamed(self, db):
        goal = db.savings_goal.create("Meta Protegida", 800.0)
        category = db.category.find_by_name("Meta Protegida", "expense")

        with pytest.raises(ValueError, match="cannot be renamed"):
            db.category.update(
                int(category["id"]),
                "Meta Renombrada",
                "expense",
                str(category["color"]),
                is_savings=True,
                parent_id=category.get("parent_id"),
                icon=str(category.get("icon") or ""),
            )

        assert db.savings_goal.get(goal["id"])["category_name"] == "Meta Protegida"

    def test_linked_savings_category_cannot_change_type_or_savings_flag(self, db):
        db.savings_goal.create("Meta Blindada", 600.0)
        category = db.category.find_by_name("Meta Blindada", "expense")

        with pytest.raises(ValueError, match="cannot change type"):
            db.category.update(
                int(category["id"]),
                "Meta Blindada",
                "income",
                str(category["color"]),
                is_savings=True,
                parent_id=category.get("parent_id"),
                icon=str(category.get("icon") or ""),
            )

        with pytest.raises(ValueError, match="must remain a savings category"):
            db.category.update(
                int(category["id"]),
                "Meta Blindada",
                "expense",
                str(category["color"]),
                is_savings=False,
                parent_id=category.get("parent_id"),
                icon=str(category.get("icon") or ""),
            )

    def test_linked_savings_category_allows_cosmetic_updates(self, db):
        db.savings_goal.create("Meta Visual", 400.0)
        category = db.category.find_by_name("Meta Visual", "expense")

        db.category.update(
            int(category["id"]),
            "Meta Visual",
            "expense",
            "#123456",
            is_savings=True,
            parent_id=category.get("parent_id"),
            icon="MV",
        )

        updated = db.category.find_by_name("Meta Visual", "expense")
        assert updated["color"] == "#123456"
        assert updated["icon"] == "MV"

    def test_linked_savings_category_cannot_be_deleted_or_merged(self, db):
        db.savings_goal.create("Meta Fija", 1000.0)
        category = db.category.find_by_name("Meta Fija", "expense")
        other = db.category.create("Otra Categoria", "expense")

        with pytest.raises(ValueError, match="cannot be deleted"):
            db.category.delete(int(category["id"]))

        with pytest.raises(ValueError, match="cannot be merged"):
            db.category.merge(int(category["id"]), int(other["id"]))

        with pytest.raises(ValueError, match="cannot be merged"):
            db.category.merge(int(other["id"]), int(category["id"]))

    def test_savings_goals_parent_category_is_reserved(self, db):
        db.savings_goal.create("Meta Padre", 1000.0)
        parent = db.category.find_by_name("Savings Goals", "expense")

        with pytest.raises(ValueError, match="reserved"):
            db.category.delete(int(parent["id"]))

        with pytest.raises(ValueError, match="reserved"):
            db.category.update(
                int(parent["id"]),
                "Savings Goals Renamed",
                "expense",
                str(parent["color"]),
                is_savings=True,
                parent_id=parent.get("parent_id"),
                icon=str(parent.get("icon") or ""),
            )


# ---------------------------------------------------------------------------
# Seeded categories: no duplicate savings-related category
# ---------------------------------------------------------------------------


class TestSeededCategoriesSavings:
    def test_seed_has_expected_savings_expense_categories(self, db):
        """seed_initial_data must include the comprehensive savings/investment category set."""
        db.setting.seed_initial_data(include_default_categories=True, account_names=None)
        expense_cats = db.category.list(cat_type="expense", include_savings=True)
        savings_cats = [c for c in expense_cats if int(c.get("is_savings") or 0) == 1]
        savings_names = sorted(c["name"] for c in savings_cats)
        expected = sorted(
            [
                "Emergency Fund",
                "Investment Savings",
                "Retirement or Investments Plan",
                "Savings",
                "Savings Goals",
                "Specific Savings Goals",
            ]
        )
        assert savings_names == expected

    def test_seed_links_default_savings_goal_to_seeded_savings_category(self, db):
        db.setting.seed_initial_data(include_default_categories=True, account_names=None)

        goal = db.savings_goal.find_by_name("Savings")

        assert goal is not None
        assert goal["category_name"] == "Savings"
        assert int(goal["category_is_savings"] or 0) == 1

    def test_ahorro_inversion_is_not_seeded(self, db):
        """'Ahorro / Inversión' must not appear in the seeded default categories."""
        db.setting.seed_initial_data(include_default_categories=True, account_names=None)
        all_cats = db.category.list(include_savings=True)
        names = [c["name"] for c in all_cats]
        assert "Ahorro / Inversión" not in names


# ---------------------------------------------------------------------------
# Reports: income / expense totals validated against known transactions
# ---------------------------------------------------------------------------


class TestReportsRealData:
    def _populate(self, db: Database):
        """Seed a controlled set of transactions for deterministic report assertions."""
        acc = db.account.get_or_create("Banco Principal")
        db.category.create("Salario", "income")
        db.category.create("Freelance", "income")
        db.category.create("Vivienda", "expense")
        db.category.create("Alimentación", "expense")
        db.category.create("Transporte", "expense")
        db.category.create("Ahorro Test", "expense", is_savings=True)

        # January 2026 – income: 3000, real expenses: 800, savings: 200
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=2500.0,
            category="Salario",
            tx_date="2026-01-05",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=500.0,
            category="Freelance",
            tx_date="2026-01-10",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=600.0,
            category="Vivienda",
            tx_date="2026-01-12",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=200.0,
            category="Alimentación",
            tx_date="2026-01-18",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=200.0,
            category="Ahorro Test",
            tx_date="2026-01-20",
        )

        # February 2026 – income: 2800, real expenses: 950, savings: 150
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=2800.0,
            category="Salario",
            tx_date="2026-02-05",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=800.0,
            category="Vivienda",
            tx_date="2026-02-10",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=150.0,
            category="Transporte",
            tx_date="2026-02-15",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=150.0,
            category="Ahorro Test",
            tx_date="2026-02-20",
        )

        return acc

    def test_summary_total_income_excludes_no_incomes(self, db):
        """Total income equals all income transactions combined."""
        self._populate(db)
        summary = db.report.summary()
        _assert_money(summary["total_income"], 2500.0 + 500.0 + 2800.0)

    def test_summary_total_expenses_excludes_savings(self, db):
        """Total expenses must not include savings-category transactions."""
        self._populate(db)
        summary = db.report.summary()
        # Real expenses: 600+200 (Jan) + 800+150 (Feb) = 1750
        _assert_money(summary["total_expenses"], 600.0 + 200.0 + 800.0 + 150.0)

    def test_summary_savings_tracks_savings_category_transactions(self, db):
        """Savings total exposes savings-category outflows separately."""
        self._populate(db)
        summary = db.report.summary()
        _assert_money(summary["savings"], 200.0 + 150.0)

    def test_summary_net_equals_income_minus_real_expenses(self, db):
        """Net balance = total income − real expenses (savings excluded)."""
        self._populate(db)
        summary = db.report.summary()
        expected_net = (2500.0 + 500.0 + 2800.0) - (600.0 + 200.0 + 800.0 + 150.0)
        _assert_money(summary["net"], expected_net)

    def test_category_summary_amounts_match_per_category(self, db):
        """get_category_summary returns correct per-category totals."""
        self._populate(db)
        rows = {r["category"]: r for r in db.report.category_summary()}

        assert "Salario" in rows
        _assert_money(rows["Salario"]["total_income"], 2500.0 + 2800.0)
        assert "Freelance" in rows
        _assert_money(rows["Freelance"]["total_income"], 500.0)
        assert "Vivienda" in rows
        _assert_money(rows["Vivienda"]["total_expenses"], 600.0 + 800.0)
        assert "Alimentación" in rows
        _assert_money(rows["Alimentación"]["total_expenses"], 200.0)
        # Savings category must be absent from category summary
        assert "Ahorro Test" not in rows

    def test_category_summary_filter_by_date_range(self, db):
        """get_category_summary respects since_date filter."""
        self._populate(db)
        # Only February data
        rows = {r["category"]: r for r in db.report.category_summary(since_date="2026-02-01")}
        assert "Salario" in rows
        _assert_money(rows["Salario"]["total_income"], 2800.0)
        assert "Freelance" not in rows  # January only

    def test_account_balance_after_transactions(self, db):
        """Account balance reflects income minus all expenses (including savings outflows)."""
        acc = self._populate(db)
        refreshed = db.account.get(acc["id"])
        # Income: 5800 − expenses: 1750 − savings outflows: 350
        expected_balance = (2500 + 500 + 2800) - (600 + 200 + 800 + 150 + 200 + 150)
        assert float(refreshed["balance"]) == pytest.approx(expected_balance)


class TestAccountBalanceReport:
    def test_balance_report_includes_credit_accounts_and_consolidated_total(self, db):
        db.account.create("Caja", "cash", 300.0, "NIO")
        db.account.create("Visa", "credit", -120.0, "USD")

        report = db.account.get_balance_report()
        rows = {row["name"]: row for row in report["rows"]}

        assert rows["Caja"]["account_type"] == "cash"
        _assert_money(rows["Caja"]["balance"], 300.0)
        assert rows["Visa"]["account_type"] == "credit"
        _assert_money(rows["Visa"]["balance"], -120.0)
        assert float(report["consolidated_total"]) == pytest.approx(180.0)


# ---------------------------------------------------------------------------
# Referential integrity and connection isolation
# ---------------------------------------------------------------------------


class TestDatabaseIntegrity:
    def test_delete_transaction_cascades_transaction_tags(self, db):
        acc = db.account.get_or_create("General")
        tx = db.transaction.create(
            account_id=int(acc["id"]),
            tx_type="expense",
            amount=20.0,
            description="Tx con tag",
            category="Comida",
        )
        tag = db.tag.create("cleanup_tag")
        db.tag.add_to_transaction(int(tx["id"]), int(tag["id"]))

        db.transaction.delete(int(tx["id"]))

        total = fetch_scalar(
            db,
            "SELECT COUNT(*) AS total FROM transaction_tags WHERE transaction_id = ?",
            (int(tx["id"]),),
        )
        assert int(total) == 0

    def test_delete_recurring_cascades_recurring_tags(self, db):
        acc = db.account.get_or_create("General")
        category = db.category.create("Suscripciones", "expense")
        tag = db.tag.create("mensual")
        recurring = db.recurring.create(
            account_id=int(acc["id"]),
            tx_type="expense",
            amount=50.0,
            description="Plan mensual",
            category=str(category["name"]),
            note=None,
            day_of_month=5,
            category_id=int(category["id"]),
            tag_ids=[int(tag["id"])],
        )

        db.recurring.delete(int(recurring["id"]))

        total = fetch_scalar(
            db,
            "SELECT COUNT(*) AS total FROM recurring_transaction_tags WHERE recurring_id = ?",
            (int(recurring["id"]),),
        )
        assert int(total) == 0

    def test_delete_category_sets_category_fk_to_null_in_transactions_and_recurring(self, db):
        acc = db.account.get_or_create("General")
        category = db.category.create("Temporal FK", "expense")
        tx = db.transaction.create(
            account_id=int(acc["id"]),
            tx_type="expense",
            amount=35.0,
            description="Gasto temporal",
            category=str(category["name"]),
            category_id=int(category["id"]),
        )
        recurring = db.recurring.create(
            account_id=int(acc["id"]),
            tx_type="expense",
            amount=15.0,
            description="Regla temporal",
            category=str(category["name"]),
            note=None,
            day_of_month=10,
            category_id=int(category["id"]),
        )

        db.category.delete(int(category["id"]))

        tx_after = db.transaction.get(int(tx["id"]))
        assert tx_after is not None
        assert tx_after["category_id"] is None
        recurring_after = next(item for item in db.recurring.list() if int(item["id"]) == int(recurring["id"]))
        assert recurring_after["category_id"] is None


class TestConnectionIsolation:
    def test_second_connected_database_instance_is_blocked_until_first_closes(self, tmp_path):
        first = Database(path=tmp_path / "first.db")
        second = Database(path=tmp_path / "second.db")
        first.connect()
        try:
            with pytest.raises(RuntimeError, match="Only one Database instance"):
                second.connect()
        finally:
            first.close()

        second.connect()
        second.close()


class TestTransactionsContextValidation:
    def test_build_monthly_context_rejects_invalid_date_format(self, db):
        with pytest.raises(ValueError, match="Invalid transaction date"):
            db.transaction.build_monthly_context({"date": "2026/01/10", "amount": 12.5, "type": "expense"})

    def test_build_monthly_context_rejects_out_of_range_amount(self, db):
        with pytest.raises(ValueError, match="out of valid range"):
            db.transaction.build_monthly_context({"date": "2026-01-10", "amount": 1e12, "type": "expense"})

    def test_build_monthly_context_accepts_negative_amount_for_adjustments(self, db):
        context = db.transaction.build_monthly_context({"date": "2026-01-10", "amount": -30.5, "type": "expense"})
        assert context["period_key"] == "2026-01"

    def test_build_monthly_context_accepts_timestamp_like_date(self, db):
        context = db.transaction.build_monthly_context(
            {"date": "2025-03-02T12:30:00", "amount": 10.0, "type": "income"}
        )
        assert context["period_key"] == "2025-03"


class TestRuntimeGuards:
    def test_set_transaction_tags_requires_active_connection(self, db):
        account = db.account.get_or_create("Guard")
        tx = db.transaction.create(
            account_id=int(account["id"]),
            tx_type="expense",
            amount=25.0,
            description="Guard tx",
            category="General",
        )
        tag = db.tag.create("GuardTag", color="#112233")
        break_backend_connection_for_test(db)

        with pytest.raises(RuntimeError, match="Database is not connected"):
            db.tag.set_for_transaction(int(tx["id"]), [int(tag["id"])])

    def test_update_transaction_raises_runtime_error_when_reloading_updated_row_fails(self, db, monkeypatch):
        account = db.account.get_or_create("GuardTx")
        tx = db.transaction.create(
            account_id=int(account["id"]),
            tx_type="expense",
            amount=40.0,
            description="Original",
            category="General",
        )
        original = db._backend.get_transaction_by_id

        calls = {"count": 0}

        def _flaky_get_transaction_by_id(tx_id: int):
            row = original(tx_id)
            calls["count"] += 1
            if calls["count"] >= 2:
                return None
            return row

        monkeypatch.setattr(db._backend, "get_transaction_by_id", _flaky_get_transaction_by_id)

        with pytest.raises(RuntimeError, match="Failed to update transaction"):
            db.transaction.update(int(tx["id"]), description="Actualizada")
