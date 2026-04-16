# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Application service for the Recurring Transactions view."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mira.app.view_services._common import OperationFeedback
from mira.db.database import Database


@dataclass(frozen=True)
class RecurringViewState:
    """Represent the RecurringViewState class."""

    recurring: list[dict[str, Any]]


class RecurringViewService:
    """Move recurring transaction orchestration out of the QWidget."""

    def __init__(self, db: Database) -> None:
        """Initialize the RecurringViewService instance."""
        self._db = db

    def load_state(self) -> RecurringViewState:
        """Return load state."""
        return RecurringViewState(recurring=self._db.recurring.list())

    def create(self, data: dict[str, Any]) -> OperationFeedback:
        """Return create."""
        created = self._db.recurring.create(
            account_id=data["account_id"],
            tx_type=data["tx_type"],
            amount=data["amount"],
            description=data["description"],
            category_id=data["category_id"],
            tag_ids=data["tag_ids"],
            category=None,
            note=data["note"],
            day_of_month=data["day_of_month"],
        )
        return OperationFeedback(selected_id=int(created["id"]))

    def update(self, recurring_id: int, data: dict[str, Any]) -> OperationFeedback:
        """Return update."""
        self._db.recurring.update(
            recurring_id,
            account_id=data["account_id"],
            tx_type=data["tx_type"],
            amount=data["amount"],
            description=data["description"],
            category_id=data["category_id"],
            tag_ids=data["tag_ids"],
            category=None,
            note=data["note"],
            day_of_month=data["day_of_month"],
        )
        return OperationFeedback(selected_id=int(recurring_id))

    def delete(self, recurring_id: int) -> OperationFeedback:
        """Return delete."""
        self._db.recurring.delete(recurring_id)
        return OperationFeedback()

    def apply_for_month(self, year: int, month: int) -> OperationFeedback:
        """Return apply for month."""
        created = self._db.recurring.apply_for_month(year, month)
        return OperationFeedback(payload={"created_count": len(created), "year": year, "month": month})
