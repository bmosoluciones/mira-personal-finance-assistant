# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Action validator for MIRA.

Ensures that the JSON dict produced by the LLM engine conforms to the
expected schema before it is passed to the executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from mira.ai.schema_contract import (
    ACTION_ALIASES,
    AMOUNT_REQUIRED_ACTIONS,
    PERIOD_PRESETS,
    REPORT_TYPES,
    REQUIRED_KEYS,
    VALID_ACTIONS,
)
from mira.db.money import MONEY_ZERO, money_to_decimal, round_money


def _normalise_base_currency(raw: dict[str, Any], *, default_base_currency: str) -> str:
    base_currency = raw.get("base_currency")
    if base_currency is None:
        return default_base_currency.strip().upper()
    return str(base_currency).upper()


def _validate_iso_date(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"'{field_name}' must be a valid ISO date YYYY-MM-DD.") from exc
    return parsed.isoformat()


def _validate_money_field(value: Any, *, field_name: str) -> Decimal:
    try:
        money_value = money_to_decimal(value)
    except ValueError as exc:
        raise ValueError(f"'{field_name}' must be numeric, got {value!r}.") from exc
    if money_value is None:
        raise ValueError(f"'{field_name}' is required.")
    return money_value


@dataclass
class ValidationResult:
    """Result of validating an action dict."""

    valid: bool
    action: dict[str, Any] | None
    error: str | None


def validate(raw: Any, *, default_base_currency: str = "USD") -> ValidationResult:
    """Validate *raw* (the output of the LLM engine).

    Parameters
    ----------
    raw:
        The parsed JSON value returned by the engine.  Must be a ``dict``.

    Returns
    -------
    ValidationResult
        ``valid=True`` and the normalised action dict on success,
        ``valid=False`` and an error message on failure.
    """
    if not isinstance(raw, dict):
        return ValidationResult(valid=False, action=None, error="Output is not a JSON object.")

    # Check for required keys
    missing = REQUIRED_KEYS - raw.keys()
    if missing:
        return ValidationResult(
            valid=False,
            action=None,
            error=f"Missing required keys: {', '.join(sorted(missing))}",
        )

    action_raw = raw.get("action")
    if action_raw is not None and not isinstance(action_raw, str):
        return ValidationResult(valid=False, action=None, error="'action' must be a string or null.")

    action = None if action_raw is None else ACTION_ALIASES.get(action_raw, action_raw)
    if action not in VALID_ACTIONS:
        return ValidationResult(
            valid=False,
            action=None,
            error=f"Invalid action {action!r}. Must be one of: {', '.join(sorted(VALID_ACTIONS))}",
        )

    amount = raw.get("amount")
    exchange_rate = raw.get("exchange_rate")
    converted_amount = raw.get("converted_amount")

    if action in AMOUNT_REQUIRED_ACTIONS:
        if amount is None:
            return ValidationResult(
                valid=False,
                action=None,
                error=f"Action '{action}' requires a non-null 'amount'.",
            )
        try:
            amount = _validate_money_field(amount, field_name="amount")
        except ValueError as exc:
            return ValidationResult(
                valid=False,
                action=None,
                error=str(exc),
            )
        if amount <= MONEY_ZERO:
            return ValidationResult(
                valid=False,
                action=None,
                error=f"'amount' must be positive, got {amount}.",
            )

        if exchange_rate is None:
            return ValidationResult(
                valid=False,
                action=None,
                error=f"Action '{action}' requires 'exchange_rate'.",
            )
        if converted_amount is None:
            return ValidationResult(
                valid=False,
                action=None,
                error=f"Action '{action}' requires 'converted_amount'.",
            )

        try:
            exchange_rate = float(exchange_rate)
            converted_amount = _validate_money_field(converted_amount, field_name="converted_amount")
        except (TypeError, ValueError) as exc:
            return ValidationResult(
                valid=False,
                action=None,
                error=(
                    str(exc)
                    if isinstance(exc, ValueError)
                    else "'exchange_rate' and 'converted_amount' must be numeric."
                ),
            )
        if exchange_rate <= 0:
            return ValidationResult(valid=False, action=None, error="'exchange_rate' must be positive.")
        expected_converted_amount = round_money(amount * Decimal(str(exchange_rate)))
        if converted_amount != expected_converted_amount:
            return ValidationResult(
                valid=False,
                action=None,
                error=(
                    "'converted_amount' must equal amount * exchange_rate rounded "
                    f"to 2 decimals (expected {expected_converted_amount})."
                ),
            )

    report_type = raw.get("report_type")
    period = raw.get("period")
    filters = raw.get("filters")

    if action in {"report", "data_analysis"}:
        if action == "report" and report_type not in REPORT_TYPES:
            return ValidationResult(
                valid=False,
                action=None,
                error=f"'report_type' must be one of: {', '.join(sorted(REPORT_TYPES))}.",
            )
        if not isinstance(period, dict):
            return ValidationResult(
                valid=False,
                action=None,
                error="'period' must be an object for report/analysis actions.",
            )

        preset = period.get("preset")
        if preset not in PERIOD_PRESETS:
            return ValidationResult(
                valid=False,
                action=None,
                error=f"'period.preset' must be one of: {', '.join(sorted(PERIOD_PRESETS))}.",
            )

        if preset == "custom":
            if period.get("from") is None or period.get("to") is None:
                return ValidationResult(
                    valid=False,
                    action=None,
                    error="'period.from' and 'period.to' are required when preset is 'custom'.",
                )

        try:
            from_date = _validate_iso_date(period.get("from"), field_name="period.from")
            to_date = _validate_iso_date(period.get("to"), field_name="period.to")
        except ValueError as exc:
            return ValidationResult(valid=False, action=None, error=str(exc))

        if from_date and to_date and from_date > to_date:
            return ValidationResult(valid=False, action=None, error="'period.from' must be <= 'period.to'.")

        if filters is not None and not isinstance(filters, dict):
            return ValidationResult(valid=False, action=None, error="'filters' must be an object or null.")

        if isinstance(filters, dict):
            try:
                min_amount = filters.get("min_amount")
                max_amount = filters.get("max_amount")
                filters = {
                    "categories": filters.get("categories"),
                    "accounts": filters.get("accounts"),
                    "min_amount": (money_to_decimal(min_amount, allow_none=True) if min_amount is not None else None),
                    "max_amount": (money_to_decimal(max_amount, allow_none=True) if max_amount is not None else None),
                    "text": filters.get("text"),
                }
            except ValueError as exc:
                return ValidationResult(valid=False, action=None, error=str(exc))

        period = {"preset": preset, "from": from_date, "to": to_date}

    if action not in {"report", "data_analysis"}:
        report_type = None
        period = None
        filters = None

    if action not in AMOUNT_REQUIRED_ACTIONS:
        amount = None
        exchange_rate = None
        converted_amount = None

    # Build normalised dict (coerce types gently)
    normalised: dict[str, Any] = {
        "action": action,
        "amount": amount,
        "description": (str(raw["description"]) if raw.get("description") is not None else None),
        "category": str(raw["category"]) if raw.get("category") is not None else None,
        "account": str(raw["account"]) if raw.get("account") is not None else None,
        "base_currency": _normalise_base_currency(raw, default_base_currency=default_base_currency),
        "exchange_rate": float(exchange_rate) if exchange_rate is not None else None,
        "converted_amount": converted_amount,
        "report_type": str(report_type) if report_type is not None else None,
        "period": period,
        "filters": filters,
        "message": str(raw["message"]) if raw.get("message") is not None else None,
    }

    return ValidationResult(valid=True, action=normalised, error=None)
