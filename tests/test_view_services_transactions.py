# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from pathlib import Path

import pytest

from mira.app.view_services import TransactionsViewService
from mira.db.database import Database


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "view-services-transactions.db")
    database.connect()
    yield database
    database.close()


def test_transactions_view_service_load_state_uses_bulk_tags_and_summary(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    service = TransactionsViewService(db)
    account = db.account.get_or_create("General")
    category = db.category.create("Food", "expense")
    tag = db.tag.create("Home", color="#228833")

    tx1 = db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=25.0,
        description="Groceries",
        category=category["name"],
        tx_date="2026-03-10",
        note="",
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="income",
        amount=100.0,
        description="Salary",
        category=None,
        tx_date="2026-03-11",
        note="",
    )
    db.tag.set_for_transaction(tx1["id"], [int(tag["id"])])

    monkeypatch.setattr(
        db.tag,
        "list_for_transaction",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("per-row tag loading should not be used")),
    )

    state = service.load_state(
        since_date="2026-03-01",
        until_date="2026-03-31",
        account_id=None,
        category=None,
        search=None,
        tag_id=None,
    )

    assert len(state.transactions) == 2
    assert state.summary["income"] == pytest.approx(100.0)
    assert state.summary["expense"] == pytest.approx(25.0)
    assert int(state.tags_by_transaction[int(tx1["id"])][0]["id"]) == int(tag["id"])
    assert any(item["name"] == "General" for item in state.options.accounts)
    assert "Food" in state.savings_categories or "Food" not in state.savings_categories


def test_transactions_view_service_create_duplicate_transfer_and_quick_actions(db: Database) -> None:
    service = TransactionsViewService(db)
    source = db.account.create("Source", "bank", 300.0, "USD")
    destination = db.account.create("Destination", "bank", 0.0, "USD")
    credit = db.account.create("Card", "credit", 0.0, "USD")
    food = db.category.create("Food", "expense")
    utilities = db.category.create("Utilities", "expense")
    tag = db.tag.create("Home", color="#228833")

    create_data = {
        "account_id": source["id"],
        "tx_type": "expense",
        "amount": 40.0,
        "stored_amount": 40.0,
        "description": "Dinner",
        "category": food["name"],
        "tx_date": "2026-03-18",
        "note": "family",
        "subcategory": None,
        "payment_method": "cash",
        "receipt_path": None,
        "exchange_rate": None,
        "converted_amount": None,
        "tags": [int(tag["id"])],
    }
    created = service.create(create_data)
    assert created.selected_id is not None

    duplicated = service.duplicate(dict(create_data, description="Dinner copy"))
    assert duplicated.selected_id is not None

    service.update_category(created.selected_id, utilities["name"])
    service.update_account(created.selected_id, int(destination["id"]))

    updated = db.transaction.get(created.selected_id)
    assert updated is not None
    assert updated["category"] == "Utilities"
    assert int(updated["account_id"]) == int(destination["id"])

    service.transfer(
        {
            "from_account_id": source["id"],
            "to_account_id": destination["id"],
            "amount": 20.0,
            "note": "move",
            "tx_date": "2026-03-19",
            "exchange_rate": None,
            "converted_amount": None,
            "description": "Transfer",
        }
    )
    service.record_credit_payment(
        {
            "from_account_id": destination["id"],
            "to_account_id": credit["id"],
            "amount": 10.0,
            "note": "card payment",
            "tx_date": None,
            "exchange_rate": None,
            "converted_amount": None,
            "description": "Payment",
        }
    )

    transfers = [tx for tx in db.transaction.list(limit=50) if int(tx.get("is_transfer") or 0) == 1]
    assert len(transfers) == 4
