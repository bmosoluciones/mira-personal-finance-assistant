# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Shared semantics for special transaction kinds."""

from __future__ import annotations

from typing import Any

from peewee import fn

BALANCE_ADJUSTMENT_PAYMENT_METHOD = "balance_adjustment"


def normalize_payment_method(value: object) -> str:
    return str(value or "").strip().lower()


def is_balance_adjustment_payment_method(value: object) -> bool:
    return normalize_payment_method(value) == BALANCE_ADJUSTMENT_PAYMENT_METHOD


def localized_balance_adjustment_description(language: str | None) -> str:
    normalized_language = str(language or "en").strip().lower()
    return "Ajuste de saldo" if normalized_language.startswith("es") else "Balance adjustment"


def is_balance_adjustment_transaction(tx: Any) -> bool:
    if isinstance(tx, dict):
        payment_method = tx.get("payment_method")
    else:
        payment_method = getattr(tx, "payment_method", None)
    return is_balance_adjustment_payment_method(payment_method)


def is_analytics_excluded_transaction(tx: Any) -> bool:
    if isinstance(tx, dict):
        raw_transfer = tx.get("is_transfer")
    else:
        raw_transfer = getattr(tx, "is_transfer", None)
    try:
        is_transfer = int(raw_transfer or 0) == 1
    except (TypeError, ValueError):
        is_transfer = bool(raw_transfer)
    return is_transfer or is_balance_adjustment_transaction(tx)


def analytics_included_expr(model: Any):
    return (fn.COALESCE(model.is_transfer, 0) == 0) & (
        fn.LOWER(fn.TRIM(fn.COALESCE(model.payment_method, ""))) != BALANCE_ADJUSTMENT_PAYMENT_METHOD
    )


__all__ = [
    "BALANCE_ADJUSTMENT_PAYMENT_METHOD",
    "analytics_included_expr",
    "is_analytics_excluded_transaction",
    "is_balance_adjustment_payment_method",
    "is_balance_adjustment_transaction",
    "localized_balance_adjustment_description",
    "normalize_payment_method",
]
