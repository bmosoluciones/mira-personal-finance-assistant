# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Module documentation."""

from __future__ import annotations


import calendar
from datetime import date
from typing import TYPE_CHECKING, Any, cast

from mira.db.helpers import _UNSET
from mira.db.money import MONEY_ZERO, MoneyLike
from mira.db.model import RecurringTransaction


class RecurringRepository:
    """Represent the RecurringRepository class."""

    if TYPE_CHECKING:

        def get_account_by_id(self, account_id: int) -> dict[str, Any] | None:
            """Return get account by id."""

        def get_category_by_id(self, cat_id: int) -> dict[str, Any] | None:
            """Return get category by id."""

        def _cents_to_money(self, value: object, *, allow_none: bool = False) -> Any:
            """Return cents to money."""

        def _enrich_recurring_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            """Return enrich recurring rows."""

        def get_accounts(self, account_types: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
            """Return get accounts."""

        def get_categories(self, cat_type: str | None = None, *, include_savings: bool = True) -> list[dict[str, Any]]:
            """Return get categories."""

        def _resolve_transaction_category_id(self, tx_type: str, category: str | None) -> int | None:
            """Return resolve transaction category id."""

        def _normalize_tag_ids(self, tag_ids: list[int] | None) -> list[int]:
            """Return normalize tag ids."""

        def _atomic(self) -> Any:
            """Return atomic."""

        def _money_to_cents(self, value: object, *, allow_none: bool = False) -> int | None:
            """Return money to cents."""

        def _money_to_decimal(self, value: object, *, allow_none: bool = False) -> Any:
            """Return money to decimal."""

        def _replace_recurring_tags(self, recurring_id: int, tag_ids: list[int]) -> None:
            """Return replace recurring tags."""

        def get_recurring_tags(self, recurring_id: int) -> list[dict[str, Any]]:
            """Return get recurring tags."""

        def get_setting(self, key: str) -> str | None:
            """Return get setting."""

        def add_transaction(
            self,
            *,
            account_id: int,
            tx_type: str,
            amount: MoneyLike,
            description: str | None = None,
            category: str | None = None,
            subcategory: str | None = None,
            payment_method: str = "cash",
            receipt_path: str | None = None,
            tx_date: str | None = None,
            note: str | None = None,
            to_account_id: int | None = None,
            is_transfer: int = 0,
            exchange_rate: float | None = None,
            converted_amount: MoneyLike | None = None,
            category_id: int | None = None,
            source: str | None = None,
        ) -> dict[str, Any]:
            """Return add transaction."""

        def set_transaction_tags(self, transaction_id: int, tag_ids: list[int]) -> None:
            """Return set transaction tags."""

        def set_setting(self, key: str, value: str) -> None:
            """Return set setting."""

    def _get_recurring_by_id(self, rec_id: int) -> dict | None:
        """Return get recurring by id."""
        row = RecurringTransaction.get_or_none(RecurringTransaction.id == rec_id)
        if row is None:
            return None
        account = self.get_account_by_id(int(row.account_id)) if row.account_id is not None else None
        category = self.get_category_by_id(int(row.category_id)) if row.category_id is not None else None
        payload = {
            "id": row.id,
            "account_id": row.account_id,
            "type": row.type,
            "amount": self._cents_to_money(row.amount),
            "description": row.description,
            "category": row.category,
            "category_id": row.category_id,
            "note": row.note,
            "day_of_month": row.day_of_month,
            "account_name": account["name"] if account is not None else None,
            "category_name": category["name"] if category is not None else None,
        }
        return self._enrich_recurring_rows([payload])[0]

    def get_recurring(self) -> list[dict]:
        """Return get recurring."""
        accounts = {int(item["id"]): item for item in self.get_accounts()}
        categories = {int(item["id"]): item for item in self.get_categories()}
        rows = []
        for row in RecurringTransaction.select().order_by(RecurringTransaction.id):
            account = accounts.get(int(row.account_id)) if row.account_id is not None else None
            category = categories.get(int(row.category_id)) if row.category_id is not None else None
            rows.append(
                {
                    "id": row.id,
                    "account_id": row.account_id,
                    "type": row.type,
                    "amount": self._cents_to_money(row.amount),
                    "description": row.description,
                    "category": row.category,
                    "category_id": row.category_id,
                    "note": row.note,
                    "day_of_month": row.day_of_month,
                    "account_name": account["name"] if account is not None else None,
                    "category_name": category["name"] if category is not None else None,
                }
            )
        return self._enrich_recurring_rows(rows)

    def _resolve_recurring_category(
        self,
        tx_type: str,
        category: str | None,
        category_id: int | None,
    ) -> tuple[int | None, str | None]:
        """Return resolve recurring category."""
        if category_id is not None:
            category_row = self.get_category_by_id(int(category_id))
            if category_row is None:
                raise ValueError(f"Category {category_id} not found")
            if category_row["type"] != tx_type:
                raise ValueError(f"Category {category_id} is not valid for {tx_type} transactions")
            return int(category_row["id"]), str(category_row["name"])

        normalized = (category or "").strip() or None
        if normalized is None:
            return None, None

        resolved_category_id = self._resolve_transaction_category_id(tx_type, normalized)
        if resolved_category_id is None:
            return None, normalized

        category_row = self.get_category_by_id(resolved_category_id)
        return resolved_category_id, (str(category_row["name"]) if category_row is not None else normalized)

    def add_recurring(
        self,
        *,
        account_id: int,
        tx_type: str,
        amount: MoneyLike,
        description: str | None,
        category: str | None,
        note: str | None,
        day_of_month: int,
        category_id: int | None = None,
        tag_ids: list[int] | None = None,
    ) -> dict:
        """Return add recurring."""
        resolved_category_id, resolved_category = self._resolve_recurring_category(tx_type, category, category_id)
        normalized_tag_ids = self._normalize_tag_ids(tag_ids)
        with self._atomic():
            recurring = RecurringTransaction.create(
                account=account_id,
                type=tx_type,
                amount=self._money_to_cents(amount),
                description=description,
                category=resolved_category,
                category_id=resolved_category_id,
                note=note,
                day_of_month=day_of_month,
            )
            rec_id = int(recurring.id)  # type: ignore[call-overload]
            self._replace_recurring_tags(rec_id, normalized_tag_ids)
        result = self._get_recurring_by_id(int(rec_id))
        if result is None:
            raise RuntimeError("Failed to create recurring transaction")
        return result

    def delete_recurring(self, rec_id: int) -> None:
        """Return delete recurring."""
        RecurringTransaction.delete().where(RecurringTransaction.id == rec_id).execute()

    def update_recurring(self, rec_id: int, **kwargs: object) -> dict:
        """Return update recurring."""
        existing = RecurringTransaction.get_or_none(RecurringTransaction.id == rec_id)
        if existing is None:
            raise ValueError(f"Recurring transaction {rec_id} not found")
        old = {
            "account_id": existing.account_id,
            "type": existing.type,
            "amount": self._cents_to_money(existing.amount),
            "description": existing.description,
            "category": existing.category,
            "category_id": existing.category_id,
            "note": existing.note,
            "day_of_month": existing.day_of_month,
        }
        current_tag_ids = [int(tag["id"]) for tag in self.get_recurring_tags(rec_id)]

        new_account_id_raw: Any = kwargs.get("account_id", old["account_id"])
        new_account_id = int(new_account_id_raw) if new_account_id_raw is not None else None
        if new_account_id is not None and self.get_account_by_id(new_account_id) is None:
            raise ValueError(f"Account {new_account_id} not found")

        new_type = kwargs.get("tx_type", old["type"])
        if new_type not in ("income", "expense"):
            raise ValueError("Recurring transaction type must be 'income' or 'expense'")

        new_amount_raw: Any = kwargs.get("amount", old["amount"])
        new_amount = self._money_to_decimal(new_amount_raw) or MONEY_ZERO
        if new_amount <= MONEY_ZERO:
            raise ValueError("Recurring transaction amount must be positive")

        new_day_raw: Any = kwargs.get("day_of_month", old["day_of_month"])
        new_day = int(new_day_raw)
        if new_day < 1 or new_day > 28:
            raise ValueError("Recurring day_of_month must be between 1 and 28")

        explicit_category_id = kwargs.get("category_id", _UNSET)
        if explicit_category_id is _UNSET:
            current_category_id = old.get("category_id")
            category_id_value = int(cast(Any, current_category_id)) if current_category_id is not None else None
        else:
            category_id_value = int(cast(Any, explicit_category_id)) if explicit_category_id is not None else None

        resolved_category_id, resolved_category = self._resolve_recurring_category(
            str(new_type),
            cast(str | None, kwargs.get("category", old.get("category"))),
            category_id_value,
        )
        explicit_tag_ids = kwargs.get("tag_ids", _UNSET)
        if explicit_tag_ids is _UNSET:
            normalized_tag_ids = self._normalize_tag_ids(current_tag_ids)
        else:
            normalized_tag_ids = self._normalize_tag_ids(cast(list[int] | None, explicit_tag_ids))

        with self._atomic():
            (
                RecurringTransaction.update(
                    account=new_account_id,
                    type=new_type,
                    amount=self._money_to_cents(new_amount),
                    description=kwargs.get("description", old.get("description")),
                    category=resolved_category,
                    category_id=resolved_category_id,
                    note=kwargs.get("note", old.get("note")),
                    day_of_month=new_day,
                )
                .where(RecurringTransaction.id == rec_id)
                .execute()
            )
            self._replace_recurring_tags(rec_id, normalized_tag_ids)
        updated = self._get_recurring_by_id(rec_id)
        if updated is None:
            raise RuntimeError(f"Failed to update recurring transaction {rec_id}")
        return updated

    def apply_recurring_for_month(self, year: int, month: int) -> list[dict]:
        """Return apply recurring for month."""
        if month < 1 or month > 12:
            raise ValueError("month must be between 1 and 12")
        if year < 1900 or year > 9999:
            raise ValueError("year must be between 1900 and 9999")

        month_key = f"recurring_applied_{year:04d}-{month:02d}"
        with self._atomic():
            if self.get_setting(month_key):
                return []

            recurring = self.get_recurring()
            created: list[dict] = []
            max_day = calendar.monthrange(year, month)[1]
            for rec in recurring:
                if rec["account_id"] is None:
                    continue
                day = min(rec["day_of_month"], max_day)
                tx_date = date(year, month, day).isoformat()
                tx = self.add_transaction(
                    account_id=rec["account_id"],
                    tx_type=rec["type"],
                    amount=rec["amount"],
                    description=rec["description"],
                    category=rec["category"],
                    category_id=rec.get("category_id"),
                    tx_date=tx_date,
                    note=rec["note"],
                )
                if rec.get("tag_ids"):
                    self.set_transaction_tags(int(tx["id"]), cast(list[int], rec["tag_ids"]))
                created.append(tx)

            if created:
                self.set_setting(month_key, "applied")
            return created
