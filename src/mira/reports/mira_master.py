# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Backend helpers for the MIRA Master Report."""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, cast

from mira.finance_summary import (
    FinancialSummary,
    build_savings_lookup,
    is_savings_transaction,
    summarize_financial_kpis,
)
from mira.transaction_kinds import TransactionType, is_balance_adjustment_transaction

# Financial analysis helper functions utilize Python 3.12 structural pattern
# matching (match/case) for better readability of range-based classifications
# and multi-signal trends.

_REFUND_KEYWORDS = ("reembolso", "refund", "devolucion", "devolución")
_DEBT_KEYWORDS = ("deuda", "prestamo", "préstamo", "loan", "tarjeta", "credit")
_MAX_WATERFALL_EXPENSE_STEPS = 6


# ---------------------------------------------------------------------------
# Typed data-transfer objects (DTOs)
# ---------------------------------------------------------------------------


@dataclass
class GoalRow:
    """Parsed, normalised representation of a single savings goal."""

    name: str
    currency: str
    target_amount: float
    current_amount: float
    remaining_amount: float
    progress_ratio: float
    progress_pct: float
    target_date: str | None
    parsed_target_date: date | None
    achieved: bool


@dataclass
class GoalAnalysisResult:
    """Output of :class:`GoalProgressAnalyzer`."""

    goal_rows: list[GoalRow]
    completed_goals: list[GoalRow]
    active_goals: list[GoalRow]
    goals_summary: dict[str, Any]
    report_period_end: date


@dataclass
class SummaryMetrics:
    """Monthly financial KPIs: income, expenses, savings, net, debt, refunds."""

    income: float
    expense_operational: float
    savings: float
    net: float
    debt_payment: float
    refunds: float


@dataclass
class AvgMetrics:
    """Rolling-average metrics for income, expenses, savings and net.

    Values are ``None`` when there is insufficient history.
    """

    income: float | None
    expense_operational: float | None
    savings: float | None
    net: float | None


@dataclass
class ComparisonResult:
    """Variance, percentage-change and directional signal between two values."""

    base: float | None
    variance: float | None
    pct: float | None
    signal: str


@dataclass
class BudgetContextData:
    """Budget availability and completeness for the current reporting period."""

    has_budget: bool
    budget_id: int | None
    budget_code: str | None
    income: float
    expense_operational: float
    is_complete_for_period: bool
    missing_income_categories: list[str] = field(default_factory=list)
    missing_expense_categories: list[str] = field(default_factory=list)


@dataclass
class LifestyleInflationMetrics:
    """Expense-growth-relative-to-income indicator."""

    income_growth_pct: float | None
    expense_growth_pct: float | None
    expense_to_income_growth_ratio: float | None
    is_applicable: bool
    is_alert: bool


@dataclass
class SavingsEfficiencyMetrics:
    """How effectively available surplus is routed to savings goals."""

    surplus_amount: float
    goal_funding_amount: float
    goal_funding_efficiency_pct: float | None
    surplus_leakage_amount: float
    has_surplus_leakage_alert: bool


@dataclass
class FreedomMarginMetrics:
    """Income-minus-expenses margin as a fraction of income."""

    pct: float | None
    zone: str | None
    label: str | None
    is_red_alert: bool


@dataclass
class GoalContributionMetrics:
    """Savings-goal contribution counts and amounts for the current period."""

    count: int
    amount: float
    by_goal: dict[str, float]


@dataclass
class Mira503020:
    """50/30/20 budget rule percentage breakdown and deviation score."""

    needs_pct: float
    wants_pct: float
    savings_pct: float
    deviation_pct: float


@dataclass
class CreditCardStats:
    """Credit-card expense vs. internal payment stats for one month."""

    expense_count: int
    expense_amount: float
    payment_count: int
    payment_amount: float
    gap_amount: float


@dataclass
class ReportInputs:
    """All raw inputs required to produce the MIRA master report payload.

    Replaces the long keyword-argument list previously passed to
    ``build_report_payload`` and ``ReportMetricsCalculator``.
    """

    year: int
    month: int
    month_transactions: list[dict[str, Any]]
    month_transactions_raw: list[dict[str, Any]]
    previous_transactions: list[dict[str, Any]]
    trailing_3: list[list[dict[str, Any]]]
    comparison_trailing_6: list[tuple[int, int, list[dict[str, Any]]]]
    historical_6: list[tuple[int, int, list[dict[str, Any]]]]
    ytd_months: list[tuple[int, int, list[dict[str, Any]]]]
    categories: list[dict[str, Any]]
    tags_by_tx: dict[int, list[dict[str, Any]]]
    budget: dict[str, Any] | None
    budget_monthly_by_type: dict[str, dict[str, float]] | None
    budget_category_rows: list[dict[str, Any]] | None
    accounts: list[dict[str, Any]]
    account_balance_total: float
    savings_goals: list[dict[str, Any]]
    relevance_threshold: float = 0.10
    language: str = "en"
    category_relations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MetricsResult:
    """All computed metrics returned by :class:`ReportMetricsCalculator`.

    All sub-structures are typed dataclasses — no stringly-typed dict access
    is needed anywhere in :class:`WaterfallChartBuilder`,
    :class:`ReportMessageGenerator`, or the ``build_report_payload`` orchestrator.
    """

    current_summary: SummaryMetrics
    previous_summary: SummaryMetrics
    avg_3: AvgMetrics
    avg_6: AvgMetrics
    ytd: list[dict[str, Any]]
    credit_card: CreditCardStats
    top_category_totals: dict[str, float]
    top_category_children: dict[str, dict[str, float]]
    tag_totals: dict[str, float]
    tag_children: dict[str, dict[str, float]]
    top_categories: list[tuple[str, float]]
    top_tags: list[tuple[str, float]]
    weekend_total: float
    weekend_days: dict[str, float]
    daily_expense_totals: dict[str, float]
    small_total: float
    income_by_root: dict[str, float]
    waterfall_category_totals: list[tuple[str, float]]
    normal_waterfall_categories: list[tuple[str, float]]
    displayed_waterfall_categories: list[tuple[str, float]]
    remaining_waterfall_categories: list[tuple[str, float]]
    inconsistent_waterfall_entry: tuple[str, float] | None
    stacked_6: dict[str, list[dict[str, Any]]]
    budget_context: BudgetContextData
    comparisons: dict[str, dict[str, ComparisonResult | None]]
    income_vs_budget: ComparisonResult | None
    expense_vs_budget: ComparisonResult | None
    income_vs_previous: ComparisonResult
    expense_vs_previous: ComparisonResult
    lifestyle_inflation_metrics: LifestyleInflationMetrics
    savings_efficiency_metrics: SavingsEfficiencyMetrics
    freedom_margin_metrics: FreedomMarginMetrics
    goal_contribution_metrics: GoalContributionMetrics
    generic_analysis: dict[str, Any]
    history_hints: list[str]
    income_total: float
    total_expense: float
    debt_payment_total: float
    debt_payment_income_pct: float | None
    debt_payment_expense_pct: float | None
    savings_rate: float | None
    expense_income_ratio: float | None
    avg_daily_expense: float
    burn_days: float | None
    daily_living_cost: float
    goal_completion_index_pct: float | None
    concentration_pct: float | None
    dependence_pct: float | None
    net_after_expenses: float
    top_total: float
    days_in_month: int
    mira_50_30_20: Mira503020


def _normalize_report_language(language: str | None) -> str:
    return "es" if str(language or "").strip().lower() == "es" else "en"


def _report_text(
    language: str,
    es: str,
    en: str,
    *,
    params: dict[str, Any] | None = None,
) -> str:
    text = {"es": es, "en": en}.get(language) or en
    if params:
        return text.format(**params)
    return text


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = (year * 12 + (month - 1)) + delta
    return idx // 12, (idx % 12) + 1


def pct_change(current: float, previous: float) -> float | None:
    if abs(previous) < 1e-9:
        return None
    return ((current - previous) / abs(previous)) * 100.0


def safe_ratio(numerator: float, denominator: float) -> float | None:
    if abs(denominator) < 1e-9:
        return None
    return numerator / denominator


def _tx_text(tx: dict[str, Any]) -> str:
    category = str(tx.get("category") or "").casefold()
    description = str(tx.get("description") or "").casefold()
    note = str(tx.get("note") or "").casefold()
    return f"{category} {description} {note}"


def _month_summary(transactions: list[dict[str, Any]], savings_lookup) -> SummaryMetrics:
    summary: FinancialSummary = summarize_financial_kpis(transactions, savings_lookup)
    debt_payment_total = 0.0
    refunds_total = 0.0

    for tx in transactions:
        tx_type = str(tx.get("type") or "")
        amount = float(tx.get("amount") or 0.0)
        text = _tx_text(tx)

        if tx_type == TransactionType.INCOME:
            if any(keyword in text for keyword in _REFUND_KEYWORDS):
                refunds_total += amount
            continue

        if tx_type != TransactionType.EXPENSE:
            continue

        if is_savings_transaction(tx, savings_lookup):
            continue

        if any(keyword in text for keyword in _DEBT_KEYWORDS):
            debt_payment_total += amount
    return SummaryMetrics(
        income=float(summary.income),
        expense_operational=float(summary.expense),
        savings=float(summary.savings),
        debt_payment=round(debt_payment_total, 2),
        refunds=round(refunds_total, 2),
        net=float(summary.net),
    )


def _trend_signal(section: str, variance: float | None) -> str:
    if variance is None or abs(variance) < 0.005:
        return "neutral"
    if section in {"income", "savings", "net"}:
        return "up" if variance > 0 else "down"
    return "up" if variance > 0 else "down"


def _message_level_priority(level: str) -> int:
    return {"critical": 0, "warning": 1, "info": 2, "success": 3}.get(level, 4)


def _build_lifestyle_inflation_metrics(
    income_growth_pct: float | None,
    expense_growth_pct: float | None,
) -> LifestyleInflationMetrics:
    ratio = None
    safe_income_growth = income_growth_pct if income_growth_pct is not None else 0.0
    if (
        income_growth_pct is not None
        and expense_growth_pct is not None
        and income_growth_pct > 0
        and expense_growth_pct >= 0
    ):
        ratio = expense_growth_pct / income_growth_pct

    is_applicable = income_growth_pct is not None and income_growth_pct >= 10.0
    is_alert = (
        is_applicable and expense_growth_pct is not None and expense_growth_pct >= max(0.0, safe_income_growth * 0.9)
    )
    return LifestyleInflationMetrics(
        income_growth_pct=round(income_growth_pct, 2) if income_growth_pct is not None else None,
        expense_growth_pct=round(expense_growth_pct, 2) if expense_growth_pct is not None else None,
        expense_to_income_growth_ratio=round(ratio, 2) if ratio is not None else None,
        is_applicable=is_applicable,
        is_alert=is_alert,
    )


def _build_goal_contribution_metrics(
    month_transactions: list[dict[str, Any]],
    savings_goals: list[dict[str, Any]],
) -> GoalContributionMetrics:
    goal_category_names: dict[int, str] = {}
    for goal in savings_goals:
        category_id = goal.get("category_id")
        if category_id is None:
            continue
        try:
            goal_category_names[int(category_id)] = str(goal.get("name") or "").strip()
        except (TypeError, ValueError):
            continue

    contributions_by_goal: dict[str, float] = defaultdict(float)
    contribution_count = 0
    contribution_total = 0.0
    for tx in month_transactions:
        if str(tx.get("type") or "") != "expense":
            continue
        category_id = tx.get("category_id")
        if category_id is None:
            continue
        try:
            goal_name = goal_category_names[int(category_id)]
        except (KeyError, TypeError, ValueError):
            continue
        amount = float(tx.get("amount") or 0.0)
        if amount <= 0:
            continue
        contributions_by_goal[goal_name] += amount
        contribution_total += amount
        contribution_count += 1

    return GoalContributionMetrics(
        count=contribution_count,
        amount=round(contribution_total, 2),
        by_goal={name: round(amount, 2) for name, amount in sorted(contributions_by_goal.items())},
    )


