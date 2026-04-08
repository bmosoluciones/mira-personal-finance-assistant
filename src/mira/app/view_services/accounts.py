# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Application service for the Accounts view."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from mira.app.view_services._common import OperationFeedback
from mira.db.database import Database


@dataclass(frozen=True)
class AccountsViewState:
    accounts: list[dict[str, Any]]


@dataclass(frozen=True)
class BalanceAdjustmentPreview:
    account_id: int | None
    currency: str
    balance_as_of: float
    signed_adjustment: float
    projected_balance: float
    warn_before_creation_date: bool


class AccountsViewService:
    """Move account CRUD orchestration out of the QWidget."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def load_state(self) -> AccountsViewState:
        return AccountsViewState(accounts=self._db.account.list())

    def list_balance_adjustment_accounts(self) -> list[dict[str, Any]]:
        return [acc for acc in self._db.account.list() if str(acc.get("account_type") or "") in {"bank", "credit"}]

    @staticmethod
    def _coerce_created_day(value: object) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        raw_value = str(value).strip()
        if not raw_value:
            return None
        try:
            return datetime.fromisoformat(raw_value.replace(" ", "T")).date()
        except ValueError:
            return None

    def preview_balance_adjustment(
        self,
        account_id: int | None,
        tx_date: str,
        signed_adjustment: float,
        *,
        exclude_transaction_id: int | None = None,
    ) -> BalanceAdjustmentPreview:
        if account_id is None:
            return BalanceAdjustmentPreview(
                account_id=None,
                currency=str(self._db.setting.get_default_currency() or "").strip().upper(),
                balance_as_of=0.0,
                signed_adjustment=float(signed_adjustment),
                projected_balance=float(signed_adjustment),
                warn_before_creation_date=False,
            )

        balance_data = self._db.account.balance_as_of(
            int(account_id),
            tx_date,
            exclude_transaction_id=exclude_transaction_id,
        )
        account = self._db.account.get(int(account_id))
        created_day = self._coerce_created_day((account or {}).get("created_at"))
        selected_day = date.fromisoformat(tx_date)
        balance_as_of = float(balance_data["balance_as_of"])
        signed_amount = float(signed_adjustment)
        return BalanceAdjustmentPreview(
            account_id=int(account_id),
            currency=str(balance_data["currency"]),
            balance_as_of=balance_as_of,
            signed_adjustment=signed_amount,
            projected_balance=balance_as_of + signed_amount,
            warn_before_creation_date=created_day is not None and selected_day < created_day,
        )

    def create(
        self, *, name: str, account_type: str, opening_balance: float, currency: str | None
    ) -> OperationFeedback:
        created = self._db.account.create(name, account_type, opening_balance, currency)
        return OperationFeedback(selected_id=int(created["id"]))

    def update(self, account_id: int, *, name: str, account_type: str, currency: str | None) -> OperationFeedback:
        self._db.account.update(account_id, name, account_type, currency)
        return OperationFeedback(selected_id=int(account_id))

    def delete(self, account_id: int) -> OperationFeedback:
        self._db.account.delete(account_id)
        return OperationFeedback()

    def set_default(self, account_id: int) -> OperationFeedback:
        self._db.account.set_default(account_id)
        return OperationFeedback(selected_id=int(account_id))

    def record_balance_adjustment(self, data: dict[str, Any]) -> OperationFeedback:
        tx = self._db.transaction.record_balance_adjustment(
            account_id=int(data["account_id"]),
            signed_amount=float(data["signed_amount"]),
            tx_date=str(data["tx_date"]),
            note=data.get("note"),
        )
        return OperationFeedback(
            selected_id=int(data["account_id"]),
            payload={"transaction_id": int(tx["id"])},
        )

    def update_balance_adjustment(self, transaction_id: int, data: dict[str, Any]) -> OperationFeedback:
        tx = self._db.transaction.update_balance_adjustment(
            transaction_id,
            account_id=int(data["account_id"]),
            signed_amount=float(data["signed_amount"]),
            tx_date=str(data["tx_date"]),
            note=data.get("note"),
        )
        return OperationFeedback(
            selected_id=int(data["account_id"]),
            payload={"transaction_id": int(tx["id"])},
        )
