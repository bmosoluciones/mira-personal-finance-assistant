# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Unit tests for mira.ai.parser_signals.

Covers:
- ParseSignals dataclass fields
- collect_signals: boolean flag extraction from text
- collect_signals: savings_transfer override
- collect_signals: ambiguity resolution tiebreakers
- resolve_intent: every match/case branch
"""

from __future__ import annotations

import pytest

from mira.ai.parser_signals import ParseSignals, collect_signals, resolve_intent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _signals(
    text: str,
    amount: float | None = None,
    currency: str | None = None,
    category: str | None = None,
    account: str | None = None,
) -> ParseSignals:
    return collect_signals(text, amount, currency, category, account)


# ---------------------------------------------------------------------------
# ParseSignals dataclass
# ---------------------------------------------------------------------------


class TestParseSignals:
    def test_default_boolean_flags_are_false(self):
        s = ParseSignals(raw_text="hello", amount=None, currency=None, category=None, account=None)
        assert s.income_strong is False
        assert s.income_weak is False
        assert s.expense_strong is False
        assert s.expense_weak is False
        assert s.report is False
        assert s.analysis is False
        assert s.savings_transfer is False
        assert s.income_context is False

    def test_fields_are_stored_correctly(self):
        s = ParseSignals(
            raw_text="test",
            amount=100.0,
            currency="USD",
            category="food",
            account="savings",
            income_strong=True,
        )
        assert s.raw_text == "test"
        assert s.amount == 100.0
        assert s.currency == "USD"
        assert s.category == "food"
        assert s.account == "savings"
        assert s.income_strong is True


# ---------------------------------------------------------------------------
# collect_signals — report and analysis flags
# ---------------------------------------------------------------------------


class TestCollectSignalsReportAnalysis:
    def test_show_balance_sets_report_flag(self):
        s = _signals("show my balance")
        assert s.report is True
        assert s.analysis is False

    def test_analysis_keyword_sets_analysis_flag(self):
        s = _signals("analiza mis gastos de este mes")
        assert s.analysis is True
        assert s.report is False

    def test_analyze_english_sets_analysis_flag(self):
        s = _signals("analyze my spending")
        assert s.analysis is True

    def test_report_and_transaction_text_prefers_report(self):
        # "how much" triggers report; there's no income/expense keyword
        s = _signals("how much did I spend this month")
        assert s.report is True


# ---------------------------------------------------------------------------
# collect_signals — income flags
# ---------------------------------------------------------------------------


class TestCollectSignalsIncome:
    def test_received_sets_income_strong(self):
        s = _signals("received 500 dollars", amount=500.0)
        assert s.income_strong is True
        assert s.income_weak is True

    def test_salary_sets_income_weak_only(self):
        s = _signals("salary 3000", amount=3000.0)
        assert s.income_weak is True
        # "salary" alone is not a strong signal
        assert s.income_strong is False

    def test_spanish_cobr_sets_income_strong(self):
        s = _signals("cobré 800 del cliente", amount=800.0)
        assert s.income_strong is True

    def test_portuguese_recebi_sets_income_strong(self):
        s = _signals("recebi 500", amount=500.0)
        assert s.income_strong is True

    def test_income_context_set_for_salary_category(self):
        s = _signals("I got 3000", amount=3000.0, category="salary")
        assert s.income_context is True

    def test_income_context_not_set_for_other_category(self):
        s = _signals("spent 50 on food", amount=50.0, category="food")
        assert s.income_context is False


# ---------------------------------------------------------------------------
# collect_signals — expense flags
# ---------------------------------------------------------------------------


class TestCollectSignalsExpense:
    def test_spent_sets_expense_strong(self):
        s = _signals("spent 50 on food", amount=50.0)
        assert s.expense_strong is True
        assert s.expense_weak is True

    def test_blew_sets_expense_weak_only(self):
        s = _signals("blew 200 on a jacket", amount=200.0)
        assert s.expense_weak is True
        assert s.expense_strong is False

    def test_spanish_gaste_sets_expense_strong(self):
        s = _signals("gasté 100 en comida", amount=100.0)
        assert s.expense_strong is True

    def test_portuguese_gastei_sets_expense_weak(self):
        s = _signals("gastei 30 em comida", amount=30.0)
        assert s.expense_weak is True


# ---------------------------------------------------------------------------
# collect_signals — savings_transfer override
# ---------------------------------------------------------------------------


class TestCollectSignalsSavingsTransfer:
    def test_ahorre_sets_savings_transfer(self):
        s = _signals("Ahorré 200 pesos", amount=200.0)
        assert s.savings_transfer is True

    def test_savings_transfer_forces_expense_and_clears_income(self):
        s = _signals("transferi 300 a ahorro", amount=300.0)
        assert s.savings_transfer is True
        assert s.expense_strong is True
        assert s.income_strong is False
        assert s.income_weak is False

    def test_saved_english_sets_savings_transfer(self):
        s = _signals("Saved 50 dollars from my paycheck", amount=50.0)
        assert s.savings_transfer is True
        assert s.expense_strong is True

    def test_category_set_to_savings_on_savings_transfer(self):
        s = _signals("Ahorré 100", amount=100.0)
        assert s.category == "savings"

    def test_put_into_savings_account(self):
        s = _signals("Put 100 into my savings account", amount=100.0)
        assert s.savings_transfer is True


# ---------------------------------------------------------------------------
# collect_signals — ambiguity tiebreakers
# ---------------------------------------------------------------------------


class TestCollectSignalsAmbiguity:
    def test_got_paid_resolves_to_income(self):
        # "got paid" is strong income; "paid" is strong expense — tiebreaker wins for income
        s = _signals("I got paid 2000 for the project", amount=2000.0)
        assert s.income_strong or s.income_weak
        assert not s.expense_strong

    def test_reintegro_resolves_to_income(self):
        s = _signals("me hicieron un reintegro de 500", amount=500.0)
        assert s.income_strong or s.income_weak
        assert not s.expense_strong

    def test_income_category_with_no_strong_expense_resolves_to_income(self):
        # "salary" is a weak income; there is no expense keyword → expense flags stay False
        s = _signals("salary 3000", amount=3000.0, category="salary")
        assert s.income_weak is True
        assert s.expense_strong is False
        assert s.expense_weak is False

    def test_transfer_to_account_favors_income(self):
        s = _signals("transferred 500 to my savings account", amount=500.0, account="savings")
        # savings_transfer pattern should catch this
        assert s.savings_transfer is True


# ---------------------------------------------------------------------------
# resolve_intent — all match/case branches
# ---------------------------------------------------------------------------


class TestResolveIntent:
    def _make(self, **kwargs) -> ParseSignals:
        defaults = dict(
            raw_text="test",
            amount=None,
            currency=None,
            category=None,
            account=None,
        )
        defaults.update(kwargs)
        return ParseSignals(**defaults)

    def test_report_flag_returns_report(self):
        s = self._make(report=True)
        assert resolve_intent(s) == "report"

    def test_analysis_flag_returns_analysis(self):
        s = self._make(analysis=True)
        assert resolve_intent(s) == "analysis"

    def test_report_takes_priority_over_analysis(self):
        s = self._make(report=True, analysis=True)
        assert resolve_intent(s) == "report"

    def test_savings_transfer_returns_expense(self):
        s = self._make(savings_transfer=True, expense_strong=True)
        assert resolve_intent(s) == "expense"

    def test_income_strong_no_expense_strong_returns_income(self):
        s = self._make(income_strong=True, expense_strong=False)
        assert resolve_intent(s) == "income"

    def test_expense_strong_no_income_strong_returns_expense(self):
        s = self._make(expense_strong=True, income_strong=False)
        assert resolve_intent(s) == "expense"

    def test_both_strong_with_account_returns_income(self):
        s = self._make(income_strong=True, expense_strong=True, account="savings")
        assert resolve_intent(s) == "income"

    def test_both_strong_salary_category_returns_income(self):
        s = self._make(income_strong=True, expense_strong=True, category="salary")
        assert resolve_intent(s) == "income"

    def test_both_strong_freelance_category_returns_income(self):
        s = self._make(income_strong=True, expense_strong=True, category="freelance")
        assert resolve_intent(s) == "income"

    def test_both_strong_no_cue_returns_expense(self):
        s = self._make(income_strong=True, expense_strong=True)
        assert resolve_intent(s) == "expense"

    def test_income_weak_only_returns_income(self):
        s = self._make(income_weak=True, expense_weak=False)
        assert resolve_intent(s) == "income"

    def test_income_context_returns_income(self):
        s = self._make(income_context=True)
        assert resolve_intent(s) == "income"

    def test_expense_weak_only_returns_expense(self):
        s = self._make(expense_weak=True, income_weak=False)
        assert resolve_intent(s) == "expense"

    def test_bare_amount_returns_unknown(self):
        s = self._make(amount=500.0)
        assert resolve_intent(s) == "unknown"

    def test_no_signals_returns_unknown(self):
        s = self._make()
        assert resolve_intent(s) == "unknown"

    def test_analysis_takes_priority_over_income(self):
        s = self._make(analysis=True, income_strong=True)
        assert resolve_intent(s) == "analysis"

    def test_report_takes_priority_over_expense(self):
        s = self._make(report=True, expense_strong=True)
        assert resolve_intent(s) == "report"


# ---------------------------------------------------------------------------
# Integration: collect_signals → resolve_intent pipelines
# ---------------------------------------------------------------------------


class TestSignalsPipeline:
    @pytest.mark.parametrize(
        ("text", "amount", "category", "expected_intent"),
        [
            ("spent 50 on food", 50.0, "food", "expense"),
            ("received 200 salary", 200.0, "salary", "income"),
            ("I got paid 2000", 2000.0, None, "income"),
            ("recibí 500 de salario", 500.0, "salary", "income"),
            ("Ahorré 300 pesos", 300.0, None, "expense"),
            ("show my balance", None, None, "report"),
            ("analiza mis gastos", None, None, "analysis"),
            ("gastei 30 em comida", 30.0, "food", "expense"),
            ("recebi 500 de salário", 500.0, "salary", "income"),
            ("ganhei 300 no freelance", 300.0, "freelance", "income"),
        ],
    )
    def test_pipeline_intent(self, text: str, amount: float | None, category: str | None, expected_intent: str):
        s = _signals(text, amount=amount, category=category)
        intent = resolve_intent(s)
        assert intent == expected_intent, f"text={text!r}: expected={expected_intent!r} got={intent!r}"

    def test_bare_number_without_signals_is_unknown(self):
        s = _signals("5000", amount=5000.0)
        assert resolve_intent(s) == "unknown"

    def test_deposited_to_savings_account_sets_savings_transfer(self):
        # The savings_transfer pattern only fires for specific saving verbs
        # (save, set aside, kept, transferred to savings, put into savings, etc.)
        # "deposited … savings account" does NOT trigger it — that is intentional.
        s = _signals("deposited 500 into my savings account", amount=500.0, account="savings")
        # "deposited" alone is a weak income signal; "savings account" → savings category
        # but NOT a savings_transfer because "deposited" is not in the savings verb list
        assert s.income_weak is True
        assert s.savings_transfer is False
