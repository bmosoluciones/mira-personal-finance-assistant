# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import pytest
from datetime import date

from mira.db.database import Database
from tests.db_inspection import execute_sql
from mira.reports.mira_master import _project_next_value, _stddev, shift_month


def test_stddev_handles_empty_and_non_empty_series() -> None:
    assert _stddev([]) is None
    assert _stddev([10.0]) == 0.0
    assert _stddev([1.0, 3.0]) == pytest.approx(1.0)


def test_project_next_value_handles_empty_and_linear_series() -> None:
    assert _project_next_value([]) is None
    assert _project_next_value([5.0]) == 5.0
    assert _project_next_value([10.0, 13.0, 16.0]) == pytest.approx(19.0)


@pytest.fixture
def db(tmp_path):
    d = Database(path=tmp_path / "test.db")
    d.connect()
    d.setting.set("language", "es")
    yield d
    d.close()


def _seed_categories_for_mira(db: Database) -> None:
    db.category.get_or_create("Salario", "income", color="#4EC9B0")
    db.category.get_or_create("Reembolso", "income", color="#86A9FF")
    housing_parent = db.category.get_or_create("Vivienda", "expense", color="#F48771")
    db.category.get_or_create("Alquiler", "expense", color="#F48771", parent_id=int(housing_parent["id"]))
    db.category.get_or_create("Comida", "expense", color="#E9C46A")
    db.category.get_or_create("Pago Tarjeta", "expense", color="#E76F51")
    db.category.get_or_create("Ahorro Meta", "expense", color="#4EC9B0", is_savings=True)


def test_controlled_dataset_exact_kpis_and_balance(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=1000,
        category="Salario",
        tx_date="2025-03-02",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=300,
        category="Alquiler",
        tx_date="2025-03-04",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=100,
        category="Comida",
        tx_date="2025-03-08",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=50,
        category="Ahorro Meta",
        tx_date="2025-03-10",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)

    assert payload["kpis"]["income"] == 1000.0
    assert payload["kpis"]["expense_operational"] == 400.0
    assert payload["kpis"]["savings"] == 50.0
    assert payload["kpis"]["net"] == 600.0
    assert payload["metrics"]["daily_living_cost"] == pytest.approx(12.9, abs=0.01)
    assert payload["metrics"]["freedom_margin"]["pct"] == pytest.approx(60.0)
    assert payload["waterfall"]["summary"]["status"] == "surplus"
    assert payload["waterfall"]["summary"]["savings_allocation"] == 0.0
    assert payload["waterfall"]["summary"]["final_balance"] == 600.0
    assert payload["waterfall"]["steps"][0]["label"] == "Ingreso total neto"
    assert payload["waterfall"]["steps"][-1]["label"] == "Balance del mes"
    assert payload["waterfall"]["steps"][-1]["kind"] == "month_balance"
    assert payload["waterfall"]["steps"][-1]["value"] == 600.0
    assert all(step["label"] != "Superávit mensual" for step in payload["waterfall"]["steps"])
    assert all(step["label"] != "Ahorro asignado" for step in payload["waterfall"]["steps"])


def test_mira_master_report_preserves_fractional_cents_with_integer_storage(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=1000.10,
        category="Salario",
        tx_date="2025-03-02",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=300.20,
        category="Alquiler",
        tx_date="2025-03-04",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=50.15,
        category="Ahorro Meta",
        tx_date="2025-03-10",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)

    assert payload["kpis"]["income"] == pytest.approx(1000.10)
    assert payload["kpis"]["expense_operational"] == pytest.approx(300.20)
    assert payload["kpis"]["savings"] == pytest.approx(50.15)
    assert payload["kpis"]["net"] == pytest.approx(699.90)
    assert payload["waterfall"]["summary"]["final_balance"] == pytest.approx(699.90)


