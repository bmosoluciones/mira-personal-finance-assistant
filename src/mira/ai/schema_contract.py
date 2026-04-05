# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Shared JSON contract for assistant-mode parsing.

This module centralises the canonical keys/actions used by:
- LLM assistant prompts
- validator rules
- tests
"""

from __future__ import annotations

VALID_ACTIONS = frozenset({"add_income", "add_expense", "report", "data_analysis", "none"})
ACTION_ALIASES = {"data_analizis": "data_analysis"}

ASSISTANT_SYSTEM_PROMPT = (
    "You are MIRA, a personal finance assistant helping users record transactions "
    "and analyze their data in natural language."
)

CHAT_SYSTEM_PROMPTS = {
    "en": "You are an expert in personal finance explaining clearly and amicably basic concepts of personal finance",
    "es": "Eres un experto en finanzas personales explicando clara y amigablemente conceptos basicos de finanzas personales",
}

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


def build_assistant_system_prompt() -> str:
    """Return the assistant-mode system prompt with shared contract constants."""
    ordered_actions = ["add_income", "add_expense", "report", "data_analysis", "none"]
    schema_fields = [
        '"action": "<add_income|add_expense|report|data_analysis|none>"',
        '"amount": <number or null>',
        '"description": <string or null>',
        '"category": <string or null>',
        '"account": <string or null>',
        '"base_currency": <ISO code>',
        '"exchange_rate": <number or null>',
        '"converted_amount": <number or null>',
        '"report_type": <string or null>',
        '"period": <object or null>',
        '"filters": <object or null>',
        '"message": <string or null>',
    ]

    return (
        ASSISTANT_SYSTEM_PROMPT + " You MUST output ONLY valid JSON "
        "with NO additional text, explanations, comments, or markdown code blocks.\n\n"
        "Available actions:\n"
        + "\n".join(f"- {name}" for name in ordered_actions)
        + "\n\nOutput schema (always include all fields):\n"
        + "{"
        + ", ".join(schema_fields)
        + "}\n\n"
        "Rules:\n"
        "- 'action' is always required\n"
        "- 'amount' must be positive for add_income and add_expense; null otherwise\n"
        "- 'base_currency' defaults to the system default currency if missing\n"
        "- add_income/add_expense require 'exchange_rate' and 'converted_amount'\n"
        "- for report include 'report_type' and 'period'; 'filters' optional\n"
        "- for data_analysis include 'period'; 'filters' optional\n"
        "- use action 'none' when request is not a finance record/report/analysis\n"
        "- 'message' is mainly useful when action='none'\n\n"
        "Examples (input → output):"
    )


def build_chat_system_prompt(language: str = "en") -> str:
    """Return the chat-mode system prompt in the requested language when available."""
    normalized = str(language or "en").strip().lower()
    return CHAT_SYSTEM_PROMPTS.get(normalized, CHAT_SYSTEM_PROMPTS["en"])
