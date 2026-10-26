# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Integration tests for the full AI pipeline."""

from __future__ import annotations

import json

import pytest

from mira.ai.parser_engine import TransactionParserEngine
from mira.ai.pipeline import Pipeline
from mira.ai.validator import ValidationResult
from mira.db.database import Database
from mira.i18n import tr


@pytest.fixture
def db(tmp_path):
    d = Database(path=tmp_path / "pipeline_test.db")
    d.connect()
    yield d
    d.close()


@pytest.fixture
def pipeline(db):
    return Pipeline(db=db, engine=TransactionParserEngine())


class TestPipelineWithTransactionParserEngine:
    def test_income_command(self, pipeline, db):
        result = pipeline.process("I received my salary of 3000")
        assert result.success is True
        assert result.action == "add_income"
        txs = db.transaction.list(tx_type="income")
        assert any(t["amount"] == pytest.approx(3000.0) for t in txs)

    def test_expense_command(self, pipeline, db):
        result = pipeline.process("spent 50 on groceries")
        assert result.success is True
        assert result.action == "add_expense"
        txs = db.transaction.list(tx_type="expense")
        assert any(t["amount"] == pytest.approx(50.0) for t in txs)

    def test_spanish_expense_command(self, pipeline, db):
        result = pipeline.process("gaste 100 cordobas en comida")
        assert result.success is True
        assert result.action == "add_expense"
        txs = db.transaction.list(tx_type="expense")
        assert any(t["amount"] == pytest.approx(100.0) for t in txs)

    def test_income_typo_game_with_salary_context(self, pipeline, db):
        result = pipeline.process("Game mil cordobas en salario")
        assert result.success is True
        assert result.action == "add_income"
        txs = db.transaction.list(tx_type="income")
        assert any(t["amount"] == pytest.approx(1000.0) for t in txs)

    def test_report_command(self, pipeline, db):
        result = pipeline.process("report")
        assert result.success is True
        assert result.action == "report"

    def test_report_command_synonym(self, pipeline, db):
        result = pipeline.process("show me my finances")
        assert result.success is True
        assert result.action == "report"

    def test_unknown_command_returns_none(self, pipeline):
        result = pipeline.process("what is the weather today")
        assert result.action == "none"
        assert result.message == tr(
            "chat.none.generic",
            "en",
            default="Sorry, I did not understand your request. I can help you record income, expenses, or review your financial summary.",
        )

    def test_currency_normalisation_k_suffix(self, pipeline, db):
        result = pipeline.process("received 2k bonus")
        assert result.success is True
        assert result.action == "add_income"
        txs = db.transaction.list(tx_type="income")
        assert any(t["amount"] == pytest.approx(2000.0) for t in txs)

    def test_currency_normalisation_dollar_sign(self, pipeline, db):
        result = pipeline.process("spent $120 on electricity")
        assert result.success is True
        assert result.action == "add_expense"

    def test_pipeline_reflects_balance(self, pipeline, db):
        pipeline.process("received 1000 salary")
        pipeline.process("spent 200 on rent")
        default_acc = db.account.get_default()
        assert default_acc is not None
        assert default_acc["balance"] == pytest.approx(800.0)

    def test_prompt_transactions_use_explicit_account_when_provided(self, pipeline, db):
        db.account.create("savings", account_type="bank", opening_balance=0.0, currency="USD")
        result = pipeline.process("received 500 in savings account")
        assert result.success is True
        assert result.action == "add_income"

        savings = db.account.find_by_name("savings")

        assert savings is not None
        assert savings["balance"] == pytest.approx(500.0)

    def test_prompt_transactions_use_default_account_when_not_provided(self, pipeline, db):
        result = pipeline.process("received 300 salary")
        assert result.success is True
        assert result.action == "add_income"

        default_acc = db.account.get_default()
        assert default_acc is not None
        assert default_acc["balance"] == pytest.approx(300.0)

    def test_empty_input_handled(self, pipeline):
        result = pipeline.process("")
        # Should not crash; returns some result
        assert result is not None

    def test_engine_property(self, pipeline):
        assert isinstance(pipeline.engine, TransactionParserEngine)


