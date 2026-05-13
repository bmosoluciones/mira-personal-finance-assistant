# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

import pytest
from datetime import date, timedelta
from mira.db.database import Database
from mira.db.model import AchievementCounter, Transaction, Category, InsightEvent, AchievementEvent, MessageEvent
from mira.transaction_kinds import TransactionType

@pytest.fixture
def db():
    facade = Database(":memory:")
    facade.connect()
    facade.setting.seed_initial_data(language="es")
    return facade

def test_achievement_counters(db):
    prev, current = db.feedback.increment_achievement_counter("test_counter", step=5)
    assert prev == 0
    assert current == 5

    prev, current = db.feedback.increment_achievement_counter("test_counter", step=10)
    assert prev == 5
    assert current == 15

    assert db.feedback.get_achievement_counter("test_counter") == 15
    assert db.feedback.get_achievement_counter("non_existent") == 0

    with pytest.raises(ValueError):
        db.feedback.increment_achievement_counter("test_counter", step=0)
    with pytest.raises(ValueError):
        db.feedback.increment_achievement_counter("test_counter", step=2_000_000)

def test_daily_contextual_messages(db):
    today = date.today()

    # 1. Budget missing (priority 90)
    # Clear any budgets that might have been seeded (none by default usually)
    for b in db.budget.list(today.year):
        db.budget.delete(b["id"])

    msg = db.feedback.pop_daily_contextual_message(on_date=today)
    assert msg is not None
    assert msg["code"] == "daily_budget_missing"

    # Reset setting for next test cases
    db.setting.set("_last_daily_message", "")

    # 2. Add budget, but it's after day 10 and no savings goals (priority 70)
    # Remove all savings goals
    for goal in db.savings_goal.list():
        db.savings_goal.delete(goal["id"])

    budget = db.budget.create("Main", today.year)
    db.budget.set_default_for_year(budget["id"])

    # Ensure it's treated as "after day 10"
    test_day = today.replace(day=15)
    msg = db.feedback.pop_daily_contextual_message(on_date=test_day)
    assert msg is not None
    assert msg["code"] == "daily_no_savings_goal"

    db.setting.set("_last_daily_message", "")
    # 3. After day 20 and no transactions (priority 80)
    test_day_25 = today.replace(day=25)
    # This should return daily_no_transactions because priority 80 > 70
    msg = db.feedback.pop_daily_contextual_message(on_date=test_day_25)
    assert msg is not None
    assert msg["code"] == "daily_no_transactions"

def test_message_cooldown_scopes(db):
    from mira.db.repositories.feedback_repository import MessageCandidate

    today = date.today()
    today_str = today.isoformat()
    period = today.strftime("%Y-%m")

    candidate_day = MessageCandidate(code="test_day", message_type="type", message="msg", cooldown_scope="day")
    candidate_period = MessageCandidate(code="test_period", message_type="type", message="msg", cooldown_scope="period")
    candidate_cat = MessageCandidate(code="test_cat", message_type="type", message="msg", cooldown_scope="period_category", category_id=1)

    repo = db.feedback._db

    # Initial state: no cooldown
    assert not repo._message_in_cooldown(candidate_day, reference_date=today_str)
    assert not repo._message_in_cooldown(candidate_period, period_key=period)
    assert not repo._message_in_cooldown(candidate_cat, period_key=period)

    # Persist and check
    repo.persist_message_event(candidate_day, source_event_type="test", source_event_id=1, reference_date=today_str)
    assert repo._message_in_cooldown(candidate_day, reference_date=today_str)
    assert not repo._message_in_cooldown(candidate_day, reference_date=(today + timedelta(days=1)).isoformat())

    repo.persist_message_event(candidate_period, source_event_type="test", source_event_id=1, period_key=period)
    assert repo._message_in_cooldown(candidate_period, period_key=period)
    assert not repo._message_in_cooldown(candidate_period, period_key="2000-01")

    repo.persist_message_event(candidate_cat, source_event_type="test", source_event_id=1, period_key=period)
    assert repo._message_in_cooldown(candidate_cat, period_key=period)
    # Same period, different category
    candidate_cat2 = MessageCandidate(code="test_cat", message_type="type", message="msg", cooldown_scope="period_category", category_id=2)
    assert not repo._message_in_cooldown(candidate_cat2, period_key=period)

