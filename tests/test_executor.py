# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tests for the action executor."""

from __future__ import annotations

from datetime import date

import pytest

from mira.ai.executor import Executor
from mira.ai import executor as executor_module
from mira.db.database import Database
from mira.ui.i18n import tr


@pytest.fixture
def db(tmp_path):
    d = Database(path=tmp_path / "exec_test.db")
    d.connect()
    yield d
    d.close()


@pytest.fixture
def executor(db):
    return Executor(db)


def _action(**overrides):
    base = {
        "action": "add_income",
        "amount": None,
        "description": None,
        "category": None,
        "account": None,
        "base_currency": "USD",
        "exchange_rate": 1.0,
        "converted_amount": None,
        "report_type": None,
        "period": None,
        "filters": None,
        "message": None,
    }
    base.update(overrides)
    return base


class TestExecutorAddIncome:
    def test_records_transaction(self, executor, db):
        executor.execute(_action(action="add_income", amount=1000.0, converted_amount=1000.0, description="salary"))
        txs = db.transaction.list(tx_type="income")
        assert any(t["amount"] == pytest.approx(1000.0) for t in txs)

    def test_updates_named_account_balance(self, executor, db):
        db.account.create("savings", account_type="bank", opening_balance=0.0, currency="USD")
        executor.execute(_action(action="add_income", amount=500.0, converted_amount=500.0, account="savings"))
        acc = db.account.find_by_name("savings")
        assert acc is not None
        assert acc["balance"] == pytest.approx(500.0)

    def test_unknown_account_falls_back_to_default(self, executor, db):
        executor.execute(_action(action="add_income", amount=500.0, converted_amount=500.0, account="nonexistent_xyz"))
        assert db.account.find_by_name("nonexistent_xyz") is None
        default_acc = db.account.get_default()
        assert default_acc is not None
        assert default_acc["balance"] == pytest.approx(500.0)

    def test_uses_converted_amount(self, executor, db):
        executor.execute(_action(action="add_income", amount=500.0, converted_amount=480.0, exchange_rate=0.96))
        default_acc = db.account.get_default()
        assert default_acc is not None
        assert default_acc["balance"] == pytest.approx(480.0)

    def test_uses_default_account_regardless_of_language(self, executor, db):
        db.setting.set("language", "es")

        executor.execute(_action(action="add_income", amount=500.0, converted_amount=500.0))

        default_acc = db.account.get_default()
        assert default_acc is not None
        assert default_acc["balance"] == pytest.approx(500.0)
        assert db.account.find_by_name("Cuenta principal") is None

    def test_unknown_category_is_not_created_for_income(self, executor, db):
        executor.execute(_action(action="add_income", amount=120.0, converted_amount=120.0, category="consultoria_xyz"))
        cat = db.category.find_by_name("consultoria_xyz", "income")
        assert cat is None

    def test_fuzzy_category_match_income(self, executor, db):
        db.setting.seed_initial_data(include_default_categories=True, account_names=[])
        executor.execute(_action(action="add_income", amount=120.0, converted_amount=120.0, category="salary"))
        txs = db.transaction.list(tx_type="income")
        assert any(tx["category"] is not None and tx["category"] != "" for tx in txs)


