# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from pathlib import Path

import pytest

from mira.db.database import Database
from tests.db_inspection import fetch_one_dict, fetch_scalar


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "mira-realtime-insights.db")
    database.connect()
    database.setting.set("language", "es")
    yield database
    database.close()


def _seed_budget_for_march_2026(db: Database) -> tuple[dict, dict, dict, dict]:
    salary = db.category.get_or_create("Salario", "income")
    food = db.category.get_or_create("Alimentación", "expense")
    transport = db.category.get_or_create("Transporte", "expense")
    budget = db.budget.create("B2026", 2026, "NIO")
    db.budget.upsert_amount(int(budget["id"]), int(salary["id"]), 2026, 3, 1000.0)
    db.budget.upsert_amount(int(budget["id"]), int(food["id"]), 2026, 3, 300.0)
    db.budget.upsert_amount(int(budget["id"]), int(transport["id"]), 2026, 3, 200.0)
    return salary, food, transport, budget


def test_income_goal_crossing_emits_single_high_priority_insight(db: Database) -> None:
    acc = db.account.get_or_create("General")
    salary, _food, _transport, _budget = _seed_budget_for_march_2026(db)

    first = db.transaction.create(
        account_id=int(acc["id"]),
        tx_type="income",
        amount=850.0,
        category=str(salary["name"]),
        tx_date="2026-03-10",
    )
    assert first["mira_insight"] is not None
    assert first["mira_insight"]["code"] == "income_goal_80"

    second = db.transaction.create(
        account_id=int(acc["id"]),
        tx_type="income",
        amount=200.0,
        category=str(salary["name"]),
        tx_date="2026-03-15",
    )
    assert second["mira_achievement"] is not None
    assert second["mira_achievement"]["code"] == "achievement_income_goal_met"
    assert second["mira_insight"] is None


def test_expense_threshold_prioritizes_budget_over_warning(db: Database) -> None:
    acc = db.account.get_or_create("General")
    salary, food, _transport, _budget = _seed_budget_for_march_2026(db)

    db.transaction.create(
        account_id=int(acc["id"]),
        tx_type="income",
        amount=1200.0,
        category=str(salary["name"]),
        tx_date="2026-03-02",
    )

    tx = db.transaction.create(
        account_id=int(acc["id"]),
        tx_type="expense",
        amount=320.0,
        category=str(food["name"]),
        tx_date="2026-03-12",
    )

    assert tx["mira_insight"] is not None
    assert tx["mira_insight"]["code"] == "expense_category_100"


def test_unusual_expense_has_daily_cooldown(db: Database) -> None:
    acc = db.account.get_or_create("General")
    salary, _food, transport, budget = _seed_budget_for_march_2026(db)
    db.budget.upsert_amount(int(budget["id"]), int(transport["id"]), 2026, 3, 1000.0)

    db.transaction.create(
        account_id=int(acc["id"]),
        tx_type="income",
        amount=1100.0,
        category=str(salary["name"]),
        tx_date="2026-03-02",
    )
    db.transaction.create(
        account_id=int(acc["id"]),
        tx_type="expense",
        amount=40.0,
        category=str(transport["name"]),
        tx_date="2026-03-05",
    )

    first_unusual = db.transaction.create(
        account_id=int(acc["id"]),
        tx_type="expense",
        amount=120.0,
        category=str(transport["name"]),
        tx_date="2026-03-20",
    )
    second_unusual_same_day = db.transaction.create(
        account_id=int(acc["id"]),
        tx_type="expense",
        amount=130.0,
        category=str(transport["name"]),
        tx_date="2026-03-20",
    )

    assert first_unusual["mira_insight"] is not None
    assert first_unusual["mira_insight"]["code"] == "expense_unusual_high"
    assert second_unusual_same_day["mira_insight"] is None


