# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from mira.db.database import Database


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "report-aggregates.db")
    database.connect()
    yield database
    database.close()


def test_report_exposes_summary_and_setting_surface_is_removed(db: Database) -> None:
    assert hasattr(db.report, "summarize_financials")
    assert not hasattr(db.setting, "summarize_financials")


def test_report_summarize_financials_uses_category_metadata(db: Database) -> None:
    account = db.account.get_or_create("General")
    salary = db.category.create("Salary", "income")
    food = db.category.create("Food", "expense")
    savings = db.category.create("Ahorro", "expense", is_savings=True)
    today = date.today().isoformat()

    db.transaction.create(
        account_id=account["id"],
        tx_type="income",
        amount=2500.0,
        description="Salary",
        category=salary["name"],
        category_id=salary["id"],
        tx_date=today,
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=300.0,
        description="Groceries",
        category=food["name"],
        category_id=food["id"],
        tx_date=today,
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=200.0,
        description="Savings",
        category=savings["name"],
        category_id=savings["id"],
        tx_date=today,
    )

    transactions = db.transaction.list(limit=10, since_date=today, until_date=today)
    summary = db.report.summarize_financials(transactions, as_dict=True)

    assert summary == {
        "income": 2500.0,
        "expense": 300.0,
        "savings": 200.0,
        "net": 2200.0,
    }


def test_report_tag_transaction_counts_group_in_sql(db: Database) -> None:
    account = db.account.get_or_create("General")
    home = db.tag.create("Home")
    work = db.tag.create("Work")
    old = db.tag.create("Old")
    today = date.today()
    last_month = today.replace(day=1) - timedelta(days=1)

    tx1 = db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=20.0,
        description="One",
        tx_date=today.isoformat(),
    )
    tx2 = db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=30.0,
        description="Two",
        tx_date=today.isoformat(),
    )
    tx3 = db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=40.0,
        description="Old",
        tx_date=last_month.isoformat(),
    )
    db.tag.set_for_transaction(tx1["id"], [home["id"], work["id"]])
    db.tag.set_for_transaction(tx2["id"], [home["id"]])
    db.tag.set_for_transaction(tx3["id"], [old["id"]])

    since = today.replace(day=1).isoformat()
    counts = db.report.tag_transaction_counts(since_date=since)

    assert counts[int(home["id"])] == 2
    assert counts[int(work["id"])] == 1
    assert int(old["id"]) not in counts


def test_report_category_transaction_counts_group_in_sql(db: Database) -> None:
    account = db.account.get_or_create("General")
    today = date.today()
    last_month = today.replace(day=1) - timedelta(days=1)

    db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=20.0,
        description="Groceries",
        category="Food",
        tx_date=today.isoformat(),
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=10.0,
        description="More groceries",
        category="Food",
        tx_date=today.isoformat(),
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="income",
        amount=100.0,
        description="Salary",
        category="Salary",
        tx_date=today.isoformat(),
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=5.0,
        description="Old groceries",
        category="Food",
        tx_date=last_month.isoformat(),
    )

    since = today.replace(day=1).isoformat()
    counts = db.report.category_transaction_counts(since_date=since)

    assert counts["Food"] == 2
    assert counts["Salary"] == 1


def test_report_aggregates_exclude_balance_adjustments(db: Database) -> None:
    account = db.account.create("Checking", "bank", 0.0, "USD")
    tag = db.tag.create("Recon", color="#224466")
    adjustment = db.transaction.record_balance_adjustment(account["id"], 150.0, tx_date="2026-04-01")
    db.tag.set_for_transaction(int(adjustment["id"]), [int(tag["id"])])

    transactions = db.transaction.list(limit=10, since_date="2026-04-01", until_date="2026-04-30")
    summary = db.report.summarize_financials(transactions, as_dict=True)
    tag_counts = db.report.tag_transaction_counts(since_date="2026-04-01", until_date="2026-04-30")
    category_counts = db.report.category_transaction_counts(since_date="2026-04-01", until_date="2026-04-30")

    assert summary == {
        "income": 0.0,
        "expense": 0.0,
        "savings": 0.0,
        "net": 0.0,
    }
    assert tag_counts == {}
    assert category_counts == {}


def test_report_summarize_financials_filtered_runs_in_sql_with_filters(db: Database) -> None:
    account = db.account.create("Checking", "bank", 0.0, "USD")
    income_category = db.category.create("Salary", "income")
    parent = db.category.create("Food", "expense")
    child = db.category.create("Dining", "expense", parent_id=int(parent["id"]))
    savings = db.category.create("Emergency", "expense", is_savings=True)
    tag = db.tag.create("Team lunch")

    tx_income = db.transaction.create(
        account_id=account["id"],
        tx_type="income",
        amount=500.0,
        description="Payroll",
        category=income_category["name"],
        tx_date="2026-03-01",
    )
    tx_expense = db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=120.0,
        description="Lunch",
        category=child["name"],
        tx_date="2026-03-02",
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=200.0,
        description="Transfer to savings",
        category=savings["name"],
        tx_date="2026-03-03",
    )
    db.tag.set_for_transaction(int(tx_expense["id"]), [int(tag["id"])])
    db.tag.set_for_transaction(int(tx_income["id"]), [int(tag["id"])])

    summary = db.report.summarize_financials_filtered(
        account_id=int(account["id"]),
        since_date="2026-03-01",
        until_date="2026-03-31",
        category=parent["name"],
        include_children=True,
        tag_id=int(tag["id"]),
    )

    assert summary == {
        "income": 0.0,
        "expense": 120.0,
        "net": -120.0,
    }
