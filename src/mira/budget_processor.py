# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Budget value processor.

Validates and processes budget cell values.  A value may be:

* A plain positive number (int or float, or a numeric string).
* A simple arithmetic formula starting with ``=`` that contains only the
  four basic operations ``+``, ``-``, ``*``, ``/`` and parentheses.

This module is independent of the UI so that it can be reused and unit-tested
without a running Qt application.
"""

from __future__ import annotations

import ast
import math
import operator as _operator

from mira.number_format import NumberFormatConfig, coerce_number_format_config, parse_number

# ---------------------------------------------------------------------------
# Allowed AST operators
# ---------------------------------------------------------------------------

_BINARY_OPS: dict[type, object] = {
    ast.Add: _operator.add,
    ast.Sub: _operator.sub,
    ast.Mult: _operator.mul,
    ast.Div: _operator.truediv,
}

_UNARY_OPS: dict[type, object] = {
    ast.UAdd: _operator.pos,
    ast.USub: _operator.neg,
}

_OPERATOR_CHARS = "+-*/()"
_UNSUPPORTED_OPERATOR_CHARS = {"^", "%", "\\"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalise_number_format(number_format: NumberFormatConfig | None) -> NumberFormatConfig:
    config = number_format or NumberFormatConfig()
    return coerce_number_format_config(config.thousands_sep, config.decimal_sep)


def _ensure_finite_number(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("Budget values must be finite numbers.")
    return float(value)


def _ensure_positive_budget_value(value: float) -> float:
    numeric = _ensure_finite_number(value)
    if numeric < 0:
        raise ValueError(f"Only positive values are allowed in budget cells. Got: {numeric}.")
    return numeric


def _looks_like_formula(raw: str) -> bool:
    stripped = raw.strip()
    if not any(ch.isdigit() for ch in stripped):
        return False
    if any(ch in stripped for ch in "*/()"):
        return True
    if "+" in stripped:
        return True
    return "-" in stripped[1:]


def _parse_plain_budget_number(raw: str, number_format: NumberFormatConfig) -> float:
    stripped = raw.strip()
    sign = 1.0
    if stripped[:1] in "+-":
        sign = -1.0 if stripped[0] == "-" else 1.0
        stripped = stripped[1:].strip()
    if not stripped:
        raise ValueError("Budget value is empty.")
    return sign * parse_number(stripped, number_format)


def _starts_number(expr: str, index: int, number_format: NumberFormatConfig) -> bool:
    char = expr[index]
    if char.isdigit():
        return True
    return char == number_format.decimal_sep and index + 1 < len(expr) and expr[index + 1].isdigit()


def _normalise_formula(expr: str, number_format: NumberFormatConfig) -> str:
    allowed_chars = set("0123456789 ()+-*/\u00a0") | {number_format.thousands_sep, number_format.decimal_sep}
    number_token_chars = set("0123456789 \u00a0") | {number_format.thousands_sep, number_format.decimal_sep}
    parts: list[str] = []
    raw_expr = expr.replace("\u00a0", " ")
    index = 0

    while index < len(raw_expr):
        char = raw_expr[index]

        if char in _UNSUPPORTED_OPERATOR_CHARS:
            raise ValueError(f"Operation not allowed: '{char}'. Only basic operations (+, -, *, /) are supported.")

        if char not in allowed_chars:
            raise ValueError(
                "Invalid formula expression. Only numbers, basic operations (+, -, *, /), and parentheses are supported."
            )

        if char.isspace():
            index += 1
            continue

        if _starts_number(raw_expr, index, number_format):
            token_chars: list[str] = []
            while index < len(raw_expr) and raw_expr[index] in number_token_chars:
                token_chars.append(raw_expr[index])
                index += 1
            token = "".join(token_chars)
            try:
                parsed_number = parse_number(token, number_format)
            except ValueError as exc:
                stripped = token.strip() or token
                raise ValueError(
                    f"Invalid number in formula: '{stripped}'. "
                    "Only valid numbers and basic operations (+, -, *, /) are supported."
                ) from exc
            parts.append(repr(_ensure_finite_number(parsed_number)))
            continue

        if char in _OPERATOR_CHARS:
            parts.append(char)
            index += 1
            continue

        raise ValueError(
            "Invalid formula expression. Only numbers, basic operations (+, -, *, /), and parentheses are supported."
        )

    return "".join(parts)


def _eval_node(node: ast.expr) -> float:
    """Recursively evaluate an AST node.

    Only numeric constants, binary operations (+, -, *, /) and unary
    operations (unary plus / minus) are accepted.  Everything else raises
    :class:`ValueError`.
    """
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError(f"Only numeric values are allowed in formulas. Got unexpected constant: {node.value!r}.")
        return _ensure_finite_number(float(node.value))

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _BINARY_OPS:
            raise ValueError(
                f"Operation not allowed: '{op_type.__name__}'. Only basic operations (+, -, *, /) are supported."
            )
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if op_type is ast.Div and right == 0:
            raise ValueError("Division by zero is not allowed in budget formulas.")
        fn = _BINARY_OPS[op_type]
        try:
            result = fn(left, right)  # type: ignore[operator]
        except ZeroDivisionError as exc:
            raise ValueError("Division by zero is not allowed in budget formulas.") from exc
        return _ensure_finite_number(float(result))

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _UNARY_OPS:
            raise ValueError(
                f"Operation not allowed: '{op_type.__name__}'. " "Only basic operations (+, -, *, /) are supported."
            )
        operand = _eval_node(node.operand)
        fn = _UNARY_OPS[op_type]
        return _ensure_finite_number(float(fn(operand)))  # type: ignore[operator]

    raise ValueError(
        "Invalid formula expression. Only basic operations (+, -, *, /), numbers, and parentheses are supported."
    )


def _evaluate_formula(expr: str, number_format: NumberFormatConfig) -> float:
    """Parse and evaluate a simple arithmetic expression string.

    Parameters
    ----------
    expr:
        The arithmetic expression *without* the leading ``=`` sign.

    Returns
    -------
    float
        The numeric result of the expression.

    Raises
    ------
    ValueError
        If the expression is syntactically invalid, contains disallowed
        operations, or evaluates to a negative value.
    """
    if not expr.strip():
        raise ValueError("Formula is empty. Please provide a valid arithmetic expression.")

    normalised_expr = _normalise_formula(expr, number_format)
    try:
        tree = ast.parse(normalised_expr, mode="eval")
    except SyntaxError:
        raise ValueError(
            f"Invalid formula: '{expr}'. " "Check that the formula contains only numbers and the operators +, -, *, /."
        )

    result = _eval_node(tree.body)
    return _ensure_positive_budget_value(result)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def process_budget_value(
    value: str | float,
    *,
    number_format: NumberFormatConfig | None = None,
) -> float:
    """Validate and process a budget cell value.

    Accepts either a plain positive number or a formula string that starts
    with ``=`` and contains only basic arithmetic operations.

    Parameters
    ----------
    value:
        The raw value entered by the user.  May be a ``str`` (including
        formula strings such as ``"=100+200"``) or a numeric ``float``/``int``.

    Returns
    -------
    float
        The validated positive numeric result.

    Raises
    ------
    ValueError
        With a descriptive human-readable message when the value is invalid.
    """
    # --- Numeric types ---------------------------------------------------
    if isinstance(value, (int, float)):
        return _ensure_positive_budget_value(float(value))

    # --- String handling -------------------------------------------------
    raw = str(value).strip()
    safe_number_format = _normalise_number_format(number_format)

    if not raw:
        return 0.0

    # Formula path
    if raw.startswith("="):
        expr = raw[1:].strip()
        return _evaluate_formula(expr, safe_number_format)

    # Plain number path – parse according to the active number format.
    try:
        parsed_number = _parse_plain_budget_number(raw, safe_number_format)
    except ValueError as exc:
        if _looks_like_formula(raw):
            raise ValueError(
                "Formulas must start with '='. Enter a positive number or prefix the expression with '='."
            ) from exc
        raise ValueError(
            f"Invalid value: '{raw}'. " "Enter a positive number or a formula starting with '=' " "(e.g. '=100+200')."
        ) from exc
    return _ensure_positive_budget_value(parsed_number)