def test_internal_transfers_are_excluded(db: Database):
    _seed_categories_for_mira(db)
    src = db.account.get_or_create("General")
    dst = db.account.get_or_create("Ahorros")
    db.transaction.create(
        account_id=src["id"],
        tx_type="income",
        amount=1000,
        category="Salario",
        tx_date="2025-03-02",
    )
    db.transaction.transfer_between_accounts(
        from_account_id=src["id"],
        to_account_id=dst["id"],
        amount=200,
        tx_date="2025-03-03",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    assert payload["kpis"]["income"] == 1000.0
    assert payload["kpis"]["expense_operational"] == 0.0


def test_balance_adjustments_are_excluded_from_mira_master_kpis(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")
    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=1000,
        category="Salario",
        tx_date="2025-03-02",
    )
    db.transaction.record_balance_adjustment(acc["id"], 250.0, tx_date="2025-03-03")

    payload = db.report.get_mira_master_report(year=2025, month=3)

    assert payload["kpis"]["income"] == 1000.0
    assert payload["kpis"]["expense_operational"] == 0.0
    assert payload["kpis"]["net"] == 1000.0


def test_budget_period_snapshot_uses_orm_without_legacy_cursor_contract(
    db: Database,
) -> None:
    year = date.today().year
    _seed_categories_for_mira(db)
    budget = db.budget.create(code=f"PLAN-{year}", year=year)
    salary = db.category.get_or_create("Salario", "income", color="#4EC9B0")
    food = db.category.get_or_create("Comida", "expense", color="#E9C46A")
    savings = db.category.get_or_create("Ahorro Meta", "expense", color="#4EC9B0", is_savings=True)
    db.budget.upsert_amount(int(budget["id"]), int(salary["id"]), year, 3, 1000.0)
    db.budget.upsert_amount(int(budget["id"]), int(food["id"]), year, 3, 300.0)
    db.budget.upsert_amount(int(budget["id"]), int(savings["id"]), year, 3, 200.0)
    assert not hasattr(db._backend, "_cursor")

    active_budget, grouped, rows = db.report.budget_period_snapshot(year, 3)

    assert active_budget is not None
    assert grouped is not None
    assert grouped["income"]["Salario"] == 1000.0
    assert grouped["expense"]["Comida"] == 300.0
    assert rows is not None
    assert len(rows) >= 3


def test_refund_and_debt_are_tracked_as_context_with_canonical_kpis(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=800,
        category="Salario",
        tx_date="2025-03-01",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=300,
        category="Comida",
        tx_date="2025-03-05",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=100,
        category="Reembolso",
        description="Reembolso supermercado",
        tx_date="2025-03-06",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=200,
        category="Pago Tarjeta",
        tx_date="2025-03-07",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    messages = {item["code"]: item["text"] for item in payload["advisor"]["messages"]}

    assert payload["kpis"]["income"] == 900.0
    assert payload["kpis"]["expense_operational"] == 500.0
    assert payload["kpis"]["debt_payment"] == 200.0
    assert payload["kpis"]["refunds"] == 100.0
    assert payload["kpis"]["net"] == 400.0
    assert payload["metrics"]["debt_payment_income_pct"] == pytest.approx(22.22, abs=0.01)
    assert payload["metrics"]["debt_payment_expense_pct"] == pytest.approx(40.0)
    assert (
        messages["credit_debt_load"]
        == "Los pagos de tarjetas de crédito y deuda sumaron 200.00. Equivalen al 22.2% de tus ingresos y al 40.0% de tus gastos operativos."
    )


def test_credit_card_spending_vs_internal_payments_warns_about_possible_indebtedness(
    db: Database,
):
    _seed_categories_for_mira(db)
    bank = db.account.create("Banco Principal", "bank", 1000.0, "NIO")
    credit = db.account.create("Visa", "credit", -300.0, "NIO")
    execute_sql(
        db,
        "UPDATE accounts SET created_at = '2025-03-01 00:00:00' WHERE id IN (?, ?)",
        (bank["id"], credit["id"]),
    )

    db.transaction.create(
        account_id=bank["id"],
        tx_type="income",
        amount=1200,
        category="Salario",
        tx_date="2025-03-01",
    )
    db.transaction.create(
        account_id=credit["id"],
        tx_type="expense",
        amount=120,
        category="Comida",
        tx_date="2025-03-05",
    )
    db.transaction.create(
        account_id=credit["id"],
        tx_type="expense",
        amount=80,
        category="Comida",
        tx_date="2025-03-09",
    )
    db.transaction.record_credit_card_payment(bank["id"], credit["id"], 150, tx_date="2025-03-20")

    payload = db.report.get_mira_master_report(year=2025, month=3)
    messages = {item["code"]: item["text"] for item in payload["advisor"]["messages"]}

    assert payload["metrics"]["credit_card_expense_count"] == 2
    assert payload["metrics"]["credit_card_expense_amount"] == pytest.approx(200.0)
    assert payload["metrics"]["credit_card_payment_count"] == 1
    assert payload["metrics"]["credit_card_payment_amount"] == pytest.approx(150.0)
    assert payload["metrics"]["credit_card_gap_amount"] == pytest.approx(50.0)
    assert messages["credit_card_usage_vs_payments"] == (
        "En tarjetas de crédito registraste 2 gasto(s) por 200.00 y 1 pago(s) internos por 150.00. "
        "Como los gastos superan los pagos, hay señal de posible endeudamiento por 50.00."
    )


def test_credit_debt_message_respects_selected_language(db: Database):
    db.setting.set("language", "en")
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=1000,
        category="Salario",
        tx_date="2025-03-01",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=250,
        category="Pago Tarjeta",
        tx_date="2025-03-05",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    messages = {item["code"]: item["text"] for item in payload["advisor"]["messages"]}

    assert messages["credit_debt_load"] == (
        "Credit card and debt payments totaled 250.00. "
        "They equal 25.0% of your income and 100.0% of your operating expenses."
    )


def test_waterfall_adds_financing_bridge_when_month_has_deficit(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=500,
        category="Salario",
        tx_date="2025-03-01",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=350,
        category="Alquiler",
        tx_date="2025-03-02",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=250,
        category="Comida",
        tx_date="2025-03-03",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    waterfall = payload["waterfall"]

    assert payload["kpis"]["net"] == -100.0
    assert waterfall["summary"]["status"] == "deficit"
    assert waterfall["summary"]["financing_amount"] == 100.0
    assert waterfall["summary"]["final_balance"] == 0.0
    assert any(step["label"] == "Deuda / uso de ahorro" and step["value"] == 100.0 for step in waterfall["steps"])
    assert waterfall["steps"][-1]["label"] == "Deuda / uso de ahorro"
    assert waterfall["steps"][-1]["value"] == 100.0
    assert all(step["kind"] != "deficit_total" for step in waterfall["steps"])
    assert all(step["kind"] != "final_total" for step in waterfall["steps"])


def test_waterfall_keeps_balanced_month_closing_at_zero_without_extra_steps(
    db: Database,
):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=500,
        category="Salario",
        tx_date="2025-03-01",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=300,
        category="Alquiler",
        tx_date="2025-03-02",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=200,
        category="Comida",
        tx_date="2025-03-03",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    waterfall = payload["waterfall"]

    assert payload["kpis"]["net"] == 0.0
    assert waterfall["summary"]["status"] == "balanced"
    assert waterfall["summary"]["final_balance"] == 0.0
    assert waterfall["steps"][-1]["label"] == "Cierre del flujo mensual"
    assert waterfall["steps"][-1]["value"] == 0.0
    assert all(step["kind"] != "financing" for step in waterfall["steps"])
    assert all(step["kind"] != "month_balance" for step in waterfall["steps"])


def test_waterfall_groups_minor_categories_into_other_expenses(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=5000,
        category="Salario",
        tx_date="2025-03-01",
    )
    for idx in range(7):
        category = db.category.get_or_create(f"Gasto {idx + 1}", "expense", color="#888888")
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=100 + idx,
            category=str(category["name"]),
            tx_date=f"2025-03-{idx + 2:02d}",
        )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    waterfall = payload["waterfall"]

    grouped_step = next(step for step in waterfall["steps"] if step["label"] == "Otros gastos")
    assert grouped_step["value"] == -100.0
    assert grouped_step["is_grouped"] is True
    assert waterfall["summary"]["expense_categories_count"] == 7
    assert waterfall["summary"]["displayed_expense_categories_count"] == 6
    assert waterfall["summary"]["displayed_expense_steps_count"] == 7
    assert waterfall["summary"]["grouped_other_expenses_count"] == 1
    assert waterfall["summary"]["has_grouped_other_expenses"] is True


def test_waterfall_routes_expense_transactions_using_income_categories_to_inconsistent_bucket(
    db: Database,
):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=1000,
        category="Salario",
        tx_date="2025-03-01",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=250,
        category="Comida",
        tx_date="2025-03-02",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=150,
        category="Reembolso",
        tx_date="2025-03-03",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    waterfall_labels = [step["label"] for step in payload["waterfall"]["steps"]]
    waterfall_values = {step["label"]: step["value"] for step in payload["waterfall"]["steps"]}

    assert payload["kpis"]["expense_operational"] == 400.0
    assert "Comida" in waterfall_labels
    assert "Reembolso" not in waterfall_labels
    assert "Gastos con categoría inconsistente" in waterfall_labels
    assert waterfall_values["Comida"] == -250.0
    assert waterfall_values["Gastos con categoría inconsistente"] == -150.0
    assert payload["waterfall"]["summary"]["inconsistent_bucket_present"] is True


def test_waterfall_keeps_inconsistent_bucket_visible_when_other_expenses_is_present(
    db: Database,
):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=5000,
        category="Salario",
        tx_date="2025-03-01",
    )
    for idx in range(7):
        category = db.category.get_or_create(f"Rubro {idx + 1}", "expense", color="#777777")
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=300 - idx,
            category=str(category["name"]),
            tx_date=f"2025-03-{idx + 2:02d}",
        )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=50,
        category="Reembolso",
        tx_date="2025-03-20",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    waterfall_values = {step["label"]: step["value"] for step in payload["waterfall"]["steps"]}

    assert waterfall_values["Otros gastos"] == -294.0
    assert waterfall_values["Gastos con categoría inconsistente"] == -50.0
    assert payload["waterfall"]["summary"]["displayed_expense_steps_count"] == 8


