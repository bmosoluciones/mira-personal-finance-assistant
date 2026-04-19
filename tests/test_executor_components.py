# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from mira.ai import executor as executor_module
from mira.ai import executor_components as components
from mira.db.database import Database


@dataclass(frozen=True)
class ActionResult:
    success: bool
    action: str
    message: str
    data: dict[str, Any] | None = None


@pytest.fixture
def db(tmp_path):
    database = Database(path=tmp_path / "executor_components.db")
    database.connect()
    yield database
    database.close()


def test_account_resolver_handles_empty_text_and_type_mismatch(db: Database) -> None:
    resolver = components.ExecutorAccountResolver(db)
    assert resolver.mentioned_accounts(None) == []
    assert resolver.resolve_known_account(" ") is None

    credit = db.account.create("Visa", account_type="credit", opening_balance=-100.0, currency="USD")
    assert resolver.resolve_known_account("Visa", account_types=("bank",)) is None
    assert resolver.resolve_known_account("Visa", account_types=("credit",))["id"] == int(credit["id"])


def test_account_resolver_uses_raw_text_mention_and_raises_when_unknown(db: Database) -> None:
    db.account.create("Wallet", account_type="bank", opening_balance=0.0, currency="USD")
    resolver = components.ExecutorAccountResolver(db)

    name, account = resolver.resolve_account(None, raw_text="spent from Wallet")
    assert name == "Wallet"
    assert account["account_type"] == "bank"

    with pytest.raises(ValueError, match="unknown"):
        resolver.resolve_account(None, raw_text=None, account_types=("credit",))


def test_account_resolver_uses_mention_when_direct_match_missing(db: Database) -> None:
    db.account.create("My Visa", account_type="credit", opening_balance=-100.0, currency="USD")
    resolver = components.ExecutorAccountResolver(db)
    assert resolver.resolve_known_account("visa", account_types=("credit",))["name"] == "My Visa"


def test_account_resolver_returns_single_candidate_when_no_default_match(db: Database) -> None:
    db.account.create("Visa", account_type="credit", opening_balance=-100.0, currency="USD")
    resolver = components.ExecutorAccountResolver(db)
    name, account = resolver.resolve_account(None, raw_text=None, account_types=("credit",))
    assert name == "Visa"
    assert account["account_type"] == "credit"


def test_category_resolver_falls_back_to_custom_matcher(db: Database) -> None:
    db.category.create("Food", "expense")
    db.category.create("Transport", "expense")

    resolver = components.ExecutorCategoryResolver(db, matcher=lambda normalized, cats: {"name": "Food"})
    assert resolver.resolve_category({"category": None}, "expense") is None
    assert resolver.resolve_category({"category": "   "}, "expense") is None
    assert resolver.resolve_category({"category": "groceries"}, "expense") == "Food"


def test_credit_card_helper_pattern_detection() -> None:
    patterns = executor_module.CreditCardDetectionPatterns(
        has_card_reference=executor_module._CARD_REFERENCE_PATTERN,
        card_payment=executor_module._CARD_PAYMENT_PATTERN,
        card_payment_target=executor_module._CARD_PAYMENT_TARGET_PATTERN,
        card_usage=executor_module._CARD_USAGE_PATTERN,
    )
    helper = components.ExecutorCreditCardHelper(
        db=SimpleNamespace(),
        account_resolver=SimpleNamespace(),
        patterns=patterns,
        action_result_cls=ActionResult,
        format_money=str,
    )

    assert helper.has_card_reference("payment to visa") is True
    assert helper.has_card_reference(None) is False
    assert helper.looks_like_credit_card_payment("payment to card visa") is True
    assert helper.looks_like_credit_card_payment("paid to mastercard") is True
    assert helper.looks_like_credit_card_payment("just a note") is False
    assert helper.looks_like_credit_card_purchase("bought with visa") is True
    assert helper.looks_like_credit_card_purchase("paid visa") is False