def _build_savings_efficiency_metrics(
    *,
    net_amount: float,
    goal_contribution_amount: float,
    has_active_goals: bool,
) -> SavingsEfficiencyMetrics:
    efficiency_pct = None
    if net_amount > 0:
        efficiency_pct = (goal_contribution_amount / net_amount) * 100.0

    leakage_amount = max(0.0, net_amount - goal_contribution_amount) if net_amount > 0 else 0.0
    has_surplus_leakage_alert = net_amount > 0 and has_active_goals and goal_contribution_amount <= 0.005
    return SavingsEfficiencyMetrics(
        surplus_amount=round(net_amount, 2) if net_amount > 0 else 0.0,
        goal_funding_amount=round(goal_contribution_amount, 2),
        goal_funding_efficiency_pct=round(efficiency_pct, 2) if efficiency_pct is not None else None,
        surplus_leakage_amount=round(leakage_amount, 2),
        has_surplus_leakage_alert=has_surplus_leakage_alert,
    )


def _build_freedom_margin_metrics(income_total: float, total_expense: float) -> FreedomMarginMetrics:
    if income_total <= 0:
        return FreedomMarginMetrics(pct=None, zone=None, label=None, is_red_alert=False)

    freedom_margin_pct = ((income_total - total_expense) / income_total) * 100.0

    match freedom_margin_pct:
        case p if p >= 30.0:
            zone = "fast_track"
            label = "via_rapida"
        case p if p >= 10.0:
            zone = "construction_zone"
            label = "zona_de_construccion"
        case p if p >= 1.0:
            zone = "balance_point"
            label = "punto_de_equilibrio"
        case _:
            zone = "red_alert"
            label = "alerta_roja"

    return FreedomMarginMetrics(
        pct=round(freedom_margin_pct, 2),
        zone=zone,
        label=label,
        is_red_alert=freedom_margin_pct < 0,
    )


def _build_goal_completion_index(goal_rows: list[GoalRow], active_goals: list[GoalRow]) -> float | None:
    if active_goals:
        return round(sum(goal.progress_pct for goal in active_goals) / len(active_goals), 2)
    if goal_rows:
        return 100.0
    return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _stddev(values: list[float]) -> float | None:
    if len(values) < 2:
        return 0.0 if values else None
    avg = _mean(values)
    if avg is None:
        return None
    variance = sum((value - avg) ** 2 for value in values) / len(values)
    return variance**0.5


def _classify_pct_trend(
    pct_value: float | None,
    *,
    stable_threshold: float = 3.0,
) -> str:
    if pct_value is None:
        return "insufficient_history"
    if pct_value >= stable_threshold:
        return "up"
    if pct_value <= -stable_threshold:
        return "down"
    return "stable"


def _build_trend_metric(current_value: float, previous_value: float | None) -> dict[str, Any]:
    pct_value = pct_change(current_value, previous_value) if previous_value is not None else None
    return {
        "current": round(current_value, 2),
        "previous": round(previous_value, 2) if previous_value is not None else None,
        "pct": round(pct_value, 2) if pct_value is not None else None,
        "direction": _classify_pct_trend(pct_value),
    }


def _project_next_value(series: list[float]) -> float | None:
    if not series:
        return None
    if len(series) == 1:
        return series[0]
    deltas = [series[index] - series[index - 1] for index in range(1, len(series))]
    avg_delta = _mean(deltas)
    if avg_delta is None:
        return series[-1]
    return series[-1] + avg_delta


def _build_financial_balance_metric(income_total: float, total_expense: float) -> dict[str, Any]:
    if income_total <= 0:
        return {"classification": "insufficient_income", "gap_amount": round(income_total - total_expense, 2)}

    freedom_margin_pct = ((income_total - total_expense) / income_total) * 100.0
    if freedom_margin_pct < 0:
        classification = "critical"
    elif freedom_margin_pct < 10.0:
        classification = "tight"
    else:
        classification = "healthy"
    return {
        "classification": classification,
        "gap_amount": round(income_total - total_expense, 2),
        "freedom_margin_pct": round(freedom_margin_pct, 2),
    }


def _build_cashflow_stability_metric(net_series: list[float], income_series: list[float]) -> dict[str, Any]:
    if len(net_series) < 3:
        return {"classification": "insufficient_history", "volatility_pct": None}
    avg_income = _mean([value for value in income_series if value > 0]) or 0.0
    if avg_income <= 0:
        return {"classification": "insufficient_income", "volatility_pct": None}
    changes = [abs(net_series[index] - net_series[index - 1]) for index in range(1, len(net_series))]
    avg_change = _mean(changes) or 0.0
    volatility_pct = (avg_change / avg_income) * 100.0
    if volatility_pct >= 12.0:
        classification = "volatile"
    elif volatility_pct >= 6.0:
        classification = "watch"
    else:
        classification = "stable"
    return {"classification": classification, "volatility_pct": round(volatility_pct, 2)}


def _build_spending_efficiency_metric(income_total: float, total_expense: float) -> dict[str, Any]:
    if income_total <= 0:
        return {"classification": "insufficient_income", "spent_pct": None, "retained_pct": None}
    spent_pct = (total_expense / income_total) * 100.0
    retained_pct = max(-9999.0, 100.0 - spent_pct)

    match spent_pct:
        case p if p >= 100.0:
            classification = "strained"
        case p if p >= 90.0:
            classification = "fragile"
        case p if p >= 70.0:
            classification = "watch"
        case _:
            classification = "efficient"

    return {
        "classification": classification,
        "spent_pct": round(spent_pct, 2),
        "retained_pct": round(retained_pct, 2),
    }