def test_nl_transaction_counter_increments_on_each_assistant_transaction(
    db: Database,
) -> None:
    acc = db.account.get_or_create("General")
    salary = db.category.get_or_create("Salario", "income")

    assert db.feedback.get_achievement_counter("nl_transactions") == 0

    for day in ("2026-03-01", "2026-03-02", "2026-03-03"):
        db.transaction.create(
            account_id=int(acc["id"]),
            tx_type="income",
            amount=100.0,
            category=str(salary["name"]),
            tx_date=day,
            source="nl_assistant",
        )

    assert db.feedback.get_achievement_counter("nl_transactions") == 3


def test_increment_achievement_counter_returns_consistent_previous_and_current_values(
    db: Database,
) -> None:
    previous, current = db.feedback.increment_achievement_counter("nl_transactions", step=2)
    assert (previous, current) == (0, 2)

    previous, current = db.feedback.increment_achievement_counter("nl_transactions", step=3)
    assert (previous, current) == (2, 5)
    assert db.feedback.get_achievement_counter("nl_transactions") == 5


def test_achievement_counter_and_month_savings_use_orm_without_legacy_cursor_contract(
    db: Database,
) -> None:
    acc = db.account.get_or_create("General")
    savings = db.category.get_or_create("Ahorro Meta", "expense", is_savings=True)
    db.transaction.create(
        account_id=int(acc["id"]),
        tx_type="expense",
        amount=75.0,
        category=str(savings["name"]),
        tx_date="2026-03-11",
    )
    assert not hasattr(db._backend, "_cursor")

    previous, current = db.feedback.increment_achievement_counter("nl_transactions", step=2)
    assert (previous, current) == (0, 2)
    assert db.feedback.get_achievement_counter("nl_transactions") == 2
    assert db.feedback.month_savings_amount(2026, 3) == pytest.approx(75.0)


def test_increment_achievement_counter_rejects_non_positive_steps(db: Database) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        db.feedback.increment_achievement_counter("nl_transactions", step=0)
    with pytest.raises(ValueError, match="positive integer"):
        db.feedback.increment_achievement_counter("nl_transactions", step=-1)


def test_increment_achievement_counter_rejects_excessive_steps(db: Database) -> None:
    with pytest.raises(ValueError, match="step must be <="):
        db.feedback.increment_achievement_counter("nl_transactions", step=1_000_001)


def test_nl_transaction_milestone_is_emitted_when_threshold_is_crossed(
    db: Database,
) -> None:
    acc = db.account.get_or_create("General")
    food = db.category.get_or_create("Alimentación", "expense")
    db.feedback.increment_achievement_counter("nl_transactions", step=99)

    tx = db.transaction.create(
        account_id=int(acc["id"]),
        tx_type="expense",
        amount=35.0,
        category=str(food["name"]),
        tx_date="2026-03-20",
        source="nl_assistant",
    )

    assert tx["mira_achievement"] is not None
    assert tx["mira_achievement"]["code"] == "achievement_nl_transactions_100"
    assert db.feedback.get_achievement_counter("nl_transactions") == 100


def test_report_milestone_achievement_suppresses_regular_insight(db: Database) -> None:
    acc = db.account.get_or_create("General")
    salary, _food, _transport, _budget = _seed_budget_for_march_2026(db)
    db.feedback.increment_achievement_counter("mira_report_views", step=10)

    tx = db.transaction.create(
        account_id=int(acc["id"]),
        tx_type="income",
        amount=850.0,
        category=str(salary["name"]),
        tx_date="2026-03-10",
    )

    assert tx["mira_achievement"] is not None
    assert tx["mira_achievement"]["code"] == "achievement_mira_report_views_10"
    assert tx["mira_insight"] is None


def test_running_mira_report_updates_views_counter(db: Database) -> None:
    assert db.feedback.get_achievement_counter("mira_report_views") == 0
    db.report.get_mira_master_report(year=2026, month=3)
    assert db.feedback.get_achievement_counter("mira_report_views") == 1