def test_credit_card_helper_resolve_targets_and_sources(db: Database) -> None:
    db.account.create("BAC", account_type="bank", opening_balance=500.0, currency="USD")
    visa = db.account.create("Visa", account_type="credit", opening_balance=-200.0, currency="USD")
    resolver = components.ExecutorAccountResolver(db)
    patterns = executor_module.CreditCardDetectionPatterns(
        has_card_reference=executor_module._CARD_REFERENCE_PATTERN,
        card_payment=executor_module._CARD_PAYMENT_PATTERN,
        card_payment_target=executor_module._CARD_PAYMENT_TARGET_PATTERN,
        card_usage=executor_module._CARD_USAGE_PATTERN,
    )
    helper = components.ExecutorCreditCardHelper(
        db=db,
        account_resolver=resolver,
        patterns=patterns,
        action_result_cls=ActionResult,
        format_money=lambda value: f"{value:.2f}",
    )

    assert helper.resolve_credit_payment_target({"account": "Visa", "description": None})["id"] == int(visa["id"])
    assert helper.resolve_credit_payment_target({"account": None, "description": "paid to visa"})["id"] == int(
        visa["id"]
    )
    assert helper.resolve_credit_payment_source("from BAC")["name"] == "BAC"


def test_credit_card_helper_multiple_credit_mentions_returns_none(db: Database) -> None:
    db.account.create("Visa", account_type="credit", opening_balance=-100.0, currency="USD")
    db.account.create("Mastercard", account_type="credit", opening_balance=-150.0, currency="USD")
    resolver = components.ExecutorAccountResolver(db)
    patterns = executor_module.CreditCardDetectionPatterns(
        has_card_reference=executor_module._CARD_REFERENCE_PATTERN,
        card_payment=executor_module._CARD_PAYMENT_PATTERN,
        card_payment_target=executor_module._CARD_PAYMENT_TARGET_PATTERN,
        card_usage=executor_module._CARD_USAGE_PATTERN,
    )
    helper = components.ExecutorCreditCardHelper(
        db=db,
        account_resolver=resolver,
        patterns=patterns,
        action_result_cls=ActionResult,
        format_money=str,
    )

    assert helper.resolve_credit_payment_target({"account": None, "description": "visa mastercard"}) is None
    db.account.create("BAC", account_type="bank", opening_balance=100.0, currency="USD")
    db.account.create("LAFISE", account_type="bank", opening_balance=100.0, currency="USD")
    assert helper.resolve_credit_payment_source("from BAC and LAFISE") is None


def test_credit_card_helper_rejects_card_reference_without_payment_verb_or_target(db: Database) -> None:
    db.account.create("Visa", account_type="credit", opening_balance=-100.0, currency="USD")
    resolver = components.ExecutorAccountResolver(db)
    patterns = executor_module.CreditCardDetectionPatterns(
        has_card_reference=executor_module._CARD_REFERENCE_PATTERN,
        card_payment=executor_module._CARD_PAYMENT_PATTERN,
        card_payment_target=executor_module._CARD_PAYMENT_TARGET_PATTERN,
        card_usage=executor_module._CARD_USAGE_PATTERN,
    )
    helper = components.ExecutorCreditCardHelper(
        db=db,
        account_resolver=resolver,
        patterns=patterns,
        action_result_cls=ActionResult,
        format_money=str,
    )

    assert helper.looks_like_credit_card_payment("visa") is False


def test_credit_card_helper_resolves_credit_account_by_single_mention(db: Database) -> None:
    db.account.create("Visa", account_type="credit", opening_balance=-100.0, currency="USD")
    resolver = components.ExecutorAccountResolver(db)
    patterns = executor_module.CreditCardDetectionPatterns(
        has_card_reference=executor_module._CARD_REFERENCE_PATTERN,
        card_payment=executor_module._CARD_PAYMENT_PATTERN,
        card_payment_target=executor_module._CARD_PAYMENT_TARGET_PATTERN,
        card_usage=executor_module._CARD_USAGE_PATTERN,
    )
    helper = components.ExecutorCreditCardHelper(
        db=db,
        account_resolver=resolver,
        patterns=patterns,
        action_result_cls=ActionResult,
        format_money=str,
    )

    assert helper.resolve_credit_payment_target({"account": None, "description": "Visa"})["name"] == "Visa"