def _build_expense_drift_metric(expense_series: list[float]) -> dict[str, Any]:
    if len(expense_series) < 4:
        return {"direction": "insufficient_history", "pct": None}
    split_index = max(1, len(expense_series) // 2)
    earlier_avg = _mean(expense_series[:split_index])
    recent_avg = _mean(expense_series[split_index:])
    pct_value = pct_change(recent_avg or 0.0, earlier_avg) if earlier_avg is not None else None
    return {
        "direction": _classify_pct_trend(pct_value, stable_threshold=5.0),
        "pct": round(pct_value, 2) if pct_value is not None else None,
    }


def _build_deficit_risk_metric(
    *,
    current_net: float,
    income_trend: dict[str, Any],
    expense_trend: dict[str, Any],
    projected_net: float | None,
) -> dict[str, Any]:
    score = 10.0
    if current_net < 0:
        score += 35.0
    if str(expense_trend.get("direction") or "") == "up":
        score += 25.0
    if str(income_trend.get("direction") or "") == "down":
        score += 20.0
    if projected_net is not None and projected_net < 0:
        score += 25.0

    match score:
        case s if s >= 70.0:
            classification = "high"
        case s if s >= 40.0:
            classification = "medium"
        case _:
            classification = "low"

    return {"classification": classification, "score": round(min(score, 100.0), 2)}


def _build_income_fragility_metric(income_series: list[float], income_trend: dict[str, Any]) -> dict[str, Any]:
    positive_income = [value for value in income_series if value > 0]
    avg_income = _mean(positive_income) or 0.0
    if avg_income <= 0:
        return {"classification": "no_income", "volatility_pct": None}
    income_stddev = _stddev(positive_income) or 0.0
    volatility_pct = (income_stddev / avg_income) * 100.0
    score = volatility_pct
    if str(income_trend.get("direction") or "") == "down":
        score += 25.0

    match score:
        case s if s >= 35.0:
            classification = "high"
        case s if s >= 18.0:
            classification = "medium"
        case _:
            classification = "low"

    return {"classification": classification, "volatility_pct": round(volatility_pct, 2)}


def _build_financial_momentum_metric(
    *,
    gap_trend: dict[str, Any],
    income_trend: dict[str, Any],
    expense_trend: dict[str, Any],
) -> dict[str, Any]:
    gap_dir = str(gap_trend.get("direction") or "")
    income_dir = str(income_trend.get("direction") or "")
    expense_dir = str(expense_trend.get("direction") or "")

    match (gap_dir, income_dir, expense_dir):
        case ("up", "up", "up"):
            direction = "neutral"
        case ("up", _, "up") if income_dir != "up":
            direction = "negative"
        case ("up", _, _):
            direction = "positive"
        case ("down", _, _):
            direction = "negative"
        case (_, _, "up") if income_dir != "up":
            direction = "negative"
        case _:
            direction = "neutral"

    return {"direction": direction}


def _build_week_spread_metric(total_expense: float, daily_expense_totals: dict[str, float]) -> dict[str, Any]:
    if total_expense <= 0 or not daily_expense_totals:
        return {"classification": "no_expense", "top3_share_pct": None, "active_days": 0}
    top3_share = (sum(sorted(daily_expense_totals.values(), reverse=True)[:3]) / total_expense) * 100.0
    if top3_share >= 60.0:
        classification = "concentrated"
    elif top3_share >= 35.0:
        classification = "clustered"
    else:
        classification = "distributed"
    return {
        "classification": classification,
        "top3_share_pct": round(top3_share, 2),
        "active_days": len(daily_expense_totals),
    }


def _build_spending_pattern_metric(
    *,
    total_expense: float,
    daily_expense_totals: dict[str, float],
    expense_trend: dict[str, Any],
) -> dict[str, Any]:
    spread = _build_week_spread_metric(total_expense, daily_expense_totals)
    spread_classification = str(spread.get("classification") or "")
    if spread_classification == "concentrated":
        classification = "impulsive"
    elif spread_classification == "clustered" or str(expense_trend.get("direction") or "") == "up":
        classification = "irregular"
    else:
        classification = "consistent"
    return {
        "classification": classification,
        "week_spread": spread,
    }


def _build_runway_trend_metric(
    *,
    account_balance_total: float,
    current_expense_total: float,
    previous_expense_total: float,
    current_days: int,
    previous_days: int,
) -> dict[str, Any]:
    if account_balance_total <= 0 or current_expense_total <= 0 or previous_expense_total <= 0:
        return {"direction": "insufficient_history", "pct": None}
    current_runway = account_balance_total / (current_expense_total / current_days)
    previous_runway = account_balance_total / (previous_expense_total / previous_days)
    pct_value = pct_change(current_runway, previous_runway)
    direction = _classify_pct_trend(pct_value, stable_threshold=5.0)
    return {
        "direction": direction,
        "pct": round(pct_value, 2) if pct_value is not None else None,
        "current_days": round(current_runway, 2),
        "previous_days": round(previous_runway, 2),
    }


def _build_expense_control_metric(
    *,
    expense_trend: dict[str, Any],
    expense_drift: dict[str, Any],
    spending_pattern: dict[str, Any],
) -> dict[str, Any]:
    pattern = str(spending_pattern.get("classification") or "")
    trend = str(expense_trend.get("direction") or "")
    drift = str(expense_drift.get("direction") or "")

    match (trend, drift, pattern):
        case ("up", "up", _) | ("up", _, "impulsive"):
            classification = "out_of_control"
        case ("down", _, "consistent"):
            classification = "in_control"
        case _:
            classification = "watch"

    return {"classification": classification}


def _build_income_control_metric(income_fragility: dict[str, Any]) -> dict[str, Any]:
    fragility = str(income_fragility.get("classification") or "")
    if fragility == "high":
        classification = "fragile"
    elif fragility == "medium":
        classification = "variable"
    elif fragility == "low":
        classification = "predictable"
    else:
        classification = "insufficient_history"
    return {"classification": classification}


def _build_cashflow_projection_metric(income_series: list[float], expense_series: list[float]) -> dict[str, Any]:
    projected_income = _project_next_value(income_series[-3:] if len(income_series) >= 3 else income_series)
    projected_expense = _project_next_value(expense_series[-3:] if len(expense_series) >= 3 else expense_series)
    if projected_income is None or projected_expense is None:
        return {
            "classification": "insufficient_history",
            "projected_income": None,
            "projected_expense": None,
            "projected_net": None,
        }
    projected_net = projected_income - projected_expense
    if projected_net < -0.5:
        classification = "deficit"
    elif projected_net > 0.5:
        classification = "surplus"
    else:
        classification = "balanced"
    return {
        "classification": classification,
        "projected_income": round(projected_income, 2),
        "projected_expense": round(projected_expense, 2),
        "projected_net": round(projected_net, 2),
    }


def _build_sustainability_score(
    *,
    financial_balance: dict[str, Any],
    cashflow_stability: dict[str, Any],
    deficit_risk: dict[str, Any],
    income_fragility: dict[str, Any],
) -> dict[str, Any]:
    score = 50.0
    balance_classification = str(financial_balance.get("classification") or "")
    if balance_classification == "healthy":
        score += 20.0
    elif balance_classification == "tight":
        score -= 5.0
    elif balance_classification == "critical":
        score -= 25.0

    stability_classification = str(cashflow_stability.get("classification") or "")
    if stability_classification == "stable":
        score += 15.0
    elif stability_classification == "volatile":
        score -= 15.0

    score -= float(deficit_risk.get("score") or 0.0) * 0.20
    fragility_classification = str(income_fragility.get("classification") or "")
    if fragility_classification == "high":
        score -= 12.0
    elif fragility_classification == "medium":
        score -= 6.0

    score = max(0.0, min(score, 100.0))
    if score >= 70.0:
        classification = "strong"
    elif score >= 45.0:
        classification = "watch"
    else:
        classification = "fragile"
    return {"score": round(score, 2), "classification": classification}


class GoalProgressAnalyzer:
    """Parses, sorts, and summarises savings-goal progress for one reporting period."""

    def __init__(
        self,
        savings_goals: list[dict[str, Any]],
        year: int,
        month: int,
        *,
        language: str = "en",
    ) -> None:
        self._goals = savings_goals
        self._year = year
        self._month = month
        self._language = _normalize_report_language(language)

    def _t(self, es: str, en: str, *, params: dict[str, Any] | None = None) -> str:
        return _report_text(self._language, es, en, params=params)

    def analyze(self) -> GoalAnalysisResult:
        """Parse raw goal dicts into GoalRow instances and return a GoalAnalysisResult."""
        default_goal_name = self._t("Meta", "Goal")
        report_period_end = month_bounds(self._year, self._month)[1]

        goal_rows: list[GoalRow] = []
        for raw_goal in self._goals:
            goal_name = str(raw_goal.get("name") or default_goal_name)
            target_amount = float(raw_goal.get("target_amount") or 0.0)
            current_amount = float(raw_goal.get("current_amount") or 0.0)
            remaining_amount = max(0.0, float(raw_goal.get("remaining_amount") or (target_amount - current_amount)))
            progress_ratio = float(raw_goal.get("progress") or 0.0)
            target_date_text = str(raw_goal.get("target_date") or "").strip()
            parsed_target_date = None
            if target_date_text:
                try:
                    parsed_target_date = date.fromisoformat(target_date_text)
                except ValueError:
                    parsed_target_date = None
            goal_rows.append(
                GoalRow(
                    name=goal_name,
                    currency=str(raw_goal.get("currency") or "").strip(),
                    target_amount=round(target_amount, 2),
                    current_amount=round(current_amount, 2),
                    remaining_amount=round(remaining_amount, 2),
                    progress_ratio=progress_ratio,
                    progress_pct=round(min(progress_ratio * 100.0, 100.0), 1),
                    target_date=target_date_text or None,
                    parsed_target_date=parsed_target_date,
                    achieved=remaining_amount <= 0.005 or progress_ratio >= 1.0,
                )
            )

        completed_goals = [g for g in goal_rows if g.achieved]
        active_goals = [g for g in goal_rows if not g.achieved]
        active_goals.sort(
            key=lambda g: (
                g.parsed_target_date is None,
                g.parsed_target_date or date.max,
                g.remaining_amount,
                g.name.casefold(),
            )
        )

        goals_summary_items: list[str] = []
        if goal_rows:
            for goal in active_goals[:2] + completed_goals[:1]:
                deadline_suffix = (
                    self._t(
                        " Meta: {target_date}.",
                        " Deadline: {target_date}.",
                        params={"target_date": goal.target_date},
                    )
                    if goal.target_date
                    else ""
                )
                if goal.achieved:
                    goals_summary_items.append(
                        self._t(
                            "{goal_name}: cumplida ({current:.2f}/{target:.2f} {currency}).",
                            "{goal_name}: achieved ({current:.2f}/{target:.2f} {currency}).",
                            params={
                                "goal_name": goal.name,
                                "current": goal.current_amount,
                                "target": goal.target_amount,
                                "currency": goal.currency,
                            },
                        )
                    )
                else:
                    goals_summary_items.append(
                        self._t(
                            "{goal_name}: {progress:.1f}% completada, faltan {remaining:.2f} {currency}.{deadline}",
                            "{goal_name}: {progress:.1f}% complete, {remaining:.2f} {currency} remaining.{deadline}",
                            params={
                                "goal_name": goal.name,
                                "progress": goal.progress_pct,
                                "remaining": goal.remaining_amount,
                                "currency": goal.currency,
                                "deadline": deadline_suffix,
                            },
                        )
                    )

        goals_summary = {
            "total_goals": len(goal_rows),
            "completed_goals": len(completed_goals),
            "active_goals": len(active_goals),
            "headline": (
                self._t(
                    "No tienes metas de ahorro configuradas todavía.",
                    "You do not have any savings goals configured yet.",
                )
                if not goal_rows
                else self._t(
                    "Resumen: {completed} metas cumplidas y {active} en progreso.",
                    "Summary: {completed} goals achieved and {active} in progress.",
                    params={"completed": len(completed_goals), "active": len(active_goals)},
                )
            ),
            "items": goals_summary_items,
        }

        return GoalAnalysisResult(
            goal_rows=goal_rows,
            completed_goals=completed_goals,
            active_goals=active_goals,
            goals_summary=goals_summary,
            report_period_end=report_period_end,
        )


class ReportMetricsCalculator:
    """Computes KPIs, comparisons, and advanced financial metrics from transaction data."""

    def __init__(self, inputs: ReportInputs, goal_result: GoalAnalysisResult) -> None:
        self._inputs = inputs
        self._goal_result = goal_result
        self._language = _normalize_report_language(inputs.language)
        self._savings_lookup = build_savings_lookup(inputs.categories)
        self._uncategorized_label = _report_text(self._language, "(sin categoría)", "(uncategorized)")
        self._untagged_label = _report_text(self._language, "(sin tag)", "(untagged)")
        self._other_expenses_label = _report_text(self._language, "Otros gastos", "Other expenses")
        self._inconsistent_expense_label = _report_text(
            self._language,
            "Gastos con categoría inconsistente",
            "Expenses with inconsistent category",
        )

    def _t(self, es: str, en: str, *, params: dict[str, Any] | None = None) -> str:
        return _report_text(self._language, es, en, params=params)

    def _compute_credit_card_stats(self) -> CreditCardStats:
        credit_account_ids = {
            int(account["id"])
            for account in self._inputs.accounts
            if account.get("id") is not None and str(account.get("account_type") or "") == "credit"
        }
        expense_count = 0
        expense_amount = 0.0
        payment_count = 0
        payment_amount = 0.0
        for tx in self._inputs.month_transactions_raw:
            account_id_raw = tx.get("account_id")
            if account_id_raw is None:
                continue
            try:
                account_id = int(account_id_raw)
            except (TypeError, ValueError):
                continue
            if account_id not in credit_account_ids:
                continue
            if is_balance_adjustment_transaction(tx):
                continue
            tx_type = str(tx.get("type") or "")
            amount = float(tx.get("amount") or 0.0)
            is_transfer = int(tx.get("is_transfer") or 0) == 1
            if tx_type == TransactionType.EXPENSE and not is_transfer:
                expense_count += 1
                expense_amount += amount
            elif tx_type == TransactionType.INCOME and is_transfer:
                payment_count += 1
                payment_amount += amount
        return CreditCardStats(
            expense_count=expense_count,
            expense_amount=round(expense_amount, 2),
            payment_count=payment_count,
            payment_amount=round(payment_amount, 2),
            gap_amount=round(expense_amount - payment_amount, 2),
        )

    def _compute_trailing_data(
        self,
    ) -> tuple[AvgMetrics, AvgMetrics, list[SummaryMetrics]]:
        trailing_3_summaries = [_month_summary(items, self._savings_lookup) for items in self._inputs.trailing_3]
        trailing_6_summaries = [
            _month_summary(items, self._savings_lookup) for _y, _m, items in self._inputs.comparison_trailing_6
        ]
        historical_6_summaries = [
            _month_summary(items, self._savings_lookup) for _y, _m, items in self._inputs.historical_6
        ]

        def _avg(summaries: list[SummaryMetrics], attr: str) -> float | None:
            if not summaries:
                return None
            return round(sum(getattr(s, attr) for s in summaries) / len(summaries), 2)

        avg_3 = AvgMetrics(
            income=_avg(trailing_3_summaries, "income"),
            expense_operational=_avg(trailing_3_summaries, "expense_operational"),
            savings=_avg(trailing_3_summaries, "savings"),
            net=_avg(trailing_3_summaries, "net"),
        )
        avg_6 = AvgMetrics(
            income=_avg(trailing_6_summaries, "income"),
            expense_operational=_avg(trailing_6_summaries, "expense_operational"),
            savings=_avg(trailing_6_summaries, "savings"),
            net=_avg(trailing_6_summaries, "net"),
        )
        return avg_3, avg_6, historical_6_summaries

    def _compute_ytd(self) -> list[dict[str, Any]]:
        ytd: list[dict[str, Any]] = []
        cum_income = 0.0
        cum_expense = 0.0
        cum_savings = 0.0
        cum_net = 0.0
        for ym_year, ym_month, txs in self._inputs.ytd_months:
            s = _month_summary(txs, self._savings_lookup)
            cum_income += s.income
            cum_expense += s.expense_operational
            cum_savings += s.savings
            cum_net += s.net
            ytd.append(
                {
                    "year": ym_year,
                    "month": ym_month,
                    "income": round(cum_income, 2),
                    "expense_operational": round(cum_expense, 2),
                    "savings": round(cum_savings, 2),
                    "net": round(cum_net, 2),
                }
            )
        return ytd

    def _build_category_metadata(self) -> tuple[dict[int, Any], dict[str, Any], dict[str, Any]]:
        by_id: dict[int, Any] = {int(cat["id"]): cat for cat in self._inputs.categories if cat.get("id") is not None}
        roots_meta: dict[str, dict[str, Any]] = {}
        root_rollup_meta: dict[str, dict[str, Any]] = {}
        for cat in self._inputs.categories:
            name = str(cat.get("name") or "").strip()
            if not name:
                continue
            parent_id = cat.get("parent_id")
            root_cat = cat
            if parent_id is not None and int(parent_id) in by_id:
                root_cat = by_id[int(parent_id)]
            root = str(root_cat.get("name") or name)
            root_type = str(root_cat.get("type") or cat.get("type") or "")
            root_is_savings = bool(int(root_cat.get("is_savings") or 0)) or bool(int(cat.get("is_savings") or 0))
            roots_meta[name.casefold()] = {
                "root": root,
                "color": str(cat.get("color") or "#888888"),
                "type": str(cat.get("type") or ""),
                "is_savings": bool(int(cat.get("is_savings") or 0)),
                "root_type": root_type,
                "root_is_savings": root_is_savings,
            }
            root_rollup_meta[root.casefold()] = {"type": root_type, "is_savings": root_is_savings}
        return by_id, roots_meta, root_rollup_meta

    def _resolve_tx_root_meta(
        self,
        tx: dict[str, Any],
        by_id: dict[int, Any],
        roots_meta: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve the root category metadata for a transaction.

        Uses the persisted category_id FK so that historical transactions remain
        correctly mapped even after a category is renamed.
        """
        tx_type = str(tx.get("type") or "")
        tx_cat_name = str(tx.get("category") or "").strip()
        tx_cat_id = tx.get("category_id")
        uncategorized_label = self._uncategorized_label
        if tx_cat_id is not None:
            try:
                resolved_cat = by_id.get(int(tx_cat_id))
            except (TypeError, ValueError):
                resolved_cat = None
            if resolved_cat is not None:
                resolved_parent = None
                parent_id = resolved_cat.get("parent_id")
                if parent_id is not None:
                    try:
                        resolved_parent = by_id.get(int(parent_id))
                    except (TypeError, ValueError):
                        resolved_parent = None
                root_cat = resolved_parent or resolved_cat
                root_name = str(root_cat.get("name") or resolved_cat.get("name") or tx_cat_name or uncategorized_label)
                root_type = str(root_cat.get("type") or resolved_cat.get("type") or tx_type)
                root_is_savings = bool(int(root_cat.get("is_savings") or 0)) or bool(
                    int(resolved_cat.get("is_savings") or 0)
                )
                return {
                    "root": root_name,
                    "type": str(resolved_cat.get("type") or tx_type),
                    "is_savings": bool(int(resolved_cat.get("is_savings") or 0)),
                    "root_type": root_type,
                    "root_is_savings": root_is_savings,
                }
        return roots_meta.get(
            tx_cat_name.casefold(),
            {
                "root": tx_cat_name or uncategorized_label,
                "type": tx_type,
                "is_savings": False,
                "root_type": tx_type,
                "root_is_savings": False,
            },
        )

    def _process_transactions(
        self,
        by_id: dict[int, Any],
        roots_meta: dict[str, Any],
        root_rollup_meta: dict[str, Any],
    ) -> dict[str, Any]:
        top_category_totals: dict[str, float] = defaultdict(float)
        top_category_children: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        tag_totals: dict[str, float] = defaultdict(float)
        tag_children: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        waterfall_expense_totals: dict[str, float] = defaultdict(float)
        weekend_total = 0.0
        weekend_days: dict[str, float] = defaultdict(float)
        daily_expense_totals: dict[str, float] = defaultdict(float)
        small_total = 0.0
        income_by_root: dict[str, float] = defaultdict(float)

        for tx in self._inputs.month_transactions:
            tx_type = str(tx.get("type") or "")
            amount = float(tx.get("amount") or 0.0)
            cat_name = str(tx.get("category") or "").strip()
            root_meta = self._resolve_tx_root_meta(tx, by_id, roots_meta)
            root_name = str(root_meta.get("root") or self._uncategorized_label)

            if tx_type == TransactionType.INCOME:
                income_by_root[root_name] += amount
                continue

            if tx_type != TransactionType.EXPENSE:
                continue

            if is_savings_transaction(tx, self._savings_lookup):
                continue

            child_label = str(tx.get("subcategory") or "").strip() or (cat_name or self._uncategorized_label)
            top_category_totals[root_name] += amount
            top_category_children[root_name][child_label] += amount
            root_rollup = root_rollup_meta.get(root_name.casefold()) or {"type": "expense", "is_savings": False}
            waterfall_root_name = (
                root_name
                if str(root_rollup.get("type") or "expense") == "expense"
                else self._inconsistent_expense_label
            )
            waterfall_expense_totals[waterfall_root_name] += amount

            tx_id = int(tx.get("id") or 0)
            for tg in self._inputs.tags_by_tx.get(tx_id, []):
                tag_name = str(tg.get("name") or "").strip() or self._untagged_label
                tag_totals[tag_name] += amount
                tag_children[tag_name][child_label] += amount

            tx_date = str(tx.get("date") or "")
            if tx_date:
                parsed_day = None
                try:
                    parsed_day = datetime.fromisoformat(tx_date.replace("Z", "+00:00")).date()
                except ValueError:
                    try:
                        parsed_day = datetime.strptime(tx_date[:10], "%Y-%m-%d").date()
                    except ValueError:
                        parsed_day = None
                if parsed_day is not None and parsed_day.weekday() >= 5:
                    weekend_total += amount
                    weekend_days[parsed_day.isoformat()] += amount
                if parsed_day is not None:
                    daily_expense_totals[parsed_day.isoformat()] += amount

            if amount < 200.0:
                small_total += amount

        return {
            "top_category_totals": top_category_totals,
            "top_category_children": top_category_children,
            "tag_totals": tag_totals,
            "tag_children": tag_children,
            "waterfall_expense_totals": waterfall_expense_totals,
            "weekend_total": weekend_total,
            "weekend_days": weekend_days,
            "daily_expense_totals": daily_expense_totals,
            "small_total": small_total,
            "income_by_root": income_by_root,
        }

    def _build_waterfall_categories(self, waterfall_expense_totals: dict[str, float]) -> dict[str, Any]:
        waterfall_category_totals = sorted(
            ((name, round(amount, 2)) for name, amount in waterfall_expense_totals.items() if amount > 0),
            key=lambda item: item[1],
            reverse=True,
        )
        inconsistent_waterfall_entry = next(
            (item for item in waterfall_category_totals if item[0] == self._inconsistent_expense_label),
            None,
        )
        normal_waterfall_categories = [
            item for item in waterfall_category_totals if item[0] != self._inconsistent_expense_label
        ]
        displayed_waterfall_categories = list(normal_waterfall_categories[:_MAX_WATERFALL_EXPENSE_STEPS])
        remaining_waterfall_categories = normal_waterfall_categories[_MAX_WATERFALL_EXPENSE_STEPS:]
        if remaining_waterfall_categories:
            displayed_waterfall_categories.append(
                (
                    self._other_expenses_label,
                    round(sum(amount for _name, amount in remaining_waterfall_categories), 2),
                )
            )
        if inconsistent_waterfall_entry is not None:
            displayed_waterfall_categories.append(inconsistent_waterfall_entry)
        return {
            "waterfall_category_totals": waterfall_category_totals,
            "inconsistent_waterfall_entry": inconsistent_waterfall_entry,
            "normal_waterfall_categories": normal_waterfall_categories,
            "displayed_waterfall_categories": displayed_waterfall_categories,
            "remaining_waterfall_categories": remaining_waterfall_categories,
        }

    def _build_stacked_history(self, roots_meta: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        def _monthly_root_stack(monthly_txs: list[dict[str, Any]], section: str) -> dict[str, float]:
            acc: dict[str, float] = defaultdict(float)
            for tx in monthly_txs:
                tx_type = str(tx.get("type") or "")
                if section == "income" and tx_type != TransactionType.INCOME:
                    continue
                if section == "expense" and tx_type != TransactionType.EXPENSE:
                    continue
                cat_name = str(tx.get("category") or "").strip()
                root_meta = roots_meta.get(
                    cat_name.casefold(), {"root": cat_name or self._uncategorized_label, "is_savings": False}
                )
                if section == "expense" and is_savings_transaction(tx, self._savings_lookup):
                    continue
                root_name = str(root_meta.get("root") or self._uncategorized_label)
                acc[root_name] += float(tx.get("amount") or 0.0)
            return {k: round(v, 2) for k, v in acc.items()}

        stacked_6: dict[str, list[dict[str, Any]]] = {"income": [], "expense": []}
        for m_year, m_month, txs in self._inputs.historical_6:
            period = f"{m_year:04d}-{m_month:02d}"
            stacked_6["income"].append({"period": period, "segments": _monthly_root_stack(txs, "income")})
            stacked_6["expense"].append({"period": period, "segments": _monthly_root_stack(txs, "expense")})
        return stacked_6

    def _build_budget_context(self) -> BudgetContextData:
        if self._inputs.budget is None or self._inputs.budget_monthly_by_type is None:
            return BudgetContextData(
                has_budget=False,
                budget_id=None,
                budget_code=None,
                income=0.0,
                expense_operational=0.0,
                is_complete_for_period=False,
            )
        income_budget = round(sum(self._inputs.budget_monthly_by_type.get("income", {}).values()), 2)
        expense_budget = round(sum(self._inputs.budget_monthly_by_type.get("expense", {}).values()), 2)
        if (income_budget + expense_budget) <= 0.0:
            return BudgetContextData(
                has_budget=False,
                budget_id=None,
                budget_code=None,
                income=0.0,
                expense_operational=0.0,
                is_complete_for_period=False,
            )
        missing_income: list[str] = []
        missing_expense: list[str] = []
        actual_income_by_cat_id: dict[int, float] = defaultdict(float)
        actual_expense_by_cat_id: dict[int, float] = defaultdict(float)
        for tx in self._inputs.month_transactions:
            cat_id_raw = tx.get("category_id")
            tx_type = str(tx.get("type") or "")
            if cat_id_raw is None:
                continue
            cat_id = int(cat_id_raw)
            amount = float(tx.get("amount") or 0.0)
            if tx_type == TransactionType.INCOME:
                actual_income_by_cat_id[cat_id] += amount
            if tx_type == TransactionType.EXPENSE and not is_savings_transaction(tx, self._savings_lookup):
                actual_expense_by_cat_id[cat_id] += amount
        if self._inputs.budget_category_rows:
            mi_set: set[str] = set()
            me_set: set[str] = set()
            for row in self._inputs.budget_category_rows:
                row_type = str(row.get("type") or "")
                row_name = str(row.get("name") or "").strip()
                row_amount = float(row.get("amount") or 0.0)
                row_cat_id = row.get("category_id")
                if row_amount <= 0 or not row_name or row_cat_id is None:
                    continue
                cat_id = int(row_cat_id)
                if row_type == TransactionType.INCOME and actual_income_by_cat_id.get(cat_id, 0.0) <= 0:
                    mi_set.add(row_name)
                if row_type == TransactionType.EXPENSE and actual_expense_by_cat_id.get(cat_id, 0.0) <= 0:
                    me_set.add(row_name)
            missing_income = sorted(mi_set)
            missing_expense = sorted(me_set)
        return BudgetContextData(
            has_budget=True,
            budget_id=int(self._inputs.budget["id"]),
            budget_code=str(self._inputs.budget.get("code") or ""),
            income=income_budget,
            expense_operational=expense_budget,
            is_complete_for_period=True,
            missing_income_categories=missing_income,
            missing_expense_categories=missing_expense,
        )

    def compute(self) -> MetricsResult:
        """Compute all metrics and return a typed MetricsResult."""
        current_summary = _month_summary(self._inputs.month_transactions, self._savings_lookup)
        previous_summary = _month_summary(self._inputs.previous_transactions, self._savings_lookup)

        cc_stats = self._compute_credit_card_stats()
        avg_3, avg_6, historical_6_summaries = self._compute_trailing_data()
        ytd = self._compute_ytd()

        by_id, roots_meta, root_rollup_meta = self._build_category_metadata()
        tx_data = self._process_transactions(by_id, roots_meta, root_rollup_meta)
        wf_data = self._build_waterfall_categories(tx_data["waterfall_expense_totals"])
        stacked_6 = self._build_stacked_history(roots_meta)
        budget_context = self._build_budget_context()

        income_total = current_summary.income
        total_expense = current_summary.expense_operational
        debt_payment_total = current_summary.debt_payment

        def _compare_value(current: float, base: float | None, section: str) -> ComparisonResult:
            variance = None if base is None else round(current - base, 2)
            pct = pct_change(current, base) if base is not None else None
            return ComparisonResult(base=base, variance=variance, pct=pct, signal=_trend_signal(section, variance))

        income_vs_previous = _compare_value(income_total, previous_summary.income, "income")
        expense_vs_previous = _compare_value(total_expense, previous_summary.expense_operational, "expense")
        comparisons: dict[str, dict[str, ComparisonResult | None]] = {
            "income": {
                "vs_previous": income_vs_previous,
                "vs_avg_3": _compare_value(income_total, avg_3.income, "income"),
                "vs_avg_6": _compare_value(income_total, avg_6.income, "income"),
                "vs_budget": (
                    _compare_value(income_total, budget_context.income, "income") if budget_context.has_budget else None
                ),
            },
            "expense_operational": {
                "vs_previous": expense_vs_previous,
                "vs_avg_3": _compare_value(total_expense, avg_3.expense_operational, "expense"),
                "vs_avg_6": _compare_value(total_expense, avg_6.expense_operational, "expense"),
                "vs_budget": (
                    _compare_value(total_expense, budget_context.expense_operational, "expense")
                    if budget_context.has_budget
                    else None
                ),
            },
            "savings": {
                "vs_previous": _compare_value(current_summary.savings, previous_summary.savings, "savings"),
                "vs_avg_3": _compare_value(current_summary.savings, avg_3.savings, "savings"),
                "vs_avg_6": _compare_value(current_summary.savings, avg_6.savings, "savings"),
            },
            "net": {
                "vs_previous": _compare_value(current_summary.net, previous_summary.net, "net"),
                "vs_avg_3": _compare_value(current_summary.net, avg_3.net, "net"),
                "vs_avg_6": _compare_value(current_summary.net, avg_6.net, "net"),
            },
        }
        income_vs_budget = comparisons["income"]["vs_budget"]
        expense_vs_budget = comparisons["expense_operational"]["vs_budget"]

        goal_contribution_metrics = _build_goal_contribution_metrics(
            self._inputs.month_transactions, self._inputs.savings_goals
        )
        lifestyle_inflation_metrics = _build_lifestyle_inflation_metrics(
            income_vs_previous.pct,
            expense_vs_previous.pct,
        )
        savings_efficiency_metrics = _build_savings_efficiency_metrics(
            net_amount=current_summary.net,
            goal_contribution_amount=goal_contribution_metrics.amount,
            has_active_goals=bool(self._goal_result.active_goals),
        )
        freedom_margin_metrics = _build_freedom_margin_metrics(income_total, total_expense)

        income_series = [s.income for s in historical_6_summaries]
        expense_series = [s.expense_operational for s in historical_6_summaries]
        net_series = [s.net for s in historical_6_summaries]

        income_trend_metric = _build_trend_metric(income_total, previous_summary.income)
        expense_trend_metric = _build_trend_metric(total_expense, previous_summary.expense_operational)
        gap_trend_metric = _build_trend_metric(current_summary.net, previous_summary.net)
        financial_balance_metric = _build_financial_balance_metric(income_total, total_expense)
        cashflow_stability_metric = _build_cashflow_stability_metric(net_series, income_series)
        spending_efficiency_metric = _build_spending_efficiency_metric(income_total, total_expense)
        expense_drift_metric = _build_expense_drift_metric(expense_series)
        cashflow_projection_metric = _build_cashflow_projection_metric(income_series, expense_series)
        deficit_risk_metric = _build_deficit_risk_metric(
            current_net=current_summary.net,
            income_trend=income_trend_metric,
            expense_trend=expense_trend_metric,
            projected_net=cast(float | None, cashflow_projection_metric["projected_net"]),
        )
        income_fragility_metric = _build_income_fragility_metric(income_series, income_trend_metric)
        financial_momentum_metric = _build_financial_momentum_metric(
            gap_trend=gap_trend_metric,
            income_trend=income_trend_metric,
            expense_trend=expense_trend_metric,
        )
        days_in_month = max(1, calendar.monthrange(self._inputs.year, self._inputs.month)[1])
        week_spread_metric = _build_week_spread_metric(total_expense, tx_data["daily_expense_totals"])
        spending_pattern_metric = _build_spending_pattern_metric(
            total_expense=total_expense,
            daily_expense_totals=tx_data["daily_expense_totals"],
            expense_trend=expense_trend_metric,
        )
        previous_year, previous_month = shift_month(self._inputs.year, self._inputs.month, -1)
        previous_days_in_month = max(1, calendar.monthrange(previous_year, previous_month)[1])
        runway_trend_metric = _build_runway_trend_metric(
            account_balance_total=self._inputs.account_balance_total,
            current_expense_total=total_expense,
            previous_expense_total=previous_summary.expense_operational,
            current_days=days_in_month,
            previous_days=previous_days_in_month,
        )
        expense_control_metric = _build_expense_control_metric(
            expense_trend=expense_trend_metric,
            expense_drift=expense_drift_metric,
            spending_pattern=spending_pattern_metric,
        )
        income_control_metric = _build_income_control_metric(income_fragility_metric)
        sustainability_score_metric = _build_sustainability_score(
            financial_balance=financial_balance_metric,
            cashflow_stability=cashflow_stability_metric,
            deficit_risk=deficit_risk_metric,
            income_fragility=income_fragility_metric,
        )
        generic_analysis = {
            "flow": {
                "income_trend": income_trend_metric,
                "expense_trend": expense_trend_metric,
                "gap_trend": gap_trend_metric,
                "financial_balance": financial_balance_metric,
                "spending_efficiency": spending_efficiency_metric,
                "expense_drift": expense_drift_metric,
                "cashflow_projection": cashflow_projection_metric,
            },
            "behavior": {
                "spending_pattern": spending_pattern_metric,
                "week_spread": week_spread_metric,
                "expense_control": expense_control_metric,
            },
            "stability": {
                "cashflow_stability": cashflow_stability_metric,
                "deficit_risk": deficit_risk_metric,
                "income_fragility": income_fragility_metric,
                "financial_momentum": financial_momentum_metric,
                "sustainability_score": sustainability_score_metric,
                "runway_trend": runway_trend_metric,
                "income_control": income_control_metric,
            },
        }

        history_hints: list[str] = []
        if (
            len(self._inputs.trailing_3) < 3
            or len([item for _y, _m, item in self._inputs.comparison_trailing_6 if item]) < 6
        ):
            history_hints.append(
                self._t(
                    "Se requiere un mayor período de transacciones para completar comparativas de 3 y 6 meses.",
                    "A longer transaction history is required to complete 3-month and 6-month comparisons.",
                )
            )

        top_categories = sorted(tx_data["top_category_totals"].items(), key=lambda item: item[1], reverse=True)[:5]
        top_tags = sorted(tx_data["tag_totals"].items(), key=lambda item: item[1], reverse=True)[:5]

        debt_payment_income_pct = (debt_payment_total / income_total * 100.0) if income_total > 0 else None
        debt_payment_expense_pct = (debt_payment_total / total_expense * 100.0) if total_expense > 0 else None
        savings_rate = ((income_total - total_expense) / income_total * 100.0) if income_total > 0 else None
        expense_income_ratio = safe_ratio(total_expense, income_total)
        avg_daily_expense = total_expense / days_in_month
        burn_days = safe_ratio(self._inputs.account_balance_total, avg_daily_expense)
        daily_living_cost = total_expense / days_in_month
        goal_completion_index_pct = _build_goal_completion_index(
            self._goal_result.goal_rows, self._goal_result.active_goals
        )

        concentration_pct: float | None = None
        if top_categories and total_expense > 0:
            top_name, top_amount = top_categories[0]
            concentration_pct = (top_amount / total_expense) * 100.0

        dependence_pct: float | None = None
        income_by_root: dict[str, float] = tx_data["income_by_root"]
        if income_by_root and income_total > 0:
            _dom_root_name, dom_root_amount = max(income_by_root.items(), key=lambda item: item[1])
            dependence_pct = (dom_root_amount / income_total) * 100.0

        needs_keywords = {"alquiler", "renta", "comida", "supermercado", "salud", "medicina", "transporte", "servicios"}
        needs_total = sum(
            amount
            for root, amount in tx_data["top_category_totals"].items()
            if any(k in root.casefold() for k in needs_keywords)
        )
        wants_total = max(0.0, total_expense - needs_total)
        needs_pct = (needs_total / income_total * 100.0) if income_total > 0 else 0.0
        wants_pct = (wants_total / income_total * 100.0) if income_total > 0 else 0.0
        savings_pct = (current_summary.savings / income_total * 100.0) if income_total > 0 else 0.0
        deviation_pct = abs(needs_pct - 50.0) + abs(wants_pct - 30.0) + abs(savings_pct - 20.0)

        net_after_expenses = round(current_summary.net, 2)
        top_total = round(sum(amount for _name, amount in top_categories), 2)

        return MetricsResult(
            current_summary=current_summary,
            previous_summary=previous_summary,
            avg_3=avg_3,
            avg_6=avg_6,
            ytd=ytd,
            credit_card=cc_stats,
            top_category_totals=dict(tx_data["top_category_totals"]),
            top_category_children={k: dict(v) for k, v in tx_data["top_category_children"].items()},
            tag_totals=dict(tx_data["tag_totals"]),
            tag_children={k: dict(v) for k, v in tx_data["tag_children"].items()},
            top_categories=top_categories,
            top_tags=top_tags,
            weekend_total=tx_data["weekend_total"],
            weekend_days=tx_data["weekend_days"],
            daily_expense_totals=tx_data["daily_expense_totals"],
            small_total=tx_data["small_total"],
            income_by_root=dict(income_by_root),
            waterfall_category_totals=wf_data["waterfall_category_totals"],
            normal_waterfall_categories=wf_data["normal_waterfall_categories"],
            displayed_waterfall_categories=wf_data["displayed_waterfall_categories"],
            remaining_waterfall_categories=wf_data["remaining_waterfall_categories"],
            inconsistent_waterfall_entry=wf_data["inconsistent_waterfall_entry"],
            stacked_6=stacked_6,
            budget_context=budget_context,
            comparisons=comparisons,
            income_vs_budget=income_vs_budget,
            expense_vs_budget=expense_vs_budget,
            income_vs_previous=income_vs_previous,
            expense_vs_previous=expense_vs_previous,
            lifestyle_inflation_metrics=lifestyle_inflation_metrics,
            savings_efficiency_metrics=savings_efficiency_metrics,
            freedom_margin_metrics=freedom_margin_metrics,
            goal_contribution_metrics=goal_contribution_metrics,
            generic_analysis=generic_analysis,
            history_hints=history_hints,
            income_total=income_total,
            total_expense=total_expense,
            debt_payment_total=debt_payment_total,
            debt_payment_income_pct=debt_payment_income_pct,
            debt_payment_expense_pct=debt_payment_expense_pct,
            savings_rate=savings_rate,
            expense_income_ratio=expense_income_ratio,
            avg_daily_expense=avg_daily_expense,
            burn_days=burn_days,
            daily_living_cost=daily_living_cost,
            goal_completion_index_pct=goal_completion_index_pct,
            concentration_pct=concentration_pct,
            dependence_pct=dependence_pct,
            net_after_expenses=net_after_expenses,
            top_total=top_total,
            days_in_month=days_in_month,
            mira_50_30_20=Mira503020(
                needs_pct=round(needs_pct, 2),
                wants_pct=round(wants_pct, 2),
                savings_pct=round(savings_pct, 2),
                deviation_pct=round(deviation_pct, 2),
            ),
        )


class WaterfallChartBuilder:
    """Constructs the waterfall chart steps and summary for the MIRA master report."""

    def __init__(
        self,
        *,
        income_total: float,
        net_after_expenses: float,
        displayed_categories: list[tuple[str, float]],
        remaining_categories: list[tuple[str, float]],
        normal_categories: list[tuple[str, float]],
        inconsistent_entry: tuple[str, float] | None,
        all_waterfall_category_totals: list[tuple[str, float]],
        language: str = "en",
    ) -> None:
        self._income_total = income_total
        self._net_after_expenses = net_after_expenses
        self._displayed_categories = displayed_categories
        self._remaining_categories = remaining_categories
        self._normal_categories = normal_categories
        self._inconsistent_entry = inconsistent_entry
        self._all_waterfall_category_totals = all_waterfall_category_totals
        self._language = _normalize_report_language(language)

    def _t(self, es: str, en: str, *, params: dict[str, Any] | None = None) -> str:
        return _report_text(self._language, es, en, params=params)

    def build(self) -> dict[str, Any]:
        """Return a dict with 'steps' list and 'summary' dict."""
        net_after_expenses = self._net_after_expenses
        waterfall_steps: list[dict[str, Any]] = [
            {
                "label": self._t("Ingreso total neto", "Total net income"),
                "kind": "income_total",
                "value": round(self._income_total, 2),
                "start": 0.0,
                "end": round(self._income_total, 2),
                "baseline": 0.0,
            }
        ]

        running_balance = round(self._income_total, 2)
        for category_name, amount in self._displayed_categories:
            next_balance = round(running_balance - amount, 2)
            is_grouped = category_name == self._t("Otros gastos", "Other expenses") and bool(self._remaining_categories)
            waterfall_steps.append(
                {
                    "label": category_name,
                    "kind": "expense",
                    "value": round(-amount, 2),
                    "start": running_balance,
                    "end": next_balance,
                    "is_grouped": is_grouped,
                }
            )
            running_balance = next_balance

        waterfall_status = "balanced"
        financing_amount = 0.0
        savings_allocation = 0.0
        final_balance = 0.0
        if net_after_expenses < 0:
            waterfall_status = "deficit"
            financing_amount = round(abs(net_after_expenses), 2)
            waterfall_steps.append(
                {
                    "label": self._t("Deuda / uso de ahorro", "Debt / prior savings"),
                    "kind": "financing",
                    "value": financing_amount,
                    "start": net_after_expenses,
                    "end": 0.0,
                }
            )
        elif net_after_expenses > 0:
            waterfall_status = "surplus"
            final_balance = net_after_expenses

        if waterfall_status != "deficit":
            waterfall_steps.append(
                {
                    "label": (
                        self._t("Balance del mes", "Month balance")
                        if waterfall_status == "surplus"
                        else self._t("Cierre del flujo mensual", "Monthly flow close")
                    ),
                    "kind": "month_balance" if waterfall_status == "surplus" else "final_total",
                    "value": final_balance,
                    "start": final_balance,
                    "end": final_balance,
                    "baseline": 0.0,
                }
            )

        return {
            "steps": waterfall_steps,
            "summary": {
                "status": waterfall_status,
                "net_after_expenses": net_after_expenses,
                "financing_amount": financing_amount,
                "savings_allocation": savings_allocation,
                "final_balance": final_balance,
                "expense_categories_count": len(self._all_waterfall_category_totals),
                "displayed_expense_categories_count": min(len(self._normal_categories), _MAX_WATERFALL_EXPENSE_STEPS),
                "displayed_expense_steps_count": len(self._displayed_categories),
                "grouped_other_expenses_count": len(self._remaining_categories),
                "has_grouped_other_expenses": bool(self._remaining_categories),
                "inconsistent_bucket_present": self._inconsistent_entry is not None,
            },
        }


class MessageBuilder:
    """Collects analysis messages for the MIRA report chat advisor.

    Pass an instance explicitly to each message-generation method so that data
    flow is visible at every call site. Call :meth:`build` when all messages
    have been added to obtain the accumulated list.
    """

    def __init__(self) -> None:
        self._messages: list[dict[str, Any]] = []

    def add(self, code: str, level: str, text: str, *, always: bool = False, pct: float | None = None) -> None:
        """Append a single message dict to the collection."""
        self._messages.append({"code": code, "level": level, "text": text, "always": always, "pct": pct})

    def build(self) -> list[dict[str, Any]]:
        """Return a snapshot of all collected messages."""
        return list(self._messages)


class ReportMessageGenerator:
    """Generates and filters analysis messages for the MIRA master report chat advisor."""

    def __init__(
        self,
        *,
        metrics: MetricsResult,
        goal_data: GoalAnalysisResult,
        savings_goals: list[dict[str, Any]],
        year: int,
        month: int,
        relevance_threshold: float = 0.10,
        language: str = "en",
    ) -> None:
        self._metrics = metrics
        self._goal_data = goal_data
        self._savings_goals = savings_goals
        self._year = year
        self._month = month
        self._relevance_threshold = relevance_threshold
        self._language = _normalize_report_language(language)

    def _t(self, es: str, en: str, *, params: dict[str, Any] | None = None) -> str:
        return _report_text(self._language, es, en, params=params)

    def _generate_income_vs_previous(self, builder: MessageBuilder) -> None:
        income_vs_previous = self._metrics.income_vs_previous
        income_prev_pct = income_vs_previous.pct
        lifestyle_inflation_metrics = self._metrics.lifestyle_inflation_metrics
        if income_prev_pct is None:
            builder.add(
                "income_vs_previous_missing",
                "warning",
                self._t(
                    "No hay historial suficiente para comparar ingresos con el mes anterior.",
                    "There is not enough history to compare income with the previous month.",
                ),
                always=True,
            )
        else:
            trend = self._t("mayores", "higher") if income_prev_pct >= 0 else self._t("menores", "lower")
            builder.add(
                "income_vs_previous",
                "info",
                self._t(
                    "Los ingresos de este mes fueron {pct:.1f}% {trend} en relación al mes pasado.",
                    "Income this month was {pct:.1f}% {trend} than last month.",
                    params={"pct": abs(income_prev_pct), "trend": trend},
                ),
                always=True,
                pct=abs(income_prev_pct),
            )

        expense_vs_previous = self._metrics.expense_vs_previous
        expense_prev_pct = expense_vs_previous.pct
        if expense_prev_pct is None:
            builder.add(
                "expense_vs_previous_missing",
                "warning",
                self._t(
                    "No hay historial suficiente para comparar gastos con el mes anterior.",
                    "There is not enough history to compare expenses with the previous month.",
                ),
                always=True,
            )
        else:
            trend = self._t("mayores", "higher") if expense_prev_pct >= 0 else self._t("menores", "lower")
            builder.add(
                "expense_vs_previous",
                "info",
                self._t(
                    "Los gastos operativos fueron {pct:.1f}% {trend} en relación al mes pasado.",
                    "Operating expenses were {pct:.1f}% {trend} than last month.",
                    params={"pct": abs(expense_prev_pct), "trend": trend},
                ),
                always=True,
                pct=abs(expense_prev_pct),
            )
            if bool(lifestyle_inflation_metrics.is_alert):
                builder.add(
                    "lifestyle_inflation_alert",
                    "warning",
                    self._t(
                        "Tus ingresos subieron {income_pct:.1f}%, pero tus gastos operativos subieron {expense_pct:.1f}%. Estas absorbiendo casi todo el aumento y eso apunta a inflacion de estilo de vida.",
                        "Your income increased {income_pct:.1f}%, but your operating expenses increased {expense_pct:.1f}%. You are absorbing nearly all of the raise, which points to lifestyle inflation.",
                        params={
                            "income_pct": float(lifestyle_inflation_metrics.income_growth_pct or 0.0),
                            "expense_pct": float(lifestyle_inflation_metrics.expense_growth_pct or 0.0),
                        },
                    ),
                    always=True,
                    pct=max(
                        float(lifestyle_inflation_metrics.income_growth_pct or 0.0),
                        float(lifestyle_inflation_metrics.expense_growth_pct or 0.0),
                    ),
                )

    def _generate_budget_messages(self, builder: MessageBuilder) -> None:
        budget_context = self._metrics.budget_context
        income_vs_budget = self._metrics.income_vs_budget
        expense_vs_budget = self._metrics.expense_vs_budget
        if not budget_context.has_budget:
            return
        income_budget_pct = income_vs_budget.pct if income_vs_budget is not None else None
        expense_budget_pct = expense_vs_budget.pct if expense_vs_budget is not None else None
        if income_budget_pct is not None:
            trend = self._t("por encima", "above") if income_budget_pct >= 0 else self._t("por debajo", "below")
            builder.add(
                "income_vs_budget",
                "info",
                self._t(
                    "Tus ingresos quedaron {pct:.1f}% {trend} del presupuesto.",
                    "Your income landed {pct:.1f}% {trend} budget.",
                    params={"pct": abs(income_budget_pct), "trend": trend},
                ),
                always=True,
                pct=abs(income_budget_pct),
            )
        if expense_budget_pct is not None:
            trend = self._t("por encima", "above") if expense_budget_pct >= 0 else self._t("por debajo", "below")
            builder.add(
                "expense_vs_budget",
                "info",
                self._t(
                    "Tus gastos operativos quedaron {pct:.1f}% {trend} del presupuesto.",
                    "Your operating expenses landed {pct:.1f}% {trend} budget.",
                    params={"pct": abs(expense_budget_pct), "trend": trend},
                ),
                always=True,
                pct=abs(expense_budget_pct),
            )
        for item in budget_context.missing_income_categories:
            builder.add(
                "missing_budgeted_income",
                "warning",
                self._t(
                    "Ingreso presupuestado no percibido: {item}.",
                    "Budgeted income not received: {item}.",
                    params={"item": item},
                ),
                always=True,
            )
        for item in budget_context.missing_expense_categories:
            builder.add(
                "missing_budgeted_expense",
                "warning",
                self._t(
                    "Gasto presupuestado no pagado: {item}.",
                    "Budgeted expense not paid: {item}.",
                    params={"item": item},
                ),
                always=True,
            )

    def _generate_net_messages(self, builder: MessageBuilder) -> None:
        current_summary = self._metrics.current_summary
        savings_efficiency_metrics = self._metrics.savings_efficiency_metrics
        if current_summary.net < 0:
            builder.add(
                "deficit",
                "critical",
                self._t(
                    "⚠️ Este mes has gastado más de lo que has ingresado. Estás utilizando {amount:.2f} de tus reservas.",
                    "⚠️ You spent more than you earned this month. You are using {amount:.2f} from your reserves.",
                    params={"amount": abs(current_summary.net)},
                ),
                always=True,
            )
        else:
            builder.add(
                "surplus",
                "success",
                self._t(
                    "✅ Vas bien: tienes {amount:.2f} disponibles para asignar a nuevas metas.",
                    "✅ You are doing well: you have {amount:.2f} available to assign to new goals.",
                    params={"amount": current_summary.net},
                ),
                always=True,
            )
            if bool(savings_efficiency_metrics.has_surplus_leakage_alert):
                builder.add(
                    "surplus_leakage",
                    "warning",
                    self._t(
                        "Cerraste el mes con un excedente de {surplus:.2f}, pero no hubo avance registrado en metas de ahorro. Hay una posible fuga de excedente: sobro en papel, pero no llego a tus metas.",
                        "You closed the month with a surplus of {surplus:.2f}, but there was no recorded progress toward savings goals. There is a possible surplus leakage: it existed on paper, but it did not reach your goals.",
                        params={"surplus": float(savings_efficiency_metrics.surplus_amount)},
                    ),
                    always=True,
                )

    def _generate_debt_messages(self, builder: MessageBuilder) -> None:
        debt_payment_total = self._metrics.debt_payment_total
        debt_payment_income_pct = self._metrics.debt_payment_income_pct
        debt_payment_expense_pct = self._metrics.debt_payment_expense_pct
        cc = self._metrics.credit_card
        if debt_payment_total > 0:
            debt_level = (
                "warning"
                if (debt_payment_income_pct or 0.0) >= 20.0 or (debt_payment_expense_pct or 0.0) >= 30.0
                else "info"
            )
            if debt_payment_income_pct is not None and debt_payment_expense_pct is not None:
                builder.add(
                    "credit_debt_load",
                    debt_level,
                    self._t(
                        "Los pagos de tarjetas de crédito y deuda sumaron {amount:.2f}. Equivalen al {income_pct:.1f}% de tus ingresos y al {expense_pct:.1f}% de tus gastos operativos.",
                        "Credit card and debt payments totaled {amount:.2f}. They equal {income_pct:.1f}% of your income and {expense_pct:.1f}% of your operating expenses.",
                        params={
                            "amount": debt_payment_total,
                            "income_pct": debt_payment_income_pct,
                            "expense_pct": debt_payment_expense_pct,
                        },
                    ),
                    always=True,
                    pct=max(debt_payment_income_pct, debt_payment_expense_pct),
                )
            else:
                builder.add(
                    "credit_debt_load",
                    "warning",
                    self._t(
                        "Registraste {amount:.2f} en pagos de tarjetas de crédito y deuda, pero no hay ingresos suficientes en el periodo para medir su peso mensual.",
                        "You recorded {amount:.2f} in credit card and debt payments, but there is not enough income in the period to measure their monthly weight.",
                        params={"amount": debt_payment_total},
                    ),
                    always=True,
                )

        if cc.expense_count > 0 or cc.payment_count > 0:
            if cc.expense_amount > cc.payment_amount:
                builder.add(
                    "credit_card_usage_vs_payments",
                    "warning",
                    self._t(
                        "En tarjetas de crédito registraste {expense_count} gasto(s) por {expense_amount:.2f} y {payment_count} pago(s) internos por {payment_amount:.2f}. Como los gastos superan los pagos, hay señal de posible endeudamiento por {gap:.2f}.",
                        "For credit cards you recorded {expense_count} expense(s) totaling {expense_amount:.2f} and {payment_count} internal payment(s) totaling {payment_amount:.2f}. Because spending is higher than payments, there is a possible indebtedness signal of {gap:.2f}.",
                        params={
                            "expense_count": cc.expense_count,
                            "expense_amount": cc.expense_amount,
                            "payment_count": cc.payment_count,
                            "payment_amount": cc.payment_amount,
                            "gap": abs(cc.gap_amount),
                        },
                    ),
                    always=True,
                )
            else:
                builder.add(
                    "credit_card_usage_vs_payments",
                    "info",
                    self._t(
                        "En tarjetas de crédito registraste {expense_count} gasto(s) por {expense_amount:.2f} y {payment_count} pago(s) internos por {payment_amount:.2f}. Los pagos van al dia frente al gasto asociado del periodo.",
                        "For credit cards you recorded {expense_count} expense(s) totaling {expense_amount:.2f} and {payment_count} internal payment(s) totaling {payment_amount:.2f}. Payments are keeping up with the card spending recorded in the period.",
                        params={
                            "expense_count": cc.expense_count,
                            "expense_amount": cc.expense_amount,
                            "payment_count": cc.payment_count,
                            "payment_amount": cc.payment_amount,
                        },
                    ),
                    always=True,
                )

    def _generate_spending_pattern_messages(self, builder: MessageBuilder) -> None:
        total_expense = self._metrics.total_expense
        weekend_total = self._metrics.weekend_total
        weekend_days = self._metrics.weekend_days
        small_total = self._metrics.small_total
        top_tags = self._metrics.top_tags
        current_summary = self._metrics.current_summary

        weekend_pct = (weekend_total / total_expense * 100.0) if total_expense > 0 else 0.0
        weekend_avg = (weekend_total / len(weekend_days)) if weekend_days else 0.0
        builder.add(
            "weekend_behavior",
            "info",
            self._t(
                "El {pct:.1f}% de tus gastos ocurre en fines de semana. Tu costo promedio por sábado/domingo es {avg:.2f}.",
                "{pct:.1f}% of your spending happens on weekends. Your average cost per Saturday/Sunday is {avg:.2f}.",
                params={"pct": weekend_pct, "avg": weekend_avg},
            ),
            pct=weekend_pct,
        )

        small_pct = (small_total / total_expense * 100.0) if total_expense > 0 else 0.0
        builder.add(
            "small_expenses",
            "info",
            self._t(
                "Tus transacciones menores a 200 suman {amount:.2f}. Esto representa el {pct:.1f}% de tu gasto total.",
                "Transactions under 200 add up to {amount:.2f}. That represents {pct:.1f}% of your total spending.",
                params={"amount": small_total, "pct": small_pct},
            ),
            pct=small_pct,
        )

        if top_tags and current_summary.income > 0:
            top_tag_name, top_tag_amount = top_tags[0]
            tag_income_pct = (top_tag_amount / current_summary.income) * 100.0
            builder.add(
                "tag_impact",
                "info",
                self._t(
                    "La etiqueta #{tag} ha consumido el {pct:.1f}% de tus ingresos.",
                    "The #{tag} tag has consumed {pct:.1f}% of your income.",
                    params={"tag": top_tag_name, "pct": tag_income_pct},
                ),
                pct=tag_income_pct,
            )

        if current_summary.income <= 0:
            builder.add(
                "zero_income",
                "warning",
                self._t(
                    "No hay ingresos registrados para el periodo; algunos ratios porcentuales no aplican.",
                    "No income is recorded for the period; some percentage ratios do not apply.",
                ),
                always=True,
            )

    def _generate_burn_rate_message(self, builder: MessageBuilder) -> None:
        burn_days = self._metrics.burn_days
        if burn_days is not None:
            builder.add(
                "burn_rate",
                "info",
                self._t(
                    "Basado en tu gasto promedio diario, tu saldo actual cubre {days:.1f} días sin ingresos nuevos.",
                    "Based on your average daily spending, your current balance covers {days:.1f} days without new income.",
                    params={"days": burn_days},
                ),
            )

    def _generate_goal_messages(self, builder: MessageBuilder) -> None:
        avg_3 = self._metrics.avg_3
        current_summary = self._metrics.current_summary
        completed_goals = self._goal_data.completed_goals
        active_goals = self._goal_data.active_goals
        report_period_end = self._goal_data.report_period_end
        default_goal_name = self._t("Meta", "Goal")

        monthly_savings_avg = avg_3.savings or current_summary.savings

        if completed_goals:
            latest_completed_goal = completed_goals[0]
            builder.add(
                "goals_completed",
                "success",
                self._t(
                    "Ya cumpliste {count} meta(s) de ahorro. La mas reciente es '{goal_name}'.",
                    "You already achieved {count} savings goal(s). The most recent one is '{goal_name}'.",
                    params={"count": len(completed_goals), "goal_name": latest_completed_goal.name},
                ),
                always=True,
            )

        if active_goals:
            focus_goal = active_goals[0]
            focus_target_date = cast(date | None, focus_goal.parsed_target_date)
            focus_currency = str(focus_goal.currency or "").strip()
            if focus_target_date is not None and focus_target_date < report_period_end:
                builder.add(
                    "goal_overdue",
                    "warning",
                    self._t(
                        "La meta '{goal_name}' esta vencida y aun faltan {remaining:.2f} {currency}.",
                        "The '{goal_name}' goal is overdue and still needs {remaining:.2f} {currency}.",
                        params={
                            "goal_name": focus_goal.name,
                            "remaining": float(focus_goal.remaining_amount),
                            "currency": focus_currency,
                        },
                    ),
                    always=True,
                )
            elif focus_target_date is not None:
                months_remaining = max(
                    1, ((focus_target_date.year - self._year) * 12) + (focus_target_date.month - self._month) + 1
                )
                required_monthly_savings = float(focus_goal.remaining_amount) / months_remaining
                if monthly_savings_avg and monthly_savings_avg >= required_monthly_savings:
                    builder.add(
                        "goal_on_track",
                        "success",
                        self._t(
                            "La meta '{goal_name}' va encaminada: llevas {progress:.1f}% y necesitas {required:.2f} {currency} por mes para llegar a {target_date}.",
                            "The '{goal_name}' goal is on track: you are at {progress:.1f}% and need {required:.2f} {currency} per month to reach {target_date}.",
                            params={
                                "goal_name": focus_goal.name,
                                "progress": float(focus_goal.progress_pct),
                                "required": required_monthly_savings,
                                "currency": focus_currency,
                                "target_date": focus_goal.target_date,
                            },
                        ),
                        always=True,
                    )
                else:
                    builder.add(
                        "goal_off_track",
                        "warning",
                        self._t(
                            "La meta '{goal_name}' requiere {required:.2f} {currency} por mes para llegar a {target_date}, pero tu ahorro reciente promedia {actual:.2f} {currency}.",
                            "The '{goal_name}' goal needs {required:.2f} {currency} per month to reach {target_date}, but your recent savings average is {actual:.2f} {currency}.",
                            params={
                                "goal_name": focus_goal.name,
                                "required": required_monthly_savings,
                                "currency": focus_currency,
                                "target_date": focus_goal.target_date,
                                "actual": float(monthly_savings_avg or 0.0),
                            },
                        ),
                        always=True,
                    )
            else:
                builder.add(
                    "goal_progress",
                    "info",
                    self._t(
                        "La meta '{goal_name}' va al {progress:.1f}% y faltan {remaining:.2f} {currency}.",
                        "The '{goal_name}' goal is {progress:.1f}% complete and still needs {remaining:.2f} {currency}.",
                        params={
                            "goal_name": focus_goal.name,
                            "progress": float(focus_goal.progress_pct),
                            "remaining": float(focus_goal.remaining_amount),
                            "currency": focus_currency,
                        },
                    ),
                    always=True,
                )

        if monthly_savings_avg and monthly_savings_avg > 0:
            for goal in self._savings_goals[:1]:
                goal_name = str(goal.get("name") or default_goal_name)
                remaining = float(goal.get("remaining_amount") or 0.0)
                if remaining <= 0:
                    break
                months_to_goal = remaining / monthly_savings_avg
                eta_year, eta_month = shift_month(self._year, self._month, int(round(months_to_goal)))
                builder.add(
                    "goal_projection",
                    "info",
                    self._t(
                        "A este ritmo de ahorro, completarás tu meta '{goal_name}' en {eta_year:04d}-{eta_month:02d}.",
                        "At this savings pace, you will complete your '{goal_name}' goal in {eta_year:04d}-{eta_month:02d}.",
                        params={"goal_name": goal_name, "eta_year": eta_year, "eta_month": eta_month},
                    ),
                )
                break

    def _generate_50_30_20_message(self, builder: MessageBuilder) -> None:
        mira_50_30_20 = self._metrics.mira_50_30_20
        builder.add(
            "mira_50_30_20",
            "info",
            self._t(
                "Tu distribución es {needs:.1f}% Necesidades / {wants:.1f}% Deseos / {savings:.1f}% Ahorro. Desviación total {deviation:.1f}%.",
                "Your mix is {needs:.1f}% Needs / {wants:.1f}% Wants / {savings:.1f}% Savings. Total deviation {deviation:.1f}%.",
                params={
                    "needs": mira_50_30_20.needs_pct,
                    "wants": mira_50_30_20.wants_pct,
                    "savings": mira_50_30_20.savings_pct,
                    "deviation": mira_50_30_20.deviation_pct,
                },
            ),
        )

    def _generate_freedom_margin_message(self, builder: MessageBuilder) -> None:
        freedom_margin_metrics = self._metrics.freedom_margin_metrics
        freedom_margin_pct = cast(float | None, freedom_margin_metrics.pct)
        if freedom_margin_pct is None:
            return
        freedom_zone = str(freedom_margin_metrics.zone or "")
        freedom_zone_text_es = {
            "fast_track": "Via Rapida",
            "construction_zone": "Zona de Construccion",
            "balance_point": "Punto de Equilibrio",
            "red_alert": "Alerta Roja",
        }.get(freedom_zone, "Zona de Construccion")
        freedom_zone_text_en = {
            "fast_track": "Fast Track",
            "construction_zone": "Construction Zone",
            "balance_point": "Balance Point",
            "red_alert": "Red Alert",
        }.get(freedom_zone, "Construction Zone")
        freedom_tone_es = {
            "fast_track": "Tu dinero esta reteniendo una parte fuerte de tu esfuerzo mensual.",
            "construction_zone": "Vas bien, aunque con poco margen para errores o imprevistos.",
            "balance_point": "Cualquier imprevisto puede desestabilizarte.",
            "red_alert": "Tu estilo de vida esta costando mas que tu realidad actual.",
        }.get(freedom_zone, "Vas bien, aunque con poco margen para errores o imprevistos.")
        freedom_tone_en = {
            "fast_track": "Your money is keeping a strong share of your monthly effort.",
            "construction_zone": "You are doing well, but with limited room for mistakes or surprises.",
            "balance_point": "Any surprise can destabilize you.",
            "red_alert": "Your lifestyle costs more than your current reality can support.",
        }.get(freedom_zone, "You are doing well, but with limited room for mistakes or surprises.")
        freedom_level = (
            "critical"
            if freedom_zone == "red_alert"
            else (
                "warning"
                if freedom_zone == "balance_point"
                else "info" if freedom_zone == "construction_zone" else "success"
            )
        )
        builder.add(
            "freedom_margin",
            freedom_level,
            self._t(
                "Tu Margen de Libertad es {pct:.1f}%. Zona: {zone}. {tone}",
                "Your Freedom Margin is {pct:.1f}%. Zone: {zone}. {tone}",
                params={
                    "pct": freedom_margin_pct,
                    "zone": self._t(freedom_zone_text_es, freedom_zone_text_en),
                    "tone": self._t(freedom_tone_es, freedom_tone_en),
                },
            ),
            always=True,
        )

    def _generate_ratios_messages(self, builder: MessageBuilder) -> None:
        income_total = self._metrics.income_total
        savings_rate = self._metrics.savings_rate
        expense_income_ratio = self._metrics.expense_income_ratio
        top_categories = self._metrics.top_categories
        income_by_root = self._metrics.income_by_root
        concentration_pct = self._metrics.concentration_pct
        dependence_pct = self._metrics.dependence_pct

        if savings_rate is not None:
            tone = (
                self._t("¡Vas por excelente camino!", "You are on an excellent path!")
                if savings_rate > 20
                else (
                    self._t("Estás tirando de ahorros o deuda.", "You are drawing on savings or debt.")
                    if savings_rate < 0
                    else self._t("Continúa monitoreando tu ritmo.", "Keep monitoring your pace.")
                )
            )
            builder.add(
                "savings_rate",
                "info",
                self._t(
                    "Tu tasa de ahorro real es {pct:.1f}%. {tone}",
                    "Your real savings rate is {pct:.1f}%. {tone}",
                    params={"pct": savings_rate, "tone": tone},
                ),
            )

        if expense_income_ratio is not None:
            builder.add(
                "expense_income_ratio",
                "info",
                self._t(
                    "Tu ratio gasto/ingreso es {ratio:.2f}.",
                    "Your expense-to-income ratio is {ratio:.2f}.",
                    params={"ratio": expense_income_ratio},
                ),
            )

        if concentration_pct is not None and top_categories:
            top_name, _top_amount = top_categories[0]
            builder.add(
                "expense_concentration",
                "info",
                self._t(
                    "El {pct:.1f}% de tu gasto está en la categoría '{name}'.",
                    "{pct:.1f}% of your spending is in the '{name}' category.",
                    params={"pct": concentration_pct, "name": top_name},
                ),
            )

        if dependence_pct is not None and income_by_root and income_total > 0:
            root_name, _root_amount = max(income_by_root.items(), key=lambda item: item[1])
            builder.add(
                "income_dependence",
                "info",
                self._t(
                    "El {pct:.1f}% de tus ingresos proviene de '{name}'.",
                    "{pct:.1f}% of your income comes from '{name}'.",
                    params={"pct": dependence_pct, "name": root_name},
                ),
            )

    def generate(self) -> list[dict[str, Any]]:
        """Generate all messages, filter by threshold, and return sorted list."""
        builder = MessageBuilder()
        self._generate_income_vs_previous(builder)
        self._generate_budget_messages(builder)
        self._generate_net_messages(builder)
        self._generate_debt_messages(builder)
        self._generate_spending_pattern_messages(builder)
        self._generate_burn_rate_message(builder)
        self._generate_goal_messages(builder)
        self._generate_50_30_20_message(builder)
        self._generate_freedom_margin_message(builder)
        self._generate_ratios_messages(builder)

        threshold_pct = self._relevance_threshold * 100.0
        filtered = [
            msg
            for msg in builder.build()
            if msg["always"] or msg.get("pct") is None or float(msg["pct"]) >= threshold_pct
        ]
        filtered.sort(key=lambda msg: (_message_level_priority(str(msg["level"])), str(msg["code"])))
        return filtered


def _comparison_to_dict(v: ComparisonResult | None) -> dict[str, Any] | None:
    """Convert a :class:`ComparisonResult` to a plain dict for the JSON payload."""
    if v is None:
        return None
    return {"base": v.base, "variance": v.variance, "pct": v.pct, "signal": v.signal}


def _build_income_vs_expense_section(
    category_relations: list[dict[str, Any]],
    income_by_root: dict[str, float],
    expense_by_root: dict[str, float],
) -> list[dict[str, Any]] | None:
    """Build the Income vs Expenses by Income Category section.

    Returns ``None`` when there are no category relations so the section
    is omitted from the report.  All monetary amounts come from the
    already period-filtered ``income_by_root`` and ``expense_by_root``
    dicts (computed from the report-month transactions).

    Each entry maps one income category to **all** its linked expense
    categories with a total for direct comparison::

        {
            "income_category": "Salarios",
            "income_amount": 2000.00,
            "expenses": [
                {"category": "Vivienda", "amount": 300.00},
                {"category": "Alimentación", "amount": 400.00},
            ],
            "expense_total": 700.00,
        }
    """
    if not category_relations:
        return None

    # Group relations by income category name.
    grouped: dict[str, list[str]] = {}
    for rel in category_relations:
        inc_name = str(rel.get("income_category_name") or "")
        exp_name = str(rel.get("expense_category_name") or "")
        if not inc_name or not exp_name:
            continue
        grouped.setdefault(inc_name, []).append(exp_name)

    if not grouped:
        return None

    result: list[dict[str, Any]] = []
    for inc_name in sorted(grouped):
        inc_amount = round(income_by_root.get(inc_name, 0.0), 2)
        expenses: list[dict[str, Any]] = []
        expense_total = 0.0
        for exp_name in sorted(grouped[inc_name]):
            exp_amount = round(expense_by_root.get(exp_name, 0.0), 2)
            expenses.append({"category": exp_name, "amount": exp_amount})
            expense_total += exp_amount
        result.append(
            {
                "income_category": inc_name,
                "income_amount": inc_amount,
                "expenses": expenses,
                "expense_total": round(expense_total, 2),
            }
        )
    return result


def build_report_payload(inputs: ReportInputs) -> dict[str, Any]:
    """Orchestrate the four specialised components and assemble the report payload."""
    report_language = _normalize_report_language(inputs.language)

    goal_data = GoalProgressAnalyzer(
        inputs.savings_goals, inputs.year, inputs.month, language=report_language
    ).analyze()

    metrics = ReportMetricsCalculator(inputs, goal_data).compute()

    waterfall = WaterfallChartBuilder(
        income_total=metrics.income_total,
        net_after_expenses=metrics.net_after_expenses,
        displayed_categories=metrics.displayed_waterfall_categories,
        remaining_categories=metrics.remaining_waterfall_categories,
        normal_categories=metrics.normal_waterfall_categories,
        inconsistent_entry=metrics.inconsistent_waterfall_entry,
        all_waterfall_category_totals=metrics.waterfall_category_totals,
        language=report_language,
    ).build()

    advisor_messages = ReportMessageGenerator(
        metrics=metrics,
        goal_data=goal_data,
        savings_goals=inputs.savings_goals,
        year=inputs.year,
        month=inputs.month,
        relevance_threshold=inputs.relevance_threshold,
        language=report_language,
    ).generate()

    cc = metrics.credit_card
    income_vs_expense_by_income = _build_income_vs_expense_section(
        inputs.category_relations,
        metrics.income_by_root,
        metrics.top_category_totals,
    )
    return {
        "period": {"year": inputs.year, "month": inputs.month},
        "kpis": {
            "income": metrics.current_summary.income,
            "expense_operational": metrics.current_summary.expense_operational,
            "savings": metrics.current_summary.savings,
            "net": metrics.current_summary.net,
            "debt_payment": metrics.current_summary.debt_payment,
            "refunds": metrics.current_summary.refunds,
        },
        "comparisons": {
            section: {k: _comparison_to_dict(v) for k, v in vals.items()}
            for section, vals in metrics.comparisons.items()
        },
        "budget": {
            "has_budget": metrics.budget_context.has_budget,
            "budget_id": metrics.budget_context.budget_id,
            "budget_code": metrics.budget_context.budget_code,
            "income": metrics.budget_context.income,
            "expense_operational": metrics.budget_context.expense_operational,
            "is_complete_for_period": metrics.budget_context.is_complete_for_period,
            "missing_income_categories": metrics.budget_context.missing_income_categories,
            "missing_expense_categories": metrics.budget_context.missing_expense_categories,
        },
        "history_hints": metrics.history_hints,
        "consistency": {
            "operational_expense_total": metrics.total_expense,
            "top5_total": metrics.top_total,
            "top5_le_total": metrics.top_total <= metrics.total_expense + 1e-9,
        },
        "ytd": metrics.ytd,
        "allocation": {
            "top_expense_categories": [
                {
                    "name": name,
                    "amount": round(amount, 2),
                    "children": [
                        {"name": child, "amount": round(child_amount, 2)}
                        for child, child_amount in sorted(
                            metrics.top_category_children.get(name, {}).items(),
                            key=lambda item: item[1],
                            reverse=True,
                        )
                    ],
                }
                for name, amount in metrics.top_categories
            ],
            "top_tags": [
                {
                    "name": name,
                    "amount": round(amount, 2),
                    "children": [
                        {"name": child, "amount": round(child_amount, 2)}
                        for child, child_amount in sorted(
                            metrics.tag_children.get(name, {}).items(),
                            key=lambda item: item[1],
                            reverse=True,
                        )
                    ],
                }
                for name, amount in metrics.top_tags
            ],
        },
        "waterfall": waterfall,
        "historical_stacked": metrics.stacked_6,
        "advisor": {"threshold": inputs.relevance_threshold, "messages": advisor_messages},
        "goals_summary": goal_data.goals_summary,
        "metrics": {
            "burn_rate_days": round(metrics.burn_days, 2) if metrics.burn_days is not None else None,
            "daily_living_cost": round(metrics.daily_living_cost, 2),
            "goal_completion_index_pct": metrics.goal_completion_index_pct,
            "savings_rate_pct": round(metrics.savings_rate, 2) if metrics.savings_rate is not None else None,
            "debt_payment_income_pct": (
                round(metrics.debt_payment_income_pct, 2) if metrics.debt_payment_income_pct is not None else None
            ),
            "debt_payment_expense_pct": (
                round(metrics.debt_payment_expense_pct, 2) if metrics.debt_payment_expense_pct is not None else None
            ),
            "credit_card_expense_count": cc.expense_count,
            "credit_card_expense_amount": cc.expense_amount,
            "credit_card_payment_count": cc.payment_count,
            "credit_card_payment_amount": cc.payment_amount,
            "credit_card_gap_amount": cc.gap_amount,
            "expense_income_ratio": (
                round(metrics.expense_income_ratio, 2) if metrics.expense_income_ratio is not None else None
            ),
            "expense_concentration_pct": (
                round(metrics.concentration_pct, 2) if metrics.concentration_pct is not None else None
            ),
            "income_dependence_pct": (round(metrics.dependence_pct, 2) if metrics.dependence_pct is not None else None),
            "freedom_margin": {
                "pct": metrics.freedom_margin_metrics.pct,
                "zone": metrics.freedom_margin_metrics.zone,
                "label": metrics.freedom_margin_metrics.label,
                "is_red_alert": metrics.freedom_margin_metrics.is_red_alert,
            },
            "lifestyle_inflation": {
                "income_growth_pct": metrics.lifestyle_inflation_metrics.income_growth_pct,
                "expense_growth_pct": metrics.lifestyle_inflation_metrics.expense_growth_pct,
                "expense_to_income_growth_ratio": metrics.lifestyle_inflation_metrics.expense_to_income_growth_ratio,
                "is_applicable": metrics.lifestyle_inflation_metrics.is_applicable,
                "is_alert": metrics.lifestyle_inflation_metrics.is_alert,
            },
            "savings_efficiency": {
                "surplus_amount": metrics.savings_efficiency_metrics.surplus_amount,
                "goal_funding_amount": metrics.savings_efficiency_metrics.goal_funding_amount,
                "goal_funding_efficiency_pct": metrics.savings_efficiency_metrics.goal_funding_efficiency_pct,
                "surplus_leakage_amount": metrics.savings_efficiency_metrics.surplus_leakage_amount,
                "has_surplus_leakage_alert": metrics.savings_efficiency_metrics.has_surplus_leakage_alert,
            },
            "goal_contributions": {
                "count": metrics.goal_contribution_metrics.count,
                "amount": metrics.goal_contribution_metrics.amount,
                "by_goal": metrics.goal_contribution_metrics.by_goal,
            },
            "generic_analysis": metrics.generic_analysis,
            "mira_50_30_20": {
                "needs_pct": metrics.mira_50_30_20.needs_pct,
                "wants_pct": metrics.mira_50_30_20.wants_pct,
                "savings_pct": metrics.mira_50_30_20.savings_pct,
                "deviation_pct": metrics.mira_50_30_20.deviation_pct,
            },
        },
        "income_vs_expense_by_income": income_vs_expense_by_income,
    }
