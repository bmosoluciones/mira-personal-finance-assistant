# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from peewee import JOIN, Case, fn

from mira.db.money import MONEY_ZERO, MoneyLike
from mira.db.model import Category, SavingsGoal
from mira.transaction_kinds import is_analytics_excluded_transaction


def _base_goal_query():
    return (
        SavingsGoal.select(
            SavingsGoal.id,
            SavingsGoal.name,
            SavingsGoal.target_amount,
            SavingsGoal.current_amount,
            SavingsGoal.currency,
            SavingsGoal.category_id,
            SavingsGoal.target_date,
            SavingsGoal.created_at,
            Category.name.alias("category_name"),
            Category.is_savings.alias("category_is_savings"),
        )
        .join(Category, on=(SavingsGoal.category_id == Category.id), join_type=JOIN.LEFT_OUTER)
        .dicts()
    )


class SavingsGoalRepository:
    if TYPE_CHECKING:

        def _cents_to_decimal(self, value: object, *, allow_none: bool = False) -> Any: ...
        def _money_to_decimal(self, value: object, *, allow_none: bool = False) -> Any: ...
        def _money_to_cents(self, value: object, *, allow_none: bool = False) -> int | None: ...
        def _ensure_goal_linked_savings_category(self, name: str) -> dict[str, Any]: ...
        def get_default_currency(self) -> str: ...
        def _category_has_transaction_history(self, category_id: int) -> bool: ...
        def _category_is_linked_to_other_goal(self, category_id: int, *, excluding_goal_id: int) -> bool: ...
        def get_category_by_id(self, cat_id: int) -> dict[str, Any] | None: ...
        def delete_category(self, cat_id: int) -> None: ...

    def _serialize_goal(self, row: dict[str, Any]) -> dict[str, Any]:
        item = {
            "id": row["id"],
            "name": row["name"],
            "target_amount": self._cents_to_decimal(row["target_amount"]),
            "current_amount": self._cents_to_decimal(row["current_amount"]),
            "currency": row["currency"],
            "category_id": row["category_id"],
            "target_date": row["target_date"],
            "created_at": row["created_at"],
            "category_name": row.get("category_name"),
            "category_is_savings": row.get("category_is_savings"),
        }
        target = item["target_amount"] or MONEY_ZERO
        current = item["current_amount"] or MONEY_ZERO
        item["progress"] = float(current / target) if target > MONEY_ZERO else 0.0
        item["remaining_amount"] = max(MONEY_ZERO, target - current)
        return item

    def add_savings_goal(
        self,
        name: str,
        target_amount: MoneyLike,
        target_date: str | None = None,
        *,
        currency: str | None = None,
        category_name: str | None = None,
    ) -> dict:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Goal name cannot be empty")
        normalized_target = self._money_to_decimal(target_amount) or MONEY_ZERO
        if normalized_target <= MONEY_ZERO:
            raise ValueError("Target amount must be greater than zero")
        savings_category = self._ensure_goal_linked_savings_category(category_name or normalized_name)
        goal_currency = (currency or self.get_default_currency()).strip().upper() or self.get_default_currency()
        row = SavingsGoal.create(
            name=normalized_name,
            target_amount=self._money_to_cents(normalized_target),
            current_amount=0,
            target_date=target_date,
            currency=goal_currency,
            category_id=int(savings_category["id"]),
        )
        return self.get_savings_goal(int(row.id))  # type: ignore[call-overload]

    def get_savings_goal_by_name(self, name: str) -> dict | None:
        normalized_name = name.strip()
        if not normalized_name:
            return None
        row = (
            _base_goal_query()
            .where(fn.LOWER(fn.TRIM(SavingsGoal.name)) == normalized_name.casefold())
            .order_by(SavingsGoal.id)
            .first()
        )
        return self._serialize_goal(row) if row is not None else None

    def get_savings_goal(self, goal_id: int) -> dict:
        row = _base_goal_query().where(SavingsGoal.id == goal_id).first()
        if row is None:
            raise ValueError(f"Savings goal {goal_id} not found")
        return self._serialize_goal(row)

    def get_savings_goals(self) -> list[dict]:
        rows = _base_goal_query().order_by(SavingsGoal.created_at.desc(), SavingsGoal.id.desc())
        return [self._serialize_goal(row) for row in rows]

    def list_savings_goals(self) -> list[dict]:
        return self.get_savings_goals()

    def get_or_create_savings_goal(
        self,
        name: str,
        target_amount: MoneyLike,
        target_date: str | None = None,
        *,
        currency: str | None = None,
        category_name: str | None = None,
    ) -> dict:
        existing = self.get_savings_goal_by_name(name)
        if existing is not None:
            return existing
        return self.add_savings_goal(
            name=name,
            target_amount=target_amount,
            target_date=target_date,
            currency=currency,
            category_name=category_name,
        )

    def contribute_to_goal(self, goal_id: int, amount: MoneyLike) -> dict:
        normalized_amount = self._money_to_decimal(amount) or MONEY_ZERO
        if normalized_amount <= MONEY_ZERO:
            raise ValueError("Goal contribution must be positive")
        amount_cents = self._money_to_cents(normalized_amount) or 0
        SavingsGoal.update(current_amount=SavingsGoal.current_amount + amount_cents).where(
            SavingsGoal.id == goal_id
        ).execute()
        return self.get_savings_goal(goal_id)

    def _savings_goal_ids_for_category_name(self, category_name: str | None) -> list[int]:
        normalized = (category_name or "").strip()
        if not normalized:
            return []
        rows = (
            SavingsGoal.select(SavingsGoal.id)
            .join(Category, on=(SavingsGoal.category_id == Category.id))
            .where(
                (Category.type == "expense")
                & (Category.is_savings == True)  # noqa: E712
                & (fn.LOWER(fn.TRIM(Category.name)) == normalized.casefold())
            )
        )
        return [int(row.id) for row in rows]

    def _apply_savings_goal_delta(self, goal_id: int, amount_delta: MoneyLike) -> None:
        normalized_delta = self._money_to_decimal(amount_delta) or MONEY_ZERO
        if normalized_delta == MONEY_ZERO:
            return
        delta_cents = self._money_to_cents(normalized_delta) or 0
        SavingsGoal.update(
            current_amount=Case(
                None,
                ((SavingsGoal.current_amount + delta_cents < 0, 0),),
                SavingsGoal.current_amount + delta_cents,
            )
        ).where(SavingsGoal.id == goal_id).execute()

    def _apply_savings_goal_delta_for_transaction(self, tx: dict | None, sign: int) -> None:
        if not tx:
            return
        if str(tx.get("type")) != "expense":
            return
        if is_analytics_excluded_transaction(tx):
            return
        amount = self._money_to_decimal(tx.get("amount")) or MONEY_ZERO
        if amount <= MONEY_ZERO:
            return
        goal_ids = self._savings_goal_ids_for_category_name(cast(str | None, tx.get("category")))
        if not goal_ids:
            return
        delta = amount if sign >= 0 else -amount
        for goal_id in goal_ids:
            self._apply_savings_goal_delta(goal_id, delta)

    def delete_savings_goal(self, goal_id: int) -> None:
        goal = self.get_savings_goal(goal_id)
        category_id = goal.get("category_id")
        linked_category_id = int(category_id) if category_id is not None else None
        if linked_category_id is not None and self._category_has_transaction_history(linked_category_id):
            raise ValueError(
                f"Savings goal '{goal['name']}' cannot be deleted because its linked savings category has transaction history."
            )
        SavingsGoal.delete().where(SavingsGoal.id == goal_id).execute()
        if linked_category_id is None:
            return
        if self._category_is_linked_to_other_goal(linked_category_id, excluding_goal_id=goal_id):
            return
        category = self.get_category_by_id(linked_category_id)
        if category is not None:
            self.delete_category(linked_category_id)

    def update_savings_goal(
        self,
        goal_id: int,
        *,
        name: str,
        target_amount: MoneyLike,
        target_date: str | None = None,
    ) -> dict:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Goal name cannot be empty")
        normalized_target = self._money_to_decimal(target_amount) or MONEY_ZERO
        if normalized_target <= MONEY_ZERO:
            raise ValueError("Target amount must be greater than zero")
        linked_category = self._ensure_goal_linked_savings_category(normalized_name)
        (
            SavingsGoal.update(
                name=normalized_name,
                target_amount=self._money_to_cents(normalized_target),
                target_date=target_date,
                category_id=int(linked_category["id"]),
            )
            .where(SavingsGoal.id == goal_id)
            .execute()
        )
        return self.get_savings_goal(goal_id)
