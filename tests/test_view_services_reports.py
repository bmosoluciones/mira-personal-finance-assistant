# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from pathlib import Path

import pytest

from mira.app.view_services import ReportsViewService, ReportsViewStateBuilder
from mira.db.database import Database
from mira.db.errors import BudgetValidationError


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "view-services-reports.db")
    database.connect()
    database.setting.set("language", "en")
    yield database
    database.close()


def test_reports_view_service_build_state_from_transactions_aggregates_tags_and_categories(db: Database) -> None:
    service = ReportsViewService(db)
    account = db.account.create("Wallet", "bank", 0.0, "USD")
    category = db.category.create("Food", "expense")
    tag = db.tag.create("Home", color="#228833")

    tx = db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=30.0,
        description="Groceries",
        category=category["name"],
        tx_date="2026-03-10",
        note="",
    )
    db.tag.set_for_transaction(tx["id"], [int(tag["id"])])

    state = service.build_state_from_transactions([tx], year=2026)

    assert state.category_root_data["Food"] == pytest.approx(30.0)
    assert state.by_tag_amount["Home"] == pytest.approx(30.0)
    assert state.by_tag_count["Home"] == 1
    assert int(state.tags_by_tx[int(tx["id"])][0]["id"]) == int(tag["id"])
    assert state.account_balance_report["rows"]


def test_reports_view_service_load_report_state_builds_comparisons(db: Database) -> None:
    service = ReportsViewService(db)
    account = db.account.create("Wallet", "bank", 0.0, "USD")
    category = db.category.create("Food", "expense")

    db.transaction.create(
        account_id=account["id"],
        tx_type="income",
        amount=100.0,
        description="March income",
        category=None,
        tx_date="2026-03-05",
        note="",
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=40.0,
        description="March expense",
        category=category["name"],
        tx_date="2026-03-06",
        note="",
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="income",
        amount=60.0,
        description="February income",
        category=None,
        tx_date="2026-02-05",
        note="",
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=15.0,
        description="February expense",
        category=category["name"],
        tx_date="2026-02-06",
        note="",
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="income",
        amount=80.0,
        description="YoY income",
        category=None,
        tx_date="2025-03-05",
        note="",
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=10.0,
        description="YoY expense",
        category=category["name"],
        tx_date="2025-03-06",
        note="",
    )

    state = service.load_report_state(
        since="2026-03-01",
        until="2026-03-31",
        filters={
            "account_id": None,
            "tx_type": None,
            "category": None,
            "tag_id": None,
            "include_children": False,
        },
    )

    assert state.comparisons is not None
    assert state.comparisons.current["income"] == pytest.approx(100.0)
    assert state.comparisons.current["expense"] == pytest.approx(40.0)
    assert state.comparisons.previous["income"] == pytest.approx(60.0)
    assert state.comparisons.previous["expense"] == pytest.approx(15.0)
    assert state.comparisons.yoy["income"] == pytest.approx(80.0)
    assert state.comparisons.yoy["expense"] == pytest.approx(10.0)
    assert state.by_month["2026-03"]["income"] == pytest.approx(100.0)


def test_reports_view_service_load_budget_comparison_swallows_domain_errors(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    service = ReportsViewService(db)

    monkeypatch.setattr(db.budget, "get_default_for_year", lambda _year: {"id": 1})
    monkeypatch.setattr(
        db.budget,
        "compare",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(BudgetValidationError("invalid")),
    )

    assert service.load_budget_comparison(2026) is None


def test_reports_view_state_builder_shapes_sections_and_pagination(db: Database) -> None:
    service = ReportsViewService(db)
    builder = ReportsViewStateBuilder(db)

    db.setting.set("default_currency", "USD")
    account = db.account.create("Wallet", "bank", 125.5, "USD")
    food = db.category.create("Food", "expense")
    dining = db.category.create("Dining", "expense", parent_id=int(food["id"]))
    utilities = db.category.create("Utilities", "expense")
    home = db.tag.create("Home", color="#228833")

    db.transaction.create(
        account_id=account["id"],
        tx_type="income",
        amount=100.0,
        description="Salary",
        category=None,
        tx_date="2026-03-05",
        note="",
    )
    expense_one = db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=30.0,
        description="Groceries",
        category=dining["name"],
        subcategory="Restaurants",
        tx_date="2026-03-10",
        note="",
    )
    db.tag.set_for_transaction(int(expense_one["id"]), [int(home["id"])])
    db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=20.0,
        description="Power bill",
        category=utilities["name"],
        tx_date="2026-03-11",
        note="",
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="income",
        amount=60.0,
        description="Previous month income",
        category=None,
        tx_date="2026-02-05",
        note="",
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=15.0,
        description="Previous month expense",
        category=utilities["name"],
        tx_date="2026-02-06",
        note="",
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="income",
        amount=80.0,
        description="YoY income",
        category=None,
        tx_date="2025-03-05",
        note="",
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=10.0,
        description="YoY expense",
        category=utilities["name"],
        tx_date="2025-03-06",
        note="",
    )

    state = service.load_report_state(
        since="2026-03-01",
        until="2026-03-31",
        filters={
            "account_id": None,
            "tx_type": None,
            "category": None,
            "tag_id": None,
            "include_children": False,
        },
    )
    presentation = builder.build_state(state, category_drill_root=None, tx_page=0, tx_page_size=2)
    drilldown = builder.build_state(state, category_drill_root="Food", tx_page=1, tx_page_size=2)

    assert presentation.comparisons.previous_text.startswith("Vs prev")
    assert presentation.comparisons.yoy_text.startswith("Vs YoY")
    assert presentation.cash_flow.chart.line_series[0].points[-1][1] == pytest.approx(50.0)
    assert presentation.category.title == "Level: Parent categories"
    assert presentation.category.rows[0].cells[0].text == "Food"
    assert drilldown.category.back_enabled is True
    assert drilldown.category.rows[0].cells[0].text == "Dining › Restaurants"
    assert presentation.tag.matrix_headers[0] == "Tags"
    assert "Dining" in presentation.tag.matrix_headers
    assert presentation.budget.rows == ()
    assert "USD" in presentation.account_balance.summary_text
    assert any(row.cells[0].text == "Wallet" for row in presentation.account_balance.rows)
    assert presentation.transactions.page_text == "1/2"
    assert presentation.transactions.next_enabled is True
    assert drilldown.transactions.page_text == "2/2"
    assert drilldown.transactions.previous_enabled is True
    detail_labels = dict(drilldown.transactions.items[0].detail_fields)
    assert detail_labels["Account"] == "Wallet"
    assert "Amount" in detail_labels