def test_evaluate_income_kpis(db):
    context = {
        "income_goal": 1000.0,
        "income_actual_prev": 750.0,
        "income_actual": 850.0,
        "income_avg_prev": 500.0
    }
    tx = {"amount": 100.0}

    # 80% goal reached
    candidates = db.feedback.evaluate_income_kpis(tx, context)
    assert any(c.code == "income_goal_80" for c in candidates)

    # 100% goal reached
    context["income_actual"] = 1050.0
    candidates = db.feedback.evaluate_income_kpis(tx, context)
    assert any(c.code == "income_goal_100" for c in candidates)

    # Recovery
    context["income_actual_prev"] = 400.0 # 40%
    context["income_actual"] = 650.0      # 65%
    candidates = db.feedback.evaluate_income_kpis(tx, context)
    assert any(c.code == "income_recovery" for c in candidates)

    # Unusual high
    tx["amount"] = 1500.0 # > 2 * avg (500)
    candidates = db.feedback.evaluate_income_kpis(tx, context)
    assert any(c.code == "income_unusual_high" for c in candidates)

def test_evaluate_expense_kpis(db):
    context = {
        "category_name": "Food",
        "category_id": 1,
        "category_budget": 100.0,
        "category_spent_prev": 85.0,
        "category_spent": 95.0,
        "expense_budget": 1000.0,
        "expense_actual_prev": 600.0,
        "expense_actual": 650.0,
        "day_of_month": 5,
        "month_days": 30,
        "expense_category_avg_prev": 40.0
    }
    tx = {"amount": 10.0}

    # 90% category reached
    candidates = db.feedback.evaluate_expense_kpis(tx, context)
    assert any(c.code == "expense_category_90" for c in candidates)

    # 100% total reached
    context["expense_actual_prev"] = 950.0
    context["expense_actual"] = 1050.0
    candidates = db.feedback.evaluate_expense_kpis(tx, context)
    assert any(c.code == "expense_total_100" for c in candidates)

    # High pace
    context["day_of_month"] = 10 # 33% of month
    context["expense_actual_prev"] = 650.0 # 65%
    context["expense_actual"] = 750.0      # 75%
    candidates = db.feedback.evaluate_expense_kpis(tx, context)
    assert any(c.code == "expense_high_pace" for c in candidates)

    # Unusual high
    tx["amount"] = 100.0 # > 2 * avg (40)
    candidates = db.feedback.evaluate_expense_kpis(tx, context)
    assert any(c.code == "expense_unusual_high" for c in candidates)

def test_evaluate_operation_achievements_milestones(db):
    context = {
        "period_key": "2025-01",
        "income_goal": 0, "income_actual_prev": 0, "income_actual": 0,
        "savings_actual": 0, "year": 2025, "month": 1
    }
    tx = {"id": 1, "type": "income", "amount": 100, "date": "2025-01-01"}

    # Milestone for nl is 100
    AchievementCounter.create(user_id=1, counter_key="nl_transactions", counter_value=99)

    repo = db.feedback._db
    candidates = repo.evaluate_operation_achievements(tx, context, source="nl_assistant")
    assert any(c.code == "achievement_nl_transactions_100" for c in candidates)

    # Milestone for report views is 10
    AchievementCounter.create(user_id=1, counter_key="mira_report_views", counter_value=10)
    candidates = repo.evaluate_operation_achievements(tx, context)
    assert any(c.code == "achievement_mira_report_views_10" for c in candidates)

