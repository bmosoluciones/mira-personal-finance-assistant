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
