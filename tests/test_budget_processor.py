# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tests for the budget_processor module."""

from __future__ import annotations

import pytest

from mira.budget_processor import process_budget_value
from mira.number_format import NumberFormatConfig

US_NUMBER_FORMAT = NumberFormatConfig(thousands_sep=",", decimal_sep=".")
EU_NUMBER_FORMAT = NumberFormatConfig(thousands_sep=".", decimal_sep=",")


# ---------------------------------------------------------------------------
# Plain numeric values
# ---------------------------------------------------------------------------


def test_positive_integer_string():
    assert process_budget_value("500") == 500.0


def test_positive_float_string():
    assert process_budget_value("100.50") == 100.50


def test_positive_grouped_number_uses_default_number_format():
    assert process_budget_value("1,234.56") == pytest.approx(1234.56)


def test_positive_number_uses_custom_decimal_separator():
    assert process_budget_value("100,50", number_format=EU_NUMBER_FORMAT) == pytest.approx(100.5)


def test_positive_grouped_number_uses_custom_number_format():
    assert process_budget_value("1.234,56", number_format=EU_NUMBER_FORMAT) == pytest.approx(1234.56)


def test_zero_string():
    assert process_budget_value("0") == 0.0


def test_empty_string_returns_zero():
    assert process_budget_value("") == 0.0


def test_positive_int():
    assert process_budget_value(200) == 200.0


def test_positive_float():
    assert process_budget_value(99.9) == pytest.approx(99.9)


def test_zero_float():
    assert process_budget_value(0.0) == 0.0


# ---------------------------------------------------------------------------
# Negative values – must raise
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [-100, -0.01, "-50", "-400"])
def test_negative_values_raise(value: int | float | str):
    with pytest.raises(ValueError, match="positive"):
        process_budget_value(value)


# ---------------------------------------------------------------------------
# Formula – valid
# ---------------------------------------------------------------------------


def test_formula_addition():
    assert process_budget_value("=100+200") == 300.0


def test_formula_subtraction_positive():
    assert process_budget_value("=500-100") == 400.0


def test_formula_multiplication():
    assert process_budget_value("=500*2") == 1000.0


def test_formula_division():
    assert process_budget_value("=1000/4") == 250.0


def test_formula_with_parentheses():
    assert process_budget_value("=(100+200)*2") == 600.0


def test_formula_spaces_inside():
    assert process_budget_value("= 100 + 200") == 300.0


def test_formula_leading_equal_space():
    assert process_budget_value("= (100+200) * 2") == 600.0


def test_formula_nested_parentheses():
    assert process_budget_value("=((50+50)*2)/2") == 100.0


def test_formula_uses_grouped_numbers_with_default_number_format():
    assert process_budget_value("=1,200.50+9.5", number_format=US_NUMBER_FORMAT) == pytest.approx(1210.0)


def test_formula_uses_localized_numbers_with_custom_number_format():
    assert process_budget_value("=(1.200,50+299,50)/2", number_format=EU_NUMBER_FORMAT) == pytest.approx(750.0)


# ---------------------------------------------------------------------------
# Formula – invalid / raises
# ---------------------------------------------------------------------------


def test_formula_result_negative_raises():
    with pytest.raises(ValueError, match="positive"):
        process_budget_value("=100-200")


def test_formula_division_by_zero_raises_value_error():
    with pytest.raises(ValueError, match="Division by zero"):
        process_budget_value("=100/0")


def test_formula_disallowed_power_operator_raises():
    with pytest.raises(ValueError, match="not allowed"):
        process_budget_value("=100**2")


def test_formula_disallowed_xor_operator_raises():
    with pytest.raises(ValueError, match="not allowed"):
        process_budget_value("=100^2")


def test_formula_disallowed_function_raises():
    with pytest.raises(ValueError, match="supported"):
        process_budget_value("=abs(-16)")


def test_formula_empty_after_equal_raises():
    with pytest.raises(ValueError, match="empty"):
        process_budget_value("=")


def test_formula_syntax_error_raises():
    with pytest.raises(ValueError, match="[Ii]nvalid"):
        process_budget_value("=100+*200")


def test_formula_invalid_localized_number_raises():
    with pytest.raises(ValueError, match="Invalid number"):
        process_budget_value("=1,2,3+4", number_format=EU_NUMBER_FORMAT)


# ---------------------------------------------------------------------------
# Non-numeric, non-formula strings – must raise
# ---------------------------------------------------------------------------


def test_text_value_raises():
    with pytest.raises(ValueError, match="[Ii]nvalid"):
        process_budget_value("hello")


def test_formula_without_equal_raises_specific_message():
    with pytest.raises(ValueError, match="start with '='"):
        process_budget_value("100+200")