class TestPipelineCreditAccounts:
    def test_credit_card_purchase_uses_credit_account(self, pipeline, db):
        visa = db.account.create("Visa", "credit", -300.0, "NIO")

        result = pipeline.process("gaste 120 en supermercado con visa")

        visa_after = db.account.get(visa["id"])
        txs = db.transaction.list(tx_type="expense")

        assert result.success is True
        assert result.action == "add_expense"
        assert visa_after["balance"] == pytest.approx(-420.0)
        assert any(int(tx["account_id"]) == int(visa["id"]) for tx in txs)

    @pytest.mark.parametrize(
        "prompt",
        [
            "pague 200 con visa platino",
            "pague 200 con visa",
            "pague 300 con la platino",
        ],
    )
    def test_credit_card_purchase_matches_existing_account_aliases(self, pipeline, db, prompt):
        visa = db.account.create("Tarjeta de Crédito Visa Platino", "credit", -300.0, "NIO")

        result = pipeline.process(prompt)

        visa_after = db.account.get(visa["id"])
        txs = db.transaction.list(tx_type="expense")

        assert result.success is True
        assert result.action == "add_expense"
        assert visa_after is not None
        assert any(int(tx["account_id"]) == int(visa["id"]) for tx in txs)
        assert (result.data or {}).get("account", {}).get("id") == visa["id"]

    def test_credit_card_payment_phrase_records_transfer(self, pipeline, db):
        bank = db.account.create("BAC", "bank", 1500.0, "NIO")
        credit = db.account.create("Visa", "credit", -1500.0, "NIO")

        result = pipeline.process("abone 1500 a visa desde bac")

        bank_after = db.account.get(bank["id"])
        credit_after = db.account.get(credit["id"])
        transfers = [tx for tx in db.transaction.list() if int(tx.get("is_transfer") or 0) == 1]
        summary = db.report.summary()

        assert result.success is True
        assert result.action == "add_expense"
        assert len(transfers) == 2
        assert bank_after["balance"] == pytest.approx(0.0)
        assert credit_after["balance"] == pytest.approx(0.0)
        assert float(summary["total_income"]) == pytest.approx(0.0)
        assert float(summary["total_expenses"]) == pytest.approx(0.0)

    def test_credit_card_payment_without_source_asks_for_clarification_when_ambiguous(self, pipeline, db):
        db.account.create("BAC", "bank", 800.0, "NIO")
        db.account.create("LAFISE", "bank", 900.0, "NIO")
        credit = db.account.create("Visa", "credit", -200.0, "NIO")
        db.account.set_default(credit["id"])

        result = pipeline.process("pague 100 a visa")

        assert result.success is True
        assert result.action == "none"


# ---------------------------------------------------------------------------
# New pipeline integration tests (Phase 3)
# ---------------------------------------------------------------------------


class TestPipelineNewCategories:
    def test_education_expense(self, pipeline, db):
        result = pipeline.process("spent 200 on tuition")
        assert result.success is True
        assert result.action == "add_expense"
        txs = db.transaction.list(tx_type="expense")
        assert any(t["amount"] == pytest.approx(200.0) for t in txs)

    def test_insurance_expense(self, pipeline, db):
        result = pipeline.process("paid 150 insurance premium")
        assert result.success is True
        assert result.action == "add_expense"
        txs = db.transaction.list(tx_type="expense")
        assert any(t["amount"] == pytest.approx(150.0) for t in txs)


class TestPipelinePortuguese:
    def test_recebi_income(self, pipeline, db):
        result = pipeline.process("recebi 500 de salário")
        assert result.success is True
        assert result.action == "add_income"
        txs = db.transaction.list(tx_type="income")
        assert any(t["amount"] == pytest.approx(500.0) for t in txs)

    def test_gastei_expense(self, pipeline, db):
        result = pipeline.process("gastei 30 em comida")
        assert result.success is True
        assert result.action == "add_expense"
        txs = db.transaction.list(tx_type="expense")
        assert any(t["amount"] == pytest.approx(30.0) for t in txs)


class TestPipelineNoneActions:
    def test_bare_number_not_recorded(self, pipeline, db):
        result = pipeline.process("5000")
        assert result.action == "none"
        # Nothing should be stored
        inc = db.transaction.list(tx_type="income")
        exp = db.transaction.list(tx_type="expense")
        assert len(inc) == 0
        assert len(exp) == 0

    def test_income_without_amount(self, pipeline):
        result = pipeline.process("recibí mi salario")
        assert result.action == "none"
        assert result.message is not None

    def test_expense_without_amount(self, pipeline):
        result = pipeline.process("gasté en comida")
        assert result.action == "none"
        assert result.message is not None


class _EngineParseError(TransactionParserEngine):
    def parse(self, _user_input: str):
        raise RuntimeError("boom")


class _EngineBadJson(TransactionParserEngine):
    def parse(self, _user_input: str):
        raise json.JSONDecodeError("bad json", "{}", 0)


class _EngineCriticalError(TransactionParserEngine):
    def parse(self, _user_input: str):
        raise AssertionError("critical failure")


