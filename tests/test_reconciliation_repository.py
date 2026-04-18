# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from mira.db.database import Database


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(path=tmp_path / "reconciliation.db")
    database.connect()
    yield database
    database.close()


def test_reconciliation_rejects_missing_account(db: Database) -> None:
    account = db.account.create("Checking", "bank", 0.0, "USD")

    with pytest.raises(ValueError, match=f"Account {account['id'] + 1} not found"):
        db.reconciliation.reconcile(
            account_id=int(account["id"]) + 1,
            date_from="2026-01-01",
            date_to="2026-01-31",
            system_transaction_ids=[1],
            external_rows=[
                {
                    "reference": "ext-1",
                    "date": "2026-01-05",
                    "description": "External payment",
                    "amount": 100.0,
                    "external_item_key": "ext-1",
                }
            ],
        )


def test_reconciliation_rejects_empty_selection_lists(db: Database) -> None:
    account = db.account.create("Checking", "bank", 0.0, "USD")

    with pytest.raises(ValueError, match="Select at least one system transaction"):
        db.reconciliation.reconcile(
            account_id=int(account["id"]),
            date_from="2026-01-01",
            date_to="2026-01-31",
            system_transaction_ids=[],
            external_rows=[{"reference": "ext", "date": "2026-01-05", "description": "External", "amount": 100.0, "external_item_key": "ext"}],
        )

    tx = db.transaction.create(
        account_id=int(account["id"]),
        tx_type="income",
        amount=50.0,
        category="Salary",
        tx_date="2026-01-02",
    )

    with pytest.raises(ValueError, match="Select at least one external movement"):
        db.reconciliation.reconcile(
            account_id=int(account["id"]),
            date_from="2026-01-01",
            date_to="2026-01-31",
            system_transaction_ids=[int(tx["id"])],
            external_rows=[],
        )


def test_reconciliation_rejects_transfer_and_balance_adjustment_transactions(db: Database) -> None:
    account = db.account.create("Checking", "bank", 0.0, "USD")
    transfer_tx = db.transaction.create(
        account_id=int(account["id"]),
        tx_type="income",
        amount=100.0,
        category="Transfer",
        tx_date="2026-01-10",
        is_transfer=1,
    )

    with pytest.raises(ValueError, match="Transfers and balance adjustments cannot be reconciled"):
        db.reconciliation.reconcile(
            account_id=int(account["id"]),
            date_from="2026-01-01",
            date_to="2026-01-31",
            system_transaction_ids=[int(transfer_tx["id"])],
            external_rows=[
                {
                    "reference": "ext-1",
                    "date": "2026-01-10",
                    "description": "Transfer attempt",
                    "amount": 100.0,
                    "external_item_key": "transfer-1",
                }
            ],
        )


def test_reconciliation_creates_group_and_clears_matches(db: Database) -> None:
    account = db.account.create("Checking", "bank", 0.0, "USD")
    tx = db.transaction.create(
        account_id=int(account["id"]),
        tx_type="income",
        amount=120.0,
        category="Salary",
        tx_date="2026-01-05",
    )

    external_row = {
        "reference": "ext-1",
        "date": "2026-01-05",
        "description": "External deposit",
        "amount": 120.0,
        "external_item_key": "item-1",
    }

    result = db.reconciliation.reconcile(
        account_id=int(account["id"]),
        date_from="2026-01-01",
        date_to="2026-01-31",
        system_transaction_ids=[int(tx["id"])],
        external_rows=[external_row],
    )

    assert result["group"]["account_id"] == int(account["id"])
    assert result["matches"]
    assert len(result["created_match_ids"]) == 1

    updated_tx = db.transaction.get(int(tx["id"]))
    assert updated_tx is not None
    assert updated_tx["is_reconciled"] == 1
    assert updated_tx["reconciled_at"] is not None

    cleared = db.reconciliation.clear_for_transactions([int(tx["id"])])
    assert cleared == 1
    assert db.reconciliation.list_groups(account_id=int(account["id"]), date_from="2026-01-01", date_to="2026-01-31") == []

    group_id = result["group"]["id"]
    deleted = db.reconciliation.clear_groups([group_id])
    assert deleted in {0, 1}
