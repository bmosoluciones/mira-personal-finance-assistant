# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from mira.db.database import Database
from mira.db.model import Transaction
from mira.transaction_kinds import (
    TransactionType,
    analytics_included_expr,
    is_analytics_excluded_transaction,
    is_balance_adjustment_payment_method,
    is_balance_adjustment_transaction,
    localized_balance_adjustment_description,
    normalize_payment_method,
    try_parse_transaction_type,
)


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "transaction-kinds.db")
    database.connect()
    yield database
    database.close()


def test_try_parse_transaction_type_normalizes_known_values_and_logs_invalid_input(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert try_parse_transaction_type(" Income ") == TransactionType.INCOME
    assert try_parse_transaction_type("expense") == TransactionType.EXPENSE
    assert try_parse_transaction_type("") is None

    with caplog.at_level(logging.WARNING):
        assert try_parse_transaction_type("transfer") is None

    assert "Invalid transaction type" in caplog.text


def test_balance_adjustment_helpers_normalize_payment_method_and_language() -> None:
    assert normalize_payment_method("  Balance_Adjustment  ") == "balance_adjustment"
    assert is_balance_adjustment_payment_method("  Balance_Adjustment  ") is True
    assert localized_balance_adjustment_description("es-NI") == "Ajuste de saldo"
    assert localized_balance_adjustment_description(None) == "Balance adjustment"


def test_balance_adjustment_detection_supports_dicts_and_objects() -> None:
    assert is_balance_adjustment_transaction({"payment_method": " balance_adjustment "}) is True
    assert is_balance_adjustment_transaction(SimpleNamespace(payment_method="balance_adjustment")) is True
    assert is_balance_adjustment_transaction(SimpleNamespace(payment_method="cash")) is False


def test_analytics_exclusion_handles_transfer_coercion_and_balance_adjustments() -> None:
    assert is_analytics_excluded_transaction({"payment_method": "cash", "is_transfer": "1"}) is True
    assert is_analytics_excluded_transaction(SimpleNamespace(payment_method="cash", is_transfer="yes")) is True
    assert is_analytics_excluded_transaction({"payment_method": "balance_adjustment", "is_transfer": 0}) is True
    assert is_analytics_excluded_transaction({"payment_method": "cash", "is_transfer": "0"}) is False


def test_analytics_included_expr_filters_transfers_and_balance_adjustments(db: Database) -> None:
    source = db.account.get_or_create("General")
    destination = db.account.create("Savings", "bank", 0.0, "USD")
    regular = db.transaction.create(
        account_id=source["id"],
        tx_type="expense",
        amount=10.0,
        description="Lunch",
        category="Food",
        tx_date="2026-04-01",
        payment_method="cash",
    )
    db.transaction.record_balance_adjustment(source["id"], 5.0, tx_date="2026-04-02")
    db.transaction.transfer_between_accounts(
        from_account_id=source["id"],
        to_account_id=destination["id"],
        amount=20.0,
        note="move",
        tx_date="2026-04-03",
    )

    included_ids = [
        int(row.id)
        for row in Transaction.select(Transaction.id)
        .where(analytics_included_expr(Transaction))
        .order_by(Transaction.id)
    ]

    assert included_ids == [int(regular["id"])]