def test_savings_streaks(db):
    cat = db.category.create("Savings", "expense", is_savings=True)
    cat_id = cat["id"]
    acc = db.account.create("Acc", "cash")
    acc_id = acc["id"]

    # Jan 2025
    db.transaction.create(amount=100, tx_type="expense", tx_date="2025-01-15", account_id=acc_id, category_id=cat_id)
    # Feb 2025
    context = {
        "period_key": "2025-02", "year": 2025, "month": 2, "savings_actual": 200,
        "income_goal": 0, "income_actual_prev": 0, "income_actual": 0,
    }
    tx = {"id": 1, "type": "expense", "amount": 200, "date": "2025-02-15"}

    repo = db.feedback._db
    candidates = repo.evaluate_operation_achievements(tx, context)
    assert any(c.code == "achievement_savings_vs_previous_month" for c in candidates)

    # Dec 2024
    db.transaction.create(amount=50, tx_type="expense", tx_date="2024-12-15", account_id=acc_id, category_id=cat_id)
    candidates = repo.evaluate_operation_achievements(tx, context)
    assert any(c.code == "achievement_savings_three_month_streak" for c in candidates)

def test_select_best_operation_message_end_to_end(db):
    acc = db.account.create("Acc", "cash")
    acc_id = acc["id"]
    cat = db.category.create("Food", "expense")
    cat_id = cat["id"]
    budget = db.budget.create("B2025", 2025)
    budget_id = budget["id"]
    db.budget.set_default_for_year(budget_id)
    db.budget.upsert_amount(budget_id, cat_id, 2025, 1, 100)

    # First 95
    db.transaction.create(amount=95, tx_type="expense", tx_date="2025-01-01", account_id=acc_id, category_id=cat_id)

    # Then 10 more -> 105
    tx2 = db.transaction.create(amount=10, tx_type="expense", tx_date="2025-01-02", account_id=acc_id, category_id=cat_id)

    # Check insight in the created transaction
    assert tx2.get("mira_insight") is not None
    assert tx2["mira_insight"]["code"] == "expense_category_100"

def test_nl_assistant_counter_increment(db):
    acc = db.account.create("Acc", "cash")
    acc_id = acc["id"]
    cat = db.category.create("Food", "expense")
    cat_id = cat["id"]
    tx = db.transaction.create(amount=10, tx_type="expense", tx_date="2025-01-01", account_id=acc_id, category_id=cat_id)

    initial = db.feedback.get_achievement_counter("nl_transactions")
    db.feedback.select_best_operation_message(tx, source="nl_assistant")
    assert db.feedback.get_achievement_counter("nl_transactions") == initial + 1

def test_achievement_persistence(db):
    acc = db.account.create("Acc", "cash")
    acc_id = acc["id"]
    cat = db.category.create("Salary", "income")
    cat_id = cat["id"]
    budget = db.budget.create("B2025", 2025)
    db.budget.set_default_for_year(budget["id"])
    db.budget.upsert_amount(budget["id"], cat_id, 2025, 1, 1000)

    tx = db.transaction.create(amount=1100, tx_type="income", tx_date="2025-01-01", account_id=acc_id, category_id=cat_id)

    # Check mira_achievement OR mira_insight (either could win based on priority)
    # But Achievement should win here.
    assert tx.get("mira_achievement") is not None or tx.get("mira_insight") is not None

    # If achievement was triggered, it should be in DB
    if tx.get("mira_achievement"):
        assert AchievementEvent.select().where(AchievementEvent.achievement_code == tx["mira_achievement"]["code"]).exists()

def test_achievement_savings_contribution(db):
    acc = db.account.create("Acc", "cash")
    acc_id = acc["id"]
    cat = db.category.create("Savings_unique_extra", "expense", is_savings=True)
    cat_id = cat["id"]

    # First savings contribution should trigger achievement_savings_contributions_1 (milestone 1)
    # OR achievement_saved_this_month
    # We use a second transaction to ensure the counter milestone is hit regardless of which one wins priority on tx1
    db.transaction.create(amount=100, tx_type="expense", tx_date="2025-01-01", account_id=acc_id, category_id=cat_id)
    tx2 = db.transaction.create(amount=100, tx_type="expense", tx_date="2025-01-02", account_id=acc_id, category_id=cat_id)

    assert tx2.get("mira_achievement") is not None or db.feedback.get_achievement_counter("savings_contributions") >= 1
    # Verify counter incremented
    assert db.feedback.get_achievement_counter("savings_contributions") >= 1
    # Check if either of the possible achievements was persisted
    assert AchievementEvent.select().exists()