class TestExecutorAddExpense:
    def test_records_transaction(self, executor, db):
        executor.execute(_action(action="add_expense", amount=50.0, converted_amount=50.0, description="groceries"))
        txs = db.transaction.list(tx_type="expense")
        assert any(t["amount"] == pytest.approx(50.0) for t in txs)

    def test_decreases_account_balance(self, executor, db):
        db.account.create("checking", account_type="bank", opening_balance=0.0, currency="USD")
        executor.execute(_action(action="add_income", amount=300.0, converted_amount=300.0, account="checking"))
        executor.execute(_action(action="add_expense", amount=100.0, converted_amount=100.0, account="checking"))
        acc = db.account.find_by_name("checking")
        assert acc["balance"] == pytest.approx(200.0)

    def test_unknown_category_is_not_created_for_expense(self, executor, db):
        executor.execute(_action(action="add_expense", amount=45.0, converted_amount=45.0, category="cafeteria_xyz"))
        cat = db.category.find_by_name("cafeteria_xyz", "expense")
        assert cat is None

    def test_savings_expense_matches_seeded_savings_category(self, executor, db):
        db.setting.seed_initial_data(include_default_categories=True, account_names=[])
        executor.execute(_action(action="add_expense", amount=60.0, converted_amount=60.0, category="savings"))

        txs = db.transaction.list(tx_type="expense")
        matched_categories = [tx["category"] for tx in txs if tx.get("category") is not None]
        assert len(matched_categories) > 0
        savings_cat = db.category.find_by_name(matched_categories[0])
        assert savings_cat is not None
        assert int(savings_cat.get("is_savings") or 0) == 1

    def test_savings_expense_matches_seeded_ahorro_category(self, executor, db):
        db.setting.seed_initial_data(include_default_categories=True, account_names=[], language="es")
        executor.execute(_action(action="add_expense", amount=60.0, converted_amount=60.0, category="ahorro"))

        txs = db.transaction.list(tx_type="expense")
        matched = [tx["category"] for tx in txs if tx.get("category") is not None]
        assert len(matched) > 0
        cat = db.category.find_by_name(matched[0])
        assert cat is not None
        assert int(cat.get("is_savings") or 0) == 1

    def test_reuses_existing_category_name_across_transaction_types(self, executor, db):
        db.category.create("impuestos", "income")

        result = executor.execute(
            _action(action="add_expense", amount=45.0, converted_amount=45.0, category="impuestos")
        )

        txs = db.transaction.list(tx_type="expense")
        assert result.success is True
        assert result.action == "add_expense"
        assert any(tx["category"] == "impuestos" for tx in txs)

    def test_credit_card_purchase_posts_expense_on_credit_account(self, executor, db):
        db.account.create("Visa", account_type="credit", opening_balance=-100.0, currency="USD")

        result = executor.execute(
            _action(
                action="add_expense",
                amount=75.0,
                converted_amount=75.0,
                description="spent 75 on groceries with visa",
            )
        )

        visa = db.account.find_by_name("Visa")
        txs = db.transaction.list(tx_type="expense")

        assert result.success is True
        assert result.action == "add_expense"
        assert visa is not None
        assert visa["balance"] == pytest.approx(-175.0)
        assert any(int(tx["account_id"]) == int(visa["id"]) for tx in txs)

    def test_credit_card_payment_records_transfer_without_new_action(self, executor, db):
        source = db.account.create("BAC", account_type="bank", opening_balance=800.0, currency="NIO")
        credit = db.account.create("Visa", account_type="credit", opening_balance=-300.0, currency="NIO")

        result = executor.execute(
            _action(
                action="add_expense",
                amount=200.0,
                converted_amount=200.0,
                description="pague la visa desde bac",
            )
        )

        source_after = db.account.get(source["id"])
        credit_after = db.account.get(credit["id"])
        transfers = [tx for tx in db.transaction.list() if int(tx.get("is_transfer") or 0) == 1]

        assert result.success is True
        assert result.action == "add_expense"
        assert len(transfers) == 2
        assert source_after["balance"] == pytest.approx(600.0)
        assert credit_after["balance"] == pytest.approx(-100.0)

    def test_credit_card_payment_without_clear_source_returns_none(self, executor, db):
        db.setting.set("language", "es")
        db.account.create("BAC", account_type="bank", opening_balance=500.0, currency="NIO")
        db.account.create("LAFISE", account_type="bank", opening_balance=400.0, currency="NIO")
        credit = db.account.create("Visa", account_type="credit", opening_balance=-250.0, currency="NIO")
        db.account.set_default(credit["id"])

        result = executor.execute(
            _action(
                action="add_expense",
                amount=100.0,
                converted_amount=100.0,
                description="pague la visa",
            )
        )

        assert result.success is True
        assert result.action == "none"
        assert result.message == tr(
            "chat.card_payment.source_required",
            "es",
            default="Necesito saber desde que cuenta bank/cash se realizo el pago de la tarjeta.",
        )

    @pytest.mark.parametrize(
        "description",
        [
            "Gaste 48 en flores para regalo desde tarjeta",
            "Pague 17 de lavado de auto desde tarjeta",
        ],
    )
    def test_card_reference_in_description_does_not_force_card_payment_flow(self, executor, db, description):
        result = executor.execute(
            _action(
                action="add_expense",
                amount=48.0,
                converted_amount=48.0,
                description=description,
            )
        )

        txs = db.transaction.list(tx_type="expense")
        assert result.success is True
        assert result.action == "add_expense"
        assert any(tx["amount"] == pytest.approx(48.0) for tx in txs)


class TestExecutorReport:
    def test_returns_report(self, executor):
        result = executor.execute(
            _action(
                action="report",
                amount=None,
                exchange_rate=None,
                converted_amount=None,
                report_type="expenses",
                period={"preset": "this_month", "from": None, "to": None},
                filters={"categories": None, "accounts": None, "min_amount": None, "max_amount": None, "text": None},
            )
        )
        assert result.success is True
        assert result.action == "report"

    def test_report_with_category_filter(self, executor, db):
        db.category.create("food", "expense")
        db.category.create("transport", "expense")
        executor.execute(_action(action="add_expense", amount=20, converted_amount=20, category="food"))
        executor.execute(_action(action="add_expense", amount=10, converted_amount=10, category="transport"))

        result = executor.execute(
            _action(
                action="report",
                amount=None,
                exchange_rate=None,
                converted_amount=None,
                report_type="expenses",
                period={"preset": "this_month", "from": None, "to": None},
                filters={
                    "categories": ["food"],
                    "accounts": None,
                    "min_amount": None,
                    "max_amount": None,
                    "text": None,
                },
            )
        )
        assert len(result.data["transactions"]) == 1
        assert result.data["transactions"][0]["category"] == "food"