def test_credit_card_helper_falls_back_to_default_credit_account_when_single_credit_exists(db: Database) -> None:
    db.account.create("Visa", account_type="credit", opening_balance=-100.0, currency="USD")
    resolver = components.ExecutorAccountResolver(db)
    patterns = executor_module.CreditCardDetectionPatterns(
        has_card_reference=executor_module._CARD_REFERENCE_PATTERN,
        card_payment=executor_module._CARD_PAYMENT_PATTERN,
        card_payment_target=executor_module._CARD_PAYMENT_TARGET_PATTERN,
        card_usage=executor_module._CARD_USAGE_PATTERN,
    )
    helper = components.ExecutorCreditCardHelper(
        db=db,
        account_resolver=resolver,
        patterns=patterns,
        action_result_cls=ActionResult,
        format_money=str,
    )

    assert helper.resolve_credit_payment_target({"account": None, "description": "payment to card"})["name"] == "Visa"


def test_credit_card_helper_target_required_when_multiple_credit_accounts(db: Database) -> None:
    db.account.create("Visa", account_type="credit", opening_balance=-100.0, currency="USD")
    db.account.create("Mastercard", account_type="credit", opening_balance=-150.0, currency="USD")
    db.account.create("BAC", account_type="bank", opening_balance=300.0, currency="USD")
    resolver = components.ExecutorAccountResolver(db)
    patterns = executor_module.CreditCardDetectionPatterns(
        has_card_reference=executor_module._CARD_REFERENCE_PATTERN,
        card_payment=executor_module._CARD_PAYMENT_PATTERN,
        card_payment_target=executor_module._CARD_PAYMENT_TARGET_PATTERN,
        card_usage=executor_module._CARD_USAGE_PATTERN,
    )
    helper = components.ExecutorCreditCardHelper(
        db=db,
        account_resolver=resolver,
        patterns=patterns,
        action_result_cls=ActionResult,
        format_money=str,
    )

    result = helper.maybe_record_credit_card_payment(
        {
            "description": "payment to card",
            "amount": 120.0,
            "converted_amount": 120.0,
            "base_currency": "USD",
        }
    )
    assert isinstance(result, ActionResult)
    assert result.action == "none"
    assert "identify the credit card" in result.message


def test_credit_card_helper_unique_credit_purchase_resolves_card(db: Database) -> None:
    db.account.create("Visa", account_type="credit", opening_balance=-100.0, currency="USD")
    resolver = components.ExecutorAccountResolver(db)
    patterns = executor_module.CreditCardDetectionPatterns(
        has_card_reference=executor_module._CARD_REFERENCE_PATTERN,
        card_payment=executor_module._CARD_PAYMENT_PATTERN,
        card_payment_target=executor_module._CARD_PAYMENT_TARGET_PATTERN,
        card_usage=executor_module._CARD_USAGE_PATTERN,
    )
    helper = components.ExecutorCreditCardHelper(
        db=db,
        account_resolver=resolver,
        patterns=patterns,
        action_result_cls=ActionResult,
        format_money=str,
    )

    result = helper.resolve_expense_account({"account": None, "description": "bought with tarjeta"})
    assert isinstance(result, tuple)
    assert result[0] == "Visa"


def test_credit_card_helper_purchase_requires_specific_card_when_multiple(db: Database) -> None:
    db.account.create("Visa", account_type="credit", opening_balance=-100.0, currency="USD")
    db.account.create("Mastercard", account_type="credit", opening_balance=-150.0, currency="USD")
    resolver = components.ExecutorAccountResolver(db)
    patterns = executor_module.CreditCardDetectionPatterns(
        has_card_reference=executor_module._CARD_REFERENCE_PATTERN,
        card_payment=executor_module._CARD_PAYMENT_PATTERN,
        card_payment_target=executor_module._CARD_PAYMENT_TARGET_PATTERN,
        card_usage=executor_module._CARD_USAGE_PATTERN,
    )
    helper = components.ExecutorCreditCardHelper(
        db=db,
        account_resolver=resolver,
        patterns=patterns,
        action_result_cls=ActionResult,
        format_money=str,
    )

    result = helper.resolve_expense_account({"account": None, "description": "bought with tarjeta"})
    assert isinstance(result, ActionResult)
    assert result.action == "none"
    assert "which credit card" in result.message


