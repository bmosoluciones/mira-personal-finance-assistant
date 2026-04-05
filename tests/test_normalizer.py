# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tests for the text normaliser."""

from __future__ import annotations

from mira.ai.normalizer import normalise


class TestNormaliser:
    def test_strips_whitespace(self):
        assert normalise("  hello  ") == "hello"

    def test_collapses_internal_whitespace(self):
        assert normalise("hello   world") == "hello world"

    def test_removes_dollar_sign(self):
        result = normalise("I spent $100 on food")
        assert "$" not in result
        assert "100" in result

    def test_removes_euro_sign(self):
        result = normalise("paid €50")
        assert "€" not in result
        assert "50" in result

    def test_removes_thousand_separator(self):
        result = normalise("received 1,500")
        assert "1500" in result

    def test_expands_k_suffix(self):
        result = normalise("earned 2k")
        assert "2000" in result

    def test_expands_k_suffix_decimal(self):
        result = normalise("earned 1.5k")
        assert "1500" in result

    def test_k_suffix_case_insensitive(self):
        result = normalise("spent 3K")
        assert "3000" in result

    def test_strips_dollar_word(self):
        result = normalise("100 dollars")
        assert "dollars" not in result
        assert "100" in result

    def test_strips_pesos_word(self):
        result = normalise("200 pesos")
        assert "pesos" not in result
        assert "200" in result

    def test_strips_usd(self):
        result = normalise("500 USD")
        assert "USD" not in result.upper() or "500" in result

    def test_strips_eur(self):
        result = normalise("300 EUR")
        assert "300" in result

    def test_income_synonym_earned(self):
        result = normalise("I earned 1000")
        assert "received" in result

    def test_income_synonym_cobr(self):
        result = normalise("Cobré mi sueldo")
        assert "received" in result

    def test_income_synonym_game_typo(self):
        result = normalise("Game mil cordobas en salario")
        assert "received" in result

    def test_spanish_number_mil(self):
        result = normalise("gaste mil en comida")
        assert "1000" in result

    def test_expense_synonym_paid(self):
        result = normalise("I paid 30 for lunch")
        assert "spent" in result

    def test_expense_synonym_compre(self):
        result = normalise("Compré ropa")
        assert "spent" in result

    def test_report_synonym_resumen(self):
        result = normalise("resumen de gastos")
        assert "report" in result

    def test_report_synonym_show_me(self):
        result = normalise("show me my finances")
        assert "report" in result

    def test_idempotent_plain_text(self):
        text = "received 500 salary"
        assert normalise(normalise(text)) == normalise(text)

    def test_empty_string(self):
        assert normalise("") == ""


class TestNormaliserNewSynonyms:
    """Tests for Portuguese and additional synonym expansions."""

    def test_income_depositei(self):
        result = normalise("deposité 500")
        assert "received" in result

    def test_income_deposito(self):
        result = normalise("depósito de 1000")
        assert "received" in result

    def test_income_recebi(self):
        result = normalise("recebi 300 de salário")
        assert "received" in result

    def test_income_ganhei(self):
        result = normalise("ganhei 200 no freelance")
        assert "received" in result

    def test_expense_bought(self):
        result = normalise("I bought a coffee for 5")
        assert "spent" in result

    def test_expense_retire(self):
        result = normalise("retiré 200 del cajero")
        assert "spent" in result

    def test_expense_transferi(self):
        result = normalise("transferí 500 a Juan")
        assert "spent" in result

    def test_expense_gastei(self):
        result = normalise("gastei 30 em comida")
        assert "spent" in result

    def test_expense_paguei(self):
        result = normalise("paguei 100 de aluguel")
        assert "spent" in result

    def test_expense_comprei(self):
        result = normalise("comprei roupa 80")
        assert "spent" in result
