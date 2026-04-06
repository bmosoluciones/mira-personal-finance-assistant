# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Behavior-level tests for the deterministic parser engine."""

from __future__ import annotations

import pytest

from mira.ai.parser_engine import TransactionParserEngine
from mira.ai.schema_contract import build_assistant_system_prompt


def test_assistant_system_prompt_mentions_required_contract_fields() -> None:
    prompt = build_assistant_system_prompt()
    assert '"action": "<add_income|add_expense|report|data_analysis|none>"' in prompt
    assert '"converted_amount": <number or null>' in prompt


@pytest.mark.parametrize(
    ("text", "expected_action", "expected_amount", "expected_category"),
    [
        ("spent 50 on food", "add_expense", 50.0, "food"),
        ("pagué 99,99 de internet", "add_expense", 99.99, "utilities"),
        ("received 99.99 bonus", "add_income", 99.99, "income"),
        ("I got paid 2k salary", "add_income", 2000.0, "salary"),
    ],
)
def test_parse_extracts_amount_and_category_through_behavior(
    text: str,
    expected_action: str,
    expected_amount: float,
    expected_category: str,
) -> None:
    result = TransactionParserEngine().parse(text)

    assert result["action"] == expected_action
    assert result["amount"] == pytest.approx(expected_amount)
    assert result["category"] == expected_category


def test_parse_extracts_account_through_behavior() -> None:
    result = TransactionParserEngine().parse("spent 80 from savings")

    assert result["action"] == "add_expense"
    assert result["account"] == "savings"


@pytest.mark.parametrize(
    ("text", "report_type", "period"),
    [
        ("show my balance", "balance", "this_month"),
        ("cash flow report last week", "cashflow", "last_week"),
        ("show my income this year", "incomes", "this_year"),
        ("show my expenses last 3 months", "expenses", "last_3_months"),
    ],
)
def test_parse_extracts_report_metadata_through_behavior(text: str, report_type: str, period: str) -> None:
    result = TransactionParserEngine().parse(text)

    assert result["action"] == "report"
    assert result["report_type"] == report_type
    assert result["period"]["preset"] == period


def test_parse_extracts_analysis_period_and_filters_through_behavior() -> None:
    result = TransactionParserEngine().parse("analiza mis gastos de salud")

    assert result["action"] == "data_analysis"
    assert result["filters"] is not None
    assert result["filters"]["categories"] == ["health"]


def test_parse_uses_category_filter_in_reports() -> None:
    result = TransactionParserEngine().parse("show me food expenses this month")

    assert result["action"] == "report"
    assert result["filters"] is not None
    assert result["filters"]["categories"] == ["food"]


@pytest.mark.parametrize(
    "text",
    [
        "Me cayó una lana de 1500",
        "Me cayó pisto 800",
        "Entró pisto 230",
        "Me cayó billete 450",
        "Me cayó rial 99",
        "Me cayó una platica 100",
        "Me entró harina 320",
        "Me cayó chen chen 70",
        "Me cayó fulita 44",
        "Me entró un baro 55",
        "Me entró un dinerito 880",
        "Me entró chavitos 75",
        "Me cayó una luca 1000",
        "Me hice unos pesos 210",
        "Me cayó una plata 120",
        "Me entró real 630",
        "Me cayó una platita 92",
        "Salió una lanita 101",
        "Me cayó sencillo 88",
        "Me entró guita 100",
        "Me hice unos mangos 260",
        "Entró guaraníes 400",
        "Caiu uma grana 350",
        "Entrou uma grana 500",
        "Me cayó pasta 60",
    ],
)
def test_parser_identifies_regional_income_patterns(text: str) -> None:
    result = TransactionParserEngine().parse(text)
    assert result["action"] == "add_income"
    assert result["amount"] is not None


@pytest.mark.parametrize(
    "text",
    [
        "Me salió un gasto de 1500",
        "Me bajaron una lana 300",
        "Me tumbaron feria 220",
        "Se me fue el varo 90",
        "Me ensartaron la cuenta 70",
        "Se me fue el pisto 180",
        "Me tocó soltar pisto 120",
        "Me tocó pagar feria 60",
        "Me tocó soltar billete 200",
        "Me salió el gasto 420",
        "Me tocó aflojar harina 80",
        "Me tocó soltar chen chen 33",
        "Tuve que soltar fulas 25",
        "Me bajé con un menudo 50",
        "Tuve que soltar cuarto 35",
        "Se me fueron los chavitos 46",
        "Me tocó sacar plata 500",
        "Se me fueron unas lucas 1000",
        "Me clavaron la cuenta 130",
        "Me tocó soltar real 65",
        "Me vaciaron el bolsillo 77",
        "Me salió caro 230",
        "Me arrancaron la cabeza 180",
        "Tive que desembolsar uma grana 120",
        "Saiu caro 80",
        "Foi uma facada 55",
    ],
)
def test_parser_identifies_regional_expense_patterns(text: str) -> None:
    result = TransactionParserEngine().parse(text)
    assert result["action"] == "add_expense"
    assert result["amount"] is not None