class TestExecutorDataAnalysis:
    def test_returns_analysis_action(self, executor):
        result = executor.execute(
            _action(
                action="data_analysis",
                amount=None,
                exchange_rate=None,
                converted_amount=None,
                period={"preset": "this_month", "from": None, "to": None},
                filters={"categories": ["food"]},
            )
        )
        assert result.success is True
        assert result.action == "data_analysis"
        assert result.data["period"]["preset"] == "this_month"


class TestExecutorNone:
    def test_returns_localized_default_message_in_spanish(self, executor, db):
        db.setting.set("language", "es")
        action = _action(
            action="none",
            amount=None,
            exchange_rate=None,
            converted_amount=None,
            message=None,
        )
        result = executor.execute(action)
        assert result.success is True
        assert result.message == tr(
            "chat.none.generic",
            "es",
            default="Sorry, I did not understand your request. I can help you record income, expenses, or review your financial summary.",
        )

    def test_returns_localized_default_message_in_english(self, executor, db):
        db.setting.set("language", "en")
        result = executor.execute(_action(action="none", message=None))
        assert result.success is True
        assert result.message == tr(
            "chat.none.generic",
            "en",
            default="Sorry, I did not understand your request. I can help you record income, expenses, or review your financial summary.",
        )


def test_execute_unknown_action_uses_none_handler(executor):
    result = executor.execute({"action": "something_unknown"})
    assert result.success is True
    assert result.action == "none"


def test_report_filters_by_multiple_categories_account_and_amount_range(executor, db):
    db.account.create("wallet", account_type="bank", opening_balance=0.0, currency="USD")
    db.account.create("bank", account_type="bank", opening_balance=0.0, currency="USD")
    db.category.create("food", "expense")
    db.category.create("transport", "expense")
    executor.execute(_action(action="add_expense", amount=10, converted_amount=10, category="food", account="wallet"))
    executor.execute(
        _action(action="add_expense", amount=20, converted_amount=20, category="transport", account="wallet")
    )
    executor.execute(_action(action="add_expense", amount=30, converted_amount=30, category="food", account="bank"))

    result = executor.execute(
        _action(
            action="report",
            amount=None,
            exchange_rate=None,
            converted_amount=None,
            report_type="expenses",
            period={"preset": "this_month", "from": None, "to": None},
            filters={
                "categories": ["transport", "food"],
                "accounts": ["wallet"],
                "min_amount": 15,
                "max_amount": 25,
                "text": None,
            },
        )
    )

    txs = result.data["transactions"]
    assert len(txs) == 1
    assert txs[0]["category"] == "transport"
    assert float(txs[0]["amount"]) == pytest.approx(20.0)


def test_income_confirmation_is_localized_in_spanish(executor, db):
    db.setting.set("language", "es")

    result = executor.execute(_action(action="add_income", amount=125.0, converted_amount=125.0, description="salario"))

    assert result.success is True
    assert result.action == "add_income"
    assert result.message.startswith("Ingreso registrado:")
    assert "(cuenta:" in result.message


def test_expense_confirmation_is_localized_in_english(executor, db):
    db.setting.set("language", "en")

    result = executor.execute(
        _action(action="add_expense", amount=45.0, converted_amount=45.0, description="groceries")
    )

    assert result.success is True
    assert result.action == "add_expense"
    assert result.message.startswith("Expense recorded:")
    assert "(account:" in result.message


def test_credit_card_payment_clarification_is_localized_in_english(executor, db):
    db.setting.set("language", "en")
    db.account.create("BAC", account_type="bank", opening_balance=500.0, currency="NIO")
    db.account.create("LAFISE", account_type="bank", opening_balance=400.0, currency="NIO")
    credit = db.account.create("Visa", account_type="credit", opening_balance=-250.0, currency="NIO")
    db.account.set_default(credit["id"])

    result = executor.execute(
        _action(
            action="add_expense",
            amount=100.0,
            converted_amount=100.0,
            description="paid 100 to visa",
        )
    )

    assert result.success is True
    assert result.action == "none"
    assert result.message == tr(
        "chat.card_payment.source_required",
        "en",
        default="I need to know which bank or cash account was used to pay the card.",
    )


