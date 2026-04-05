# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Pressure tests for natural-language credit-account resolution.

To extend this suite:
1. Add more rows to ``CREDIT_ACCOUNT_FIXTURES`` to seed extra credit accounts.
2. Add more rows to ``CREDIT_PROMPT_CASES`` to stress the resolver with new prompts.

The test body stays unchanged on purpose so it is easy to grow the catalog.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mira.ai.parser_engine import TransactionParserEngine
from mira.ai.pipeline import Pipeline
from mira.db.database import Database

# Add new credit accounts here. ``key`` is the stable identifier used by prompt cases.
CREDIT_ACCOUNT_FIXTURES = [
    {"key": "visa_platino", "name": "Tarjeta de Crédito Visa Platino", "currency": "USD"},
    {"key": "master_walmart", "name": "Mastercard Walmart Rewards", "currency": "NIO"},
    {"key": "amex_blue", "name": "American Express Blue Cash", "currency": "USD"},
    {"key": "lafise_premia", "name": "LAFISE Premia Black", "currency": "NIO"},
]


# Add new prompts here. Each case points to one of the seeded account ``key`` values above.
CREDIT_PROMPT_CASES = [
    {"id": "es_visa_platino_full", "prompt": "pague 200 con visa platino", "expected_account_key": "visa_platino"},
    {"id": "es_visa_token", "prompt": "pague 200 con visa", "expected_account_key": "visa_platino"},
    {"id": "es_platino_short", "prompt": "pague 300 con la platino", "expected_account_key": "visa_platino"},
    {
        "id": "es_walmart_rewards",
        "prompt": "pague 125 con la walmart rewards",
        "expected_account_key": "master_walmart",
    },
    {"id": "es_lafise_premia", "prompt": "pague 85 con lafise premia", "expected_account_key": "lafise_premia"},
    {"id": "en_blue_cash", "prompt": "I paid 35 with blue cash", "expected_account_key": "amex_blue"},
    {"id": "en_amex_blue", "prompt": "I paid 40 with amex blue", "expected_account_key": "amex_blue"},
    {
        "id": "en_mastercard_walmart",
        "prompt": "I paid 90 with the walmart rewards card",
        "expected_account_key": "master_walmart",
    },
    {"id": "en_lafise_black", "prompt": "I paid 55 with lafise black", "expected_account_key": "lafise_premia"},
]


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "credit-account-resolution.db")
    database.connect()
    yield database
    database.close()


@pytest.fixture
def pipeline(db: Database) -> Pipeline:
    return Pipeline(db=db, engine=TransactionParserEngine())


def _seed_credit_accounts(db: Database) -> dict[str, dict]:
    seeded: dict[str, dict] = {}
    db.account.create("Cuenta principal", "bank", 2500.0, "NIO")
    for fixture in CREDIT_ACCOUNT_FIXTURES:
        seeded[fixture["key"]] = db.account.create(
            fixture["name"],
            "credit",
            -100.0,
            fixture["currency"],
        )
    return seeded


@pytest.mark.parametrize("case", CREDIT_PROMPT_CASES, ids=[case["id"] for case in CREDIT_PROMPT_CASES])
def test_credit_account_prompts_resolve_seeded_credit_accounts(
    db: Database,
    pipeline: Pipeline,
    case: dict[str, str],
) -> None:
    accounts_by_key = _seed_credit_accounts(db)
    expected = accounts_by_key[case["expected_account_key"]]

    result = pipeline.process(case["prompt"])

    assert result.success is True
    assert result.action == "add_expense"
    resolved_account = (result.data or {}).get("account")
    assert resolved_account is not None
    assert int(resolved_account["id"]) == int(expected["id"])

    expenses = db.transaction.list(tx_type="expense")
    assert any(int(tx["account_id"]) == int(expected["id"]) for tx in expenses)