def test_pipeline_falls_back_when_engine_parse_fails(db):
    pipeline = Pipeline(db=db, engine=_EngineParseError())
    result = pipeline.process("hola")
    assert result.success is False
    assert result.action == "none"
    assert result.message == tr(
        "chat.parser.error",
        "es",
        default=(
            "Disculpa, no pude procesar tu solicitud. "
            "Por favor intenta con algo como:\n"
            '  - "recibi 500 de salario"\n'
            '  - "gaste 30 en comida"\n'
            '  - "reporte"'
        ),
    )


def test_pipeline_falls_back_when_engine_parse_fails_in_english(db):
    db.setting.set("language", "en")
    pipeline = Pipeline(db=db, engine=_EngineParseError())
    result = pipeline.process("hello there")

    assert result.success is False
    assert result.action == "none"
    assert result.message == tr(
        "chat.parser.error",
        "en",
        default=(
            "Sorry, I couldn't process your request. "
            "Please try something like:\n"
            '  - "received 500 salary"\n'
            '  - "spent 30 on groceries"\n'
            '  - "report"'
        ),
    )


def test_pipeline_falls_back_when_engine_returns_invalid_json(db):
    pipeline = Pipeline(db=db, engine=_EngineBadJson())
    result = pipeline.process("hola")
    assert result.success is False
    assert result.action == "none"


def test_pipeline_falls_back_when_validation_fails(monkeypatch, db):
    pipeline = Pipeline(db=db, engine=TransactionParserEngine())
    monkeypatch.setattr(
        "mira.ai.pipeline.validate",
        lambda *_args, **_kwargs: ValidationResult(valid=False, action=None, error="invalid"),
    )
    result = pipeline.process("received 100 salary")
    assert result.success is False
    assert result.action == "none"


def test_pipeline_falls_back_when_executor_raises(monkeypatch, db):
    pipeline = Pipeline(db=db, engine=TransactionParserEngine())
    monkeypatch.setattr(pipeline._executor, "execute", lambda _action: (_ for _ in ()).throw(RuntimeError("db fail")))
    result = pipeline.process("received 100 salary")
    assert result.success is False
    assert result.action == "none"


def test_pipeline_process_raises_unexpected_parser_errors(db):
    pipeline = Pipeline(db=db, engine=_EngineCriticalError())

    with pytest.raises(AssertionError, match="critical failure"):
        pipeline.process("hola")


def test_pipeline_process_raises_unexpected_executor_errors(monkeypatch, db):
    pipeline = Pipeline(db=db, engine=TransactionParserEngine())
    monkeypatch.setattr(
        pipeline._executor,
        "execute",
        lambda _action: (_ for _ in ()).throw(AssertionError("critical executor failure")),
    )

    with pytest.raises(AssertionError, match="critical executor failure"):
        pipeline.process("received 100 salary")


def test_pipeline_shutdown_calls_engine_shutdown(db):
    class ShutdownEngine(TransactionParserEngine):
        def __init__(self) -> None:
            self.called = False

        def shutdown(self) -> None:
            self.called = True

    engine = ShutdownEngine()
    pipeline = Pipeline(db=db, engine=engine)
    pipeline.shutdown()
    assert engine.called is True


def test_pipeline_passes_default_currency_to_engine(tmp_path):
    """Pipeline auto-wires the DB default currency into TransactionParserEngine."""
    db = Database(path=tmp_path / "currency_test.db")
    db.connect()
    db.setting.set("default_currency", "NIO")

    pipeline = Pipeline(db=db)

    # "$" is used colloquially for córdobas in Nicaragua.  With NIO as the
    # default currency the broad USD "$" pattern must not trigger USD.
    # We test via the engine's parse() directly to inspect base_currency.
    parsed = pipeline.engine.parse("gasté $200 en comida")
    db.close()

    assert parsed["action"] == "add_expense"
    # base_currency should not be USD when default is NIO
    assert parsed.get("base_currency") != "USD"


def test_pipeline_reload_engine_refreshes_parser_default_currency(db: Database) -> None:
    db.setting.set("default_currency", "USD")
    pipeline = Pipeline(db=db)

    usd_parsed = pipeline.engine.parse("spent $120 on groceries")
    assert usd_parsed["base_currency"] == "USD"

    db.setting.set("default_currency", "NIO")
    pipeline.reload_engine()

    nio_parsed = pipeline.engine.parse("gasté $200 en comida")

    assert nio_parsed["action"] == "add_expense"
    assert nio_parsed.get("base_currency") != "USD"
