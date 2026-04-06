# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Unit tests for the specialised report component classes.

Each class is tested in isolation, without a database, using simple
in-memory data structures.  This directly satisfies the SRP refactoring
goal: the new classes must be independently unit-testable.
"""

from __future__ import annotations

import pytest
from datetime import date
from mira.reports.mira_master import (
    AvgMetrics,
    BudgetContextData,
    ComparisonResult,
    CreditCardStats,
    FreedomMarginMetrics,
    GoalAnalysisResult,
    GoalContributionMetrics,
    GoalProgressAnalyzer,
    GoalRow,
    LifestyleInflationMetrics,
    MetricsResult,
    Mira503020,
    ReportInputs,
    ReportMessageGenerator,
    ReportMetricsCalculator,
    SavingsEfficiencyMetrics,
    SummaryMetrics,
    WaterfallChartBuilder,
    build_report_payload,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures shared across test classes
# ---------------------------------------------------------------------------


def _make_tx(
    *,
    tx_id: int = 1,
    tx_type: str = "expense",
    amount: float = 100.0,
    category: str = "Comida",
    category_id: int | None = None,
    account_id: int = 1,
    tx_date: str = "2025-03-05",
    is_transfer: int = 0,
) -> dict:
    return {
        "id": tx_id,
        "type": tx_type,
        "amount": amount,
        "category": category,
        "category_id": category_id,
        "account_id": account_id,
        "date": tx_date,
        "is_transfer": is_transfer,
    }


def _make_goal(
    *,
    name: str = "Vacaciones",
    target_amount: float = 1000.0,
    current_amount: float = 500.0,
    remaining_amount: float | None = None,
    progress: float | None = None,
    target_date: str | None = None,
    currency: str = "USD",
    category_id: int | None = None,
) -> dict:
    if remaining_amount is None:
        remaining_amount = target_amount - current_amount
    if progress is None:
        progress = current_amount / target_amount if target_amount > 0 else 0.0
    return {
        "name": name,
        "target_amount": target_amount,
        "current_amount": current_amount,
        "remaining_amount": remaining_amount,
        "progress": progress,
        "target_date": target_date,
        "currency": currency,
        "category_id": category_id,
    }


_CATEGORIES_WITH_SAVINGS = [
    {"id": 1, "name": "Ahorro", "type": "expense", "is_savings": 1, "parent_id": None, "color": "#4EC9B0"},
    {"id": 2, "name": "Comida", "type": "expense", "is_savings": 0, "parent_id": None, "color": "#E9C46A"},
    {"id": 3, "name": "Salario", "type": "income", "is_savings": 0, "parent_id": None, "color": "#4EC9B0"},
]


def _make_goal_analysis_result(
    goal_rows: list | None = None,
    active_goals: list | None = None,
) -> GoalAnalysisResult:
    """Return a minimal GoalAnalysisResult for tests that need one."""
    return GoalAnalysisResult(
        goal_rows=goal_rows or [],
        completed_goals=[],
        active_goals=active_goals or [],
        goals_summary={"total_goals": 0, "completed_goals": 0, "active_goals": 0, "headline": "", "items": []},
        report_period_end=date(2025, 3, 31),
    )


def _build_minimal_metrics_calc(
    month_transactions=None,
    previous_transactions=None,
    categories=None,
    savings_goals=None,
) -> ReportMetricsCalculator:
    """Build a ReportMetricsCalculator with safe defaults for unit tests."""
    inputs = ReportInputs(
        year=2025,
        month=3,
        month_transactions=month_transactions or [],
        month_transactions_raw=month_transactions or [],
        previous_transactions=previous_transactions or [],
        trailing_3=[],
        comparison_trailing_6=[],
        historical_6=[],
        ytd_months=[],
        categories=categories if categories is not None else _CATEGORIES_WITH_SAVINGS,
        tags_by_tx={},
        accounts=[],
        account_balance_total=0.0,
        budget=None,
        budget_monthly_by_type=None,
        budget_category_rows=None,
        savings_goals=savings_goals or [],
    )
    return ReportMetricsCalculator(inputs, _make_goal_analysis_result())


# ---------------------------------------------------------------------------
# GoalProgressAnalyzer tests
# ---------------------------------------------------------------------------


class TestGoalProgressAnalyzer:
    def test_no_goals_returns_empty_summary(self) -> None:
        result = GoalProgressAnalyzer([], 2025, 3).analyze()

        assert result.goal_rows == []
        assert result.completed_goals == []
        assert result.active_goals == []
        assert result.goals_summary["total_goals"] == 0
        assert result.goals_summary["items"] == []
        assert "You do not have" in result.goals_summary["headline"]

    def test_active_goal_is_parsed_correctly(self) -> None:
        goal = _make_goal(name="House", target_amount=10000.0, current_amount=3000.0, currency="USD")
        result = GoalProgressAnalyzer([goal], 2025, 3).analyze()

        assert len(result.active_goals) == 1
        row = result.active_goals[0]
        assert row.name == "House"
        assert row.target_amount == 10000.0
        assert row.current_amount == 3000.0
        assert row.remaining_amount == 7000.0
        assert row.progress_pct == pytest.approx(30.0)
        assert row.achieved is False

    def test_completed_goal_is_marked_achieved(self) -> None:
        goal = _make_goal(name="Emergency", target_amount=1000.0, current_amount=1000.0)
        result = GoalProgressAnalyzer([goal], 2025, 3).analyze()

        assert len(result.completed_goals) == 1
        assert result.completed_goals[0].achieved is True
        assert len(result.active_goals) == 0

    def test_goal_with_zero_remaining_is_achieved(self) -> None:
        goal = _make_goal(target_amount=500.0, current_amount=400.0, remaining_amount=0.0, progress=1.0)
        result = GoalProgressAnalyzer([goal], 2025, 3).analyze()

        assert result.goal_rows[0].achieved is True

    def test_report_period_end_matches_year_month(self) -> None:
        result = GoalProgressAnalyzer([], 2025, 2).analyze()
        assert result.report_period_end == date(2025, 2, 28)

    def test_active_goals_are_sorted_by_target_date_first(self) -> None:
        goals = [
            _make_goal(name="Z_late", target_amount=1000.0, current_amount=0.0, target_date="2026-12-01"),
            _make_goal(name="A_early", target_amount=1000.0, current_amount=0.0, target_date="2025-06-01"),
        ]
        result = GoalProgressAnalyzer(goals, 2025, 3).analyze()

        names = [g.name for g in result.active_goals]
        assert names == ["A_early", "Z_late"]

    def test_goals_without_date_sort_after_dated_goals(self) -> None:
        goals = [
            _make_goal(name="No date", target_amount=1000.0, current_amount=0.0),
            _make_goal(name="Has date", target_amount=1000.0, current_amount=0.0, target_date="2025-12-01"),
        ]
        result = GoalProgressAnalyzer(goals, 2025, 3).analyze()

        names = [g.name for g in result.active_goals]
        assert names[0] == "Has date"
        assert names[1] == "No date"

    def test_spanish_headline_when_language_es(self) -> None:
        result = GoalProgressAnalyzer([], 2025, 3, language="es").analyze()
        assert "todavía" in result.goals_summary["headline"]

    def test_english_headline_when_language_en(self) -> None:
        result = GoalProgressAnalyzer([], 2025, 3, language="en").analyze()
        assert "You do not have" in result.goals_summary["headline"]

    def test_summary_counts_active_and_completed(self) -> None:
        goals = [
            _make_goal(name="Done", target_amount=100.0, current_amount=100.0),
            _make_goal(name="Active1", target_amount=1000.0, current_amount=100.0),
            _make_goal(name="Active2", target_amount=2000.0, current_amount=200.0),
        ]
        result = GoalProgressAnalyzer(goals, 2025, 3).analyze()
        summary = result.goals_summary

        assert summary["total_goals"] == 3
        assert summary["completed_goals"] == 1
        assert summary["active_goals"] == 2

    def test_summary_items_include_active_and_one_completed(self) -> None:
        goals = [
            _make_goal(name="DoneGoal", target_amount=500.0, current_amount=500.0),
            _make_goal(name="Active1", target_amount=1000.0, current_amount=200.0),
            _make_goal(name="Active2", target_amount=2000.0, current_amount=400.0),
        ]
        result = GoalProgressAnalyzer(goals, 2025, 3).analyze()
        items = result.goals_summary["items"]

        # max 2 active + 1 completed = 3 items
        assert len(items) == 3
        all_text = " ".join(items)
        assert "Active1" in all_text
        assert "Active2" in all_text
        assert "DoneGoal" in all_text

    def test_progress_pct_is_capped_at_100(self) -> None:
        goal = _make_goal(target_amount=100.0, current_amount=150.0, remaining_amount=0.0, progress=1.5)
        result = GoalProgressAnalyzer([goal], 2025, 3).analyze()
        assert result.goal_rows[0].progress_pct == 100.0

    def test_invalid_target_date_is_treated_as_no_date(self) -> None:
        goal = _make_goal(target_amount=1000.0, current_amount=200.0, target_date="not-a-date")
        result = GoalProgressAnalyzer([goal], 2025, 3).analyze()
        row = result.goal_rows[0]
        assert row.parsed_target_date is None
        assert row.target_date == "not-a-date"


# ---------------------------------------------------------------------------
# WaterfallChartBuilder tests
# ---------------------------------------------------------------------------


class TestWaterfallChartBuilder:
    def _make_builder(
        self,
        income: float,
        net: float,
        displayed: list[tuple[str, float]] | None = None,
        remaining: list[tuple[str, float]] | None = None,
        normal: list[tuple[str, float]] | None = None,
        inconsistent: tuple[str, float] | None = None,
        all_totals: list[tuple[str, float]] | None = None,
        language: str = "en",
    ) -> WaterfallChartBuilder:
        if displayed is None:
            displayed = []
        if remaining is None:
            remaining = []
        if normal is None:
            normal = displayed[:]
        if all_totals is None:
            all_totals = displayed[:]
        return WaterfallChartBuilder(
            income_total=income,
            net_after_expenses=net,
            displayed_categories=displayed,
            remaining_categories=remaining,
            normal_categories=normal,
            inconsistent_entry=inconsistent,
            all_waterfall_category_totals=all_totals,
            language=language,
        )

    def test_surplus_month_creates_correct_steps(self) -> None:
        builder = self._make_builder(
            income=1000.0,
            net=600.0,
            displayed=[("Comida", 200.0), ("Alquiler", 200.0)],
        )
        result = builder.build()

        steps = result["steps"]
        assert steps[0]["kind"] == "income_total"
        assert steps[0]["value"] == 1000.0
        assert steps[-1]["kind"] == "month_balance"
        assert steps[-1]["value"] == 600.0

    def test_surplus_summary_status_is_surplus(self) -> None:
        result = self._make_builder(income=1000.0, net=400.0).build()
        assert result["summary"]["status"] == "surplus"
        assert result["summary"]["final_balance"] == 400.0
        assert result["summary"]["financing_amount"] == 0.0

    def test_deficit_month_adds_financing_bridge(self) -> None:
        builder = self._make_builder(
            income=800.0,
            net=-200.0,
            displayed=[("Comida", 1000.0)],
        )
        result = builder.build()

        kinds = [s["kind"] for s in result["steps"]]
        assert "financing" in kinds
        financing_step = next(s for s in result["steps"] if s["kind"] == "financing")
        assert financing_step["value"] == 200.0

    def test_deficit_summary_status_is_deficit(self) -> None:
        result = self._make_builder(income=500.0, net=-100.0).build()
        assert result["summary"]["status"] == "deficit"
        assert result["summary"]["financing_amount"] == 100.0

    def test_balanced_month_has_final_total_step(self) -> None:
        result = self._make_builder(income=500.0, net=0.0).build()
        steps = result["steps"]
        assert steps[-1]["kind"] == "final_total"
        assert result["summary"]["status"] == "balanced"

    def test_expense_steps_reduce_running_balance(self) -> None:
        builder = self._make_builder(
            income=1000.0,
            net=600.0,
            displayed=[("Comida", 250.0), ("Transporte", 150.0)],
        )
        result = builder.build()

        expense_steps = [s for s in result["steps"] if s["kind"] == "expense"]
        assert expense_steps[0]["start"] == 1000.0
        assert expense_steps[0]["end"] == 750.0
        assert expense_steps[1]["start"] == 750.0
        assert expense_steps[1]["end"] == 600.0

    def test_first_step_is_income_total(self) -> None:
        result = self._make_builder(income=1234.56, net=100.0).build()
        assert result["steps"][0]["kind"] == "income_total"
        assert result["steps"][0]["value"] == 1234.56

    def test_grouped_step_flag_set_when_remaining_categories_exist(self) -> None:
        other_label = "Other expenses"
        remaining = [("Misc", 50.0)]
        displayed = [("Comida", 200.0), (other_label, 50.0)]
        builder = self._make_builder(
            income=1000.0,
            net=750.0,
            displayed=displayed,
            remaining=remaining,
        )
        result = builder.build()

        other_step = next((s for s in result["steps"] if s["label"] == other_label), None)
        assert other_step is not None
        assert other_step["is_grouped"] is True

    def test_summary_counts_expense_categories(self) -> None:
        all_totals = [("A", 100.0), ("B", 200.0), ("C", 300.0)]
        builder = self._make_builder(
            income=1000.0,
            net=400.0,
            displayed=all_totals,
            all_totals=all_totals,
            normal=all_totals,
        )
        result = builder.build()
        assert result["summary"]["expense_categories_count"] == 3

    def test_spanish_labels_when_language_es(self) -> None:
        result = self._make_builder(income=1000.0, net=400.0, language="es").build()
        assert result["steps"][0]["label"] == "Ingreso total neto"
        assert result["steps"][-1]["label"] == "Balance del mes"

    def test_english_labels_when_language_en(self) -> None:
        result = self._make_builder(income=1000.0, net=400.0, language="en").build()
        assert result["steps"][0]["label"] == "Total net income"
        assert result["steps"][-1]["label"] == "Month balance"

    def test_deficit_financing_label_in_spanish(self) -> None:
        result = self._make_builder(income=500.0, net=-100.0, language="es").build()
        financing = next(s for s in result["steps"] if s["kind"] == "financing")
        assert "Deuda" in financing["label"]

    def test_inconsistent_bucket_flag_in_summary(self) -> None:
        inconsistent = ("Inconsistent", 50.0)
        builder = self._make_builder(
            income=1000.0,
            net=550.0,
            displayed=[("Comida", 200.0), inconsistent],
            inconsistent=inconsistent,
        )
        result = builder.build()
        assert result["summary"]["inconsistent_bucket_present"] is True

    def test_no_inconsistent_bucket_flag_when_absent(self) -> None:
        result = self._make_builder(income=1000.0, net=800.0, displayed=[("Comida", 200.0)]).build()
        assert result["summary"]["inconsistent_bucket_present"] is False


# ---------------------------------------------------------------------------
# ReportMetricsCalculator tests
# ---------------------------------------------------------------------------


class TestReportMetricsCalculator:
    def test_compute_returns_typed_result(self) -> None:
        calc = _build_minimal_metrics_calc()
        result = calc.compute()

        assert isinstance(result, MetricsResult)
        assert isinstance(result.credit_card, CreditCardStats)
        assert isinstance(result.current_summary, SummaryMetrics)
        assert isinstance(result.previous_summary, SummaryMetrics)
        assert isinstance(result.avg_3, AvgMetrics)
        assert isinstance(result.avg_6, AvgMetrics)
        assert isinstance(result.income_vs_previous, ComparisonResult)
        assert isinstance(result.expense_vs_previous, ComparisonResult)
        assert isinstance(result.budget_context, BudgetContextData)
        assert isinstance(result.lifestyle_inflation_metrics, LifestyleInflationMetrics)
        assert isinstance(result.savings_efficiency_metrics, SavingsEfficiencyMetrics)
        assert isinstance(result.freedom_margin_metrics, FreedomMarginMetrics)
        assert isinstance(result.goal_contribution_metrics, GoalContributionMetrics)
        assert isinstance(result.mira_50_30_20, Mira503020)
        assert isinstance(result.ytd, list)
        assert isinstance(result.top_categories, list)
        assert isinstance(result.generic_analysis, dict)

    def test_empty_transactions_produce_zero_kpis(self) -> None:
        calc = _build_minimal_metrics_calc()
        result = calc.compute()

        assert result.income_total == 0.0
        assert result.total_expense == 0.0
        assert result.net_after_expenses == 0.0

    def test_expense_transaction_appears_in_top_categories(self) -> None:
        tx = _make_tx(tx_type="expense", amount=300.0, category="Comida", category_id=2)
        calc = _build_minimal_metrics_calc(month_transactions=[tx])
        result = calc.compute()

        top_names = [name for name, _amount in result.top_categories]
        assert "Comida" in top_names

    def test_income_transaction_is_not_in_top_expense_categories(self) -> None:
        tx = _make_tx(tx_type="income", amount=1000.0, category="Salario", category_id=3)
        calc = _build_minimal_metrics_calc(month_transactions=[tx])
        result = calc.compute()

        assert result.top_categories == []
        assert result.income_total == pytest.approx(1000.0)

    def test_credit_card_stats_count_expenses_on_credit_account(self) -> None:
        accounts = [{"id": 10, "account_type": "credit", "balance": 0}]
        tx = {
            "id": 1,
            "type": "expense",
            "amount": 500.0,
            "category": "Comida",
            "category_id": 2,
            "account_id": 10,
            "date": "2025-03-10",
            "is_transfer": 0,
        }
        calc = ReportMetricsCalculator(
            ReportInputs(
                year=2025,
                month=3,
                month_transactions=[tx],
                month_transactions_raw=[tx],
                previous_transactions=[],
                trailing_3=[],
                comparison_trailing_6=[],
                historical_6=[],
                ytd_months=[],
                categories=_CATEGORIES_WITH_SAVINGS,
                tags_by_tx={},
                accounts=accounts,
                account_balance_total=0.0,
                budget=None,
                budget_monthly_by_type=None,
                budget_category_rows=None,
                savings_goals=[],
            ),
            _make_goal_analysis_result(),
        )
        result = calc.compute()

        assert result.credit_card.expense_count == 1
        assert result.credit_card.expense_amount == pytest.approx(500.0)
        assert result.credit_card.gap_amount == pytest.approx(500.0)

    def test_budget_context_has_budget_false_when_no_budget(self) -> None:
        calc = _build_minimal_metrics_calc()
        result = calc.compute()
        assert result.budget_context.has_budget is False

    def test_budget_context_populated_when_budget_provided(self) -> None:
        budget = {"id": 1, "code": "B2025"}
        budget_by_type = {"income": {"Salario": 1000.0}, "expense": {"Comida": 300.0}}
        calc = ReportMetricsCalculator(
            ReportInputs(
                year=2025,
                month=3,
                month_transactions=[],
                month_transactions_raw=[],
                previous_transactions=[],
                trailing_3=[],
                comparison_trailing_6=[],
                historical_6=[],
                ytd_months=[],
                categories=_CATEGORIES_WITH_SAVINGS,
                tags_by_tx={},
                accounts=[],
                account_balance_total=0.0,
                budget=budget,
                budget_monthly_by_type=budget_by_type,
                budget_category_rows=None,
                savings_goals=[],
            ),
            _make_goal_analysis_result(),
        )
        result = calc.compute()

        assert result.budget_context.has_budget is True
        assert result.budget_context.income == pytest.approx(1000.0)
        assert result.budget_context.expense_operational == pytest.approx(300.0)

    def test_ytd_is_empty_when_no_ytd_months(self) -> None:
        calc = _build_minimal_metrics_calc()
        assert calc.compute().ytd == []

    def test_history_hints_appear_when_trailing_history_is_incomplete(self) -> None:
        calc = _build_minimal_metrics_calc()  # trailing_3=[] → < 3 months
        result = calc.compute()
        assert len(result.history_hints) >= 1

    def test_no_history_hints_when_full_history_available(self) -> None:
        # Supply 3 non-empty trailing months and 6 non-empty comparison months.
        # The hint condition checks `if item` (truthy), so lists must be non-empty.
        dummy_tx = _make_tx(tx_type="income", amount=100.0, category="Salario", category_id=3)
        trailing_3 = [[dummy_tx], [dummy_tx], [dummy_tx]]
        comparison_trailing_6 = [(2024, m, [dummy_tx]) for m in range(10, 16)]
        calc = ReportMetricsCalculator(
            ReportInputs(
                year=2025,
                month=3,
                month_transactions=[],
                month_transactions_raw=[],
                previous_transactions=[],
                trailing_3=trailing_3,
                comparison_trailing_6=comparison_trailing_6,
                historical_6=[],
                ytd_months=[],
                categories=_CATEGORIES_WITH_SAVINGS,
                tags_by_tx={},
                accounts=[],
                account_balance_total=0.0,
                budget=None,
                budget_monthly_by_type=None,
                budget_category_rows=None,
                savings_goals=[],
            ),
            _make_goal_analysis_result(),
        )
        result = calc.compute()
        assert result.history_hints == []

    def test_mira_50_30_20_keys_present(self) -> None:
        calc = _build_minimal_metrics_calc()
        result = calc.compute()
        m = result.mira_50_30_20
        assert isinstance(m, Mira503020)
        assert hasattr(m, "needs_pct")
        assert hasattr(m, "wants_pct")
        assert hasattr(m, "savings_pct")
        assert hasattr(m, "deviation_pct")

    def test_savings_transaction_excluded_from_top_expense_categories(self) -> None:
        categories = [
            {"id": 1, "name": "Ahorro", "type": "expense", "is_savings": 1, "parent_id": None, "color": "#4EC9B0"},
        ]
        tx = _make_tx(tx_type="expense", amount=200.0, category="Ahorro", category_id=1)
        calc = ReportMetricsCalculator(
            ReportInputs(
                year=2025,
                month=3,
                month_transactions=[tx],
                month_transactions_raw=[tx],
                previous_transactions=[],
                trailing_3=[],
                comparison_trailing_6=[],
                historical_6=[],
                ytd_months=[],
                categories=categories,
                tags_by_tx={},
                accounts=[],
                account_balance_total=0.0,
                budget=None,
                budget_monthly_by_type=None,
                budget_category_rows=None,
                savings_goals=[],
            ),
            _make_goal_analysis_result(),
        )
        result = calc.compute()
        # Savings are excluded from operational expense categories
        assert result.top_categories == []
        assert result.total_expense == 0.0


# ---------------------------------------------------------------------------
# ReportMessageGenerator tests
# ---------------------------------------------------------------------------


def _minimal_metrics_for_messages(
    *,
    income: float = 1000.0,
    expense: float = 600.0,
    net: float | None = None,
    savings: float = 0.0,
    debt_payment: float = 0.0,
) -> MetricsResult:
    """Build a minimal MetricsResult sufficient for ReportMessageGenerator tests."""
    if net is None:
        net = income - expense

    summary = SummaryMetrics(
        income=income,
        expense_operational=expense,
        savings=savings,
        net=net,
        debt_payment=debt_payment,
        refunds=0.0,
    )
    avg = AvgMetrics(income=income, expense_operational=expense, savings=savings, net=net)
    return MetricsResult(
        current_summary=summary,
        previous_summary=SummaryMetrics(
            income=income, expense_operational=expense, savings=savings, net=net, debt_payment=0.0, refunds=0.0
        ),
        avg_3=avg,
        avg_6=avg,
        credit_card=CreditCardStats(
            expense_count=0,
            expense_amount=0.0,
            payment_count=0,
            payment_amount=0.0,
            gap_amount=0.0,
        ),
        top_category_totals={},
        top_category_children={},
        tag_totals={},
        tag_children={},
        top_categories=[],
        top_tags=[],
        weekend_total=0.0,
        weekend_days={},
        daily_expense_totals={},
        small_total=0.0,
        income_by_root={},
        waterfall_category_totals=[],
        normal_waterfall_categories=[],
        displayed_waterfall_categories=[],
        remaining_waterfall_categories=[],
        inconsistent_waterfall_entry=None,
        stacked_6={"income": [], "expense": []},
        ytd=[],
        budget_context=BudgetContextData(
            has_budget=False,
            budget_id=None,
            budget_code=None,
            income=0.0,
            expense_operational=0.0,
            is_complete_for_period=False,
        ),
        comparisons={},
        income_vs_previous=ComparisonResult(pct=None, base=None, variance=None, signal="neutral"),
        expense_vs_previous=ComparisonResult(pct=None, base=None, variance=None, signal="neutral"),
        income_vs_budget=None,
        expense_vs_budget=None,
        lifestyle_inflation_metrics=LifestyleInflationMetrics(
            is_alert=False,
            income_growth_pct=None,
            expense_growth_pct=None,
            expense_to_income_growth_ratio=None,
            is_applicable=False,
        ),
        savings_efficiency_metrics=SavingsEfficiencyMetrics(
            surplus_amount=max(0.0, net),
            goal_funding_amount=0.0,
            goal_funding_efficiency_pct=None,
            surplus_leakage_amount=max(0.0, net),
            has_surplus_leakage_alert=False,
        ),
        freedom_margin_metrics=FreedomMarginMetrics(pct=None, zone=None, label=None, is_red_alert=False),
        goal_contribution_metrics=GoalContributionMetrics(count=0, amount=0.0, by_goal={}),
        generic_analysis={},
        history_hints=[],
        income_total=income,
        total_expense=expense,
        debt_payment_total=debt_payment,
        debt_payment_income_pct=(debt_payment / income * 100.0) if income > 0 and debt_payment > 0 else None,
        debt_payment_expense_pct=(debt_payment / expense * 100.0) if expense > 0 and debt_payment > 0 else None,
        savings_rate=((income - expense) / income * 100.0) if income > 0 else None,
        expense_income_ratio=expense / income if income > 0 else None,
        avg_daily_expense=expense / 31,
        burn_days=None,
        daily_living_cost=expense / 31,
        goal_completion_index_pct=None,
        concentration_pct=None,
        dependence_pct=None,
        net_after_expenses=round(net, 2),
        top_total=0.0,
        days_in_month=31,
        mira_50_30_20=Mira503020(needs_pct=0.0, wants_pct=0.0, savings_pct=0.0, deviation_pct=0.0),
    )


def _minimal_goal_data() -> GoalAnalysisResult:
    return GoalAnalysisResult(
        goal_rows=[],
        completed_goals=[],
        active_goals=[],
        goals_summary={"total_goals": 0, "completed_goals": 0, "active_goals": 0, "headline": "", "items": []},
        report_period_end=date(2025, 3, 31),
    )


class TestReportMessageGenerator:
    def _make_gen(
        self, metrics=None, goal_data=None, relevance_threshold=0.10, language="en"
    ) -> ReportMessageGenerator:
        if metrics is None:
            metrics = _minimal_metrics_for_messages()
        if goal_data is None:
            goal_data = _minimal_goal_data()
        return ReportMessageGenerator(
            metrics=metrics,
            goal_data=goal_data,
            savings_goals=[],
            year=2025,
            month=3,
            relevance_threshold=relevance_threshold,
            language=language,
        )

    def test_generate_returns_list(self) -> None:
        gen = self._make_gen()
        messages = gen.generate()
        assert isinstance(messages, list)

    def test_deficit_message_present_when_net_negative(self) -> None:
        metrics = _minimal_metrics_for_messages(income=500.0, expense=700.0, net=-200.0)
        gen = self._make_gen(metrics=metrics)
        codes = [m["code"] for m in gen.generate()]
        assert "deficit" in codes

    def test_surplus_message_present_when_net_positive(self) -> None:
        metrics = _minimal_metrics_for_messages(income=1000.0, expense=600.0, net=400.0)
        gen = self._make_gen(metrics=metrics)
        codes = [m["code"] for m in gen.generate()]
        assert "surplus" in codes

    def test_zero_income_warning_present_when_no_income(self) -> None:
        metrics = _minimal_metrics_for_messages(income=0.0, expense=0.0, net=0.0)
        gen = self._make_gen(metrics=metrics)
        codes = [m["code"] for m in gen.generate()]
        assert "zero_income" in codes

    def test_messages_sorted_by_priority_level_then_code(self) -> None:
        metrics = _minimal_metrics_for_messages(income=500.0, expense=700.0, net=-200.0)
        messages = self._make_gen(metrics=metrics).generate()
        # critical messages should appear before info messages
        levels = [m["level"] for m in messages]
        critical_indices = [i for i, lvl in enumerate(levels) if lvl == "critical"]
        info_indices = [i for i, lvl in enumerate(levels) if lvl == "info"]
        if critical_indices and info_indices:
            assert min(critical_indices) < min(info_indices)

    def test_threshold_filters_out_low_pct_non_always_messages(self) -> None:
        # weekend_behavior message has pct=0 and always=False → should be filtered
        metrics = _minimal_metrics_for_messages()
        gen = self._make_gen(metrics=metrics, relevance_threshold=0.50)
        messages = gen.generate()
        # weekend_behavior has pct=0 and always=False, should NOT appear at 50% threshold
        codes = [m["code"] for m in messages]
        assert "weekend_behavior" not in codes

    def test_always_true_messages_survive_threshold_filter(self) -> None:
        # deficit has always=True → survives any threshold
        metrics = _minimal_metrics_for_messages(income=100.0, expense=200.0, net=-100.0)
        gen = self._make_gen(metrics=metrics, relevance_threshold=1.0)
        codes = [m["code"] for m in gen.generate()]
        assert "deficit" in codes

    def test_income_vs_previous_missing_when_no_history(self) -> None:
        metrics = _minimal_metrics_for_messages()
        # income_vs_previous.pct is None by default
        codes = [m["code"] for m in self._make_gen(metrics=metrics).generate()]
        assert "income_vs_previous_missing" in codes

    def test_income_vs_previous_present_when_history_available(self) -> None:
        metrics = _minimal_metrics_for_messages()
        metrics.income_vs_previous = ComparisonResult(pct=5.0, base=950.0, variance=50.0, signal="up")
        codes = [m["code"] for m in self._make_gen(metrics=metrics).generate()]
        assert "income_vs_previous" in codes
        assert "income_vs_previous_missing" not in codes

    def test_lifestyle_inflation_alert_when_flagged(self) -> None:
        metrics = _minimal_metrics_for_messages()
        metrics.income_vs_previous = ComparisonResult(pct=5.0, base=950.0, variance=50.0, signal="up")
        metrics.expense_vs_previous = ComparisonResult(pct=20.0, base=500.0, variance=100.0, signal="up")
        metrics.lifestyle_inflation_metrics = LifestyleInflationMetrics(
            is_alert=True,
            income_growth_pct=5.0,
            expense_growth_pct=20.0,
            expense_to_income_growth_ratio=None,
            is_applicable=True,
        )
        codes = [m["code"] for m in self._make_gen(metrics=metrics).generate()]
        assert "lifestyle_inflation_alert" in codes

    def test_surplus_leakage_message_present_when_flagged(self) -> None:
        metrics = _minimal_metrics_for_messages(income=1000.0, expense=600.0, net=400.0)
        metrics.savings_efficiency_metrics.has_surplus_leakage_alert = True
        metrics.savings_efficiency_metrics.surplus_amount = 400.0
        codes = [m["code"] for m in self._make_gen(metrics=metrics).generate()]
        assert "surplus_leakage" in codes

    def test_goal_overdue_message_when_goal_past_due(self) -> None:
        goal = GoalRow(
            name="Car",
            currency="USD",
            target_amount=5000.0,
            current_amount=1000.0,
            remaining_amount=4000.0,
            progress_ratio=0.2,
            progress_pct=20.0,
            target_date="2025-01-01",
            parsed_target_date=date(2025, 1, 1),
            achieved=False,
        )
        goal_data = GoalAnalysisResult(
            goal_rows=[goal],
            completed_goals=[],
            active_goals=[goal],
            goals_summary={"total_goals": 1, "completed_goals": 0, "active_goals": 1, "headline": "", "items": []},
            report_period_end=date(2025, 3, 31),
        )
        metrics = _minimal_metrics_for_messages()
        codes = [m["code"] for m in self._make_gen(metrics=metrics, goal_data=goal_data).generate()]
        assert "goal_overdue" in codes

    def test_goal_on_track_message_when_savings_sufficient(self) -> None:
        goal = GoalRow(
            name="Vacation",
            currency="USD",
            target_amount=1000.0,
            current_amount=500.0,
            remaining_amount=500.0,
            progress_ratio=0.5,
            progress_pct=50.0,
            target_date="2025-08-01",
            parsed_target_date=date(2025, 8, 1),
            achieved=False,
        )
        goal_data = GoalAnalysisResult(
            goal_rows=[goal],
            completed_goals=[],
            active_goals=[goal],
            goals_summary={"total_goals": 1, "completed_goals": 0, "active_goals": 1, "headline": "", "items": []},
            report_period_end=date(2025, 3, 31),
        )
        metrics = _minimal_metrics_for_messages(income=1000.0, expense=500.0)
        # avg_3["savings"] needs to be high enough
        metrics.avg_3.savings = 200.0  # 500 remaining / 5 months = 100 required, 200 >= 100
        codes = [m["code"] for m in self._make_gen(metrics=metrics, goal_data=goal_data).generate()]
        assert "goal_on_track" in codes

    def test_budget_messages_generated_when_has_budget(self) -> None:
        metrics = _minimal_metrics_for_messages()
        metrics.budget_context.has_budget = True
        metrics.budget_context.income = 1000.0
        metrics.budget_context.expense_operational = 600.0
        metrics.income_vs_budget = ComparisonResult(pct=-5.0, base=1000.0, variance=-50.0, signal="neutral")
        metrics.expense_vs_budget = ComparisonResult(pct=10.0, base=600.0, variance=60.0, signal="up")
        codes = [m["code"] for m in self._make_gen(metrics=metrics).generate()]
        assert "income_vs_budget" in codes
        assert "expense_vs_budget" in codes

    def test_spanish_messages_when_language_es(self) -> None:
        metrics = _minimal_metrics_for_messages(income=500.0, expense=700.0, net=-200.0)
        gen = self._make_gen(metrics=metrics, language="es")
        messages = gen.generate()
        deficit_msg = next(m for m in messages if m["code"] == "deficit")
        assert "gastado" in deficit_msg["text"]

    def test_english_messages_when_language_en(self) -> None:
        metrics = _minimal_metrics_for_messages(income=500.0, expense=700.0, net=-200.0)
        gen = self._make_gen(metrics=metrics, language="en")
        messages = gen.generate()
        deficit_msg = next(m for m in messages if m["code"] == "deficit")
        assert "spent" in deficit_msg["text"]

    def test_generate_is_idempotent(self) -> None:
        gen = self._make_gen()
        first = gen.generate()
        second = gen.generate()
        assert [m["code"] for m in first] == [m["code"] for m in second]


# ---------------------------------------------------------------------------
# End-to-end orchestration tests (no database)
# ---------------------------------------------------------------------------


def _make_report_inputs(
    *,
    income: float = 1000.0,
    expense: float = 400.0,
    savings: float = 50.0,
    language: str = "es",
) -> ReportInputs:
    """Build a minimal ReportInputs for end-to-end build_report_payload tests."""
    income_tx = {
        "id": 1,
        "type": "income",
        "amount": income,
        "category": "Salario",
        "category_id": 1,
        "description": "",
        "note": "",
        "date": "2025-03-02",
    }
    expense_tx = {
        "id": 2,
        "type": "expense",
        "amount": expense,
        "category": "Comida",
        "category_id": 2,
        "description": "",
        "note": "",
        "date": "2025-03-08",
    }
    savings_tx = {
        "id": 3,
        "type": "expense",
        "amount": savings,
        "category": "Ahorro",
        "category_id": 3,
        "description": "",
        "note": "",
        "date": "2025-03-10",
    }
    categories = [
        {"id": 1, "name": "Salario", "type": "income", "is_savings": 0, "parent_id": None, "color": "#4EC9B0"},
        {"id": 2, "name": "Comida", "type": "expense", "is_savings": 0, "parent_id": None, "color": "#E9C46A"},
        {"id": 3, "name": "Ahorro", "type": "expense", "is_savings": 1, "parent_id": None, "color": "#86C5DA"},
    ]
    month_txs = [income_tx, expense_tx, savings_tx]
    return ReportInputs(
        year=2025,
        month=3,
        month_transactions=month_txs,
        month_transactions_raw=month_txs,
        previous_transactions=[],
        trailing_3=[],
        comparison_trailing_6=[],
        historical_6=[],
        ytd_months=[],
        categories=categories,
        tags_by_tx={},
        accounts=[{"id": 1, "name": "General", "balance": 5000.0}],
        account_balance_total=5000.0,
        budget=None,
        budget_monthly_by_type=None,
        budget_category_rows=None,
        savings_goals=[],
        language=language,
    )


class TestBuildReportPayloadEndToEnd:
    """End-to-end tests for build_report_payload without a database."""

    def test_payload_has_expected_top_level_keys(self) -> None:
        payload = build_report_payload(_make_report_inputs())
        for key in ("period", "kpis", "comparisons", "budget", "waterfall", "allocation", "advisor", "metrics"):
            assert key in payload, f"Missing top-level key: {key}"

    def test_kpis_income_and_expense_operational_correct(self) -> None:
        payload = build_report_payload(_make_report_inputs(income=1000.0, expense=400.0, savings=50.0))
        assert payload["kpis"]["income"] == pytest.approx(1000.0)
        assert payload["kpis"]["expense_operational"] == pytest.approx(400.0)
        assert payload["kpis"]["savings"] == pytest.approx(50.0)
        assert payload["kpis"]["net"] == pytest.approx(600.0)

    def test_waterfall_surplus_state_and_final_balance(self) -> None:
        payload = build_report_payload(_make_report_inputs(income=1000.0, expense=400.0, savings=50.0))
        assert payload["waterfall"]["summary"]["status"] == "surplus"
        assert payload["waterfall"]["summary"]["final_balance"] == pytest.approx(600.0)

    def test_freedom_margin_in_metrics(self) -> None:
        payload = build_report_payload(_make_report_inputs(income=1000.0, expense=400.0))
        assert payload["metrics"]["freedom_margin"]["pct"] == pytest.approx(60.0)

    def test_payload_kpis_are_plain_dict(self) -> None:
        """Payload kpis must be a plain dict so the UI can access payload['kpis']['income']."""
        payload = build_report_payload(_make_report_inputs())
        assert isinstance(payload["kpis"], dict)
        assert isinstance(payload["budget"], dict)
        assert isinstance(payload["metrics"]["freedom_margin"], dict)
        assert isinstance(payload["metrics"]["mira_50_30_20"], dict)

    def test_spanish_waterfall_labels(self) -> None:
        payload = build_report_payload(_make_report_inputs(language="es"))
        assert payload["waterfall"]["steps"][0]["label"] == "Ingreso total neto"
        assert payload["waterfall"]["steps"][-1]["label"] == "Balance del mes"

    def test_english_waterfall_labels(self) -> None:
        payload = build_report_payload(_make_report_inputs(language="en"))
        assert payload["waterfall"]["steps"][0]["label"] == "Total net income"
        assert payload["waterfall"]["steps"][-1]["label"] == "Month balance"

    def test_advisor_messages_are_list_of_dicts(self) -> None:
        payload = build_report_payload(_make_report_inputs())
        messages = payload["advisor"]["messages"]
        assert isinstance(messages, list)
        if messages:
            assert "code" in messages[0]
            assert "level" in messages[0]
            assert "text" in messages[0]
