# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Canonical financial KPI helpers shared across MIRA."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mira.db.money import MONEY_ZERO, Money, money_to_decimal, round_money
from mira.transaction_kinds import TransactionType, is_analytics_excluded_transaction

SavingsLookup = tuple[set[int], set[str]]


@dataclass(frozen=True, slots=True)
class FinancialSummary:
    """Aggregated financial KPIs for a period or set of transactions."""

    income: Money
    expense: Money
    savings: Money
    net: Money


def build_savings_lookup(categories: list[dict[str, Any]]) -> SavingsLookup:
    """Return build savings lookup."""
    savings_ids: set[int] = set()
    savings_names: set[str] = set()
    for category in categories:
        if str(category.get("type") or "").strip().casefold() != TransactionType.EXPENSE:
            continue
        if int(category.get("is_savings") or 0) != 1:
            continue

        category_id = category.get("id")
        if category_id is not None:
            savings_ids.add(int(category_id))

        name = str(category.get("name") or "").strip().casefold()
        if name:
            savings_names.add(name)

    return savings_ids, savings_names


def is_savings_transaction(tx: dict[str, Any], savings_lookup: SavingsLookup) -> bool:
    """Return whether savings transaction."""
    if str(tx.get("type") or "").strip().casefold() != TransactionType.EXPENSE:
        return False

    savings_ids, savings_names = savings_lookup
    category_id = tx.get("category_id")
    if category_id is not None:
        try:
            if int(category_id) in savings_ids:
                return True
        except (TypeError, ValueError):
            pass

    category_name = str(tx.get("category") or "").strip().casefold()
    return bool(category_name) and category_name in savings_names


def summarize_financial_kpis(
    transactions: list[dict[str, Any]],
    savings_lookup: SavingsLookup,
) -> FinancialSummary:
    """Return summarize financial kpis."""
    income = MONEY_ZERO
    expense = MONEY_ZERO
    savings = MONEY_ZERO

    for tx in transactions:
        if is_analytics_excluded_transaction(tx):
            continue

        amount = money_to_decimal(tx.get("amount")) or MONEY_ZERO
        tx_type = str(tx.get("type") or "").strip().casefold()
        if tx_type == TransactionType.INCOME:
            income += amount
            continue
        if tx_type != TransactionType.EXPENSE:
            continue

        if is_savings_transaction(tx, savings_lookup):
            savings += amount
        else:
            expense += amount

    income = round_money(income)
    expense = round_money(expense)
    savings = round_money(savings)
    return FinancialSummary(
        income=income,
        expense=expense,
        savings=savings,
        net=round_money(income - expense),
    )


def summarize_financial_kpis_as_dict(
    transactions: list[dict[str, Any]],
    savings_lookup: SavingsLookup,
) -> dict[str, Money]:
    """Compatibility wrapper that returns KPIs as a dictionary."""
    summary = summarize_financial_kpis(transactions, savings_lookup)
    return {
        "income": summary.income,
        "expense": summary.expense,
        "savings": summary.savings,
        "net": summary.net,
    }