def test_report_builder_period_range_presets() -> None:
    assert components.ExecutorReportBuilder.period_range(None)[2] == "this_month"
    assert components.ExecutorReportBuilder.period_range({"preset": "last_month"})[2] == "last_month"
    assert components.ExecutorReportBuilder.period_range({"preset": "last_week"})[2] == "last_week"
    assert components.ExecutorReportBuilder.period_range({"preset": "last_2_months"})[2] == "last_2_months"
    assert components.ExecutorReportBuilder.period_range({"preset": "last_3_months"})[2] == "last_3_months"
    assert components.ExecutorReportBuilder.period_range({"preset": "last_6_months"})[2] == "last_6_months"
    assert components.ExecutorReportBuilder.period_range({"preset": "all_time"})[2] == "all_time"
    assert components.ExecutorReportBuilder.period_range(
        {"preset": "custom", "from": "2026-01-01", "to": "2026-01-31"}
    ) == ("2026-01-01", "2026-01-31", "custom")


def test_transaction_recorder_add_income_uses_amount_when_converted_missing() -> None:
    fake_db = SimpleNamespace(
        transaction=SimpleNamespace(create=lambda **kwargs: kwargs),
        setting=SimpleNamespace(get=lambda key, default=None: "en"),
    )
    recorder = components.ExecutorTransactionRecorder(
        db=fake_db,
        action_result_cls=ActionResult,
        format_money=lambda amount: f"{amount:.2f}",
        account_resolver=SimpleNamespace(
            resolve_account=lambda requested, raw_text=None: ("Wallet", {"id": 1, "name": "Wallet"})
        ),
        category_resolver=SimpleNamespace(resolve_category=lambda action, cat_type: "Food"),
        credit_card_helper=SimpleNamespace(
            maybe_record_credit_card_payment=lambda action: None,
            resolve_expense_account=lambda action: ("Wallet", {"id": 1, "name": "Wallet"}),
        ),
    )

    result = recorder.add_income(
        {"amount": 100.0, "converted_amount": None, "description": "salary", "base_currency": "USD"}
    )
    assert result.success is True
    assert result.data["transaction"]["amount"] == 100.0
    assert result.data["transaction"]["category"] == "Food"


def test_transaction_recorder_add_income_raises_when_amount_missing() -> None:
    fake_db = SimpleNamespace(
        transaction=SimpleNamespace(create=lambda **kwargs: kwargs),
        setting=SimpleNamespace(get=lambda key, default=None: "en"),
    )
    recorder = components.ExecutorTransactionRecorder(
        db=fake_db,
        action_result_cls=ActionResult,
        format_money=lambda amount: f"{amount:.2f}",
        account_resolver=SimpleNamespace(
            resolve_account=lambda requested, raw_text=None: ("Wallet", {"id": 1, "name": "Wallet"})
        ),
        category_resolver=SimpleNamespace(resolve_category=lambda action, cat_type: "Food"),
        credit_card_helper=SimpleNamespace(
            maybe_record_credit_card_payment=lambda action: None,
            resolve_expense_account=lambda action: ("Wallet", {"id": 1, "name": "Wallet"}),
        ),
    )

    with pytest.raises(ValueError, match="income amount is required"):
        recorder.add_income({"description": "salary", "amount": None, "converted_amount": None})