def test_waterfall_uses_persisted_category_id_after_income_category_rename(
    db: Database,
):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")
    income_cat = db.category.find_by_name("Reembolso", "income")
    assert income_cat is not None

    # El reporte es mensual, pero el usuario puede abrir un mes histórico desde
    # los filtros después de renombrar una categoría. El category_id persistido
    # debe seguir enroutando el gasto al bucket inconsistente para ese mes.
    tx = db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=180,
        category="Reembolso",
        category_id=int(income_cat["id"]),
        tx_date="2025-03-11",
    )
    assert int(tx.get("category_id") or 0) == int(income_cat["id"])

    db.category.update(
        int(income_cat["id"]),
        name="Ingreso Reasignado",
        cat_type="income",
        color=str(income_cat.get("color") or "#86A9FF"),
        parent_id=income_cat.get("parent_id"),
        icon=str(income_cat.get("icon") or ""),
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    waterfall_values = {step["label"]: step["value"] for step in payload["waterfall"]["steps"]}

    assert waterfall_values["Gastos con categoría inconsistente"] == -180.0
    assert "Reembolso" not in waterfall_values
    assert "Ingreso Reasignado" not in waterfall_values


@pytest.mark.full
def test_budget_comparison_and_missing_budgeted_items(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")
    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=1000,
        category="Salario",
        tx_date="2025-03-02",
    )

    budget = db.budget.create("B2025", 2025, "NIO")
    income_cat = db.category.find_by_name("Salario", "income")
    expense_cat = db.category.find_by_name("Comida", "expense")
    assert income_cat and expense_cat
    db.budget.upsert_amount(int(budget["id"]), int(income_cat["id"]), 2025, 3, 1200)
    db.budget.upsert_amount(int(budget["id"]), int(expense_cat["id"]), 2025, 3, 300)

    payload = db.report.get_mira_master_report(year=2025, month=3)

    assert payload["budget"]["has_budget"] is True
    assert "Comida" in payload["budget"]["missing_expense_categories"]


def test_incomplete_budget_period_is_ignored(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")
    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=1000,
        category="Salario",
        tx_date="2025-03-02",
    )

    budget = db.budget.create("B2025-2", 2025, "NIO")
    income_cat = db.category.find_by_name("Salario", "income")
    assert income_cat
    db.budget.upsert_amount(int(budget["id"]), int(income_cat["id"]), 2025, 2, 1000)

    payload = db.report.get_mira_master_report(year=2025, month=3)
    assert payload["budget"]["has_budget"] is False


def test_zero_income_has_no_invalid_ratios_and_warns(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=250,
        category="Comida",
        tx_date="2025-03-02",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)

    assert payload["metrics"]["expense_income_ratio"] is None
    assert payload["metrics"]["savings_rate_pct"] is None
    assert any(m["code"] == "zero_income" for m in payload["advisor"]["messages"])


def test_report_respects_selected_language_for_payload_texts(db: Database):
    db.setting.set("language", "en")
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=1000,
        category="Salario",
        tx_date="2025-02-02",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=200,
        category="Comida",
        tx_date="2025-02-10",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=1100,
        category="Salario",
        tx_date="2025-03-02",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=300,
        category="Comida",
        tx_date="2025-03-10",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    messages = {item["code"]: item["text"] for item in payload["advisor"]["messages"]}

    assert payload["waterfall"]["steps"][0]["label"] == "Total net income"
    assert payload["waterfall"]["steps"][-1]["label"] == "Month balance"
    assert payload["history_hints"] == [
        "A longer transaction history is required to complete 3-month and 6-month comparisons."
    ]
    assert messages["income_vs_previous"] == "Income this month was 10.0% higher than last month."
    assert messages["expense_vs_previous"] == "Operating expenses were 50.0% higher than last month."
    assert messages["surplus"] == "✅ You are doing well: you have 800.00 available to assign to new goals."


def test_relevance_threshold_filters_minor_messages_and_prioritizes_deficit(
    db: Database,
):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=200,
        category="Salario",
        tx_date="2025-02-02",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=100,
        category="Comida",
        tx_date="2025-02-10",
    )

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=190,
        category="Salario",
        tx_date="2025-03-02",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=250,
        category="Comida",
        tx_date="2025-03-10",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3, relevance_threshold=0.10)
    messages = payload["advisor"]["messages"]

    assert messages[0]["code"] == "deficit"
    assert any(m["code"] == "expense_vs_previous" for m in messages)