class TestFallbackMisclassificationGuards:
    def test_balance_statement_not_expense(self):
        r = TransactionParserEngine().parse("my balance is 5000")
        assert r["action"] == "report"

    def test_bare_number_returns_none(self):
        r = TransactionParserEngine().parse("5000")
        assert r["action"] == "none"
        assert r["message"] is not None
        assert "5000" in r["message"]

    def test_income_without_amount_returns_none(self):
        r = TransactionParserEngine().parse("recibí mi salario")
        assert r["action"] == "none"
        assert "monto" in r["message"].lower() or "cuánto" in r["message"].lower()

    def test_expense_without_amount_returns_none(self):
        r = TransactionParserEngine().parse("gasté en comida")
        assert r["action"] == "none"
        assert "monto" in r["message"].lower() or "cuánto" in r["message"].lower()

    def test_non_finance_sentence_with_number(self):
        r = TransactionParserEngine().parse("I have 2 dogs")
        assert r["action"] == "none"

    def test_question_with_number_not_recorded(self):
        r = TransactionParserEngine().parse("how much is 500 in euros")
        assert r["action"] == "report"

    def test_weather_question(self):
        r = TransactionParserEngine().parse("what is the weather today")
        assert r["action"] == "none"

    def test_greeting(self):
        r = TransactionParserEngine().parse("hello")
        assert r["action"] == "none"


class TestFallbackEdgeCases:
    def test_empty_string(self):
        r = TransactionParserEngine().parse("")
        assert r["action"] == "none"

    def test_whitespace_only(self):
        r = TransactionParserEngine().parse("   ")
        assert r["action"] == "none"

    def test_special_characters_only(self):
        r = TransactionParserEngine().parse("!@#$%^&*()")
        assert r["action"] == "none"

    def test_very_long_input(self):
        text = "I spent 100 on food " * 50
        r = TransactionParserEngine().parse(text)
        assert r["action"] == "add_expense"
        assert r["amount"] == 100.0

    def test_unicode_input(self):
        r = TransactionParserEngine().parse("我花了500元")
        assert r["action"] == "none"

    def test_mixed_language(self):
        r = TransactionParserEngine().parse("gasté 50 on food")
        assert r["action"] == "add_expense"
        assert r["amount"] == 50.0
        assert r["category"] == "food"

    def test_transfer_to_savings_is_expense_with_savings_category(self):
        r = TransactionParserEngine().parse("transferi 200 a ahorro")
        assert r["action"] == "add_expense"
        assert r["amount"] == 200.0
        assert r["category"] == "savings"

    def test_saved_phrase_is_expense_with_savings_category(self):
        r = TransactionParserEngine().parse("Saved 50 dollars from my paycheck")
        assert r["action"] == "add_expense"
        assert r["amount"] == pytest.approx(50.0)
        assert r["category"] == "savings"

    def test_put_into_savings_account_is_expense_with_savings_category(self):
        r = TransactionParserEngine().parse("Put 100 dollars into my savings account")
        assert r["action"] == "add_expense"
        assert r["amount"] == pytest.approx(100.0)
        assert r["category"] == "savings"

    def test_amount_supports_mil_suffix_for_savings_phrase(self):
        r = TransactionParserEngine().parse("Ahorré 50 mil pesos colombianos para la navidad")
        assert r["action"] == "add_expense"
        assert r["amount"] == pytest.approx(50000.0)
        assert r["base_currency"] == "COP"

    def test_freeform_category_from_trailing_phrase(self):
        r = TransactionParserEngine().parse("gasté 80 en cafeteria")
        assert r["action"] == "add_expense"
        assert r["account"] is None
        assert r["category"] == "cafeteria"


class TestFallbackPortuguese:
    def test_recebi_income(self):
        r = TransactionParserEngine().parse("recebi 500 de salário")
        assert r["action"] == "add_income"
        assert r["amount"] == 500.0

    def test_ganhei_income(self):
        r = TransactionParserEngine().parse("ganhei 300 no freelance")
        assert r["action"] == "add_income"
        assert r["amount"] == 300.0

    def test_gastei_expense(self):
        r = TransactionParserEngine().parse("gastei 30 em comida")
        assert r["action"] == "add_expense"
        assert r["amount"] == 30.0

    def test_paguei_expense(self):
        r = TransactionParserEngine().parse("paguei 100 de aluguel")
        assert r["action"] == "add_expense"
        assert r["amount"] == 100.0

    def test_comprei_expense(self):
        r = TransactionParserEngine().parse("comprei roupa 80")
        assert r["action"] == "add_expense"
        assert r["amount"] == 80.0


