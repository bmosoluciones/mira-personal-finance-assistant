# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Application service for the Transactions view."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mira.app.view_services._common import OperationFeedback
from mira.db.database import Database
from mira.finance_summary import build_savings_lookup


@dataclass(frozen=True)
class TransactionsFilterOptions:
    accounts: list[dict[str, Any]]
    categories: list[dict[str, Any]]
    tags: list[dict[str, Any]]


@dataclass(frozen=True)
class TransactionsViewState:
    options: TransactionsFilterOptions
    transactions: list[dict[str, Any]]
    summary: dict[str, float]
    tags_by_transaction: dict[int, list[dict[str, Any]]]
    savings_categories: set[str]


class TransactionsViewService:
    """Move transaction querying and commands out of the QWidget."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def load_state(
        self,
        *,
        since_date: str,
        until_date: str,
        account_id: int | None,
        category: str | None,
        search: str | None,
        tag_id: int | None,
        limit: int = 1_000,
    ) -> TransactionsViewState:
        options = TransactionsFilterOptions(
            accounts=self._db.account.list(),
            categories=self._db.category.list(),
            tags=self._db.tag.list(),
        )
        transactions = self._db.transaction.list(
            limit=limit,
            since_date=since_date,
            until_date=until_date,
            account_id=account_id,
            category=category,
            search=search,
            tag_id=tag_id,
        )
        tx_ids = [int(tx["id"]) for tx in transactions if tx.get("id") is not None]
        return TransactionsViewState(
            options=options,
            transactions=transactions,
            summary={
                key: float(value)
                for key, value in self._db.report.summarize_financials(transactions, as_dict=True).items()
            },
            tags_by_transaction=self._db.tag.list_bulk_for_transactions(tx_ids),
            savings_categories=build_savings_lookup(options.categories)[1],
        )

    def create(self, data: dict[str, Any]) -> OperationFeedback:
        tx = self._db.transaction.create(
            account_id=data["account_id"],
            tx_type=data["tx_type"],
            amount=data.get("stored_amount", data["amount"]),
            description=data["description"],
            category=data["category"],
            tx_date=data["tx_date"],
            note=data["note"],
            subcategory=data.get("subcategory"),
            payment_method=data.get("payment_method") or "cash",
            receipt_path=data.get("receipt_path"),
            exchange_rate=data.get("exchange_rate"),
            converted_amount=data.get("converted_amount"),
        )
        self._db.tag.set_for_transaction(tx["id"], data.get("tags", []))
        return OperationFeedback(
            selected_id=int(tx["id"]),
            payload={"highlighted_message": tx.get("mira_achievement") or tx.get("mira_insight")},
        )

    def update(self, transaction_id: int, data: dict[str, Any]) -> OperationFeedback:
        self._db.transaction.update(
            transaction_id,
            account_id=data["account_id"],
            tx_type=data["tx_type"],
            amount=data.get("stored_amount", data["amount"]),
            description=data["description"],
            category=data["category"],
            tx_date=data["tx_date"],
            note=data["note"],
            subcategory=data.get("subcategory"),
            payment_method=data.get("payment_method") or "cash",
            receipt_path=data.get("receipt_path"),
            exchange_rate=data.get("exchange_rate"),
            converted_amount=data.get("converted_amount"),
        )
        self._db.tag.set_for_transaction(transaction_id, data.get("tags", []))
        return OperationFeedback(selected_id=int(transaction_id))

    def delete(self, transaction_id: int) -> OperationFeedback:
        self._db.transaction.delete(transaction_id)
        return OperationFeedback()

    def duplicate(self, data: dict[str, Any]) -> OperationFeedback:
        return self.create(data)

    def transfer(self, data: dict[str, Any]) -> OperationFeedback:
        self._db.transaction.transfer_between_accounts(
            from_account_id=data["from_account_id"],
            to_account_id=data["to_account_id"],
            amount=data["amount"],
            note=data["note"],
            tx_date=data["tx_date"],
            exchange_rate=data["exchange_rate"],
            converted_amount=data["converted_amount"],
            description=data.get("description"),
        )
        return OperationFeedback()

    def record_credit_payment(self, data: dict[str, Any]) -> OperationFeedback:
        self._db.transaction.record_credit_card_payment(
            from_account_id=data["from_account_id"],
            credit_account_id=data["to_account_id"],
            amount=data["amount"],
            note=data["note"],
            tx_date=data["tx_date"],
            exchange_rate=data["exchange_rate"],
            converted_amount=data["converted_amount"],
            description=data.get("description"),
        )
        return OperationFeedback()

    def update_balance_adjustment(self, transaction_id: int, data: dict[str, Any]) -> OperationFeedback:
        self._db.transaction.update_balance_adjustment(
            transaction_id,
            account_id=int(data["account_id"]),
            signed_amount=float(data["signed_amount"]),
            tx_date=str(data["tx_date"]),
            note=data.get("note"),
        )
        return OperationFeedback(selected_id=int(transaction_id))

    def update_account(self, transaction_id: int, account_id: int) -> OperationFeedback:
        self._db.transaction.update_account(transaction_id, account_id)
        return OperationFeedback(selected_id=int(transaction_id))

    def update_category(self, transaction_id: int, category: str) -> OperationFeedback:
        self._db.transaction.update_category(transaction_id, category)
        return OperationFeedback(selected_id=int(transaction_id))

    def update_date(self, transaction_id: int, tx_date: str) -> OperationFeedback:
        self._db.transaction.update(transaction_id, tx_date=tx_date)
        return OperationFeedback(selected_id=int(transaction_id))
