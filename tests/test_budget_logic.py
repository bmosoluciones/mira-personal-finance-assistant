# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

import pytest
from mira.db.database import Database


@pytest.fixture
def db(tmp_path):
    database = Database(path=tmp_path / "budget-logic.db")
    database.connect()
    database.setting.seed_initial_data(include_default_categories=True)
    yield database
    database.close()


def test_budget_creation_and_defaults(db):
    budget = db.budget.create("TEST-2026", 2026, currency="USD")
    assert budget["code"] == "TEST-2026"
    assert budget["year"] == 2026
    assert budget["is_default_year"] == 1

    # Create another one for same year
    budget2 = db.budget.create("TEST-2026-B", 2026, currency="USD")
    assert budget2["is_default_year"] == 0

    db.budget.set_default_for_year(int(budget2["id"]))
    assert db.budget.get(int(budget2["id"]))["is_default_year"] == 1
    assert db.budget.get(int(budget["id"]))["is_default_year"] == 0


def test_budget_matrix_and_amounts(db):
    budget = db.budget.create("M-2026", 2026)
    categories = db.category.list(cat_type="expense", include_savings=False)
    cat_id = int(categories[0]["id"])

    db.budget.upsert_amount(int(budget["id"]), cat_id, 2026, 1, 150.0)

    matrix = db.budget.get_matrix(int(budget["id"]))
    row = next((r for r in matrix["rows"] if r["category_id"] == cat_id), None)
    assert row is not None
    assert float(row["months"][0]) == 150.0
    assert float(matrix["totals"]["expense"][0]) == 150.0


def test_budget_comparison_granularity(db):
    budget = db.budget.create("COMP-2026", 2026)

    for gran in ["annual", "semiannual", "monthly", "quarterly"]:
        comp = db.budget.compare(int(budget["id"]), granularity=gran)
        assert comp["granularity"] == gran


def test_budget_tracking_and_reassignment(db):
    budget = db.budget.create("TRACK-2026", 2026)
    cats = db.category.list(cat_type="expense", include_savings=False)
    cat1 = int(cats[0]["id"])
    cat2 = int(cats[1]["id"])

    db.budget.upsert_amount(int(budget["id"]), cat1, 2026, 5, 200.0)
    db.budget.upsert_amount(int(budget["id"]), cat2, 2026, 5, 100.0)

    db.budget.reassign_monthly(int(budget["id"]), 2026, 5, cat1, cat2, 50.0)

    tracking = db.budget.get_monthly_tracking(int(budget["id"]), 2026, 5)
    r1 = next(r for r in tracking["rows"] if r["category_id"] == cat1)
    r2 = next(r for r in tracking["rows"] if r["category_id"] == cat2)

    assert float(r1["assigned"]) == 150.0
    assert float(r2["assigned"]) == 150.0


def test_budget_invalid_year_raises(db):
    with pytest.raises(Exception):
        db.budget.create("BAD", 1800)


def test_budget_duplicate_code_raises(db):
    db.budget.create("DUP", 2026)
    with pytest.raises(Exception):
        db.budget.create("DUP", 2027)


def test_budget_propose_logic(db):
    budget = db.budget.create("PROPOSE-2027", 2027, currency="USD")

    # We need transactions in 2026 to propose for 2027
    acc = db.account.get_default()
    cat = db.category.list(cat_type="expense", include_savings=False)[0]

    # Add transactions in at least 3 different months of 2026
    for month in [1, 2, 3]:
        db.transaction.create(
            account_id=int(acc["id"]),
            tx_type="expense",
            amount=120.0,
            category=cat["name"],
            tx_date=f"2026-{month:02d}-15",
        )

    res = db.budget.propose(int(budget["id"]))
    assert res["applied"] is True
    assert res["source_year"] == 2026

    matrix = db.budget.get_matrix(int(budget["id"]))
    row = next(r for r in matrix["rows"] if r["category_id"] == int(cat["id"]))
    # (120*3) / 12 = 30 per month
    assert float(row["months"][0]) == 30.0


def test_budget_delete_and_active_switching(db):
    b1 = db.budget.create("B1", 2026)
    db.budget.create("B2", 2026)

    db.setting.set("active_budget_code", "B1")
    db.budget.delete(int(b1["id"]))

    # Active budget code should be empty or switched
    assert db.setting.get("active_budget_code") == ""
    # Should have a new default for 2026
    assert db.budget.get_default_for_year(2026)["code"] == "B2"


def test_budget_execution_totals_with_currency_mismatch(db):
    budget = db.budget.create("CURR-2026", 2026, currency="USD")
    acc_usd = db.account.create("USD ACC", currency="USD")
    acc_nio = db.account.create("NIO ACC", currency="NIO")
    cat = db.category.list(cat_type="expense", include_savings=False)[0]

    db.transaction.create(
        account_id=acc_usd["id"], tx_type="expense", amount=10.0, category=cat["name"], tx_date="2026-01-01"
    )
    db.transaction.create(
        account_id=acc_nio["id"], tx_type="expense", amount=100.0, category=cat["name"], tx_date="2026-01-02"
    )

    # Comparison should only include USD
    comp = db.budget.compare(int(budget["id"]), granularity="annual")
    row = next(r for r in comp["rows"] if r["category_id"] == int(cat["id"]))
    assert float(row["annual_real"]) == 10.0
    assert comp["excluded_transactions"] >= 1
