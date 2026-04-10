# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Intermediate signal extraction and intent resolution for the parser.

This module defines:

* :class:`ParseSignals` — a lightweight dataclass that captures everything
  the raw text "signals" before any decision is made.
* :func:`collect_signals` — populates a ``ParseSignals`` instance from text.
* :func:`resolve_intent` — maps a ``ParseSignals`` to an :data:`Intent` using
  ``match/case`` so the priority order is explicit and testable in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

import mira.ai.parser_vocab as _vocab
from mira.transaction_kinds import TransactionType

# Re-export Intent so callers only need one import.
Intent = Literal["income", "expense", "report", "analysis", "unknown"] | TransactionType

# Patterns that live here because they belong to the signal-collection layer.
_SAVINGS_EXPENSE_PATTERN = re.compile(
    r"(?:"
    r"\bahorr(?:e|é|o|ó)\b|\bahorra(?:r|do)?\b|\bapart(?:e|é)\b|\bguard(?:e|é)\b|\breserv(?:e|é)\b|\bdestin(?:e|é)\b"
    r"|\bsave(?:d)?\b|\bset\s+aside\b|\bkept\b"
    r"|(?:\btransfer[ií]\b|\btransfier(?:o|e|es|en|a|as|an)\b|\btransferred\b|\bmand(?:e|é)\b|\bpuse\b|\bput\b|\bmoved\b|\badded\b)"
    r".*\b(?:ahorro|ahorros|savings?|savings\s+acc(?:ount)?|cuenta\s+de\s+ahorro|cuenta\s+de\s+ahorros|caja\s+de\s+ahorro|caja\s+de\s+ahorros|alcanc[ií]a|chanchito|piggy\s+bank|jar|wallet|monedero|billetera|cartera|caj[oó]n|frasco|lata|caja\s+fuerte|colch[oó]n|fund|portfolio|envelope|fixed\s+deposit|investment(?:\s+account)?|mutual\s+fund)\b"
    r")",
    re.IGNORECASE,
)
_REPORT_PATTERN = re.compile(
    r"\b(report|resumen|reporte|balance|summary|show|muéstrame|cuanto|how much|how am i)\b",
    re.IGNORECASE,
)
_ANALYSIS_PATTERN = re.compile(r"\b(analiza|analizar|análisis|analysis|analyze)\b", re.IGNORECASE)

# Tiebreaker overrides that are kept close to the logic that uses them.
_GOT_PAID_PATTERN = re.compile(r"\bgot\s+pa(?:id|yd|yed)\b", re.IGNORECASE)
_REINTEGRO_PATTERN = re.compile(r"\breintegro\b", re.IGNORECASE)
_TRANSFER_TO_PATTERN = re.compile(r"\b(to|into|a|al)\b", re.IGNORECASE)
_TAX_RETURN_PATTERN = re.compile(r"\btax\s+return\b", re.IGNORECASE)
_SHOPPING_SPREE_PATTERN = re.compile(r"\bshopping\s+spree\b", re.IGNORECASE)

# Categories that indicate income even when expense keywords are also present.
_INCOME_CATEGORIES = frozenset({"salary", "freelance"})


@dataclass(slots=True)
class ParseSignals:
    """Structured representation of signals extracted from a raw text input."""

    raw_text: str
    amount: float | None
    currency: str | None
    category: str | None
    account: str | None

    income_strong: bool = field(default=False)
    income_weak: bool = field(default=False)
    expense_strong: bool = field(default=False)
    expense_weak: bool = field(default=False)

    report: bool = field(default=False)
    analysis: bool = field(default=False)
    savings_transfer: bool = field(default=False)
    income_context: bool = field(default=False)