def test_lifestyle_inflation_alert_warns_when_expenses_rise_with_income(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=1000,
        category="Salario",
        tx_date="2025-02-02",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=400,
        category="Comida",
        tx_date="2025-02-10",
    )

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=1100,
        category="Salario",
        tx_date="2025-03-02",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=440,
        category="Comida",
        tx_date="2025-03-10",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    messages = {item["code"]: item["text"] for item in payload["advisor"]["messages"]}

    assert payload["metrics"]["lifestyle_inflation"] == {
        "income_growth_pct": pytest.approx(10.0),
        "expense_growth_pct": pytest.approx(10.0),
        "expense_to_income_growth_ratio": pytest.approx(1.0),
        "is_applicable": True,
        "is_alert": True,
    }
    assert "lifestyle_inflation_alert" in messages
    assert "inflacion de estilo de vida" in messages["lifestyle_inflation_alert"]


def test_freedom_margin_classifies_fast_track_zone(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=1000,
        category="Salario",
        tx_date="2025-03-02",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=400,
        category="Comida",
        tx_date="2025-03-10",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    messages = {item["code"]: item["text"] for item in payload["advisor"]["messages"]}

    assert payload["metrics"]["freedom_margin"] == {
        "pct": pytest.approx(60.0),
        "zone": "fast_track",
        "label": "via_rapida",
        "is_red_alert": False,
    }
    assert "freedom_margin" in messages
    assert "Margen de Libertad" in messages["freedom_margin"]
    assert "Via Rapida" in messages["freedom_margin"]


def test_freedom_margin_classifies_red_alert_zone(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=200,
        category="Salario",
        tx_date="2025-03-02",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=250,
        category="Comida",
        tx_date="2025-03-10",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    messages = {item["code"]: item["text"] for item in payload["advisor"]["messages"]}

    assert payload["metrics"]["freedom_margin"] == {
        "pct": pytest.approx(-25.0),
        "zone": "red_alert",
        "label": "alerta_roja",
        "is_red_alert": True,
    }
    assert "freedom_margin" in messages
    assert "Alerta Roja" in messages["freedom_margin"]


def test_surplus_leakage_warns_when_surplus_does_not_reach_goals(db: Database):
    _seed_categories_for_mira(db)
    db.savings_goal.create("Fondo Emergencia", 1000.0)
    acc = db.account.get_or_create("General")

    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=1000,
        category="Salario",
        tx_date="2025-03-02",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=600,
        category="Comida",
        tx_date="2025-03-10",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    messages = {item["code"]: item["text"] for item in payload["advisor"]["messages"]}

    assert payload["kpis"]["net"] == pytest.approx(400.0)
    assert payload["metrics"]["goal_contributions"] == {
        "count": 0,
        "amount": 0.0,
        "by_goal": {},
    }
    assert payload["metrics"]["goal_completion_index_pct"] == pytest.approx(0.0)
    assert payload["metrics"]["savings_efficiency"] == {
        "surplus_amount": pytest.approx(400.0),
        "goal_funding_amount": pytest.approx(0.0),
        "goal_funding_efficiency_pct": pytest.approx(0.0),
        "surplus_leakage_amount": pytest.approx(400.0),
        "has_surplus_leakage_alert": True,
    }
    assert "surplus_leakage" in messages
    assert "fuga de excedente" in messages["surplus_leakage"]


def test_generic_analysis_groups_flow_behavior_and_stability_metrics(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    monthly_income = [1400, 900, 1300, 850, 1200, 800]
    monthly_expense = [500, 550, 650, 750, 850, 930]
    for month, (income_amount, expense_amount) in enumerate(zip(monthly_income, monthly_expense, strict=True), start=1):
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=income_amount,
            category="Salario",
            tx_date=f"2025-{month:02d}-01",
        )
        if month == 6:
            db.transaction.create(
                account_id=acc["id"],
                tx_type="expense",
                amount=500.0,
                category="Comida",
                tx_date="2025-06-05",
            )
            db.transaction.create(
                account_id=acc["id"],
                tx_type="expense",
                amount=430.0,
                category="Comida",
                tx_date="2025-06-21",
            )
        else:
            db.transaction.create(
                account_id=acc["id"],
                tx_type="expense",
                amount=expense_amount,
                category="Comida",
                tx_date=f"2025-{month:02d}-06",
            )

    payload = db.report.get_mira_master_report(year=2025, month=6)
    generic = payload["metrics"]["generic_analysis"]

    assert generic["flow"]["income_trend"]["direction"] == "down"
    assert generic["flow"]["expense_trend"]["direction"] == "up"
    assert generic["flow"]["gap_trend"]["direction"] == "down"
    assert generic["flow"]["financial_balance"]["classification"] == "critical"
    assert generic["flow"]["cashflow_projection"]["classification"] == "deficit"

    assert generic["behavior"]["spending_pattern"]["classification"] == "impulsive"
    assert generic["behavior"]["week_spread"]["classification"] == "concentrated"
    assert generic["behavior"]["expense_control"]["classification"] == "out_of_control"

    assert generic["stability"]["cashflow_stability"]["classification"] == "volatile"
    assert generic["stability"]["deficit_risk"]["classification"] == "high"
    assert generic["stability"]["income_fragility"]["classification"] == "high"
    assert generic["stability"]["financial_momentum"]["direction"] == "negative"
    assert generic["stability"]["income_control"]["classification"] == "fragile"
    assert generic["stability"]["runway_trend"]["direction"] == "down"
    assert generic["stability"]["sustainability_score"]["classification"] == "fragile"


def test_generic_analysis_handles_zero_division_cases_safely(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=250,
        category="Comida",
        tx_date="2025-03-02",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    generic = payload["metrics"]["generic_analysis"]

    assert generic["flow"]["financial_balance"]["classification"] == "insufficient_income"
    assert generic["flow"]["spending_efficiency"]["classification"] == "insufficient_income"
    assert generic["flow"]["income_trend"]["pct"] is None
    assert generic["stability"]["cashflow_stability"]["classification"] in {
        "insufficient_income",
        "insufficient_history",
    }
    assert generic["stability"]["income_fragility"]["classification"] == "no_income"
    assert generic["stability"]["income_control"]["classification"] == "insufficient_history"
    assert generic["stability"]["runway_trend"]["pct"] is None


def test_top5_consistency_and_historical_periods(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")
    for m in range(1, 7):
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=1000 + m,
            category="Salario",
            tx_date=f"2025-{m:02d}-02",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=100 + m,
            category="Comida",
            tx_date=f"2025-{m:02d}-05",
        )
        db.transaction.create(
            account_id=acc["id"],
            tx_type="expense",
            amount=20 + m,
            category="Ahorro Meta",
            tx_date=f"2025-{m:02d}-06",
        )

    report_year = 2025
    report_month = 6
    payload = db.report.get_mira_master_report(year=report_year, month=report_month)
    expected_periods = []
    for delta in range(-5, 1):
        period_year, period_month = shift_month(report_year, report_month, delta)
        expected_periods.append(f"{period_year:04d}-{period_month:02d}")

    assert len(payload["historical_stacked"]["income"]) == 6
    assert len(payload["historical_stacked"]["expense"]) == 6
    assert [row["period"] for row in payload["historical_stacked"]["income"]] == expected_periods
    assert payload["consistency"]["top5_le_total"] is True


@pytest.mark.full
def test_budget_missing_categories_uses_category_id_after_rename(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    budget = db.budget.create("B2025-REN", 2025, "NIO")
    expense_cat = db.category.find_by_name("Comida", "expense")
    assert expense_cat is not None
    db.budget.upsert_amount(int(budget["id"]), int(expense_cat["id"]), 2025, 3, 300)

    # Rename category after budgeting.
    db.category.update(
        int(expense_cat["id"]),
        name="Alimentos",
        cat_type="expense",
        color=str(expense_cat.get("color") or "#E9C46A"),
        parent_id=expense_cat.get("parent_id"),
        icon=str(expense_cat.get("icon") or ""),
    )

    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=120,
        category="Alimentos",
        tx_date="2025-03-10",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    assert "Comida" not in payload["budget"]["missing_expense_categories"]
    assert "Alimentos" not in payload["budget"]["missing_expense_categories"]


def test_historical_tx_before_category_rename_keeps_budget_match_via_persisted_fk(
    db: Database,
):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    budget = db.budget.create("B2025-HIST", 2025, "NIO")
    expense_cat = db.category.find_by_name("Comida", "expense")
    assert expense_cat is not None
    db.budget.upsert_amount(int(budget["id"]), int(expense_cat["id"]), 2025, 3, 300)

    # Historical transaction stores category_id at creation time.
    tx = db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=120,
        category="Comida",
        tx_date="2025-03-10",
    )
    assert tx.get("category_id") == int(expense_cat["id"])

    # Rename category afterwards. Historical tx category text can stay as-is,
    # but budget matching must remain stable via persisted FK.
    db.category.update(
        int(expense_cat["id"]),
        name="Alimentos",
        cat_type="expense",
        color=str(expense_cat.get("color") or "#E9C46A"),
        parent_id=expense_cat.get("parent_id"),
        icon=str(expense_cat.get("icon") or ""),
    )

    tx_rows = db.transaction.list(limit=10)
    assert tx_rows
    assert int(tx_rows[0].get("category_id") or 0) == int(expense_cat["id"])

    payload = db.report.get_mira_master_report(year=2025, month=3)
    assert "Comida" not in payload["budget"]["missing_expense_categories"]
    assert "Alimentos" not in payload["budget"]["missing_expense_categories"]


def test_update_transaction_recomputes_category_id_when_category_changes(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")
    transport = db.category.get_or_create("Transporte", "expense", color="#888888")

    tx = db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=50,
        category="Comida",
        tx_date="2025-03-10",
    )

    updated = db.transaction.update(int(tx["id"]), category="Transporte")
    assert updated["category"] == "Transporte"
    assert int(updated.get("category_id") or 0) == int(transport["id"])


def test_report_tolerates_timestamp_like_transaction_dates(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")
    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=500,
        category="Salario",
        tx_date="2025-03-01",
    )
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=120,
        category="Comida",
        tx_date="2025-03-02T12:30:00",
    )

    payload = db.report.get_mira_master_report(year=2025, month=3)
    assert payload["kpis"]["expense_operational"] == 120.0


def test_3m_and_6m_averages_exclude_current_month(db: Database):
    _seed_categories_for_mira(db)
    acc = db.account.get_or_create("General")

    # Months prior to June: Jan..May income = 100 each month.
    for m in range(1, 6):
        db.transaction.create(
            account_id=acc["id"],
            tx_type="income",
            amount=100,
            category="Salario",
            tx_date=f"2025-{m:02d}-02",
        )

    # Current month (June) has a very different value and must not affect avg_3/avg_6.
    db.transaction.create(
        account_id=acc["id"],
        tx_type="income",
        amount=1000,
        category="Salario",
        tx_date="2025-06-02",
    )

    payload = db.report.get_mira_master_report(year=2025, month=6)
    income_comparisons = payload["comparisons"]["income"]

    # avg_3 must be based on Mar-Apr-May = 100.
    assert income_comparisons["vs_avg_3"]["base"] == 100.0
    # avg_6 must be based on Dec..May; Dec has no tx and contributes 0.
    assert income_comparisons["vs_avg_6"]["base"] == 83.33
