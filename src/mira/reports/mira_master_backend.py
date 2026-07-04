# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Module documentation."""

from __future__ import annotations

from datetime import date
from typing import Any, cast

from mira.db.model import BudgetDetail, Category
from mira.reports.mira_master import ReportInputs, build_report_payload, month_bounds, shift_month
from mira.transaction_kinds import is_analytics_excluded_transaction


def transactions_for_month(db: Any, year: int, month: int) -> list[dict[str, Any]]:
    """Return transactions for month."""
    start, end = month_bounds(year, month)
    txs = db.get_transactions(limit=50_000, since_date=start.isoformat(), until_date=end.isoformat())
    return [tx for tx in txs if not is_analytics_excluded_transaction(tx)]


def budget_period_snapshot(
    db: Any,
    year: int,
    month: int,
) -> tuple[dict | None, dict[str, dict[str, float]] | None, list[dict[str, Any]] | None]:
    """Return budget period snapshot."""
    budget = db.get_default_budget_for_year(year)
    if budget is None:
        return None, None, None

    query = (
        BudgetDetail.select(
            Category.id.alias("category_id"),
            Category.type,
            Category.name,
            Category.is_savings,
            BudgetDetail.amount,
        )
        .join(Category, on=(BudgetDetail.category == Category.id))
        .where(
            (BudgetDetail.budget == int(budget["id"]))
            & (BudgetDetail.year == int(year))
            & (BudgetDetail.month == int(month))
        )
    )
    rows = [dict(row) for row in query.dicts()]  # type: ignore[call-overload]
    for row in rows:
        row["amount"] = db._cents_to_money(row["amount"])

    grouped: dict[str, dict[str, float]] = {"income": {}, "expense": {}}
    for row in rows:
        row_type = str(row.get("type") or "")
        if row_type not in grouped:
            continue
        if row_type == "expense" and int(row.get("is_savings") or 0) == 1:
            continue
        grouped[row_type][str(row.get("name") or "")] = float(row.get("amount") or 0.0)

    if (sum(grouped["income"].values()) + sum(grouped["expense"].values())) <= 0:
        return None, None, rows

    return budget, grouped, rows


def get_mira_master_report(
    db: Any,
    *,
    year: int,
    month: int,
    relevance_threshold: float = 0.10,
) -> dict[str, Any]:
    """Return get mira master report."""
    if year < 1900 or year > 9999:
        raise ValueError("year out of range")
    if month < 1 or month > 12:
        raise ValueError("month out of range")
    db.increment_achievement_counter("mira_report_views")

    month_txs = transactions_for_month(db, year, month)
    start, end = month_bounds(year, month)
    month_txs_raw = db.get_transactions(limit=50_000, since_date=start.isoformat(), until_date=end.isoformat())
    prev_year, prev_month = shift_month(year, month, -1)
    previous_txs = transactions_for_month(db, prev_year, prev_month)

    trailing_3: list[list[dict[str, Any]]] = []
    for delta in range(-3, 0):
        y, m = shift_month(year, month, delta)
        txs = transactions_for_month(db, y, m)
        if txs:
            trailing_3.append(txs)

    trailing_6: list[tuple[int, int, list[dict[str, Any]]]] = []
    for delta in range(-6, 0):
        y, m = shift_month(year, month, delta)
        txs = transactions_for_month(db, y, m)
        trailing_6.append((y, m, txs))

    historical_6: list[tuple[int, int, list[dict[str, Any]]]] = []
    for delta in range(-5, 1):
        y, m = shift_month(year, month, delta)
        txs = transactions_for_month(db, y, m)
        historical_6.append((y, m, txs))

    ytd_months: list[tuple[int, int, list[dict[str, Any]]]] = []
    for m in range(1, month + 1):
        ytd_months.append((year, m, transactions_for_month(db, year, m)))

    tx_ids = [int(tx["id"]) for tx in month_txs if tx.get("id") is not None]
    tags_by_tx = db.get_transactions_tags_bulk(tx_ids)

    budget, budget_grouped, budget_rows = budget_period_snapshot(db, year, month)
    accounts = db.get_accounts()
    account_balance_total = sum(float(acc.get("balance") or 0.0) for acc in accounts)

    categories = db.get_categories()
    goals = db.get_savings_goals()
    category_relations = db.list_category_relations()
    language = str(db.get_setting("language") or "en").strip().lower()
    if language not in {"es", "en"}:
        language = "en"

    return build_report_payload(
        ReportInputs(
            year=year,
            month=month,
            month_transactions=month_txs,
            month_transactions_raw=month_txs_raw,
            previous_transactions=previous_txs,
            trailing_3=trailing_3,
            comparison_trailing_6=trailing_6,
            historical_6=historical_6,
            ytd_months=ytd_months,
            categories=categories,
            tags_by_tx=tags_by_tx,
            budget=budget,
            budget_monthly_by_type=budget_grouped,
            budget_category_rows=budget_rows,
            accounts=accounts,
            account_balance_total=account_balance_total,
            savings_goals=goals,
            relevance_threshold=relevance_threshold,
            language=language,
            category_relations=category_relations,
        )
    )


def get_budget_alerts(db: Any) -> list[dict]:
    """Return current-month alerts driven by the active annual budget.

    Contract:
    - Uses monthly real-vs-budget execution for the active budget.
    - Returns only ``name``, ``budget_amount``, ``spent_amount``, ``progress`` and ``status``.
    - Does not include bucket-cycle metadata (for example ``start_day``/``end_day``).
    """
    active_budget = db.get_active_budget()
    if active_budget is None:
        return []
    comparison = db.get_budget_comparison(int(active_budget["id"]), granularity="monthly")
    current_month_index = date.today().month - 1
    alerts: list[dict] = []
    comparison_rows = cast(list[dict[str, Any]], comparison["rows"])
    for row in comparison_rows:
        if row["type"] != "expense":
            continue
        current_period = cast(list[dict[str, Any]], row["periods"])[current_month_index]
        budget_amount = float(current_period["budget"])
        real_amount = float(current_period["real"])
        progress = (real_amount / budget_amount) if budget_amount > 0 else 0.0
        status = "ok"
        if budget_amount > 0 and real_amount >= budget_amount:
            status = "exceeded"
        elif budget_amount > 0 and progress >= 0.75:
            status = "warning"
        alerts.append(
            {
                "name": row["name"],
                "budget_amount": budget_amount,
                "spent_amount": real_amount,
                "progress": progress,
                "status": status,
            }
        )
    return alerts
