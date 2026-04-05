# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Application service for the Savings Goals view."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mira.app.view_services._common import OperationFeedback
from mira.db.database import Database


@dataclass(frozen=True)
class SavingsGoalsViewState:
    goals: list[dict[str, Any]]


class SavingsGoalsViewService:
    """Move savings goal loading and commands out of the QWidget."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def load_state(self) -> SavingsGoalsViewState:
        return SavingsGoalsViewState(goals=self._db.savings_goal.list())

    def create(self, *, name: str, target_amount: float, target_date: str | None = None) -> OperationFeedback:
        created = self._db.savings_goal.create(
            name=name,
            target_amount=target_amount,
            target_date=target_date,
        )
        return OperationFeedback(selected_id=int(created["id"]))

    def update(
        self,
        goal_id: int,
        *,
        name: str,
        target_amount: float,
        target_date: str | None = None,
    ) -> OperationFeedback:
        self._db.savings_goal.update(
            goal_id,
            name=name,
            target_amount=target_amount,
            target_date=target_date,
        )
        return OperationFeedback(selected_id=int(goal_id))

    def contribute(self, goal_id: int, amount: float) -> OperationFeedback:
        self._db.savings_goal.contribute(goal_id, amount)
        return OperationFeedback(selected_id=int(goal_id))

    def delete(self, goal_id: int) -> OperationFeedback:
        self._db.savings_goal.delete(goal_id)
        return OperationFeedback()