def collect_signals(
    text: str,
    amount: float | None,
    currency: str | None,
    category: str | None,
    account: str | None,
) -> ParseSignals:
    """Extract boolean intent signals from *text* and return a :class:`ParseSignals`.

    Parameters
    ----------
    text:
        The raw user input string.
    amount:
        Pre-extracted numeric amount (may be ``None``).
    currency:
        Pre-extracted currency code (may be ``None``).
    category:
        Pre-extracted category keyword (may be ``None``).
    account:
        Pre-extracted account name (may be ``None``).
    """
    savings_transfer = bool(_SAVINGS_EXPENSE_PATTERN.search(text))
    resolved_category = "savings" if savings_transfer else category

    income_strong = bool(_vocab.INCOME_STRONG_RE.search(text))
    income_weak = bool(_vocab.INCOME_BASE_RE.search(text))
    expense_strong = bool(_vocab.EXPENSE_STRONG_RE.search(text))
    expense_weak = bool(_vocab.EXPENSE_BASE_RE.search(text))

    # Savings transfers always count as an expense, never income.
    if savings_transfer:
        expense_strong = True
        expense_weak = True
        income_strong = False
        income_weak = False

    # Resolve ambiguity: explicit lexical tiebreakers take priority.
    if expense_weak and income_weak:
        if _GOT_PAID_PATTERN.search(text) or _REINTEGRO_PATTERN.search(text):
            expense_strong = False
            expense_weak = False
        elif expense_strong and not income_strong:
            income_strong = False
            income_weak = False
        elif income_strong and not expense_strong:
            expense_strong = False
            expense_weak = False
        # Still ambiguous → resolve with account/category cues.
        elif expense_weak and income_weak:
            if account and _TRANSFER_TO_PATTERN.search(text):
                expense_strong = False
                expense_weak = False
            elif resolved_category in _INCOME_CATEGORIES and not expense_strong:
                expense_strong = False
                expense_weak = False
            else:
                income_strong = False
                income_weak = False

    # Explicit special-case overrides that could not be captured by the
    # vocabulary alone without introducing false positives.
    if not income_weak and _TAX_RETURN_PATTERN.search(text):
        income_strong = True
        income_weak = True
    if not expense_weak and _SHOPPING_SPREE_PATTERN.search(text):
        expense_strong = True
        expense_weak = True

    return ParseSignals(
        raw_text=text,
        amount=amount,
        currency=currency,
        category=resolved_category,
        account=account,
        income_strong=income_strong,
        income_weak=income_weak,
        expense_strong=expense_strong,
        expense_weak=expense_weak,
        report=bool(_REPORT_PATTERN.search(text)),
        analysis=bool(_ANALYSIS_PATTERN.search(text)),
        savings_transfer=savings_transfer,
        income_context=(resolved_category == "salary"),
    )


def resolve_intent(signals: ParseSignals) -> Intent:
    """Map a :class:`ParseSignals` to an :data:`Intent` using ``match/case``.

    The priority order is made explicit by the case ordering:

    1. Report / analysis take priority over transaction classification.
    2. Savings transfers are always expenses.
    3. Strong signals without opposing strong signal win immediately.
    4. Ambiguous strong signals fall back to category/account cues.
    5. Weak signals are used as a last resort.
    6. A bare amount with no signal returns ``"unknown"``.
    """
    match signals:
        case ParseSignals(report=True):
            return "report"

        case ParseSignals(analysis=True):
            return "analysis"

        case ParseSignals(savings_transfer=True):
            return TransactionType.EXPENSE

        case ParseSignals(income_strong=True, expense_strong=False):
            return TransactionType.INCOME

        case ParseSignals(expense_strong=True, income_strong=False):
            return TransactionType.EXPENSE

        case ParseSignals(income_strong=True, expense_strong=True, account=str()):
            # Moving money *into* an account is treated as income in this domain.
            return TransactionType.INCOME

        case ParseSignals(income_strong=True, expense_strong=True, category="salary" | "freelance"):
            return TransactionType.INCOME

        case ParseSignals(income_strong=True, expense_strong=True):
            return TransactionType.EXPENSE

        case ParseSignals(income_weak=True, expense_weak=False):
            return TransactionType.INCOME

        case ParseSignals(income_context=True):
            return TransactionType.INCOME

        case ParseSignals(expense_weak=True, income_weak=False):
            return TransactionType.EXPENSE

        case ParseSignals(amount=float() | int()):
            return "unknown"

        case _:
            return "unknown"
