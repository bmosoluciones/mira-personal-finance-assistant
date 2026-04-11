# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from pathlib import Path

import pytest

from mira.db.database import Database
from mira.db.helpers import _SAVINGS_GOALS_PARENT_NAMES


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "setting-core.db")
    database.connect()
    yield database
    database.close()


def test_setting_repository_get_delegates_and_default_currency_normalizes_or_falls_back(db: Database) -> None:
    assert db.setting.get("missing") is None
    assert db.setting.get_default_currency() == "USD"

    db.setting.set("default_currency", " nio ")

    assert db.setting.get("default_currency") == " nio "
    assert db.setting.get_default_currency() == "NIO"


def test_setting_repository_savings_parent_name_uses_language_fallback_or_existing_category(db: Database) -> None:
    db.setting.set("language", "es")

    assert db.setting.get_savings_goals_parent_name() == _SAVINGS_GOALS_PARENT_NAMES["es"]

    db.setting.seed_initial_data(include_default_categories=True, account_names=[], language="es")

    assert db.setting.get_savings_goals_parent_name() == _SAVINGS_GOALS_PARENT_NAMES["es"]


def test_setting_repository_list_currencies_can_return_all_regions(db: Database) -> None:
    americas = db.setting.list_currencies(region="americas")
    all_regions = db.setting.list_currencies(region=None)

    assert americas
    assert all_regions
    assert len(all_regions) >= len(americas)
    assert any(item["region"] != "americas" for item in all_regions)
