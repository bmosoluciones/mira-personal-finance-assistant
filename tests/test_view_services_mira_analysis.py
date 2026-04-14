# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from pathlib import Path

import pytest

from mira.app.view_services import (
    MiraAnalysisMessageBuilder,
    MiraAnalysisService,
    MiraAnalysisViewStateBuilder,
    PresentationContext,
)
from mira.app.view_services._common import ANALYTICS_PALETTE, AnalyticsSemanticRole, WaterfallStepKind
from mira.db.database import Database


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "view-services-mira-analysis.db")
    database.connect()
    database.setting.set("language", "en")
    yield database
    database.close()


def test_mira_analysis_service_load_payload_delegates(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    service = MiraAnalysisService(db)
    expected = {"period": {"year": 2026, "month": 3}, "kpis": {"net": 50.0}}

    monkeypatch.setattr(db.report, "get_mira_master_report", lambda **_kwargs: expected)

    assert service.load_payload(year=2026, month=3) == expected


def test_mira_analysis_message_builder_builds_context_in_english(db: Database) -> None:
    builder = MiraAnalysisMessageBuilder(db)
    payload = {
        "kpis": {"net": 800.0},
        "comparisons": {
            "income": {
                "vs_previous": {"base": 1000.0, "variance": 100.0, "pct": 10.0},
                "vs_avg_3": {"base": 950.0, "variance": 150.0, "pct": 15.79},
                "vs_avg_6": {"base": 900.0, "variance": 200.0, "pct": 22.22},
                "vs_budget": {"base": 1050.0, "variance": 50.0, "pct": 4.76},
            },
            "expense_operational": {
                "vs_previous": {"base": 200.0, "variance": 100.0, "pct": 50.0},
                "vs_avg_3": {"base": 240.0, "variance": 60.0, "pct": 25.0},
                "vs_avg_6": {"base": 260.0, "variance": 40.0, "pct": 15.38},
                "vs_budget": {"base": 280.0, "variance": 20.0, "pct": 7.14},
            },
        },
        "metrics": {
            "expense_income_ratio": 0.27,
            "daily_living_cost": 10.0,
            "burn_rate_days": 80.0,
            "goal_completion_index_pct": 72.5,
            "mira_50_30_20": {"needs_pct": 20.0, "wants_pct": 7.0, "savings_pct": 10.0},
        },
        "budget": {
            "has_budget": True,
            "budget_code": "B2025",
            "missing_income_categories": ["Bonus"],
            "missing_expense_categories": ["Rent"],
        },
        "history_hints": ["A longer transaction history is required to complete 3-month and 6-month comparisons."],
    }

    context = builder.build_context_message(payload, language="en")

    assert context.startswith("Comparisons and context")
    assert "\nEfficiency report\n" in context
    assert "Expense-to-income ratio: 0.27." in context
    assert "Applied budget: B2025." in context
    assert "\nSecurity report\n" in context
    assert "Days of autonomy: 80.0." in context
    assert "\nPurpose report\n" in context
    assert "Completion index: 72.5%." in context


def test_mira_analysis_message_builder_builds_assistant_messages(db: Database) -> None:
    builder = MiraAnalysisMessageBuilder(db)
    payload = {
        "period": {"year": 2026, "month": 3},
        "kpis": {"net": 100.0},
        "comparisons": {},
        "budget": {"has_budget": False},
        "metrics": {},
        "advisor": {"messages": [{"text": "Keep saving."}]},
    }

    messages = builder.build_assistant_messages(payload, language="en")

    # First two messages are the Efficiency and Security sub-reports; no Purpose
    # because there is no goals data in the payload.
    assert len(messages) == 3
    assert messages[0][0].startswith("Efficiency report")
    assert messages[0][1] == "Efficiency report"
    assert messages[1][0].startswith("Security report")
    assert messages[1][1] == "Security report"
    # Advisor message is last and remains its own entry.
    assert messages[2][0] == "Keep saving."
    assert messages[2][1] == "MIRA Analysis"


def test_mira_analysis_message_builder_splits_sub_reports_into_separate_messages(db: Database) -> None:
    """Each sub-report section must produce its own short message, not a single block."""
    builder = MiraAnalysisMessageBuilder(db)
    payload = {
        "kpis": {"net": 500.0},
        "comparisons": {},
        "budget": {"has_budget": False},
        "metrics": {"goal_completion_index_pct": 50.0, "burn_rate_days": 30.0},
        "goals_summary": {"headline": "1 meta en progreso", "items": []},
        "advisor": {"messages": [{"text": "Msg A."}, {"text": "Msg B."}]},
    }

    messages = builder.build_assistant_messages(payload, language="en")

    texts = [m[0] for m in messages]
    titles = [m[1] for m in messages]

    # Three context sub-reports plus two advisor messages.
    assert len(messages) == 5

    # Efficiency is first and self-contained.
    assert texts[0].startswith("Efficiency report")
    assert "Security report" not in texts[0]
    assert "Purpose report" not in texts[0]
    assert titles[0] == "Efficiency report"

    # Security is second and self-contained.
    assert texts[1].startswith("Security report")
    assert "Efficiency report" not in texts[1]
    assert titles[1] == "Security report"

    # Purpose is third (goals data present).
    assert texts[2].startswith("Purpose report")
    assert titles[2] == "Purpose report"

    # Advisor messages remain individual short entries.
    assert texts[3] == "Msg A."
    assert texts[4] == "Msg B."


def test_mira_analysis_message_builder_omits_purpose_when_no_goals(db: Database) -> None:
    """Purpose message is only emitted when goal data is present."""
    builder = MiraAnalysisMessageBuilder(db)
    payload = {
        "kpis": {"net": 0.0},
        "comparisons": {},
        "budget": {"has_budget": False},
        "metrics": {},
        "goals_summary": {},
        "advisor": {"messages": []},
    }

    messages = builder.build_assistant_messages(payload, language="es")

    titles = [m[1] for m in messages]
    assert "Reporte de Propósito" not in titles
    # Efficiency and Security are always present.
    assert any(t == "Reporte de Eficiencia" for t in titles)
    assert any(t == "Reporte de Seguridad" for t in titles)


def test_mira_analysis_message_builder_no_message_contains_all_sub_reports(db: Database) -> None:
    """No single message should contain text from more than one sub-report section."""
    builder = MiraAnalysisMessageBuilder(db)
    payload = {
        "kpis": {"net": 200.0},
        "comparisons": {},
        "budget": {"has_budget": False},
        "metrics": {"goal_completion_index_pct": 80.0},
        "goals_summary": {"headline": "on track", "items": []},
        "advisor": {"messages": []},
    }

    messages = builder.build_assistant_messages(payload, language="en")

    for text, _ in messages:
        sections_present = sum(header in text for header in ("Efficiency report", "Security report", "Purpose report"))
        assert sections_present <= 1, f"Message contains multiple sub-report headers: {text!r}"


def test_mira_analysis_view_state_builder_shapes_cards_waterfall_and_trends(db: Database) -> None:
    builder = MiraAnalysisViewStateBuilder(db)
    payload = {
        "kpis": {
            "income": 1200.0,
            "expense_operational": 450.0,
            "net": 750.0,
            "savings": 200.0,
        },
        "comparisons": {
            "income": {
                "vs_previous": {"base": 1000.0, "variance": 200.0, "pct": 20.0},
                "vs_budget": {"base": 1100.0, "variance": 100.0, "pct": 9.09},
            },
            "expense_operational": {
                "vs_previous": {"base": 400.0, "variance": 50.0, "pct": 12.5},
                "vs_budget": {"base": 500.0, "variance": -50.0, "pct": -10.0},
            },
            "net": {
                "vs_previous": {"base": 600.0, "variance": 150.0, "pct": 25.0},
                "vs_avg_3": {"base": 700.0, "variance": 50.0, "pct": 7.14},
            },
            "savings": {
                "vs_previous": {"base": 150.0, "variance": 50.0, "pct": 33.33},
                "vs_avg_3": {"base": 180.0, "variance": 20.0, "pct": 11.11},
            },
        },
        "allocation": {
            "top_expense_categories": [
                {
                    "name": "Housing",
                    "amount": 300.0,
                    "children": [{"name": "Rent", "amount": 250.0}],
                }
            ],
            "top_tags": [
                {
                    "name": "home",
                    "amount": 180.0,
                    "children": [{"name": "Housing", "amount": 180.0}],
                }
            ],
        },
        "waterfall": {
            "steps": [
                {"kind": "income_total", "label": "Income", "value": 1200.0, "start": 0.0, "end": 1200.0},
                {"kind": "expense", "label": "Housing", "value": -300.0, "start": 1200.0, "end": 900.0},
                {"kind": "final_total", "label": "Final", "value": 900.0, "start": 0.0, "end": 900.0, "baseline": 0.0},
            ],
            "summary": {"status": "surplus", "net_after_expenses": 900.0, "final_balance": 900.0},
        },
        "ytd": [
            {"month": 1, "year": 2026, "income": 1000.0, "expense_operational": 400.0, "savings": 150.0, "net": 600.0},
            {"month": 2, "year": 2026, "income": 1200.0, "expense_operational": 450.0, "savings": 200.0, "net": 750.0},
        ],
        "historical_stacked": {
            "income": [
                {"period": "2026-01", "segments": {"Salary": 1000.0}},
                {"period": "2026-02", "segments": {"Salary": 1200.0}},
            ],
            "expense": [
                {"period": "2026-01", "segments": {"Housing": 300.0, "Food": 100.0}},
                {"period": "2026-02", "segments": {"Housing": 320.0, "Food": 130.0}},
            ],
        },
    }

    state = builder.build_state(payload)

    assert state.income_card.value == "1,200.00"
    assert state.income_card.primary_text.startswith("↑ 20.0%")
    assert state.expense_card.secondary_color == "#4EC9B0"
    assert "Housing" in state.categories.top_rows[0].detail_title
    assert state.categories.top_rows[0].detail_rows[0].amount_text == "250.00"
    assert "Income" in state.waterfall.legend_html
    assert ANALYTICS_PALETTE.waterfall_hex(WaterfallStepKind.INCOME_TOTAL) in state.waterfall.legend_html
    assert ANALYTICS_PALETTE.waterfall_hex(WaterfallStepKind.FINAL_TOTAL) in state.waterfall.legend_html
    assert "900.00" in state.waterfall.summary_text
    assert [label for label in state.ytd_chart.labels] == ["01/2026", "02/2026"]
    assert state.ytd_chart.series[0].color == ANALYTICS_PALETTE.semantic_hex(AnalyticsSemanticRole.INCOME)
    assert state.ytd_chart.series[1].color == ANALYTICS_PALETTE.semantic_hex(AnalyticsSemanticRole.EXPENSE)
    assert state.ytd_chart.series[2].color == ANALYTICS_PALETTE.semantic_hex(AnalyticsSemanticRole.NET)
    assert state.ytd_chart.series[3].color == ANALYTICS_PALETTE.semantic_hex(AnalyticsSemanticRole.SAVINGS)
    assert state.ytd_chart.series[0].points[-1][1] == pytest.approx(1200.0)
    assert [label for label in state.trend_charts["income"].labels] == ["2026-01", "2026-02"]
    assert state.trend_charts["expense"].series[0].color == ANALYTICS_PALETTE.palette_hex(0)
    assert state.trend_charts["expense"].series[1].color == ANALYTICS_PALETTE.palette_hex(1)
    assert state.trend_charts["expense"].series[0].values[0] == pytest.approx(300.0)


def test_mira_analysis_view_state_builder_and_message_builder_share_comparison_text(db: Database) -> None:
    message_builder = MiraAnalysisMessageBuilder(db)
    state_builder = MiraAnalysisViewStateBuilder(db)
    payload = {
        "kpis": {"income": 1100.0, "expense_operational": 300.0, "net": 800.0, "savings": 250.0},
        "comparisons": {
            "income": {"vs_previous": {"base": 1000.0, "variance": 100.0, "pct": 10.0}},
            "expense_operational": {},
            "net": {},
            "savings": {},
        },
        "budget": {"has_budget": False},
        "metrics": {},
        "waterfall": {"steps": [], "summary": {"status": "balanced"}},
        "allocation": {"top_expense_categories": [], "top_tags": []},
        "historical_stacked": {},
        "ytd": [],
    }

    view_state = state_builder.build_state(payload)
    context = message_builder.build_context_message(payload, language="en")

    assert view_state.income_card.primary_text in context


@pytest.mark.parametrize(
    ("step", "expected"),
    [
        ({"kind": "income_total"}, "Total net income"),
        ({"kind": "deficit_total"}, "Monthly deficit"),
        ({"kind": "surplus_total"}, "Monthly surplus"),
        ({"kind": "month_balance"}, "Month balance"),
        ({"kind": "financing"}, "Debt / prior savings"),
        ({"kind": "savings_allocation"}, "Allocated savings"),
        ({"kind": "final_total"}, "Monthly flow close"),
        ({"kind": "expense", "is_grouped": True}, "Other expenses"),
        (
            {"kind": "expense", "label": "Gastos con categoría inconsistente"},
            "Expenses with inconsistent category",
        ),
        ({"kind": "unknown_kind", "label": "Custom label"}, "Custom label"),
    ],
)
def test_mira_analysis_view_state_builder_waterfall_label_preserves_expected_labels(
    db: Database,
    step: dict[str, object],
    expected: str,
) -> None:
    builder = MiraAnalysisViewStateBuilder(db)
    context = PresentationContext.from_db(db)

    assert builder._waterfall_label(step, context) == expected
