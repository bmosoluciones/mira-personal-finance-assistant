# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, cast

from peewee import JOIN, Case, IntegrityError as PeeweeIntegrityError, fn

from mira.db.errors import BudgetValidationError, DuplicateBudgetCodeError
from mira.db.money import MONEY_ZERO, MoneyLike
from mira.db.model import Account, BudgetDetail, BudgetMaster, Category, Transaction


class BudgetRepository:
    if TYPE_CHECKING:

        def get_categories(
            self, cat_type: str | None = None, *, include_savings: bool = True
        ) -> list[dict[str, Any]]: ...
        def get_accounts(self, account_types: tuple[str, ...] | None = None) -> list[dict[str, Any]]: ...
        def _serialize_transaction_row(self, row: Transaction) -> dict[str, Any]: ...
        def _money_to_decimal(self, value: object, *, allow_none: bool = False) -> Any: ...
        def _cents_to_decimal(self, value: object, *, allow_none: bool = False) -> Any: ...
        def _money_to_cents(self, value: object, *, allow_none: bool = False) -> int | None: ...
        def _round_money(self, value: object) -> Any: ...
        def _atomic(self) -> Any: ...
        def get_setting(self, key: str) -> str | None: ...
        def set_setting(self, key: str, value: str) -> None: ...
        def get_default_currency(self) -> str: ...

    def _budget_master_totals_query(
        self,
        *,
        year: int | None = None,
        budget_id: int | None = None,
    ):
        category = Category.alias()
        income_sum = fn.COALESCE(
            fn.SUM(Case(None, (((category.type == "income"), BudgetDetail.amount),), 0)),
            0,
        )
        reportable_expense = (category.type == "expense") & (fn.COALESCE(category.is_savings, 0) == 0)
        expense_sum = fn.COALESCE(
            fn.SUM(Case(None, ((reportable_expense, BudgetDetail.amount),), 0)),
            0,
        )
        query = (
            BudgetMaster.select(
                BudgetMaster.id,
                BudgetMaster.code,
                BudgetMaster.year,
                BudgetMaster.is_default_year,
                BudgetMaster.currency,
                BudgetMaster.created_at,
                income_sum.alias("total_income_cents"),
                expense_sum.alias("total_expenses_cents"),
            )
            .join(BudgetDetail, JOIN.LEFT_OUTER, on=(BudgetDetail.budget == BudgetMaster.id))
            .join(category, JOIN.LEFT_OUTER, on=(BudgetDetail.category == category.id))
        )
        if year is not None:
            query = query.where(BudgetMaster.year == int(year))
        if budget_id is not None:
            query = query.where(BudgetMaster.id == int(budget_id))
        return query.group_by(
            BudgetMaster.id,
            BudgetMaster.code,
            BudgetMaster.year,
            BudgetMaster.is_default_year,
            BudgetMaster.currency,
            BudgetMaster.created_at,
        )

    def _serialize_budget_master_row(self, row: dict[str, Any]) -> dict[str, Any]:
        created_at = row["created_at"]
        created_value = (
            created_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(created_at, datetime) else str(created_at)
        )
        total_income = self._round_money(self._cents_to_decimal(row["total_income_cents"]) or MONEY_ZERO)
        total_expenses = self._round_money(self._cents_to_decimal(row["total_expenses_cents"]) or MONEY_ZERO)
        return {
            "id": row["id"],
            "code": row["code"],
            "year": row["year"],
            "is_default_year": int(bool(row["is_default_year"])),
            "currency": row["currency"],
            "created_at": created_value,
            "total_income": total_income,
            "total_expenses": total_expenses,
            "balance": self._round_money(total_income - total_expenses),
        }

    def _merge_budget_details_for_categories(
        self,
        source_category_id: int,
        target_category_id: int,
    ) -> None:
        source_details = BudgetDetail.select().where(BudgetDetail.category == source_category_id)
        for detail in source_details:
            target_detail = BudgetDetail.get_or_none(
                (BudgetDetail.budget == detail.budget_id)
                & (BudgetDetail.category == target_category_id)
                & (BudgetDetail.year == detail.year)
                & (BudgetDetail.month == detail.month)
            )
            if target_detail is not None:
                (
                    BudgetDetail.update(amount=BudgetDetail.amount + int(detail.amount or 0))
                    .where(BudgetDetail.id == target_detail.id)
                    .execute()
                )
                BudgetDetail.delete().where(BudgetDetail.id == detail.id).execute()
            else:
                (BudgetDetail.update(category=target_category_id).where(BudgetDetail.id == detail.id).execute())

    def _normalise_budget_code(self, code: str) -> str:
        normalized = code.strip()
        if not normalized:
            raise ValueError("Budget code cannot be empty")
        return normalized

    def _sync_budget_detail_rows(self, budget_id: int, year: int) -> None:
        categories = self.get_categories(include_savings=False)
        if not categories:
            return
        for category in categories:
            category_id = int(category["id"])
            for month in range(1, 13):
                BudgetDetail.insert(
                    budget=budget_id,
                    category=category_id,
                    year=year,
                    month=month,
                    amount=0,
                ).on_conflict_ignore().execute()

    def _budget_periods(self, granularity: str) -> list[dict[str, Any]]:
        if granularity == "annual":
            return [{"key": "annual", "label": "Anual", "months": list(range(1, 13))}]
        if granularity == "semiannual":
            return [
                {"key": "s1", "label": "S1", "months": [1, 2, 3, 4, 5, 6]},
                {"key": "s2", "label": "S2", "months": [7, 8, 9, 10, 11, 12]},
            ]
        if granularity == "monthly":
            labels = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
            return [{"key": f"m{month:02d}", "label": labels[month - 1], "months": [month]} for month in range(1, 13)]
        return [
            {"key": "q1", "label": "T1", "months": [1, 2, 3]},
            {"key": "q2", "label": "T2", "months": [4, 5, 6]},
            {"key": "q3", "label": "T3", "months": [7, 8, 9]},
            {"key": "q4", "label": "T4", "months": [10, 11, 12]},
        ]

    def _budget_savings_category_lookup(self) -> tuple[set[int], set[str]]:
        savings_category_ids: set[int] = set()
        savings_category_names: set[str] = set()
        for row in self.get_categories(cat_type="expense", include_savings=True):
            if not bool(int(row.get("is_savings") or 0)):
                continue
            category_id = row.get("id")
            if category_id is not None:
                savings_category_ids.add(int(category_id))
            category_name = str(row.get("name") or "").strip()
            if category_name:
                savings_category_names.add(category_name.casefold())
        return savings_category_ids, savings_category_names

    def _get_budget_transactions_for_period(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        account_currency_by_id = {int(row["id"]): str(row.get("currency") or "").upper() for row in self.get_accounts()}
        savings_category_ids, savings_category_names = self._budget_savings_category_lookup()
        query = (
            Transaction.select()
            .where(
                (fn.COALESCE(Transaction.is_transfer, 0) == 0)
                & (Transaction.date >= start_date)
                & (Transaction.date <= end_date)
            )
            .order_by(Transaction.date, Transaction.id)
        )

        rows: list[dict[str, Any]] = []
        for tx in query:
            tx_type = str(tx.type or "")
            tx_category = str(tx.category or "").strip().casefold()
            tx_category_id = int(tx.category_id) if tx.category_id is not None else None
            if tx_type == "expense" and (
                (tx_category_id is not None and tx_category_id in savings_category_ids)
                or tx_category in savings_category_names
            ):
                continue
            item = self._serialize_transaction_row(tx)
            account_id = item.get("account_id")
            item["account_currency"] = account_currency_by_id.get(int(account_id), "") if account_id is not None else ""
            rows.append(item)
        return rows

    def _get_budget_transactions(self, year: int) -> list[dict[str, Any]]:
        return self._get_budget_transactions_for_period(date(year, 1, 1), date(year, 12, 31))

    def _get_budget_execution_totals(
        self,
        *,
        year: int,
        budget_currency: str,
        category_ids: set[int],
        tx_types: tuple[str, ...],
        month: int | None = None,
    ) -> tuple[dict[tuple[int, int], Any], int]:
        if not category_ids:
            return {}, 0

        tx = Transaction.alias()
        account = Account.alias()
        linked_category = Category.alias()
        normalized_category_ids = sorted(int(category_id) for category_id in category_ids)
        start_date = date(year, month or 1, 1)
        end_date = date(year, month or 12, calendar.monthrange(year, month or 12)[1])

        query = (
            tx.select(
                linked_category.id.alias("resolved_category_id"),
                fn.strftime("%m", tx.date).alias("month_key"),
                fn.COALESCE(account.currency, "").alias("account_currency"),
                fn.COUNT(tx.id).alias("tx_count"),
                fn.COALESCE(fn.SUM(tx.amount), 0).alias("amount_total_cents"),
            )
            .join(account, JOIN.LEFT_OUTER, on=(tx.account_id == account.id))
            .switch(tx)
            .join(linked_category, JOIN.LEFT_OUTER, on=(tx.category_id == linked_category.id))
            .where(
                (fn.COALESCE(tx.is_transfer, 0) == 0)
                & (tx.date >= start_date)
                & (tx.date <= end_date)
                & (tx.type << list(tx_types))
                & (tx.category_id << normalized_category_ids)
                & ((tx.type != "expense") | (fn.COALESCE(linked_category.is_savings, 0) == 0))
            )
            .group_by(
                linked_category.id,
                fn.strftime("%m", tx.date),
                fn.COALESCE(account.currency, ""),
            )
            .dicts()
        )

        totals: dict[tuple[int, int], Any] = defaultdict(lambda: MONEY_ZERO)
        excluded_transactions = 0
        normalized_budget_currency = budget_currency.strip().upper()
        for row in query:
            category_id = row.get("resolved_category_id")
            month_key = str(row.get("month_key") or "").strip()
            if category_id is None or not month_key:
                continue
            account_currency = str(row.get("account_currency") or "").strip().upper()
            if account_currency != normalized_budget_currency:
                excluded_transactions += int(row.get("tx_count") or 0)
                continue
            totals[(int(category_id), int(month_key))] += (
                self._cents_to_decimal(row["amount_total_cents"]) or MONEY_ZERO
            )

        return dict(totals), excluded_transactions

    def _find_budget_source_year(self, budget_year: int) -> int | None:
        if budget_year <= 1900:
            return None
        savings_category_ids, savings_category_names = self._budget_savings_category_lookup()
        query = (
            Transaction.select(
                Transaction.date,
                Transaction.type,
                Transaction.category,
                Transaction.category_id,
                Transaction.is_transfer,
            )
            .where((Transaction.date >= date(1900, 1, 1)) & (Transaction.date <= date(budget_year - 1, 12, 31)))
            .order_by(Transaction.date.desc(), Transaction.id.desc())
        )

        active_months_by_year: dict[int, set[str]] = defaultdict(set)
        for tx in query:
            if bool(tx.is_transfer):
                continue
            tx_type = str(tx.type or "")
            tx_category = str(tx.category or "").strip().casefold()
            tx_category_id = int(tx.category_id) if tx.category_id is not None else None
            if tx_type == "expense" and (
                (tx_category_id is not None and tx_category_id in savings_category_ids)
                or tx_category in savings_category_names
            ):
                continue
            tx_date = tx.date.isoformat() if hasattr(tx.date, "isoformat") else str(tx.date or "")
            if len(tx_date) < 7:
                continue
            tx_year = int(tx_date[:4])
            active_months_by_year[tx_year].add(tx_date[:7])

        for year_cursor in sorted(active_months_by_year.keys(), reverse=True):
            if len(active_months_by_year[year_cursor]) >= 3:
                return year_cursor
        return None

    def _transaction_amount_for_budget_currency(
        self,
        tx: dict[str, Any],
        budget_currency: str,
    ):
        account_currency = str(tx.get("account_currency") or "").strip().upper()
        if account_currency == budget_currency:
            return self._money_to_decimal(tx.get("amount")) or MONEY_ZERO
        return None

    def get_active_budget(self) -> dict | None:
        active_code = (self.get_setting("active_budget_code") or "").strip()
        if active_code:
            budget = self.get_budget_by_code(active_code)
            if budget is not None:
                return budget
        current_year = date.today().year
        return self.get_default_budget_for_year(current_year)

    def list_budgets(self, year: int | None = None) -> list[dict]:
        query = self._budget_master_totals_query(year=year).order_by(
            BudgetMaster.year.desc(),
            BudgetMaster.is_default_year.desc(),
            BudgetMaster.code,
        )
        return [self._serialize_budget_master_row(row) for row in query.dicts()]

    def get_budget_by_id(self, budget_id: int) -> dict | None:
        row = next(iter(self._budget_master_totals_query(budget_id=budget_id).limit(1).dicts()), None)
        if row is None:
            return None
        budget = self._serialize_budget_master_row(row)
        self._sync_budget_detail_rows(int(budget["id"]), int(budget["year"]))
        return budget

    def get_budget_by_code(self, code: str) -> dict | None:
        normalized = self._normalise_budget_code(code)
        row = BudgetMaster.get_or_none(BudgetMaster.code == normalized)
        if row is None:
            return None
        return self.get_budget_by_id(int(row.id))

    def get_default_budget_for_year(self, year: int) -> dict | None:
        row = (
            BudgetMaster.select(BudgetMaster.id)
            .where((BudgetMaster.year == int(year)) & (BudgetMaster.is_default_year == True))  # noqa: E712
            .limit(1)
            .first()
        )
        if row is None:
            return None
        return self.get_budget_by_id(int(row.id))

    def _has_explicit_default_budget_for_year(self, year: int) -> bool:
        return (
            BudgetMaster.select(BudgetMaster.id)
            .where((BudgetMaster.year == int(year)) & (BudgetMaster.is_default_year == True))  # noqa: E712
            .limit(1)
            .first()
            is not None
        )

    def set_default_budget_for_year(self, budget_id: int) -> None:
        budget = self.get_budget_by_id(budget_id)
        if budget is None:
            raise ValueError(f"Budget {budget_id} not found")
        year = int(budget["year"])
        with self._atomic():
            BudgetMaster.update(is_default_year=False).where(BudgetMaster.year == year).execute()
            BudgetMaster.update(is_default_year=True).where(BudgetMaster.id == int(budget_id)).execute()

    def create_budget(self, code: str, year: int, currency: str | None = None) -> dict:
        normalized_code = self._normalise_budget_code(code)
        normalized_currency = (currency or self.get_default_currency()).strip().upper()
        if year < 1900 or year > 9999:
            raise BudgetValidationError("Budget year must be between 1900 and 9999")
        had_explicit_default = self._has_explicit_default_budget_for_year(year)
        try:
            budget_row = BudgetMaster.create(
                code=normalized_code,
                year=year,
                currency=normalized_currency,
                is_default_year=False,
            )
        except PeeweeIntegrityError as exc:
            raise DuplicateBudgetCodeError(f"Budget code '{normalized_code}' already exists") from exc
        budget_id = int(budget_row.id)
        if not had_explicit_default:
            self.set_default_budget_for_year(int(budget_id))
        self._sync_budget_detail_rows(int(budget_id), year)
        self.set_setting("active_budget_code", normalized_code)
        budget = self.get_budget_by_id(int(budget_id))
        if budget is None:
            raise RuntimeError(f"Failed to create budget {normalized_code}")
        return budget

    def delete_budget(self, budget_id: int) -> None:
        budget = self.get_budget_by_id(budget_id)
        year = int(budget["year"]) if budget is not None else None
        was_default = bool(int(budget.get("is_default_year") or 0)) if budget is not None else False
        BudgetMaster.delete().where(BudgetMaster.id == budget_id).execute()
        active_code = (self.get_setting("active_budget_code") or "").strip()
        if budget is not None and active_code == str(budget["code"]):
            self.set_setting("active_budget_code", "")
        if year is not None and was_default:
            remaining = self.list_budgets(year=year)
            if remaining:
                self.set_default_budget_for_year(int(remaining[0]["id"]))

    def upsert_budget_amount(
        self,
        budget_id: int,
        category_id: int,
        year: int,
        month: int,
        amount: MoneyLike,
    ) -> None:
        if month < 1 or month > 12:
            raise ValueError("Budget month must be between 1 and 12")
        BudgetDetail.insert(
            budget=budget_id,
            category=category_id,
            year=year,
            month=month,
            amount=self._money_to_cents(amount),
        ).on_conflict(
            conflict_target=[BudgetDetail.budget, BudgetDetail.category, BudgetDetail.year, BudgetDetail.month],
            update={BudgetDetail.amount: self._money_to_cents(amount)},
        ).execute()

    def get_budget_matrix(self, budget_id: int) -> dict[str, object]:
        budget = self.get_budget_by_id(budget_id)
        if budget is None:
            raise ValueError(f"Budget {budget_id} not found")

        self._sync_budget_detail_rows(int(budget["id"]), int(budget["year"]))
        categories = [
            row for row in self.get_categories(include_savings=False) if bool(int(row.get("is_savings") or 0)) is False
        ]
        detail_rows = (
            BudgetDetail.select()
            .where((BudgetDetail.budget == budget_id) & (BudgetDetail.year == int(budget["year"])))
            .order_by(BudgetDetail.month)
        )
        details_by_category_month = {
            (int(row.category_id), int(row.month)): self._cents_to_decimal(row.amount) or MONEY_ZERO
            for row in detail_rows
        }

        category_map: dict[int, dict[str, Any]] = {}
        income_months = [MONEY_ZERO for _ in range(12)]
        expense_months = [MONEY_ZERO for _ in range(12)]

        sorted_categories = sorted(
            categories,
            key=lambda row: (0 if str(row.get("type")) == "income" else 1, str(row.get("name") or "").casefold()),
        )
        for row in sorted_categories:
            category_id = int(row["id"])
            item = category_map.setdefault(
                category_id,
                {
                    "category_id": category_id,
                    "name": row["name"],
                    "type": row["type"],
                    "color": row["color"],
                    "months": [MONEY_ZERO for _ in range(12)],
                    "annual_total": MONEY_ZERO,
                },
            )
            item_months = cast(list[Any], item["months"])
            for month_idx in range(12):
                amount = details_by_category_month.get((category_id, month_idx + 1), MONEY_ZERO)
                item_months[month_idx] = amount
                item["annual_total"] = item["annual_total"] + amount
                if str(row["type"]) == "income":
                    income_months[month_idx] += amount
                else:
                    expense_months[month_idx] += amount

        income_total = self._round_money(sum(income_months, MONEY_ZERO))
        expense_total = self._round_money(sum(expense_months, MONEY_ZERO))
        balance_months = [self._round_money(income_months[idx] - expense_months[idx]) for idx in range(12)]
        return {
            "budget": budget,
            "rows": list(category_map.values()),
            "totals": {
                "income": [self._round_money(value) for value in income_months],
                "expense": [self._round_money(value) for value in expense_months],
                "balance": balance_months,
                "income_annual": income_total,
                "expense_annual": expense_total,
                "balance_annual": self._round_money(income_total - expense_total),
            },
        }

    def budget_has_values(self, budget_id: int) -> bool:
        return (
            BudgetDetail.select(BudgetDetail.id)
            .where((BudgetDetail.budget == budget_id) & (fn.ABS(BudgetDetail.amount) > 0))
            .limit(1)
            .first()
            is not None
        )

    def propose_budget(self, budget_id: int) -> dict[str, object]:
        budget = self.get_budget_by_id(budget_id)
        if budget is None:
            raise ValueError(f"Budget {budget_id} not found")

        budget_year = int(budget["year"])
        source_year = self._find_budget_source_year(budget_year)
        if source_year is None:
            return {
                "applied": False,
                "reason": "No hay información suficiente en periodos anteriores para proponer un presupuesto.",
            }

        source_transactions = self._get_budget_transactions(source_year)
        if not source_transactions:
            return {
                "applied": False,
                "reason": "No hay información suficiente en periodos anteriores para proponer un presupuesto.",
            }

        categories = self.get_categories(include_savings=False)
        category_lookup = {
            (str(category["type"]), str(category["name"]).strip().casefold()): int(category["id"])
            for category in categories
        }
        annual_totals: dict[int, Any] = defaultdict(lambda: MONEY_ZERO)
        used_months: set[str] = set()

        for tx in source_transactions:
            tx_type = str(tx.get("type") or "").strip()
            category_name = str(tx.get("category") or "").strip()
            if not category_name or tx_type not in {"income", "expense"}:
                continue
            amount = self._transaction_amount_for_budget_currency(tx, str(budget["currency"]))
            if amount is None:
                continue
            category_id = category_lookup.get((tx_type, category_name.casefold()))
            if category_id is None:
                continue
            annual_totals[category_id] += amount
            used_months.add(str(tx.get("date") or "")[:7])

        if len(used_months) < 3:
            return {
                "applied": False,
                "reason": "No hay información suficiente en periodos anteriores para proponer un presupuesto.",
            }

        applied_cells = 0
        with self._atomic():
            for category in categories:
                category_id = int(category["id"])
                average_amount = self._round_money(annual_totals.get(category_id, MONEY_ZERO) / 12)
                for month in range(1, 13):
                    self.upsert_budget_amount(
                        int(budget["id"]),
                        category_id,
                        int(budget["year"]),
                        month,
                        average_amount,
                    )
                    applied_cells += 1

        return {
            "applied": True,
            "source_year": source_year,
            "applied_cells": applied_cells,
        }

    def get_budget_comparison(self, budget_id: int, granularity: str = "quarterly") -> dict[str, object]:
        budget = self.get_budget_by_id(budget_id)
        if budget is None:
            raise ValueError(f"Budget {budget_id} not found")

        matrix = self.get_budget_matrix(budget_id)
        periods = self._budget_periods(granularity)
        period_index_by_month: dict[int, int] = {}
        for index, period in enumerate(periods):
            for month in cast(list[int], period["months"]):
                period_index_by_month[int(month)] = index

        rows: list[dict[str, Any]] = []
        category_ids: set[int] = set()
        for source_row in cast(list[dict[str, Any]], matrix["rows"]):
            months = cast(list[Any], source_row["months"])
            period_values: list[dict[str, Any]] = []
            for period in periods:
                month_indexes = [int(month) - 1 for month in cast(list[int], period["months"])]
                budget_value = self._round_money(sum((months[idx] for idx in month_indexes), MONEY_ZERO))
                period_values.append(
                    {
                        "label": period["label"],
                        "budget": budget_value,
                        "real": MONEY_ZERO,
                        "variance": MONEY_ZERO,
                    }
                )
            row = {
                "category_id": source_row["category_id"],
                "name": source_row["name"],
                "type": source_row["type"],
                "periods": period_values,
                "annual_budget": self._round_money(source_row["annual_total"]),
                "annual_real": MONEY_ZERO,
                "annual_variance": MONEY_ZERO,
            }
            rows.append(row)
            category_ids.add(int(source_row["category_id"]))

        actuals_by_category_month, excluded_transactions = self._get_budget_execution_totals(
            year=int(budget["year"]),
            budget_currency=str(budget["currency"]),
            category_ids=category_ids,
            tx_types=("income", "expense"),
        )
        for row in rows:
            category_id = int(row["category_id"])
            row_periods = cast(list[dict[str, Any]], row["periods"])
            annual_real = self._round_money(
                sum(
                    (actuals_by_category_month.get((category_id, month), MONEY_ZERO) for month in range(1, 13)),
                    MONEY_ZERO,
                )
            )
            for period_idx, period in enumerate(periods):
                period_real = self._round_money(
                    sum(
                        (
                            actuals_by_category_month.get((category_id, int(month)), MONEY_ZERO)
                            for month in cast(list[int], period["months"])
                        ),
                        MONEY_ZERO,
                    )
                )
                row_periods[period_idx]["real"] = period_real
            row["annual_real"] = annual_real

        totals: dict[str, Any] = {
            "income": [
                {"label": str(period["label"]), "budget": MONEY_ZERO, "real": MONEY_ZERO, "variance": MONEY_ZERO}
                for period in periods
            ],
            "expense": [
                {"label": str(period["label"]), "budget": MONEY_ZERO, "real": MONEY_ZERO, "variance": MONEY_ZERO}
                for period in periods
            ],
            "balance": [
                {"label": str(period["label"]), "budget": MONEY_ZERO, "real": MONEY_ZERO, "variance": MONEY_ZERO}
                for period in periods
            ],
            "income_annual": {"budget": MONEY_ZERO, "real": MONEY_ZERO, "variance": MONEY_ZERO},
            "expense_annual": {"budget": MONEY_ZERO, "real": MONEY_ZERO, "variance": MONEY_ZERO},
            "balance_annual": {"budget": MONEY_ZERO, "real": MONEY_ZERO, "variance": MONEY_ZERO},
        }

        income_periods = cast(list[dict[str, Any]], totals["income"])
        expense_periods = cast(list[dict[str, Any]], totals["expense"])
        balance_periods = cast(list[dict[str, Any]], totals["balance"])
        income_annual = cast(dict[str, Any], totals["income_annual"])
        expense_annual = cast(dict[str, Any], totals["expense_annual"])
        balance_annual = cast(dict[str, Any], totals["balance_annual"])

        for row in rows:
            row_periods = cast(list[dict[str, Any]], row["periods"])
            for period in row_periods:
                period["variance"] = self._round_money(period["real"] - period["budget"])
            row["annual_variance"] = self._round_money(row["annual_real"] - row["annual_budget"])

            if row["type"] == "income":
                target_periods = income_periods
                target_annual = income_annual
            else:
                target_periods = expense_periods
                target_annual = expense_annual

            for index, period in enumerate(row_periods):
                target_periods[index]["budget"] = self._round_money(target_periods[index]["budget"] + period["budget"])
                target_periods[index]["real"] = self._round_money(target_periods[index]["real"] + period["real"])
            target_annual["budget"] = self._round_money(target_annual["budget"] + row["annual_budget"])
            target_annual["real"] = self._round_money(target_annual["real"] + row["annual_real"])

        for index in range(len(periods)):
            income_periods[index]["variance"] = self._round_money(
                income_periods[index]["real"] - income_periods[index]["budget"]
            )
            expense_periods[index]["variance"] = self._round_money(
                expense_periods[index]["real"] - expense_periods[index]["budget"]
            )
            balance_periods[index]["budget"] = self._round_money(
                income_periods[index]["budget"] - expense_periods[index]["budget"]
            )
            balance_periods[index]["real"] = self._round_money(
                income_periods[index]["real"] - expense_periods[index]["real"]
            )
            balance_periods[index]["variance"] = self._round_money(
                balance_periods[index]["real"] - balance_periods[index]["budget"]
            )

        income_annual["variance"] = self._round_money(income_annual["real"] - income_annual["budget"])
        expense_annual["variance"] = self._round_money(expense_annual["real"] - expense_annual["budget"])
        balance_annual["budget"] = self._round_money(income_annual["budget"] - expense_annual["budget"])
        balance_annual["real"] = self._round_money(income_annual["real"] - expense_annual["real"])
        balance_annual["variance"] = self._round_money(balance_annual["real"] - balance_annual["budget"])

        return {
            "budget": budget,
            "granularity": granularity,
            "periods": periods,
            "rows": rows,
            "totals": totals,
            "excluded_transactions": excluded_transactions,
        }

    def get_monthly_budget_tracking(self, budget_id: int, year: int, month: int) -> dict[str, Any]:
        budget = self.get_budget_by_id(budget_id)
        if budget is None:
            raise ValueError(f"Budget {budget_id} not found")
        if month < 1 or month > 12:
            raise ValueError("Budget month must be between 1 and 12")

        budget_year = int(budget["year"])
        if year != budget_year:
            raise ValueError(f"Monthly budget tracking is only available for budget year {budget_year}.")

        matrix = self.get_budget_matrix(budget_id)
        assigned_by_category: dict[int, Any] = {}
        for row in cast(list[dict[str, Any]], matrix["rows"]):
            if row["type"] != "expense":
                continue
            months = cast(list[Any], row["months"])
            assigned_by_category[int(row["category_id"])] = self._round_money(months[month - 1])

        expense_category_ids: set[int] = set()
        for row in cast(list[dict[str, Any]], matrix["rows"]):
            if row["type"] != "expense":
                continue
            expense_category_ids.add(int(row["category_id"]))

        execution_by_category, excluded_transactions = self._get_budget_execution_totals(
            year=year,
            budget_currency=str(budget["currency"]),
            category_ids=expense_category_ids,
            tx_types=("expense",),
            month=month,
        )

        rows: list[dict[str, Any]] = []
        for source_row in cast(list[dict[str, Any]], matrix["rows"]):
            if source_row["type"] != "expense":
                continue
            category_id = int(source_row["category_id"])
            assigned = self._round_money(assigned_by_category.get(category_id, MONEY_ZERO))
            executed = self._round_money(execution_by_category.get((category_id, month), MONEY_ZERO))
            if assigned <= MONEY_ZERO and executed <= MONEY_ZERO:
                continue
            available = self._round_money(assigned - executed)
            status = (
                "over"
                if executed > assigned
                else "matched" if abs(available) < MONEY_ZERO + self._money_to_decimal("0.005") else "available"
            )
            rows.append(
                {
                    "category_id": category_id,
                    "name": source_row["name"],
                    "assigned": assigned,
                    "executed": executed,
                    "available": available,
                    "status": status,
                }
            )
        rows.sort(key=lambda item: str(item["name"]).casefold())

        total_assigned = self._round_money(sum((row["assigned"] for row in rows), MONEY_ZERO))
        total_executed = self._round_money(sum((row["executed"] for row in rows), MONEY_ZERO))
        total_available = self._round_money(total_assigned - total_executed)

        categories_with_assignment = [row for row in rows if row["assigned"] > MONEY_ZERO]
        has_defined_budget = bool(categories_with_assignment)
        is_partial = has_defined_budget and len(categories_with_assignment) < len(rows)

        return {
            "budget": budget,
            "year": year,
            "month": month,
            "rows": rows,
            "totals": {
                "assigned": total_assigned,
                "executed": total_executed,
                "available": total_available,
            },
            "validations": {
                "has_defined_budget": has_defined_budget,
                "is_partial_budget": is_partial,
            },
            "excluded_transactions": excluded_transactions,
        }

    def reassign_monthly_budget(
        self,
        budget_id: int,
        year: int,
        month: int,
        source_category_id: int,
        target_category_id: int,
        amount: MoneyLike,
    ) -> dict[str, Any]:
        if source_category_id == target_category_id:
            raise ValueError("Source and target categories must be different.")
        normalized_amount = self._money_to_decimal(amount) or MONEY_ZERO
        if normalized_amount <= MONEY_ZERO:
            raise ValueError("Reassignment amount must be greater than zero.")

        tracking = self.get_monthly_budget_tracking(budget_id, year, month)
        rows = {int(row["category_id"]): row for row in cast(list[dict[str, Any]], tracking["rows"])}
        source = rows.get(source_category_id)
        target = rows.get(target_category_id)
        if source is None:
            raise ValueError("Source category is not eligible for reassignment.")
        if target is None:
            raise ValueError("Target category is not available in the monthly report.")

        source_available = self._money_to_decimal(source["available"]) or MONEY_ZERO
        if source_available <= MONEY_ZERO:
            raise ValueError("Source category has no available amount.")
        if normalized_amount > source_available:
            raise ValueError("Reassignment amount cannot exceed source available amount.")

        budget = self.get_budget_by_id(budget_id)
        if budget is None:
            raise ValueError(f"Budget {budget_id} not found")
        budget_year = int(budget["year"])

        source_assigned = self._money_to_decimal(source["assigned"]) or MONEY_ZERO
        target_assigned = self._money_to_decimal(target["assigned"]) or MONEY_ZERO
        self.upsert_budget_amount(
            budget_id,
            source_category_id,
            budget_year,
            month,
            self._round_money(source_assigned - normalized_amount),
        )
        self.upsert_budget_amount(
            budget_id,
            target_category_id,
            budget_year,
            month,
            self._round_money(target_assigned + normalized_amount),
        )

        refreshed = self.get_monthly_budget_tracking(budget_id, year, month)
        return {
            "source_category_id": source_category_id,
            "target_category_id": target_category_id,
            "amount": self._round_money(normalized_amount),
            "tracking": refreshed,
        }
