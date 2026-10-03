# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

import mira.db.database as database_module
from mira.db.database import Database
from mira.db.repositories.report_repository import ReportRepository


def test_database_no_longer_defines_settings_tags_or_recurring_business_methods() -> None:
    moved_methods = {
        "get_setting",
        "set_setting",
        "get_default_currency",
        "add_tag",
        "get_tags",
        "get_transaction_tags",
        "get_recurring",
        "add_recurring",
        "update_recurring",
        "apply_recurring_for_month",
    }

    assert moved_methods.isdisjoint(Database.__dict__.keys())


def test_database_no_longer_defines_summary_reporting_business_methods() -> None:
    reporting_methods = {
        "get_summary",
        "get_category_summary",
        "_cursor",
    }

    assert reporting_methods.isdisjoint(Database.__dict__.keys())
    assert {"get_summary", "get_category_summary"}.issubset(ReportRepository.__dict__.keys())


def test_database_has_no_backend_or_facade_layer() -> None:
    assert not hasattr(database_module, "_DatabaseBackend")
    facade_names = [name for name in vars(database_module) if name.endswith("Facade")]
    assert facade_names == []

    db = Database(path=":memory:")
    assert not hasattr(db, "_backend")
    assert isinstance(db.account, database_module._Namespace)
    assert db.account.list.__self__ is db


def test_public_api_tables_never_expose_a_private_repository_method() -> None:
    tables = {
        name: value
        for name, value in vars(database_module).items()
        if name.endswith("_API") and isinstance(value, dict)
    }

    assert tables
    private = {
        f"{table}.{entry}"
        for table, entries in tables.items()
        for entry, target in entries.items()
        if isinstance(target, str) and target.startswith("_")
    }

    assert private == set()


def test_facade_accepts_the_pre_collapse_keyword_names(tmp_path) -> None:
    db = Database(path=tmp_path / "aliases.db")
    db.connect()
    category = db.category.create("Groceries", "expense")
    recurring = db.recurring.create(
        account_id=int(db.account.get_or_create("Cash")["id"]),
        tx_type="expense",
        amount=10.0,
        description="Weekly",
        category="Groceries",
        note=None,
        day_of_month=1,
    )

    db.category.update(cat_id=int(category["id"]), name="Food", cat_type="expense")
    assert db.category.get(int(category["id"]))["name"] == "Food"

    assert db.recurring.get(recurring_id=int(recurring["id"])) is not None
    db.recurring.update(recurring_id=int(recurring["id"]), amount=20.0)
    assert float(db.recurring.get(int(recurring["id"]))["amount"]) == 20.0
    db.recurring.delete(recurring_id=int(recurring["id"]))
    assert db.recurring.get(int(recurring["id"])) is None
    db.close()