def test_transaction_recorder_add_expense_uses_amount_when_converted_missing() -> None:
    fake_db = SimpleNamespace(
        transaction=SimpleNamespace(create=lambda **kwargs: kwargs),
        setting=SimpleNamespace(get=lambda key, default=None: "en"),
    )
    recorder = components.ExecutorTransactionRecorder(
        db=fake_db,
        action_result_cls=ActionResult,
        format_money=lambda amount: f"{amount:.2f}",
        account_resolver=SimpleNamespace(
            resolve_account=lambda requested, raw_text=None: ("Wallet", {"id": 1, "name": "Wallet"})
        ),
        category_resolver=SimpleNamespace(resolve_category=lambda action, cat_type: "Food"),
        credit_card_helper=SimpleNamespace(
            maybe_record_credit_card_payment=lambda action: None,
            resolve_expense_account=lambda action: ("Wallet", {"id": 1, "name": "Wallet"}),
        ),
    )

    result = recorder.add_expense(
        {"amount": 60.0, "converted_amount": None, "description": "coffee", "base_currency": "USD"}
    )
    assert result.success is True
    assert result.data["transaction"]["amount"] == 60.0
    assert result.data["transaction"]["category"] == "Food"


def test_transaction_recorder_add_expense_raises_when_amount_missing() -> None:
    fake_db = SimpleNamespace(
        transaction=SimpleNamespace(create=lambda **kwargs: kwargs),
        setting=SimpleNamespace(get=lambda key, default=None: "en"),
    )
    recorder = components.ExecutorTransactionRecorder(
        db=fake_db,
        action_result_cls=ActionResult,
        format_money=lambda amount: f"{amount:.2f}",
        account_resolver=SimpleNamespace(
            resolve_account=lambda requested, raw_text=None: ("Wallet", {"id": 1, "name": "Wallet"})
        ),
        category_resolver=SimpleNamespace(resolve_category=lambda action, cat_type: "Food"),
        credit_card_helper=SimpleNamespace(
            maybe_record_credit_card_payment=lambda action: None,
            resolve_expense_account=lambda action: ("Wallet", {"id": 1, "name": "Wallet"}),
        ),
    )

    with pytest.raises(ValueError, match="expense amount is required"):
        recorder.add_expense({"description": "coffee", "amount": None, "converted_amount": None})


def test_summary_tools_all_presets() -> None:
    today = date(2026, 4, 15)
    assert components.ExecutorSummaryTools.period_range(None, today=today)[2] == "this_month"
    assert components.ExecutorSummaryTools.period_range({"preset": "last_month"}, today=today)[2] == "last_month"
    assert components.ExecutorSummaryTools.period_range({"preset": "last_week"}, today=today)[2] == "last_week"
    assert components.ExecutorSummaryTools.period_range({"preset": "last_2_months"}, today=today)[2] == "last_2_months"
    assert components.ExecutorSummaryTools.period_range({"preset": "last_3_months"}, today=today)[2] == "last_3_months"
    assert components.ExecutorSummaryTools.period_range({"preset": "last_6_months"}, today=today)[2] == "last_6_months"
    assert components.ExecutorSummaryTools.period_range({"preset": "this_year"}, today=today)[2] == "this_year"
    assert components.ExecutorSummaryTools.period_range({"preset": "all_time"}, today=today)[2] == "all_time"
    assert components.ExecutorSummaryTools.period_range(
        {"preset": "custom", "from": "2026-01-01", "to": "2026-01-31"}, today=today
    ) == ("2026-01-01", "2026-01-31", "custom")


def test_resolve_expense_account_branches(db: Database) -> None:
    db.account.create("Visa", account_type="credit", opening_balance=-100.0, currency="USD")
    db.account.create("Mastercard", account_type="credit", opening_balance=-150.0, currency="USD")
    resolver = components.ExecutorAccountResolver(db)
    patterns = executor_module.CreditCardDetectionPatterns(
        has_card_reference=executor_module._CARD_REFERENCE_PATTERN,
        card_payment=executor_module._CARD_PAYMENT_PATTERN,
        card_payment_target=executor_module._CARD_PAYMENT_TARGET_PATTERN,
        card_usage=executor_module._CARD_USAGE_PATTERN,
    )
    helper = components.ExecutorCreditCardHelper(
        db=db,
        account_resolver=resolver,
        patterns=patterns,
        action_result_cls=ActionResult,
        format_money=str,
    )

    name, account = helper.resolve_expense_account({"account": "Visa", "description": None})
    assert name == "Visa"
    assert account["account_type"] == "credit"

    name, account = helper.resolve_expense_account({"account": None, "description": "charged with Visa"})
    assert name == "Visa"

    result = helper.resolve_expense_account({"account": None, "description": "charged with Visa Mastercard"})
    assert isinstance(result, ActionResult)
    assert result.action == "none"

    result = helper.resolve_expense_account({"account": None, "description": "bought using Visa"})
    assert isinstance(result, tuple)
    assert result[0] == "Visa"


