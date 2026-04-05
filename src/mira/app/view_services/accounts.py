# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Application service for the Accounts view."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mira.app.view_services._common import OperationFeedback
from mira.db.database import Database


@dataclass(frozen=True)
class AccountsViewState:
    accounts: list[dict[str, Any]]


class AccountsViewService:
    """Move account CRUD orchestration out of the QWidget."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def load_state(self) -> AccountsViewState:
        return AccountsViewState(accounts=self._db.account.list())

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
