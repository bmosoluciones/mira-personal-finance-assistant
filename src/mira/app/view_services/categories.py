# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Application service for the Categories view."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from mira.app.view_services._common import OperationFeedback
from mira.db.database import Database


@dataclass(frozen=True)
class CategoriesViewState:
    """Represent the CategoriesViewState class."""

    income_categories: list[dict[str, Any]]

    expense_categories: list[dict[str, Any]]
    income_tree: list[dict[str, Any]]
    expense_tree: list[dict[str, Any]]
    monthly_counts: dict[str, int]


class CategoriesViewService:
    """Move category data loading and commands out of the QWidget."""

    def __init__(self, db: Database) -> None:
        """Initialize the CategoriesViewService instance."""
        self._db = db

    def load_state(self) -> CategoriesViewState:
        """Return load state."""
        since = date.today().replace(day=1).isoformat()
        return CategoriesViewState(
            income_categories=self._db.category.list("income"),
            expense_categories=self._db.category.list("expense"),
            income_tree=self._db.category.tree("income"),
            expense_tree=self._db.category.tree("expense"),
            monthly_counts=self._db.report.category_transaction_counts(since_date=since),
        )

    def get(self, category_id: int) -> dict[str, Any] | None:
        """Return get."""
        return self._db.category.get(category_id)

    def create(
        self,
        *,
        name: str,
        cat_type: str,
        color: str,
        icon: str = "",
        parent_id: int | None = None,
    ) -> OperationFeedback:
        """Return create."""
        created = self._db.category.create(
            name,
            cat_type,
            color,
            icon=icon,
            parent_id=parent_id,
        )
        return OperationFeedback(selected_id=int(created["id"]))

    def update(
        self,
        category_id: int,
        *,
        name: str,
        cat_type: str,
        color: str,
        icon: str = "",
        parent_id: int | None = None,
    ) -> OperationFeedback:
        """Return update."""
        self._db.category.update(
            category_id,
            name,
            cat_type,
            color,
            icon=icon,
            parent_id=parent_id,
        )
        return OperationFeedback(selected_id=int(category_id))

    def delete(self, category_id: int) -> OperationFeedback:
        """Return delete."""
        self._db.category.delete(category_id)
        return OperationFeedback()

    def merge(self, source_id: int, target_id: int) -> OperationFeedback:
        """Return merge."""
        merged = self._db.category.merge(source_id, target_id)
        target = merged.get("target") if isinstance(merged, dict) else None
        selected_id = int(target["id"]) if isinstance(target, dict) and target.get("id") is not None else int(target_id)
        return OperationFeedback(selected_id=selected_id)

    # -- Income-Expense Relation helpers ------------------------------------

    def list_relations(self) -> list[dict[str, Any]]:
        """Return list relations."""
        return self._db.category.list_relations()

    def create_relation(self, income_category_id: int, expense_category_id: int) -> dict[str, Any]:
        """Return create relation."""
        return self._db.category.create_relation(income_category_id, expense_category_id)

    def delete_relation(self, relation_id: int) -> None:
        """Return delete relation."""
        self._db.category.delete_relation(relation_id)

    def parent_income_categories(self) -> list[dict[str, Any]]:
        """Return level-1 income categories (no parent)."""
        return [c for c in self._db.category.list("income") if c.get("parent_id") is None]

    def available_parent_expense_categories(self) -> list[dict[str, Any]]:
        """Return level-1 expense categories that are not already linked."""
        linked = self._db.category.linked_expense_ids()
        return [
            c for c in self._db.category.list("expense") if c.get("parent_id") is None and int(c["id"]) not in linked
        ]
