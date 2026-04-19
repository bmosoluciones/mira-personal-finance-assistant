# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from conftest import opengl_import_error
from mira.db.database import Database


def _get_qapplication_or_xfail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        qtwidgets = importlib.import_module("PySide6.QtWidgets")
    except (ImportError, OSError) as exc:
        pytest.xfail(f"Qt runtime unavailable for MIRA analysis view test: {exc}")

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "mira-analysis-view.db")
    database.connect()
    database.setting.set("language", "en")
    yield database
    database.close()


@pytest.mark.skipif(
    opengl_import_error(), reason="PySide6.QtCharts requires OpenGL (not available in headless environments)"
)
def test_mira_analysis_context_message_respects_selected_language(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.mira_analysis")

    view = views_module.MiraAnalysisView(db)

    try:
        view._payload = {
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

        context = view._build_context_message()
        header = view._t(
            "mira.analysis.assistant.messages_header",
            "Mensaje MIRA {year:04d}-{month:02d}",
            params={"year": 2025, "month": 3},
        )

        assert header == "MIRA message 2025-03"
        assert context.startswith("Comparisons and context")
        assert "\nEfficiency report\n" in context
        assert "Expense-to-income ratio: 0.27." in context
        assert "Daily living cost:" in context
        assert "- Income:" in context
        assert "- Operating expenses:" in context
        assert "more vs previous month" in context
        assert "Applied budget: B2025." in context
        assert "Income vs budget:" in context
        assert "Expense vs budget:" in context
        assert "Budgeted income not received: Bonus." in context
        assert "Budgeted expenses not paid: Rent." in context
        assert "\nSecurity report\n" in context
        assert "Days of autonomy: 80.0." in context
        assert "Month status: surplus." in context
        assert "\nPurpose report\n" in context
        assert "Completion index: 72.5%." in context
        assert "Ingresos" not in context
        assert "Presupuesto" not in context
        assert "mes anterior" not in context
        assert "más" not in context
    finally:
        view.close()


@pytest.mark.skipif(
    opengl_import_error(), reason="PySide6.QtCharts requires OpenGL (not available in headless environments)"
)
def test_mira_analysis_context_message_includes_savings_goals_summary(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.mira_analysis")

    view = views_module.MiraAnalysisView(db)

    try:
        view._payload = {
            "kpis": {"net": 350.0},
            "comparisons": {},
            "budget": {"has_budget": False},
            "metrics": {"daily_living_cost": 12.5, "goal_completion_index_pct": 65.0},
            "goals_summary": {
                "headline": "Summary: 1 goals achieved and 2 in progress.",
                "items": [
                    "Emergency Fund: 65.0% complete, 350.00 USD remaining. Deadline: 2026-12-31.",
                    "Laptop: achieved (1200.00/1200.00 USD).",
                ],
            },
        }

        context = view._build_context_message()

        assert "\nPurpose report\n" in context
        assert "- Completion index: 65.0%." in context
        assert "- Summary: 1 goals achieved and 2 in progress." in context
        assert "- Emergency Fund: 65.0% complete, 350.00 USD remaining. Deadline: 2026-12-31." in context
        assert "- Laptop: achieved (1200.00/1200.00 USD)." in context
    finally:
        view.close()


@pytest.mark.skipif(
    opengl_import_error(), reason="PySide6.QtCharts requires OpenGL (not available in headless environments)"
)
def test_mira_analysis_view_binds_precomputed_view_state_and_keeps_drilldown(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.mira_analysis")

    view = views_module.MiraAnalysisView(db)

    try:
        view._payload = {
            "kpis": {
                "income": 1200.0,
                "expense_operational": 450.0,
                "net": 750.0,
                "savings": 200.0,
            },
            "comparisons": {
                "income": {"vs_previous": {"base": 1000.0, "variance": 200.0, "pct": 20.0}},
                "expense_operational": {"vs_previous": {"base": 500.0, "variance": -50.0, "pct": -10.0}},
                "net": {"vs_previous": {"base": 600.0, "variance": 150.0, "pct": 25.0}},
                "savings": {"vs_previous": {"base": 150.0, "variance": 50.0, "pct": 33.33}},
            },
            "allocation": {
                "top_expense_categories": [
                    {"name": "Housing", "amount": 300.0, "children": [{"name": "Rent", "amount": 250.0}]}
                ],
                "top_tags": [{"name": "home", "amount": 180.0, "children": [{"name": "Housing", "amount": 180.0}]}],
            },
            "waterfall": {
                "steps": [{"kind": "income_total", "label": "Income", "value": 1200.0, "start": 0.0, "end": 1200.0}],
                "summary": {"status": "balanced"},
            },
            "ytd": [
                {
                    "month": 1,
                    "year": 2026,
                    "income": 1000.0,
                    "expense_operational": 400.0,
                    "savings": 150.0,
                    "net": 600.0,
                }
            ],
            "historical_stacked": {"income": [{"period": "2026-01", "segments": {"Salary": 1000.0}}], "expense": []},
            "budget": {"has_budget": False},
            "metrics": {},
        }

        view._render_payload()
        view.refresh()

        assert view._view_state is not None
        assert view._top_categories_table.rowCount() == 1
        assert view._category_detail_table.rowCount() == 1
        assert "Housing" in view._category_detail_title.text()
        assert view._top_tags_table.rowCount() == 1
        assert view._tag_detail_table.rowCount() == 1
    finally:
        view.close()


@pytest.mark.skipif(
    opengl_import_error(), reason="PySide6.QtCharts requires OpenGL (not available in headless environments)"
)
def test_mira_analysis_honors_theme_palette_for_waterfall_labels(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.mira_analysis")

    view = views_module.MiraAnalysisView(db)

    try:
        legend_style = view._waterfall_legend.styleSheet()
        summary_style = view._waterfall_summary.styleSheet()

        assert "#D6DEE8" not in legend_style
        assert "#D6DEE8" not in summary_style
        assert "palette(midlight)" in legend_style
        assert "palette(midlight)" in summary_style
    finally:
        view.close()


@pytest.mark.skipif(
    opengl_import_error(), reason="PySide6.QtCharts requires OpenGL (not available in headless environments)"
)
def test_mira_analysis_ytd_and_trend_chart_legends_use_theme_palette(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.mira_analysis")

    view = views_module.MiraAnalysisView(db)

    try:
        view._payload = {
            "kpis": {
                "income": 1000.0,
                "expense_operational": 600.0,
                "net": 400.0,
                "savings": 100.0,
            },
            "comparisons": {},
            "budget": {"has_budget": False},
            "metrics": {},
            "ytd": [
                {
                    "month": 1,
                    "year": 2026,
                    "income": 1000.0,
                    "expense_operational": 600.0,
                    "net": 400.0,
                    "savings": 100.0,
                }
            ],
            "historical_stacked": {"income": [{"period": "2026-01", "segments": {"Salary": 1000.0}}]},
        }

        view._render_payload()

        ytd_chart = view._ytd_chart.chart()
        trend_chart = view._trend_chart.chart()
        theme_color = view._theme_color(view.foregroundRole(), "#DDD").name()

        assert ytd_chart is not None
        assert trend_chart is not None
        assert ytd_chart.legend().isVisible()
        assert trend_chart.legend().isVisible()
        assert ytd_chart.legend().labelColor().name() == theme_color
        assert trend_chart.legend().labelColor().name() == theme_color
    finally:
        view.close()
