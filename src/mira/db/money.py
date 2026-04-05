# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Exact money helpers backed by integer cents.

Money is normalized only at the persistence boundary:
- SQLite stores exact integer cents such as ``1234``.
- Python-facing money values use :class:`decimal.Decimal`.
- ``float`` is reserved for display-only edges such as Qt widgets or chart APIs.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

type MoneyLike = Decimal | str | int | float
Money = Decimal

_CENT_FACTOR = Decimal("100")
_MONEY_QUANT = Decimal("0.01")
MONEY_ZERO = Decimal("0.00")
MAX_MONEY_CENTS = 9_223_372_036_854_775_807


def money_to_decimal(value: Any, *, allow_none: bool = False) -> Money | None:
    """Normalize a money-like input into a quantized Decimal."""
    if value is None:
        return None if allow_none else MONEY_ZERO
    if isinstance(value, str) and not value.strip():
        return None if allow_none else MONEY_ZERO
    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid money value: {value!r}") from exc
    if not decimal_value.is_finite():
        raise ValueError(f"Money value must be finite, got {value!r}")
    return decimal_value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def round_money(value: Any) -> Money:
    """Round an arbitrary money value to the canonical two-decimal precision."""
    return money_to_decimal(value) or MONEY_ZERO


def money_to_cents(value: Any, *, allow_none: bool = False) -> int | None:
    """Convert a user-facing money value into exact integer cents."""
    decimal_value = money_to_decimal(value, allow_none=allow_none)
    if decimal_value is None:
        return None
    cents = (decimal_value * _CENT_FACTOR).to_integral_value(rounding=ROUND_HALF_UP)
    cents_int = int(cents)
    if abs(cents_int) > MAX_MONEY_CENTS:
        raise OverflowError(f"Money value exceeds SQLite INTEGER range in cents: {value!r}")
    return cents_int


def cents_to_decimal(value: Any, *, allow_none: bool = False) -> Money | None:
    """Convert exact integer cents back into a Decimal money amount."""
    if value is None:
        return None if allow_none else MONEY_ZERO
    return (Decimal(str(value)) / _CENT_FACTOR).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def cents_to_money(value: Any, *, allow_none: bool = False) -> float | None:
    """Display-only float conversion for UI/chart/export edges."""
    decimal_value = cents_to_decimal(value, allow_none=allow_none)
    if decimal_value is None:
        return None
    return float(decimal_value)