def test_report_message_is_localized_in_english(executor, db):
    db.setting.set("language", "en")
    result = executor.execute(
        _action(
            action="report",
            amount=None,
            exchange_rate=None,
            converted_amount=None,
            report_type="expenses",
            period={"preset": "this_month", "from": None, "to": None},
            filters={"categories": None, "accounts": None, "min_amount": None, "max_amount": None, "text": None},
        )
    )

    assert result.success is True
    assert result.action == "report"
    assert result.message.splitlines()[0] == "Report (expenses) - period: this_month"
    assert "Accounts:" in result.message


def test_compute_summary_mixed_transactions(db) -> None:
    savings_name = "Ahorro Test"
    db.category.get_or_create(savings_name, "expense", is_savings=True)
    summary = executor_module._compute_summary(
        db,
        [
            {"type": "income", "amount": "100"},
            {"type": "income", "amount": 50},
            {"type": "expense", "amount": 40},
            {"type": "expense", "amount": 10, "category": savings_name},
        ],
    )
    assert summary == {
        "total_income": pytest.approx(150.0),
        "total_expenses": pytest.approx(40.0),
        "savings": pytest.approx(10.0),
        "net": pytest.approx(110.0),
    }


def test_period_range_custom_and_all_time(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 14)

    monkeypatch.setattr(executor_module, "date", FixedDate)

    start, end, preset = executor_module._period_range({"preset": "all_time"})
    assert start is None
    assert end == "2026-03-14"
    assert preset == "all_time"

    start, end, preset = executor_module._period_range({"preset": "custom", "from": "2026-01-01", "to": "2026-01-31"})
    assert start == "2026-01-01"
    assert end == "2026-01-31"
    assert preset == "custom"


class TestCategoryMatching:
    """Tests for the category fuzzy-matching helpers."""

    def _cats(self, names_types: list[tuple[str, str]]) -> list[dict]:
        return [{"name": n, "type": t, "id": i} for i, (n, t) in enumerate(names_types)]

    def test_exact_match_returns_correct_category(self):
        cats = self._cats([("Food", "expense"), ("Transport", "expense")])
        result = executor_module._find_best_category_match("Food", cats)
        assert result is not None
        assert result["name"] == "Food"

    def test_case_insensitive_exact_match(self):
        cats = self._cats([("Food", "expense"), ("Transport", "expense")])
        result = executor_module._find_best_category_match("food", cats)
        assert result is not None
        assert result["name"] == "Food"

    def test_synonym_lookup_english_to_spanish_category(self):
        cats = self._cats([("Alimentación", "expense"), ("Transporte", "expense")])
        result = executor_module._find_best_category_match("food", cats)
        assert result is not None
        assert result["name"] == "Alimentación"

    def test_synonym_lookup_spanish_to_english_category(self):
        cats = self._cats([("Food", "expense"), ("Transport", "expense")])
        result = executor_module._find_best_category_match("comida", cats)
        assert result is not None
        assert result["name"] == "Food"

    def test_synonym_lookup_savings(self):
        cats = self._cats([("Savings", "expense"), ("Housing", "expense")])
        result = executor_module._find_best_category_match("savings", cats)
        assert result is not None
        assert result["name"] == "Savings"

    def test_synonym_lookup_ahorro(self):
        cats = self._cats([("Ahorro", "expense"), ("Vivienda", "expense")])
        result = executor_module._find_best_category_match("ahorro", cats)
        assert result is not None
        assert result["name"] == "Ahorro"

    def test_fuzzy_substring_match(self):
        cats = self._cats([("Groceries and Pantry", "expense"), ("Transport", "expense")])
        result = executor_module._find_best_category_match("groceries", cats)
        assert result is not None
        assert result["name"] == "Groceries and Pantry"

    def test_garbage_input_returns_none(self):
        cats = self._cats([("Food", "expense"), ("Transport", "expense"), ("Housing", "expense")])
        assert executor_module._find_best_category_match("en", cats) is None
        assert executor_module._find_best_category_match("mi", cats) is None

    def test_empty_category_list_returns_none(self):
        assert executor_module._find_best_category_match("food", []) is None

    def test_score_similarity_exact(self):
        assert executor_module._score_name_similarity("food", "food") == 1.0

    def test_score_similarity_containment(self):
        score = executor_module._score_name_similarity("groceries", "groceries and pantry")
        assert score >= executor_module._CATEGORY_MATCH_THRESHOLD

    def test_score_similarity_garbage_short_word(self):
        score = executor_module._score_name_similarity("en", "entertainment")
        assert score < executor_module._CATEGORY_MATCH_THRESHOLD
