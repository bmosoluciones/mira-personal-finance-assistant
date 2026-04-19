# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tests for the action validator."""

from __future__ import annotations

from decimal import Decimal

from mira.ai.schema_contract import REQUIRED_KEYS
from mira.ai.validator import VALID_ACTIONS, validate


def _valid_action(**overrides):
    base = {
        "action": "add_income",
        "amount": 100.0,
        "description": "salary",
        "category": "salary",
        "account": None,
        "base_currency": "USD",
        "exchange_rate": 1.0,
        "converted_amount": 100.0,
        "report_type": None,
        "period": None,
        "filters": None,
        "message": None,
    }
    base.update(overrides)
    return base


class TestValidator:
    def test_valid_add_income(self):
        result = validate(_valid_action(action="add_income", amount=500.0, converted_amount=500.0))
        assert result.valid is True
        assert result.action["action"] == "add_income"
        assert result.action["amount"] == Decimal("500.00")
        assert result.error is None

    def test_valid_add_expense(self):
        result = validate(_valid_action(action="add_expense", amount=30.5, converted_amount=30.5))
        assert result.valid is True
        assert result.action["action"] == "add_expense"
        assert result.action["amount"] == Decimal("30.50")
        assert result.action["converted_amount"] == Decimal("30.50")

    def test_valid_report(self):
        result = validate(
            _valid_action(
                action="report",
                amount=None,
                exchange_rate=None,
                converted_amount=None,
                report_type="expenses",
                period={"preset": "last_3_months", "from": None, "to": None},
                filters={"categories": ["restaurant"]},
            )
        )
        assert result.valid is True
        assert result.action["report_type"] == "expenses"

    def test_valid_data_analysis(self):
        result = validate(
            _valid_action(
                action="data_analysis",
                amount=None,
                exchange_rate=None,
                converted_amount=None,
                period={"preset": "this_month", "from": None, "to": None},
                filters={"categories": ["education"]},
            )
        )
        assert result.valid is True
        assert result.action["action"] == "data_analysis"

    def test_valid_none(self):
        result = validate(
            _valid_action(
                action="none",
                amount=None,
                exchange_rate=None,
                converted_amount=None,
                message="Disculpa, no entendí tu solicitud.",
            )
        )
        assert result.valid is True

    def test_missing_new_keys(self):
        action = {
            "action": "add_income",
            "amount": 10,
            "description": None,
            "category": None,
            "account": None,
            "message": None,
        }
        result = validate(action)
        assert result.valid is False
        assert "missing" in result.error.lower()

    def test_action_must_be_string_or_null(self):
        result = validate(_valid_action(action=123))
        assert result.valid is False
        assert "action" in str(result.error).lower()

    def test_income_requires_exchange_and_converted(self):
        result = validate(_valid_action(exchange_rate=None))
        assert result.valid is False
        result = validate(_valid_action(converted_amount=None))
        assert result.valid is False

    def test_money_fields_are_normalized_with_decimal_semantics(self):
        result = validate(
            _valid_action(
                amount="10.235",
                exchange_rate=1.0,
                converted_amount="10.24",
            )
        )
        assert result.valid is True
        assert result.action["amount"] == Decimal("10.24")
        assert result.action["converted_amount"] == Decimal("10.24")

    def test_converted_amount_must_match_rounded_formula(self):
        result = validate(
            _valid_action(
                amount="36.6432",
                exchange_rate=1.0,
                converted_amount="36.64",
            )
        )
        assert result.valid is True

        invalid = validate(
            _valid_action(
                amount="36.6432",
                exchange_rate=1.0,
                converted_amount="36.63",
            )
        )
        assert invalid.valid is False
        assert "rounded" in str(invalid.error)

    def test_report_requires_period_and_report_type(self):
        result = validate(_valid_action(action="report", amount=None, exchange_rate=None, converted_amount=None))
        assert result.valid is False

    def test_report_custom_requires_dates(self):
        result = validate(
            _valid_action(
                action="report",
                amount=None,
                exchange_rate=None,
                converted_amount=None,
                report_type="summary",
                period={"preset": "custom", "from": None, "to": None},
            )
        )
        assert result.valid is False

    def test_report_custom_invalid_date(self):
        result = validate(
            _valid_action(
                action="report",
                amount=None,
                exchange_rate=None,
                converted_amount=None,
                report_type="summary",
                period={"preset": "custom", "from": "2025-13-01", "to": "2025-01-31"},
            )
        )
        assert result.valid is False

    def test_alias_action_data_analizis_is_normalized(self):
        result = validate(
            _valid_action(
                action="data_analizis",
                amount=None,
                exchange_rate=None,
                converted_amount=None,
                period={"preset": "this_month", "from": None, "to": None},
            )
        )
        assert result.valid is True
        assert result.action["action"] == "data_analysis"

    def test_validate_rejects_non_object(self):
        result = validate("not-a-json-object")
        assert result.valid is False
        assert "output is not a json object" in result.error.lower()

    def test_validate_rejects_invalid_action(self):
        result = validate(_valid_action(action="unsupported"))
        assert result.valid is False
        assert "invalid action" in result.error.lower()

    def test_validate_rejects_missing_amount_for_income(self):
        result = validate(_valid_action(action="add_income", amount=None))
        assert result.valid is False
        assert "requires a non-null 'amount'" in result.error

    def test_validate_rejects_negative_amount(self):
        result = validate(_valid_action(amount=-10.0))
        assert result.valid is False
        assert "must be positive" in result.error

    def test_validate_rejects_non_numeric_exchange_rate_or_converted_amount(self):
        result = validate(_valid_action(exchange_rate="abc"))
        assert result.valid is False
        assert "could not convert string to float" in result.error.lower()

        result = validate(_valid_action(converted_amount="abc"))
        assert result.valid is False
        assert "'converted_amount' must be numeric" in result.error

    def test_validate_rejects_zero_exchange_rate(self):
        result = validate(_valid_action(exchange_rate=0))
        assert result.valid is False
        assert "must be positive" in result.error

    def test_validate_rejects_report_with_non_dict_period(self):
        result = validate(
            _valid_action(
                action="report",
                amount=None,
                exchange_rate=None,
                converted_amount=None,
                report_type="expenses",
                period="not-a-dict",
            )
        )
        assert result.valid is False
        assert "'period' must be an object" in result.error

    def test_validate_rejects_unknown_period_preset(self):
        result = validate(
            _valid_action(
                action="data_analysis",
                amount=None,
                exchange_rate=None,
                converted_amount=None,
                period={"preset": "unsupported", "from": None, "to": None},
            )
        )
        assert result.valid is False
        assert "'period.preset' must be one of" in result.error

    def test_validate_rejects_period_from_after_to(self):
        result = validate(
            _valid_action(
                action="report",
                amount=None,
                exchange_rate=None,
                converted_amount=None,
                report_type="expenses",
                period={"preset": "custom", "from": "2025-03-01", "to": "2025-02-01"},
            )
        )
        assert result.valid is False
        assert "must be <= 'period.to'" in result.error

    def test_validate_rejects_filters_not_object(self):
        result = validate(
            _valid_action(
                action="data_analysis",
                amount=None,
                exchange_rate=None,
                converted_amount=None,
                period={"preset": "this_month", "from": None, "to": None},
                filters="not-an-object",
            )
        )
        assert result.valid is False
        assert "'filters' must be an object or null" in result.error

    def test_validate_rejects_invalid_filter_amounts(self):
        result = validate(
            _valid_action(
                action="report",
                amount=None,
                exchange_rate=None,
                converted_amount=None,
                report_type="expenses",
                period={"preset": "this_year", "from": None, "to": None},
                filters={"min_amount": "px", "max_amount": None},
            )
        )
        assert result.valid is False
        assert "invalid money value" in result.error.lower()

    def test_valid_actions_constant(self):
        assert "add_income" in VALID_ACTIONS
        assert "add_expense" in VALID_ACTIONS
        assert "report" in VALID_ACTIONS
        assert "data_analysis" in VALID_ACTIONS
        assert "none" in VALID_ACTIONS


def test_required_keys_match_contract() -> None:
    action = _valid_action()
    assert set(action.keys()) == set(REQUIRED_KEYS)
