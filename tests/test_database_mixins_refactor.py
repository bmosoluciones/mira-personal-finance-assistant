# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from mira.db.database import Database, _DatabaseBackend


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


def test_database_backend_no_longer_defines_summary_reporting_business_methods() -> None:
    backend_methods = {
        "get_summary",
        "get_category_summary",
        "_cursor",
    }

    assert backend_methods.isdisjoint(_DatabaseBackend.__dict__.keys())
