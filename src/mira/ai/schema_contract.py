# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Shared JSON contract for assistant-mode parsing.

This module centralises the canonical keys and actions used by the parser
and validator.
"""

from __future__ import annotations

VALID_ACTIONS = frozenset({"add_income", "add_expense", "report", "data_analysis", "none"})
ACTION_ALIASES = {"data_analizis": "data_analysis"}

REQUIRED_KEYS = frozenset(
    {
        "action",
        "amount",
        "description",
        "category",
        "account",
        "base_currency",
        "exchange_rate",
        "converted_amount",
        "report_type",
        "period",
        "filters",
        "message",
    }
)

AMOUNT_REQUIRED_ACTIONS = frozenset({"add_income", "add_expense"})
REPORT_TYPES = frozenset({"expenses", "incomes", "balance", "cashflow", "summary"})
PERIOD_PRESETS = frozenset(
    {
        "this_month",
        "last_month",
        "last_week",
        "last_2_months",
        "last_3_months",
        "last_6_months",
        "this_year",
        "all_time",
        "custom",
    }
)