class TestDefaultCurrencyPriority:
    """Tests for the default_currency priority logic in TransactionParserEngine.

    Rules under test
    ----------------
    * When USD is the default currency: broad USD patterns ("$", "dollars",
      "bucks", heuristic phrases) are applied; fallback is None (→ USD).
    * When a non-USD currency is the default: only the explicit ISO code "USD"
      / "US$" triggers USD detection; all USD heuristic phrases are suppressed
      so that ambiguous tokens (e.g. "$") are not misread as USD.
    """

    # ------------------------------------------------------------------
    # USD-default behaviour (unchanged from original)
    # ------------------------------------------------------------------

    def test_dollar_sign_detected_as_usd_when_usd_is_default(self):
        r = TransactionParserEngine(default_currency="USD").parse("spent $50 on food")
        assert r["action"] == "add_expense"
        assert r["base_currency"] == "USD"

    def test_dollars_word_detected_when_usd_is_default(self):
        r = TransactionParserEngine(default_currency="USD").parse("received 300 dollars")
        assert r["action"] == "add_income"
        assert r["base_currency"] == "USD"

    def test_usd_heuristic_phrase_returns_usd_when_default_is_usd(self):
        r = TransactionParserEngine(default_currency="USD").parse("I got paid 1000 from my job")
        assert r["action"] == "add_income"
        assert r["base_currency"] == "USD"

    # ------------------------------------------------------------------
    # Non-USD default: broad USD slang suppressed
    # ------------------------------------------------------------------

    def test_dollar_sign_not_usd_when_nio_is_default(self):
        """'$' is used for córdobas in Nicaragua – should not be mapped to USD."""
        r = TransactionParserEngine(default_currency="NIO").parse("gasté $200 en comida")
        assert r["action"] == "add_expense"
        assert r["base_currency"] != "USD"

    def test_dollars_word_not_matched_when_nio_is_default(self):
        """Generic 'dollars'/'dólares' slang should not override a non-USD default."""
        r = TransactionParserEngine(default_currency="NIO").parse("gasté 200 dólares en comida")
        assert r["action"] == "add_expense"
        assert r["base_currency"] != "USD"

    def test_usd_heuristic_phrase_suppressed_when_default_is_nio(self):
        """English heuristic USD phrase must not produce USD for a NIO-default user."""
        r = TransactionParserEngine(default_currency="NIO").parse("I got paid 500 from my job")
        assert r["action"] == "add_income"
        assert r["base_currency"] != "USD"

    def test_explicit_usd_code_still_detected_when_nio_is_default(self):
        """If the user writes 'USD' explicitly we should still detect it."""
        r = TransactionParserEngine(default_currency="NIO").parse("received 100 USD")
        assert r["action"] == "add_income"
        assert r["base_currency"] == "USD"

    def test_no_default_currency_keeps_legacy_usd_behaviour(self):
        """Omitting default_currency must preserve the original behaviour."""
        r = TransactionParserEngine().parse("spent $50 on food")
        assert r["action"] == "add_expense"
        assert r["base_currency"] == "USD"

    def test_explicit_non_usd_currency_always_wins(self):
        """Explicit currency code overrides regardless of default."""
        r = TransactionParserEngine(default_currency="USD").parse("gasté 50 córdobas en comida")
        assert r["action"] == "add_expense"
        assert r["base_currency"] == "NIO"

    def test_cop_detected_when_default_is_cop(self):
        r = TransactionParserEngine(default_currency="COP").parse("gasté 20000 en el supermercado")
        assert r["action"] == "add_expense"
        assert r["base_currency"] != "USD"

    def test_mxn_detected_when_default_is_mxn(self):
        r = TransactionParserEngine(default_currency="MXN").parse("pagué 500 pesos")
        assert r["action"] == "add_expense"
        assert r["base_currency"] == "MXN"

    def test_peso_with_cop_default_detects_cop_via_hint(self):
        """When 'pesos colombianos' is said and default is COP, COP must be detected."""
        r = TransactionParserEngine(default_currency="COP").parse("gasté 50000 pesos colombianos")
        assert r["action"] == "add_expense"
        assert r["base_currency"] == "COP"

    def test_bare_peso_still_returns_mxn_regardless_of_default(self):
        """'pesos' with no country qualifier falls back to MXN (existing behaviour)."""
        r = TransactionParserEngine(default_currency="COP").parse("pagué 100 pesos")
        assert r["action"] == "add_expense"
        assert r["base_currency"] == "MXN"
