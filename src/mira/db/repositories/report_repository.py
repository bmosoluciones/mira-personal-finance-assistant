# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from peewee import JOIN, Case, fn

from mira.db.money import MONEY_ZERO
from mira.db.model import Category, Transaction, TransactionTag
from mira.finance_summary import build_savings_lookup, summarize_financial_kpis
from mira.reports import mira_master_backend
from mira.transaction_kinds import analytics_included_expr


class ReportRepository:
    if TYPE_CHECKING:

        def get_categories(
            self,
            cat_type: str | None = None,
            *,
            include_savings: bool = True,
        ) -> list[dict[str, Any]]: ...

        def get_transactions(
            self,
            *,
            limit: int = 50,
            tx_type: str | None = None,
            account_id: int | None = None,
            since_date: str | None = None,
            until_date: str | None = None,
            category: str | None = None,
            payment_method: str | None = None,
            min_amount: Any = None,
            max_amount: Any = None,
            search: str | None = None,
            tag_id: int | None = None,
            include_children: bool = False,
        ) -> list[dict[str, Any]]: ...

        def _cents_to_money(self, value: object, *, allow_none: bool = False) -> Any: ...

    def summarize_financials(
        self,
        transactions: list[dict[str, Any]],
        *,
        categories: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        category_rows = categories if categories is not None else self.get_categories()
        return summarize_financial_kpis(transactions, build_savings_lookup(category_rows))

    def get_summary(self, since_date: str | None = None) -> dict[str, Any]:
        transactions = self.get_transactions(limit=1_000_000, since_date=since_date)
        summary = self.summarize_financials(transactions)
        return {
            "total_income": summary["income"],
            "total_expenses": summary["expense"],
            "savings": summary["savings"],
            "net": summary["net"],
        }

    def get_category_summary(
        self,
        since_date: str | None = None,
        until_date: str | None = None,
        aggregate_by_parent: bool = False,
    ) -> list[dict[str, Any]]:
        tx = Transaction.alias()
        linked_category = Category.alias()

        legacy_name_match = fn.LOWER(fn.TRIM(fn.COALESCE(tx.category, ""))) == fn.LOWER(fn.TRIM(linked_category.name))
        category_expr = fn.COALESCE(linked_category.name, tx.category, "")
        income_sum = fn.COALESCE(
            fn.SUM(Case(None, ((tx.type == "income", tx.amount),), 0.0)),
            0.0,
        )
        reportable_expense = (tx.type == "expense") & (fn.COALESCE(linked_category.is_savings, 0) == 0)
        expense_sum = fn.COALESCE(
            fn.SUM(Case(None, ((reportable_expense, tx.amount),), 0.0)),
            0.0,
        )

        query = tx.select(
            category_expr.alias("category"),
            income_sum.alias("total_income"),
            expense_sum.alias("total_expenses"),
        ).join(
            linked_category,
            JOIN.LEFT_OUTER,
            on=(
                ((tx.category_id.is_null(False)) & (tx.category_id == linked_category.id))
                | ((tx.category_id.is_null(True)) & (linked_category.type == tx.type) & legacy_name_match)
            ),
        )

        if since_date:
            query = query.where(tx.date >= since_date)
        if until_date:
            query = query.where(tx.date <= until_date)
        query = query.where(analytics_included_expr(tx))

        rows = [
            dict(row)
            for row in query.group_by(category_expr)
            .having((income_sum > 0) | (expense_sum > 0))
            .order_by(expense_sum.desc(), income_sum.desc())
            .dicts()
        ]
        for row in rows:
            row["total_income"] = self._cents_to_money(row["total_income"])
            row["total_expenses"] = self._cents_to_money(row["total_expenses"])

        if not aggregate_by_parent:
            return rows

        all_categories = self.get_categories()
        category_by_id = {int(category["id"]): category for category in all_categories}
        category_by_name = {str(category["name"]).strip().casefold(): category for category in all_categories}

        def _root_name(category_name: str) -> str:
            category = category_by_name.get(category_name.strip().casefold())
            if category is None:
                return category_name
            while category.get("parent_id") is not None:
                parent = category_by_id.get(int(category["parent_id"]))
                if parent is None:
                    break
                category = parent
            return str(category["name"])

        aggregated: dict[str, dict[str, Any]] = {}
        for row in rows:
            root = _root_name(str(row["category"]))
            item = aggregated.setdefault(
                root,
                {
                    "category": root,
                    "total_income": MONEY_ZERO,
                    "total_expenses": MONEY_ZERO,
                },
            )
            item["total_income"] = item["total_income"] + row["total_income"]
            item["total_expenses"] = item["total_expenses"] + row["total_expenses"]

        result = list(aggregated.values())
        result.sort(
            key=lambda item: (
                -float(item["total_expenses"]),
                -float(item["total_income"]),
            )
        )
        return result

    def get_tag_transaction_counts(
        self,
        *,
        since_date: str | None = None,
        until_date: str | None = None,
    ) -> dict[int, int]:
        tx = Transaction.alias()
        tx_tag = TransactionTag.alias()
        query = tx_tag.select(
            tx_tag.tag.alias("tag_id"),
            fn.COUNT(tx_tag.transaction_id).alias("count"),
        ).join(tx, on=(tx_tag.transaction_id == tx.id))
        query = query.where(analytics_included_expr(tx))
        if since_date:
            query = query.where(tx.date >= since_date)
        if until_date:
            query = query.where(tx.date <= until_date)
        return {int(row["tag_id"]): int(row["count"]) for row in query.group_by(tx_tag.tag).dicts()}

    def get_category_transaction_counts(
        self,
        *,
        since_date: str | None = None,
        until_date: str | None = None,
    ) -> dict[str, int]:
        category_expr = fn.COALESCE(Transaction.category, "")
        query = Transaction.select(
            category_expr.alias("category"),
            fn.COUNT(Transaction.id).alias("count"),
        )
        query = query.where(analytics_included_expr(Transaction))
        if since_date:
            query = query.where(Transaction.date >= since_date)
        if until_date:
            query = query.where(Transaction.date <= until_date)
        return {str(row["category"]): int(row["count"]) for row in query.group_by(category_expr).dicts()}

    def _transactions_for_month(self, year: int, month: int) -> list[dict[str, Any]]:
        return mira_master_backend.transactions_for_month(self, year, month)

    def get_budget_period_snapshot(
        self,
        year: int,
        month: int,
    ) -> tuple[dict | None, dict[str, dict[str, float]] | None, list[dict[str, Any]] | None]:
        return mira_master_backend.budget_period_snapshot(self, year, month)

    def get_mira_master_report(
        self,
        *,
        year: int,
        month: int,
        relevance_threshold: float = 0.10,
    ) -> dict[str, Any]:
        return mira_master_backend.get_mira_master_report(
            self,
            year=year,
            month=month,
            relevance_threshold=relevance_threshold,
        )

    def get_budget_alerts(self) -> list[dict]:
        return mira_master_backend.get_budget_alerts(self)
