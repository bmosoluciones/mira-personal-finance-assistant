# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations
import pytest
import math
from mira.budget_processor import process_budget_value, _ensure_finite_number, _looks_like_formula
from mira.number_format import NumberFormatConfig

def test_ensure_finite_number_raises():
    with pytest.raises(ValueError, match="finite numbers"):
        _ensure_finite_number(float('inf'))
    with pytest.raises(ValueError, match="finite numbers"):
        _ensure_finite_number(float('nan'))

def test_looks_like_formula_variations():
    assert _looks_like_formula("1*2") is True
    assert _looks_like_formula("1/2") is True
    assert _looks_like_formula("(1)") is True
    assert _looks_like_formula("1+2") is True
    assert _looks_like_formula("-1") is False # leading minus is not enough to be a formula if it's just a number
    assert _looks_like_formula("1-2") is True

def test_process_budget_value_empty_plain_number_raises():
    from mira.budget_processor import _parse_plain_budget_number
    # To hit line 91, we need _parse_plain_budget_number to be called with something that becomes empty
    # but the public API strips it first.
    with pytest.raises(ValueError, match="Budget value is empty"):
        _parse_plain_budget_number("+", NumberFormatConfig())
    with pytest.raises(ValueError, match="Budget value is empty"):
        _parse_plain_budget_number("-", NumberFormatConfig())

def test_unsupported_grouping_symbols():
    with pytest.raises(ValueError, match="Grouping symbol not allowed"):
        process_budget_value("=[1+2]")
    with pytest.raises(ValueError, match="Grouping symbol not allowed"):
        process_budget_value("={1+2}")

def test_invalid_number_in_formula():
    # To hit line 168
    with pytest.raises(ValueError, match="Invalid number in formula"):
        # This will be caught by parse_number inside _normalise_formula
        process_budget_value("=1.2.3+4", number_format=NumberFormatConfig(thousands_sep=",", decimal_sep="."))

def test_eval_node_non_numeric_constant():
    from mira.budget_processor import _eval_node
    import ast
    node = ast.Constant(value="not a number")
    with pytest.raises(ValueError, match="Only numeric values are allowed"):
        _eval_node(node)

    node_bool = ast.Constant(value=True)
    with pytest.raises(ValueError, match="Only numeric values are allowed"):
        _eval_node(node_bool)

def test_formula_with_unsupported_ops_in_ast():
    from mira.budget_processor import _eval_node
    import ast
    # Test unsupported binary op (e.g. BitAnd)
    node = ast.BinOp(left=ast.Constant(value=1), op=ast.BitAnd(), right=ast.Constant(value=2))
    with pytest.raises(ValueError, match="Operation not allowed"):
        _eval_node(node)

    # Test unsupported unary op (e.g. Not)
    node_unary = ast.UnaryOp(op=ast.Not(), operand=ast.Constant(value=1))
    with pytest.raises(ValueError, match="Operation not allowed"):
        _eval_node(node_unary)

    # Test completely unknown node
    node_unknown = ast.Pass()
    with pytest.raises(ValueError, match="Invalid formula expression"):
        _eval_node(node_unknown)

def test_ensure_positive_budget_value_with_inf():
    with pytest.raises(ValueError, match="finite numbers"):
        process_budget_value(float('inf'))
