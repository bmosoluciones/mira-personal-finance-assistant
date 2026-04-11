# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from pathlib import Path

import pytest

from mira.db.database import Database
from mira.db.model import RecurringTransaction


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "recurring-core.db")
    database.connect()
    yield database
    database.close()


def test_recurring_create_validates_category_id_existence_and_type(db: Database) -> None:
    account = db.account.get_or_create("General")
    income_category = db.category.create("Salary", "income")

    with pytest.raises(ValueError, match="Category 999999 not found"):
        db.recurring.create(
            account_id=account["id"],
            tx_type="expense",
            amount=25.0,
            description="Missing category",
            category=None,
            category_id=999999,
            tag_ids=[],
            note=None,
            day_of_month=5,
        )

    with pytest.raises(ValueError, match="not valid for expense transactions"):
        db.recurring.create(
            account_id=account["id"],
            tx_type="expense",
            amount=25.0,
            description="Wrong type",
            category=None,
            category_id=income_category["id"],
            tag_ids=[],
            note=None,
            day_of_month=5,
        )


def test_recurring_create_preserves_unknown_category_label_when_not_resolved(db: Database) -> None:
    account = db.account.get_or_create("General")

    recurring = db.recurring.create(
        account_id=account["id"],
        tx_type="expense",
        amount=25.0,
        description="Ad hoc",
        category="Manual Category",
        category_id=None,
        tag_ids=[],
        note="monthly",
        day_of_month=7,
    )

    assert recurring["category_id"] is None
    assert recurring["category"] == "Manual Category"


def test_recurring_update_validates_missing_rule_account_type_amount_and_day(db: Database) -> None:
    account = db.account.get_or_create("General")
    category = db.category.create("Internet", "expense")
    recurring = db.recurring.create(
        account_id=account["id"],
        tx_type="expense",
        amount=40.0,
        description="Internet",
        category=None,
        category_id=category["id"],
        tag_ids=[],
        note="monthly",
        day_of_month=5,
    )

    with pytest.raises(ValueError, match="Recurring transaction 999999 not found"):
        db.recurring.update(999999, description="missing")

    with pytest.raises(ValueError, match="Account 999999 not found"):
        db.recurring.update(int(recurring["id"]), account_id=999999)

    with pytest.raises(ValueError, match="must be 'income' or 'expense'"):
        db.recurring.update(int(recurring["id"]), tx_type="transfer")

    with pytest.raises(ValueError, match="amount must be positive"):
        db.recurring.update(int(recurring["id"]), amount=0)

    with pytest.raises(ValueError, match="between 1 and 28"):
        db.recurring.update(int(recurring["id"]), day_of_month=29)


def test_recurring_update_preserves_current_category_and_tags_when_omitted(db: Database) -> None:
    account = db.account.get_or_create("General")
    category = db.category.create("Internet", "expense")
    tag = db.tag.create("Fixed")
    recurring = db.recurring.create(
        account_id=account["id"],
        tx_type="expense",
        amount=40.0,
        description="Internet",
        category=None,
        category_id=category["id"],
        tag_ids=[int(tag["id"])],
        note="monthly",
        day_of_month=5,
    )

    updated = db.recurring.update(
        int(recurring["id"]),
        amount=42.5,
        description="Internet Plus",
    )

    assert updated["category_id"] == int(category["id"])
    assert updated["category"] == "Internet"
    assert updated["description"] == "Internet Plus"
    assert float(updated["amount"]) == pytest.approx(42.5)
    assert {int(tag_id) for tag_id in updated["tag_ids"]} == {int(tag["id"])}


def test_apply_recurring_for_month_skips_rules_without_account_and_leaves_period_unmarked(db: Database) -> None:
    RecurringTransaction.create(
        account=None,
        type="expense",
        amount=1500,
        description="Orphan recurring",
        category="Misc",
        category_id=None,
        note=None,
        day_of_month=5,
    )

    created = db.recurring.apply_for_month(2026, 4)

    assert created == []
    assert db.transaction.list() == []
    assert db.setting.get("recurring_applied_2026-04") is None