def test_report_builder_period_range_and_filters(monkeypatch) -> None:
    class FakeDate(date):
        @classmethod
        def today(cls) -> date:
            return cls(2026, 4, 15)

    monkeypatch.setattr(components, "date", FakeDate)

    def fake_transaction_list(
        limit, tx_type, account_id, since_date, until_date, category, search, min_amount, max_amount
    ):
        transactions = [
            {"id": 1, "type": "income", "account_id": 1, "category": "food", "amount": 20, "description": "groceries"},
            {"id": 2, "type": "income", "account_id": 2, "category": "transport", "amount": 10, "description": "uber"},
            {"id": 3, "type": "expense", "account_id": 1, "category": "food", "amount": 5, "description": "snacks"},
        ]
        if tx_type is not None:
            transactions = [t for t in transactions if t["type"] == tx_type]
        if account_id is not None:
            transactions = [t for t in transactions if t["account_id"] == account_id]
        if category is not None:
            transactions = [t for t in transactions if t["category"] == category]
        if min_amount is not None:
            transactions = [t for t in transactions if t["amount"] >= min_amount]
        if max_amount is not None:
            transactions = [t for t in transactions if t["amount"] <= max_amount]
        return transactions

    fake_db = SimpleNamespace(
        setting=SimpleNamespace(get=lambda key, default=None: "en"),
        account=SimpleNamespace(
            find_by_name=lambda name: {
                "wallet": {"id": 1, "name": "wallet", "account_type": "bank", "balance": 100.0},
                "bank": {"id": 2, "name": "bank", "account_type": "bank", "balance": 50.0},
            }.get(name),
            list=lambda *_args, **_kwargs: [
                {"id": 1, "name": "wallet", "balance": 100.0},
                {"id": 2, "name": "bank", "balance": 50.0},
            ],
        ),
        transaction=SimpleNamespace(list=fake_transaction_list),
    )

    builder = components.ExecutorReportBuilder(
        fake_db,
        action_result_cls=ActionResult,
        compute_summary=lambda _db, txs: {
            "total_income": 30.0,
            "total_expenses": 5.0,
            "savings": 0.0,
            "net": 25.0,
        },
        format_money=lambda value: f"{value:.2f}",
    )

    result = builder.build_report(
        {
            "report_type": "incomes",
            "period": {"preset": "this_year"},
            "filters": {
                "categories": ["food", "transport"],
                "accounts": ["wallet", "bank"],
                "min_amount": 5,
                "max_amount": 20,
                "text": None,
            },
        }
    )

    assert result.success is True
    assert result.action == "report"
    assert result.data["report_type"] == "incomes"
    assert len(result.data["transactions"]) == 2
    assert "Report (incomes)" in result.message


def test_report_builder_period_range_defaults_and_summary_tools() -> None:
    assert components.ExecutorReportBuilder.period_range(None)[2] == "this_month"
    assert components.ExecutorReportBuilder.period_range({"preset": "this_year"})[2] == "this_year"

    start, end, preset = components.ExecutorSummaryTools.period_range(
        {"preset": "unsupported"}, today=date(2026, 4, 15)
    )
    assert preset == "this_month"
    assert start == "2026-04-01"
    assert end == "2026-04-15"
    assert components.ExecutorSummaryTools.format_money("1234.5") == "1,234.50"