def test_transaction_message_pipeline_persists_single_unified_message_event(
    db: Database,
) -> None:
    acc = db.account.get_or_create("General")
    salary, _food, _transport, _budget = _seed_budget_for_march_2026(db)
    db.feedback.increment_achievement_counter("mira_report_views", step=10)

    tx = db.transaction.create(
        account_id=int(acc["id"]),
        tx_type="income",
        amount=900.0,
        category=str(salary["name"]),
        tx_date="2026-03-10",
    )

    assert tx["mira_achievement"] is not None
    row = fetch_one_dict(
        db,
        "SELECT COUNT(*) AS total FROM message_events WHERE source_event_type = 'transaction' AND source_event_id = ?",
        (int(tx["id"]),),
    )
    assert int(row["total"]) == 1


def test_delete_transaction_keeps_message_events_as_historical_records(
    db: Database,
) -> None:
    acc = db.account.get_or_create("General")
    salary, _food, _transport, _budget = _seed_budget_for_march_2026(db)
    db.feedback.increment_achievement_counter("mira_report_views", step=10)

    tx = db.transaction.create(
        account_id=int(acc["id"]),
        tx_type="income",
        amount=900.0,
        category=str(salary["name"]),
        tx_date="2026-03-10",
    )
    db.transaction.delete(int(tx["id"]))

    row = fetch_one_dict(
        db,
        "SELECT COUNT(*) AS total FROM message_events WHERE source_event_type = 'transaction' AND source_event_id = ?",
        (int(tx["id"]),),
    )
    assert int(row["total"]) == 1


def test_update_transaction_keeps_message_events_as_historical_records_without_legacy_cursor_contract(
    db: Database,
) -> None:
    acc = db.account.get_or_create("General")
    salary, _food, _transport, _budget = _seed_budget_for_march_2026(db)
    db.feedback.increment_achievement_counter("mira_report_views", step=10)
    assert not hasattr(db._backend, "_cursor")

    tx = db.transaction.create(
        account_id=int(acc["id"]),
        tx_type="income",
        amount=900.0,
        category=str(salary["name"]),
        tx_date="2026-03-10",
    )

    db.transaction.update(
        int(tx["id"]),
        amount=950.0,
        description="Ingreso ajustado",
    )

    row = fetch_one_dict(
        db,
        "SELECT COUNT(*) AS total FROM message_events WHERE source_event_type = 'transaction' AND source_event_id = ?",
        (int(tx["id"]),),
    )
    assert int(row["total"]) == 1


def test_update_transaction_keeps_message_events_as_historical_records(
    db: Database,
) -> None:
    acc = db.account.get_or_create("General")
    salary, _food, _transport, _budget = _seed_budget_for_march_2026(db)
    db.feedback.increment_achievement_counter("mira_report_views", step=10)

    tx = db.transaction.create(
        account_id=int(acc["id"]),
        tx_type="income",
        amount=900.0,
        category=str(salary["name"]),
        tx_date="2026-03-10",
    )

    db.transaction.update(
        int(tx["id"]),
        amount=950.0,
        description="Ingreso ajustado",
    )

    total = fetch_scalar(
        db,
        "SELECT COUNT(*) AS total FROM message_events WHERE source_event_type = 'transaction' AND source_event_id = ?",
        (int(tx["id"]),),
    )
    assert int(total) == 1


def test_resolve_single_message_without_persistence_returns_candidate_only(
    db: Database,
) -> None:
    candidate = {
        "code": "test_candidate",
        "message_type": "daily_context",
        "message": "hola",
        "priority": 10,
        "counter_updates": [("savings_contributions", 1)],
        "cooldown_scope": "day",
    }
    selected = db.feedback.resolve_single_message(
        [candidate],
        source_event_type="app_start",
        source_event_id=None,
        period_key="2026-03",
        persist=False,
    )
    assert selected is not None
    assert selected["counter_updates"] == [("savings_contributions", 1)]
    assert selected["cooldown_scope"] == "day"
    row = fetch_one_dict(
        db,
        "SELECT COUNT(*) AS total FROM message_events WHERE message_code = 'test_candidate'",
    )
    assert int(row["total"]) == 0
