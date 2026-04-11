# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from decimal import Decimal

import pytest

from mira.db.money import (
    MAX_MONEY_CENTS,
    MONEY_ZERO,
    cents_to_decimal,
    cents_to_money,
    money_to_cents,
    money_to_decimal,
    round_money,
)


def test_money_to_decimal_handles_none_blank_and_rounds_half_up() -> None:
    assert money_to_decimal(None) == MONEY_ZERO
    assert money_to_decimal("   ") == MONEY_ZERO
    assert money_to_decimal(None, allow_none=True) is None
    assert money_to_decimal("   ", allow_none=True) is None
    assert money_to_decimal("12.345") == Decimal("12.35")
    assert round_money("5.004") == Decimal("5.00")


@pytest.mark.parametrize("value", ["abc", "NaN", "Infinity", float("inf"), float("-inf")])
def test_money_to_decimal_rejects_invalid_or_non_finite_values(value: object) -> None:
    with pytest.raises(ValueError):
        money_to_decimal(value)


def test_money_to_cents_respects_allow_none_and_detects_overflow() -> None:
    assert money_to_cents(None, allow_none=True) is None
    assert money_to_cents("12.345") == 1235
    assert money_to_cents("-1.235") == -124

    overflow_value = f"{(MAX_MONEY_CENTS // 100) + 1}.00"
    with pytest.raises(OverflowError, match="SQLite INTEGER range"):
        money_to_cents(overflow_value)


def test_cents_conversions_roundtrip_to_decimal_and_display_float() -> None:
    assert cents_to_decimal(None) == MONEY_ZERO
    assert cents_to_decimal(None, allow_none=True) is None
    assert cents_to_decimal(123) == Decimal("1.23")
    assert cents_to_money(123) == pytest.approx(1.23)
    assert cents_to_money(None, allow_none=True) is None
