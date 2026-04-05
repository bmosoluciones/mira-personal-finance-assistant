# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Backend helpers for the MIRA Master Report."""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime
from typing import Any, TypedDict, cast

from mira.finance_summary import build_savings_lookup, is_savings_transaction, summarize_financial_kpis

_REFUND_KEYWORDS = ("reembolso", "refund", "devolucion", "devolución")
_DEBT_KEYWORDS = ("deuda", "prestamo", "préstamo", "loan", "tarjeta", "credit")
_MAX_WATERFALL_EXPENSE_STEPS = 6


class _ComparisonValue(TypedDict):
    base: float | None
    variance: float | None
    pct: float | None
    signal: str


class _BudgetContext(TypedDict):
    has_budget: bool
    budget_id: int | None
    budget_code: str | None
    income: float
    expense_operational: float
    is_complete_for_period: bool
    missing_income_categories: list[str]
    missing_expense_categories: list[str]


def _normalize_report_language(language: str | None) -> str:
    return "es" if str(language or "").strip().lower() == "es" else "en"


def _report_text(
    language: str,
    es: str,
    en: str,
    *,
    params: dict[str, Any] | None = None,
) -> str:
    text = es if language == "es" else en
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


def _month_summary(transactions: list[dict[str, Any]], savings_lookup) -> dict[str, float]:
    summary = summarize_financial_kpis(transactions, savings_lookup)
    debt_payment_total = 0.0
    refunds_total = 0.0

    for tx in transactions:
        tx_type = str(tx.get("type") or "")
        amount = float(tx.get("amount") or 0.0)
        text = _tx_text(tx)

        if tx_type == "income":
            if any(keyword in text for keyword in _REFUND_KEYWORDS):
                refunds_total += amount
            continue

        if tx_type != "expense":
            continue

        if is_savings_transaction(tx, savings_lookup):
            continue

        if any(keyword in text for keyword in _DEBT_KEYWORDS):
            debt_payment_total += amount
    return {
        "income": float(summary["income"]),
        "expense_operational": float(summary["expense"]),
        "savings": float(summary["savings"]),
        "debt_payment": round(debt_payment_total, 2),
        "refunds": round(refunds_total, 2),
        "net": float(summary["net"]),
    }


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
) -> dict[str, Any]:
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
    return {
        "income_growth_pct": round(income_growth_pct, 2) if income_growth_pct is not None else None,
        "expense_growth_pct": round(expense_growth_pct, 2) if expense_growth_pct is not None else None,
        "expense_to_income_growth_ratio": round(ratio, 2) if ratio is not None else None,
        "is_applicable": is_applicable,
        "is_alert": is_alert,
    }


def _build_goal_contribution_metrics(
    month_transactions: list[dict[str, Any]],
    savings_goals: list[dict[str, Any]],
) -> dict[str, Any]:
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

    return {
        "count": contribution_count,
        "amount": round(contribution_total, 2),
        "by_goal": {name: round(amount, 2) for name, amount in sorted(contributions_by_goal.items())},
    }


def _build_savings_efficiency_metrics(
    *,
    net_amount: float,
    goal_contribution_amount: float,
    has_active_goals: bool,
) -> dict[str, Any]:
    efficiency_pct = None
    if net_amount > 0:
        efficiency_pct = (goal_contribution_amount / net_amount) * 100.0

    leakage_amount = max(0.0, net_amount - goal_contribution_amount) if net_amount > 0 else 0.0
    has_surplus_leakage_alert = net_amount > 0 and has_active_goals and goal_contribution_amount <= 0.005
    return {
        "surplus_amount": round(net_amount, 2) if net_amount > 0 else 0.0,
        "goal_funding_amount": round(goal_contribution_amount, 2),
        "goal_funding_efficiency_pct": round(efficiency_pct, 2) if efficiency_pct is not None else None,
        "surplus_leakage_amount": round(leakage_amount, 2),
        "has_surplus_leakage_alert": has_surplus_leakage_alert,
    }


def _build_freedom_margin_metrics(income_total: float, total_expense: float) -> dict[str, Any]:
    if income_total <= 0:
        return {
            "pct": None,
            "zone": None,
            "label": None,
            "is_red_alert": False,
        }

    freedom_margin_pct = ((income_total - total_expense) / income_total) * 100.0
    if freedom_margin_pct >= 30.0:
        zone = "fast_track"
        label = "via_rapida"
    elif freedom_margin_pct >= 10.0:
        zone = "construction_zone"
        label = "zona_de_construccion"
    elif freedom_margin_pct >= 1.0:
        zone = "balance_point"
        label = "punto_de_equilibrio"
    else:
        zone = "red_alert"
        label = "alerta_roja"

    return {
        "pct": round(freedom_margin_pct, 2),
        "zone": zone,
        "label": label,
        "is_red_alert": freedom_margin_pct < 0,
    }


def _build_goal_completion_index(goal_rows: list[dict[str, Any]], active_goals: list[dict[str, Any]]) -> float | None:
    if active_goals:
        return round(sum(float(goal["progress_pct"]) for goal in active_goals) / len(active_goals), 2)
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
    if spent_pct >= 100.0:
        classification = "strained"
    elif spent_pct >= 90.0:
        classification = "fragile"
    elif spent_pct >= 70.0:
        classification = "watch"
    else:
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
    if score >= 70.0:
        classification = "high"
    elif score >= 40.0:
        classification = "medium"
    else:
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
    if score >= 35.0:
        classification = "high"
    elif score >= 18.0:
        classification = "medium"
    else:
        classification = "low"
    return {"classification": classification, "volatility_pct": round(volatility_pct, 2)}


def _build_financial_momentum_metric(
    *,
    gap_trend: dict[str, Any],
    income_trend: dict[str, Any],
    expense_trend: dict[str, Any],
) -> dict[str, Any]:
    if str(gap_trend.get("direction") or "") == "up" and str(expense_trend.get("direction") or "") != "up":
        direction = "positive"
    elif str(gap_trend.get("direction") or "") == "down" or (
        str(expense_trend.get("direction") or "") == "up" and str(income_trend.get("direction") or "") != "up"
    ):
        direction = "negative"
    else:
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
    if trend == "up" and (drift == "up" or pattern == "impulsive"):
        classification = "out_of_control"
    elif trend == "down" and pattern == "consistent":
        classification = "in_control"
    else:
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


def build_report_payload(
    *,
    year: int,
    month: int,
    month_transactions: list[dict[str, Any]],
    month_transactions_raw: list[dict[str, Any]],
    previous_transactions: list[dict[str, Any]],
    trailing_3: list[list[dict[str, Any]]],
    comparison_trailing_6: list[tuple[int, int, list[dict[str, Any]]]],
    historical_6: list[tuple[int, int, list[dict[str, Any]]]],
    ytd_months: list[tuple[int, int, list[dict[str, Any]]]],
    categories: list[dict[str, Any]],
    tags_by_tx: dict[int, list[dict[str, Any]]],
    budget: dict[str, Any] | None,
    budget_monthly_by_type: dict[str, dict[str, float]] | None,
    budget_category_rows: list[dict[str, Any]] | None,
    accounts: list[dict[str, Any]],
    account_balance_total: float,
    savings_goals: list[dict[str, Any]],
    relevance_threshold: float = 0.10,
    language: str = "en",
) -> dict[str, Any]:
    report_language = _normalize_report_language(language)

    def _t(es: str, en: str, *, params: dict[str, Any] | None = None) -> str:
        return _report_text(report_language, es, en, params=params)

    uncategorized_label = _t("(sin categoría)", "(uncategorized)")
    untagged_label = _t("(sin tag)", "(untagged)")
    default_goal_name = _t("Meta", "Goal")
    other_expenses_label = _t("Otros gastos", "Other expenses")
    inconsistent_expense_label = _t(
        "Gastos con categoría inconsistente",
        "Expenses with inconsistent category",
    )

    threshold_pct = relevance_threshold * 100.0
    savings_lookup = build_savings_lookup(categories)
    current_summary = _month_summary(month_transactions, savings_lookup)
    previous_summary = _month_summary(previous_transactions, savings_lookup)
    credit_account_ids = {
        int(account["id"])
        for account in accounts
        if account.get("id") is not None and str(account.get("account_type") or "") == "credit"
    }

    credit_card_expense_count = 0
    credit_card_expense_amount = 0.0
    credit_card_payment_count = 0
    credit_card_payment_amount = 0.0
    for tx in month_transactions_raw:
        account_id_raw = tx.get("account_id")
        if account_id_raw is None:
            continue
        try:
            account_id = int(account_id_raw)
        except (TypeError, ValueError):
            continue
        if account_id not in credit_account_ids:
            continue

        tx_type = str(tx.get("type") or "")
        amount = float(tx.get("amount") or 0.0)
        is_transfer = int(tx.get("is_transfer") or 0) == 1
        if tx_type == "expense" and not is_transfer:
            credit_card_expense_count += 1
            credit_card_expense_amount += amount
        elif tx_type == "income" and is_transfer:
            credit_card_payment_count += 1
            credit_card_payment_amount += amount

    credit_card_gap_amount = round(credit_card_expense_amount - credit_card_payment_amount, 2)

    trailing_3_summaries = [_month_summary(items, savings_lookup) for items in trailing_3]
    trailing_6_summaries = [_month_summary(items, savings_lookup) for _y, _m, items in comparison_trailing_6]
    historical_6_summaries = [_month_summary(items, savings_lookup) for _y, _m, items in historical_6]

    def _avg(summaries: list[dict[str, float]], key: str) -> float | None:
        if not summaries:
            return None
        return round(sum(item[key] for item in summaries) / len(summaries), 2)

    avg_3 = {
        "income": _avg(trailing_3_summaries, "income"),
        "expense_operational": _avg(trailing_3_summaries, "expense_operational"),
        "savings": _avg(trailing_3_summaries, "savings"),
        "net": _avg(trailing_3_summaries, "net"),
    }
    avg_6 = {
        "income": _avg(trailing_6_summaries, "income"),
        "expense_operational": _avg(trailing_6_summaries, "expense_operational"),
        "savings": _avg(trailing_6_summaries, "savings"),
        "net": _avg(trailing_6_summaries, "net"),
    }

    ytd = []
    cumulative = {"income": 0.0, "expense_operational": 0.0, "savings": 0.0, "net": 0.0}
    for ym_year, ym_month, txs in ytd_months:
        summary = _month_summary(txs, savings_lookup)
        cumulative["income"] += summary["income"]
        cumulative["expense_operational"] += summary["expense_operational"]
        cumulative["savings"] += summary["savings"]
        cumulative["net"] += summary["net"]
        ytd.append(
            {
                "year": ym_year,
                "month": ym_month,
                "income": round(cumulative["income"], 2),
                "expense_operational": round(cumulative["expense_operational"], 2),
                "savings": round(cumulative["savings"], 2),
                "net": round(cumulative["net"], 2),
            }
        )

    report_period_end = month_bounds(year, month)[1]
    goal_rows: list[dict[str, Any]] = []
    for raw_goal in savings_goals:
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
            {
                "name": goal_name,
                "currency": str(raw_goal.get("currency") or "").strip(),
                "target_amount": round(target_amount, 2),
                "current_amount": round(current_amount, 2),
                "remaining_amount": round(remaining_amount, 2),
                "progress_ratio": progress_ratio,
                "progress_pct": round(min(progress_ratio * 100.0, 100.0), 1),
                "target_date": target_date_text or None,
                "parsed_target_date": parsed_target_date,
                "achieved": remaining_amount <= 0.005 or progress_ratio >= 1.0,
            }
        )

    completed_goals = [goal for goal in goal_rows if bool(goal["achieved"])]
    active_goals = [goal for goal in goal_rows if not bool(goal["achieved"])]
    active_goals.sort(
        key=lambda goal: (
            goal["parsed_target_date"] is None,
            cast(date | None, goal["parsed_target_date"]) or date.max,
            float(goal["remaining_amount"]),
            str(goal["name"]).casefold(),
        )
    )

    goals_summary_items: list[str] = []
    if goal_rows:
        ordered_summary_goals = active_goals[:2] + completed_goals[:1]
        for goal in ordered_summary_goals:
            deadline_suffix = (
                _t(" Meta: {target_date}.", " Deadline: {target_date}.", params={"target_date": goal["target_date"]})
                if goal.get("target_date")
                else ""
            )
            if bool(goal["achieved"]):
                goals_summary_items.append(
                    _t(
                        "{goal_name}: cumplida ({current:.2f}/{target:.2f} {currency}).",
                        "{goal_name}: achieved ({current:.2f}/{target:.2f} {currency}).",
                        params={
                            "goal_name": goal["name"],
                            "current": float(goal["current_amount"]),
                            "target": float(goal["target_amount"]),
                            "currency": goal["currency"],
                        },
                    )
                )
            else:
                goals_summary_items.append(
                    _t(
                        "{goal_name}: {progress:.1f}% completada, faltan {remaining:.2f} {currency}.{deadline}",
                        "{goal_name}: {progress:.1f}% complete, {remaining:.2f} {currency} remaining.{deadline}",
                        params={
                            "goal_name": goal["name"],
                            "progress": float(goal["progress_pct"]),
                            "remaining": float(goal["remaining_amount"]),
                            "currency": goal["currency"],
                            "deadline": deadline_suffix,
                        },
                    )
                )

    goals_summary = {
        "total_goals": len(goal_rows),
        "completed_goals": len(completed_goals),
        "active_goals": len(active_goals),
        "headline": (
            _t(
                "No tienes metas de ahorro configuradas todavia.",
                "You do not have any savings goals configured yet.",
            )
            if not goal_rows
            else _t(
                "Resumen: {completed} metas cumplidas y {active} en progreso.",
                "Summary: {completed} goals achieved and {active} in progress.",
                params={"completed": len(completed_goals), "active": len(active_goals)},
            )
        ),
        "items": goals_summary_items,
    }
    goal_contribution_metrics = _build_goal_contribution_metrics(month_transactions, savings_goals)

    roots_meta: dict[str, dict[str, Any]] = {}
    root_rollup_meta: dict[str, dict[str, Any]] = {}
    by_id = {int(cat["id"]): cat for cat in categories if cat.get("id") is not None}
    for cat in categories:
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

    # Este reporte siempre se calcula para un único mes seleccionado por año/mes,
    # pero ese mes puede ser histórico. Si una categoría se renombra después,
    # necesitamos usar el category_id persistido para reconstruir correctamente
    # la raíz del mes consultado.
    def _resolve_tx_root_meta(tx: dict[str, Any]) -> dict[str, Any]:
        tx_type = str(tx.get("type") or "")
        tx_cat_name = str(tx.get("category") or "").strip()
        tx_cat_id = tx.get("category_id")
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

    for tx in month_transactions:
        tx_type = str(tx.get("type") or "")
        amount = float(tx.get("amount") or 0.0)
        cat_name = str(tx.get("category") or "").strip()
        root_meta = _resolve_tx_root_meta(tx)
        root_name = str(root_meta.get("root") or uncategorized_label)

        if tx_type == "income":
            income_by_root[root_name] += amount
            continue

        if tx_type != "expense":
            continue

        if is_savings_transaction(tx, savings_lookup):
            continue

        child_label = str(tx.get("subcategory") or "").strip() or (cat_name or uncategorized_label)
        top_category_totals[root_name] += amount
        top_category_children[root_name][child_label] += amount
        root_rollup = root_rollup_meta.get(root_name.casefold()) or {"type": "expense", "is_savings": False}
        waterfall_root_name = (
            root_name if str(root_rollup.get("type") or "expense") == "expense" else inconsistent_expense_label
        )
        waterfall_expense_totals[waterfall_root_name] += amount

        tx_id = int(tx.get("id") or 0)
        for tg in tags_by_tx.get(tx_id, []):
            tag_name = str(tg.get("name") or "").strip() or untagged_label
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

    top_categories = sorted(top_category_totals.items(), key=lambda item: item[1], reverse=True)[:5]
    top_tags = sorted(tag_totals.items(), key=lambda item: item[1], reverse=True)[:5]
    waterfall_category_totals = sorted(
        ((name, round(amount, 2)) for name, amount in waterfall_expense_totals.items() if amount > 0),
        key=lambda item: item[1],
        reverse=True,
    )
    inconsistent_waterfall_entry = next(
        (item for item in waterfall_category_totals if item[0] == inconsistent_expense_label),
        None,
    )
    normal_waterfall_categories = [item for item in waterfall_category_totals if item[0] != inconsistent_expense_label]
    displayed_waterfall_categories = list(normal_waterfall_categories[:_MAX_WATERFALL_EXPENSE_STEPS])
    remaining_waterfall_categories = normal_waterfall_categories[_MAX_WATERFALL_EXPENSE_STEPS:]
    if remaining_waterfall_categories:
        displayed_waterfall_categories.append(
            (other_expenses_label, round(sum(amount for _name, amount in remaining_waterfall_categories), 2))
        )
    if inconsistent_waterfall_entry is not None:
        displayed_waterfall_categories.append(inconsistent_waterfall_entry)

    def _monthly_root_stack(monthly_txs: list[dict[str, Any]], section: str) -> dict[str, float]:
        acc: dict[str, float] = defaultdict(float)
        for tx in monthly_txs:
            tx_type = str(tx.get("type") or "")
            if section == "income" and tx_type != "income":
                continue
            if section == "expense" and tx_type != "expense":
                continue
            cat_name = str(tx.get("category") or "").strip()
            root_meta = roots_meta.get(
                cat_name.casefold(), {"root": cat_name or uncategorized_label, "is_savings": False}
            )
            if section == "expense" and is_savings_transaction(tx, savings_lookup):
                continue
            root_name = str(root_meta.get("root") or uncategorized_label)
            acc[root_name] += float(tx.get("amount") or 0.0)
        return {k: round(v, 2) for k, v in acc.items()}

    stacked_6: dict[str, list[dict[str, Any]]] = {"income": [], "expense": []}
    for m_year, m_month, txs in historical_6:
        period = f"{m_year:04d}-{m_month:02d}"
        stacked_6["income"].append({"period": period, "segments": _monthly_root_stack(txs, "income")})
        stacked_6["expense"].append({"period": period, "segments": _monthly_root_stack(txs, "expense")})

    budget_context: _BudgetContext = {
        "has_budget": False,
        "budget_id": None,
        "budget_code": None,
        "income": 0.0,
        "expense_operational": 0.0,
        "is_complete_for_period": False,
        "missing_income_categories": [],
        "missing_expense_categories": [],
    }
    if budget is not None and budget_monthly_by_type is not None:
        income_budget = round(sum(budget_monthly_by_type.get("income", {}).values()), 2)
        expense_budget = round(sum(budget_monthly_by_type.get("expense", {}).values()), 2)
        if (income_budget + expense_budget) > 0.0:
            budget_context["has_budget"] = True
            budget_context["budget_id"] = int(budget["id"])
            budget_context["budget_code"] = str(budget.get("code") or "")
            budget_context["income"] = income_budget
            budget_context["expense_operational"] = expense_budget
            budget_context["is_complete_for_period"] = True
            actual_income_by_cat_id: dict[int, float] = defaultdict(float)
            actual_expense_by_cat_id: dict[int, float] = defaultdict(float)
            for tx in month_transactions:
                cat_id_raw = tx.get("category_id")
                tx_type = str(tx.get("type") or "")
                if cat_id_raw is None:
                    continue
                cat_id = int(cat_id_raw)
                amount = float(tx.get("amount") or 0.0)
                if tx_type == "income":
                    actual_income_by_cat_id[cat_id] += amount
                if tx_type == "expense" and not is_savings_transaction(tx, savings_lookup):
                    actual_expense_by_cat_id[cat_id] += amount

            if budget_category_rows:
                missing_income: set[str] = set()
                missing_expense: set[str] = set()
                for row in budget_category_rows:
                    row_type = str(row.get("type") or "")
                    row_name = str(row.get("name") or "").strip()
                    row_amount = float(row.get("amount") or 0.0)
                    row_cat_id = row.get("category_id")
                    if row_amount <= 0 or not row_name or row_cat_id is None:
                        continue
                    cat_id = int(row_cat_id)
                    if row_type == "income" and actual_income_by_cat_id.get(cat_id, 0.0) <= 0:
                        missing_income.add(row_name)
                    if row_type == "expense" and actual_expense_by_cat_id.get(cat_id, 0.0) <= 0:
                        missing_expense.add(row_name)
                budget_context["missing_income_categories"] = sorted(missing_income)
                budget_context["missing_expense_categories"] = sorted(missing_expense)

    def _compare_value(current: float, base: float | None, section: str) -> _ComparisonValue:
        variance = None if base is None else round(current - base, 2)
        pct = pct_change(current, base) if base is not None else None
        return {"base": base, "variance": variance, "pct": pct, "signal": _trend_signal(section, variance)}

    comparisons: dict[str, dict[str, _ComparisonValue | None]] = {
        "income": {
            "vs_previous": _compare_value(current_summary["income"], previous_summary["income"], "income"),
            "vs_avg_3": _compare_value(current_summary["income"], avg_3["income"], "income"),
            "vs_avg_6": _compare_value(current_summary["income"], avg_6["income"], "income"),
            "vs_budget": (
                _compare_value(current_summary["income"], budget_context["income"], "income")
                if budget_context["has_budget"]
                else None
            ),
        },
        "expense_operational": {
            "vs_previous": _compare_value(
                current_summary["expense_operational"], previous_summary["expense_operational"], "expense"
            ),
            "vs_avg_3": _compare_value(current_summary["expense_operational"], avg_3["expense_operational"], "expense"),
            "vs_avg_6": _compare_value(current_summary["expense_operational"], avg_6["expense_operational"], "expense"),
            "vs_budget": (
                _compare_value(current_summary["expense_operational"], budget_context["expense_operational"], "expense")
                if budget_context["has_budget"]
                else None
            ),
        },
        "savings": {
            "vs_previous": _compare_value(current_summary["savings"], previous_summary["savings"], "savings"),
            "vs_avg_3": _compare_value(current_summary["savings"], avg_3["savings"], "savings"),
            "vs_avg_6": _compare_value(current_summary["savings"], avg_6["savings"], "savings"),
        },
        "net": {
            "vs_previous": _compare_value(current_summary["net"], previous_summary["net"], "net"),
            "vs_avg_3": _compare_value(current_summary["net"], avg_3["net"], "net"),
            "vs_avg_6": _compare_value(current_summary["net"], avg_6["net"], "net"),
        },
    }
    income_vs_previous = cast(_ComparisonValue, comparisons["income"]["vs_previous"])
    expense_vs_previous = cast(_ComparisonValue, comparisons["expense_operational"]["vs_previous"])
    income_vs_budget = comparisons["income"]["vs_budget"]
    expense_vs_budget = comparisons["expense_operational"]["vs_budget"]
    lifestyle_inflation_metrics = _build_lifestyle_inflation_metrics(
        income_vs_previous["pct"],
        expense_vs_previous["pct"],
    )
    savings_efficiency_metrics = _build_savings_efficiency_metrics(
        net_amount=current_summary["net"],
        goal_contribution_amount=float(goal_contribution_metrics["amount"]),
        has_active_goals=bool(active_goals),
    )

    messages: list[dict[str, Any]] = []

    def add_message(code: str, level: str, text: str, *, always: bool = False, pct: float | None = None) -> None:
        messages.append({"code": code, "level": level, "text": text, "always": always, "pct": pct})

    income_prev_pct = income_vs_previous["pct"]
    if income_prev_pct is None:
        add_message(
            "income_vs_previous_missing",
            "warning",
            _t(
                "No hay historial suficiente para comparar ingresos con el mes anterior.",
                "There is not enough history to compare income with the previous month.",
            ),
            always=True,
        )
    else:
        trend = _t("mayores", "higher") if income_prev_pct >= 0 else _t("menores", "lower")
        add_message(
            "income_vs_previous",
            "info",
            _t(
                "Los ingresos de este mes fueron {pct:.1f}% {trend} en relación al mes pasado.",
                "Income this month was {pct:.1f}% {trend} than last month.",
                params={"pct": abs(income_prev_pct), "trend": trend},
            ),
            always=True,
            pct=abs(income_prev_pct),
        )

    expense_prev_pct = expense_vs_previous["pct"]
    if expense_prev_pct is None:
        add_message(
            "expense_vs_previous_missing",
            "warning",
            _t(
                "No hay historial suficiente para comparar gastos con el mes anterior.",
                "There is not enough history to compare expenses with the previous month.",
            ),
            always=True,
        )
    else:
        trend = _t("mayores", "higher") if expense_prev_pct >= 0 else _t("menores", "lower")
        add_message(
            "expense_vs_previous",
            "info",
            _t(
                "Los gastos operativos fueron {pct:.1f}% {trend} en relación al mes pasado.",
                "Operating expenses were {pct:.1f}% {trend} than last month.",
                params={"pct": abs(expense_prev_pct), "trend": trend},
            ),
            always=True,
            pct=abs(expense_prev_pct),
        )
        if bool(lifestyle_inflation_metrics["is_alert"]):
            add_message(
                "lifestyle_inflation_alert",
                "warning",
                _t(
                    "Tus ingresos subieron {income_pct:.1f}%, pero tus gastos operativos subieron {expense_pct:.1f}%. Estas absorbiendo casi todo el aumento y eso apunta a inflacion de estilo de vida.",
                    "Your income increased {income_pct:.1f}%, but your operating expenses increased {expense_pct:.1f}%. You are absorbing nearly all of the raise, which points to lifestyle inflation.",
                    params={
                        "income_pct": float(lifestyle_inflation_metrics["income_growth_pct"] or 0.0),
                        "expense_pct": float(lifestyle_inflation_metrics["expense_growth_pct"] or 0.0),
                    },
                ),
                always=True,
                pct=max(
                    float(lifestyle_inflation_metrics["income_growth_pct"] or 0.0),
                    float(lifestyle_inflation_metrics["expense_growth_pct"] or 0.0),
                ),
            )

    if budget_context["has_budget"]:
        income_budget_pct = income_vs_budget["pct"] if income_vs_budget is not None else None
        expense_budget_pct = expense_vs_budget["pct"] if expense_vs_budget is not None else None
        if income_budget_pct is not None:
            trend = _t("por encima", "above") if income_budget_pct >= 0 else _t("por debajo", "below")
            add_message(
                "income_vs_budget",
                "info",
                _t(
                    "Tus ingresos quedaron {pct:.1f}% {trend} del presupuesto.",
                    "Your income landed {pct:.1f}% {trend} budget.",
                    params={"pct": abs(income_budget_pct), "trend": trend},
                ),
                always=True,
                pct=abs(income_budget_pct),
            )
        if expense_budget_pct is not None:
            trend = _t("por encima", "above") if expense_budget_pct >= 0 else _t("por debajo", "below")
            add_message(
                "expense_vs_budget",
                "info",
                _t(
                    "Tus gastos operativos quedaron {pct:.1f}% {trend} del presupuesto.",
                    "Your operating expenses landed {pct:.1f}% {trend} budget.",
                    params={"pct": abs(expense_budget_pct), "trend": trend},
                ),
                always=True,
                pct=abs(expense_budget_pct),
            )
        for item in budget_context["missing_income_categories"]:
            add_message(
                "missing_budgeted_income",
                "warning",
                _t(
                    "Ingreso presupuestado no percibido: {item}.",
                    "Budgeted income not received: {item}.",
                    params={"item": item},
                ),
                always=True,
            )
        for item in budget_context["missing_expense_categories"]:
            add_message(
                "missing_budgeted_expense",
                "warning",
                _t(
                    "Gasto presupuestado no pagado: {item}.",
                    "Budgeted expense not paid: {item}.",
                    params={"item": item},
                ),
                always=True,
            )

    if current_summary["net"] < 0:
        add_message(
            "deficit",
            "critical",
            _t(
                "⚠️ Este mes has gastado más de lo que has ingresado. Estás utilizando {amount:.2f} de tus reservas.",
                "⚠️ You spent more than you earned this month. You are using {amount:.2f} from your reserves.",
                params={"amount": abs(current_summary["net"])},
            ),
            always=True,
        )
    else:
        add_message(
            "surplus",
            "success",
            _t(
                "✅ Vas bien: tienes {amount:.2f} disponibles para asignar a nuevas metas.",
                "✅ You are doing well: you have {amount:.2f} available to assign to new goals.",
                params={"amount": current_summary["net"]},
            ),
            always=True,
        )
        if bool(savings_efficiency_metrics["has_surplus_leakage_alert"]):
            add_message(
                "surplus_leakage",
                "warning",
                _t(
                    "Cerraste el mes con un excedente de {surplus:.2f}, pero no hubo avance registrado en metas de ahorro. Hay una posible fuga de excedente: sobro en papel, pero no llego a tus metas.",
                    "You closed the month with a surplus of {surplus:.2f}, but there was no recorded progress toward savings goals. There is a possible surplus leakage: it existed on paper, but it did not reach your goals.",
                    params={"surplus": float(savings_efficiency_metrics["surplus_amount"])},
                ),
                always=True,
            )

    total_expense = current_summary["expense_operational"]
    income_total = current_summary["income"]
    debt_payment_total = current_summary["debt_payment"]
    debt_payment_income_pct = (debt_payment_total / income_total * 100.0) if income_total > 0 else None
    debt_payment_expense_pct = (debt_payment_total / total_expense * 100.0) if total_expense > 0 else None

    if debt_payment_total > 0:
        debt_level = (
            "warning"
            if (debt_payment_income_pct or 0.0) >= 20.0 or (debt_payment_expense_pct or 0.0) >= 30.0
            else "info"
        )
        if debt_payment_income_pct is not None and debt_payment_expense_pct is not None:
            add_message(
                "credit_debt_load",
                debt_level,
                _t(
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
            add_message(
                "credit_debt_load",
                "warning",
                _t(
                    "Registraste {amount:.2f} en pagos de tarjetas de crédito y deuda, pero no hay ingresos suficientes en el periodo para medir su peso mensual.",
                    "You recorded {amount:.2f} in credit card and debt payments, but there is not enough income in the period to measure their monthly weight.",
                    params={"amount": debt_payment_total},
                ),
                always=True,
            )

    if credit_card_expense_count > 0 or credit_card_payment_count > 0:
        if credit_card_expense_amount > credit_card_payment_amount:
            add_message(
                "credit_card_usage_vs_payments",
                "warning",
                _t(
                    "En tarjetas de credito registraste {expense_count} gasto(s) por {expense_amount:.2f} y {payment_count} pago(s) internos por {payment_amount:.2f}. Como los gastos superan los pagos, hay senal de posible endeudamiento por {gap:.2f}.",
                    "For credit cards you recorded {expense_count} expense(s) totaling {expense_amount:.2f} and {payment_count} internal payment(s) totaling {payment_amount:.2f}. Because spending is higher than payments, there is a possible indebtedness signal of {gap:.2f}.",
                    params={
                        "expense_count": credit_card_expense_count,
                        "expense_amount": credit_card_expense_amount,
                        "payment_count": credit_card_payment_count,
                        "payment_amount": credit_card_payment_amount,
                        "gap": abs(credit_card_gap_amount),
                    },
                ),
                always=True,
            )
        else:
            add_message(
                "credit_card_usage_vs_payments",
                "info",
                _t(
                    "En tarjetas de credito registraste {expense_count} gasto(s) por {expense_amount:.2f} y {payment_count} pago(s) internos por {payment_amount:.2f}. Los pagos van al dia frente al gasto asociado del periodo.",
                    "For credit cards you recorded {expense_count} expense(s) totaling {expense_amount:.2f} and {payment_count} internal payment(s) totaling {payment_amount:.2f}. Payments are keeping up with the card spending recorded in the period.",
                    params={
                        "expense_count": credit_card_expense_count,
                        "expense_amount": credit_card_expense_amount,
                        "payment_count": credit_card_payment_count,
                        "payment_amount": credit_card_payment_amount,
                    },
                ),
                always=True,
            )

    weekend_pct = (weekend_total / total_expense * 100.0) if total_expense > 0 else 0.0
    weekend_avg = (weekend_total / len(weekend_days)) if weekend_days else 0.0
    add_message(
        "weekend_behavior",
        "info",
        _t(
            "El {pct:.1f}% de tus gastos ocurre en fines de semana. Tu costo promedio por sábado/domingo es {avg:.2f}.",
            "{pct:.1f}% of your spending happens on weekends. Your average cost per Saturday/Sunday is {avg:.2f}.",
            params={"pct": weekend_pct, "avg": weekend_avg},
        ),
        pct=weekend_pct,
    )

    small_pct = (small_total / total_expense * 100.0) if total_expense > 0 else 0.0
    add_message(
        "small_expenses",
        "info",
        _t(
            "Tus transacciones menores a 200 suman {amount:.2f}. Esto representa el {pct:.1f}% de tu gasto total.",
            "Transactions under 200 add up to {amount:.2f}. That represents {pct:.1f}% of your total spending.",
            params={"amount": small_total, "pct": small_pct},
        ),
        pct=small_pct,
    )

    if top_tags and current_summary["income"] > 0:
        top_tag_name, top_tag_amount = top_tags[0]
        tag_income_pct = (top_tag_amount / current_summary["income"]) * 100.0
        add_message(
            "tag_impact",
            "info",
            _t(
                "La etiqueta #{tag} ha consumido el {pct:.1f}% de tus ingresos.",
                "The #{tag} tag has consumed {pct:.1f}% of your income.",
                params={"tag": top_tag_name, "pct": tag_income_pct},
            ),
            pct=tag_income_pct,
        )

    if current_summary["income"] <= 0:
        add_message(
            "zero_income",
            "warning",
            _t(
                "No hay ingresos registrados para el periodo; algunos ratios porcentuales no aplican.",
                "No income is recorded for the period; some percentage ratios do not apply.",
            ),
            always=True,
        )

    avg_daily_expense = total_expense / max(1, calendar.monthrange(year, month)[1])
    burn_days = safe_ratio(account_balance_total, avg_daily_expense)
    if burn_days is not None:
        add_message(
            "burn_rate",
            "info",
            _t(
                "Basado en tu gasto promedio diario, tu saldo actual cubre {days:.1f} días sin ingresos nuevos.",
                "Based on your average daily spending, your current balance covers {days:.1f} days without new income.",
                params={"days": burn_days},
            ),
        )

    monthly_savings_avg = avg_3["savings"] or current_summary["savings"]
    if completed_goals:
        latest_completed_goal = completed_goals[0]
        add_message(
            "goals_completed",
            "success",
            _t(
                "Ya cumpliste {count} meta(s) de ahorro. La mas reciente es '{goal_name}'.",
                "You already achieved {count} savings goal(s). The most recent one is '{goal_name}'.",
                params={"count": len(completed_goals), "goal_name": latest_completed_goal["name"]},
            ),
            always=True,
        )

    if active_goals:
        focus_goal = active_goals[0]
        focus_target_date = cast(date | None, focus_goal["parsed_target_date"])
        focus_currency = str(focus_goal["currency"] or "").strip()
        if focus_target_date is not None and focus_target_date < report_period_end:
            add_message(
                "goal_overdue",
                "warning",
                _t(
                    "La meta '{goal_name}' esta vencida y aun faltan {remaining:.2f} {currency}.",
                    "The '{goal_name}' goal is overdue and still needs {remaining:.2f} {currency}.",
                    params={
                        "goal_name": focus_goal["name"],
                        "remaining": float(focus_goal["remaining_amount"]),
                        "currency": focus_currency,
                    },
                ),
                always=True,
            )
        elif focus_target_date is not None:
            months_remaining = max(1, ((focus_target_date.year - year) * 12) + (focus_target_date.month - month) + 1)
            required_monthly_savings = float(focus_goal["remaining_amount"]) / months_remaining
            if monthly_savings_avg and monthly_savings_avg >= required_monthly_savings:
                add_message(
                    "goal_on_track",
                    "success",
                    _t(
                        "La meta '{goal_name}' va encaminada: llevas {progress:.1f}% y necesitas {required:.2f} {currency} por mes para llegar a {target_date}.",
                        "The '{goal_name}' goal is on track: you are at {progress:.1f}% and need {required:.2f} {currency} per month to reach {target_date}.",
                        params={
                            "goal_name": focus_goal["name"],
                            "progress": float(focus_goal["progress_pct"]),
                            "required": required_monthly_savings,
                            "currency": focus_currency,
                            "target_date": focus_goal["target_date"],
                        },
                    ),
                    always=True,
                )
            else:
                add_message(
                    "goal_off_track",
                    "warning",
                    _t(
                        "La meta '{goal_name}' requiere {required:.2f} {currency} por mes para llegar a {target_date}, pero tu ahorro reciente promedia {actual:.2f} {currency}.",
                        "The '{goal_name}' goal needs {required:.2f} {currency} per month to reach {target_date}, but your recent savings average is {actual:.2f} {currency}.",
                        params={
                            "goal_name": focus_goal["name"],
                            "required": required_monthly_savings,
                            "currency": focus_currency,
                            "target_date": focus_goal["target_date"],
                            "actual": float(monthly_savings_avg or 0.0),
                        },
                    ),
                    always=True,
                )
        else:
            add_message(
                "goal_progress",
                "info",
                _t(
                    "La meta '{goal_name}' va al {progress:.1f}% y faltan {remaining:.2f} {currency}.",
                    "The '{goal_name}' goal is {progress:.1f}% complete and still needs {remaining:.2f} {currency}.",
                    params={
                        "goal_name": focus_goal["name"],
                        "progress": float(focus_goal["progress_pct"]),
                        "remaining": float(focus_goal["remaining_amount"]),
                        "currency": focus_currency,
                    },
                ),
                always=True,
            )

    if monthly_savings_avg and monthly_savings_avg > 0:
        for goal in savings_goals[:1]:
            goal_name = str(goal.get("name") or default_goal_name)
            remaining = float(goal.get("remaining_amount") or 0.0)
            if remaining <= 0:
                continue
            months_to_goal = remaining / monthly_savings_avg
            eta_year, eta_month = shift_month(year, month, int(round(months_to_goal)))
            add_message(
                "goal_projection",
                "info",
                _t(
                    "A este ritmo de ahorro, completarás tu meta '{goal_name}' en {eta_year:04d}-{eta_month:02d}.",
                    "At this savings pace, you will complete your '{goal_name}' goal in {eta_year:04d}-{eta_month:02d}.",
                    params={"goal_name": goal_name, "eta_year": eta_year, "eta_month": eta_month},
                ),
            )
            break

    needs_keywords = {"alquiler", "renta", "comida", "supermercado", "salud", "medicina", "transporte", "servicios"}
    needs_total = sum(
        amount for root, amount in top_category_totals.items() if any(k in root.casefold() for k in needs_keywords)
    )
    wants_total = max(0.0, total_expense - needs_total)
    needs_pct = (needs_total / income_total * 100.0) if income_total > 0 else 0.0
    wants_pct = (wants_total / income_total * 100.0) if income_total > 0 else 0.0
    savings_pct = (current_summary["savings"] / income_total * 100.0) if income_total > 0 else 0.0
    deviation_pct = abs(needs_pct - 50.0) + abs(wants_pct - 30.0) + abs(savings_pct - 20.0)
    add_message(
        "mira_50_30_20",
        "info",
        _t(
            "Tu distribución es {needs:.1f}% Necesidades / {wants:.1f}% Deseos / {savings:.1f}% Ahorro. Desviación total {deviation:.1f}%.",
            "Your mix is {needs:.1f}% Needs / {wants:.1f}% Wants / {savings:.1f}% Savings. Total deviation {deviation:.1f}%.",
            params={
                "needs": needs_pct,
                "wants": wants_pct,
                "savings": savings_pct,
                "deviation": deviation_pct,
            },
        ),
    )

    freedom_margin_metrics = _build_freedom_margin_metrics(income_total, total_expense)
    freedom_margin_pct = cast(float | None, freedom_margin_metrics["pct"])
    if freedom_margin_pct is not None:
        freedom_zone = str(freedom_margin_metrics["zone"] or "")
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
        add_message(
            "freedom_margin",
            freedom_level,
            _t(
                "Tu Margen de Libertad es {pct:.1f}%. Zona: {zone}. {tone}",
                "Your Freedom Margin is {pct:.1f}%. Zone: {zone}. {tone}",
                params={
                    "pct": freedom_margin_pct,
                    "zone": freedom_zone_text_es if report_language == "es" else freedom_zone_text_en,
                    "tone": freedom_tone_es if report_language == "es" else freedom_tone_en,
                },
            ),
            always=True,
        )

    savings_rate = ((income_total - total_expense) / income_total * 100.0) if income_total > 0 else None
    if savings_rate is not None:
        tone = (
            _t("¡Vas por excelente camino!", "You are on an excellent path!")
            if savings_rate > 20
            else (
                _t("Estás tirando de ahorros o deuda.", "You are drawing on savings or debt.")
                if savings_rate < 0
                else _t("Continúa monitoreando tu ritmo.", "Keep monitoring your pace.")
            )
        )
        add_message(
            "savings_rate",
            "info",
            _t(
                "Tu tasa de ahorro real es {pct:.1f}%. {tone}",
                "Your real savings rate is {pct:.1f}%. {tone}",
                params={"pct": savings_rate, "tone": tone},
            ),
        )

    expense_income_ratio = safe_ratio(total_expense, income_total)
    if expense_income_ratio is not None:
        add_message(
            "expense_income_ratio",
            "info",
            _t(
                "Tu ratio gasto/ingreso es {ratio:.2f}.",
                "Your expense-to-income ratio is {ratio:.2f}.",
                params={"ratio": expense_income_ratio},
            ),
        )

    if top_categories and total_expense > 0:
        top_name, top_amount = top_categories[0]
        concentration_pct = (top_amount / total_expense) * 100.0
        add_message(
            "expense_concentration",
            "info",
            _t(
                "El {pct:.1f}% de tu gasto está en la categoría '{name}'.",
                "{pct:.1f}% of your spending is in the '{name}' category.",
                params={"pct": concentration_pct, "name": top_name},
            ),
        )
    else:
        concentration_pct = None

    if income_by_root and income_total > 0:
        root_name, root_amount = max(income_by_root.items(), key=lambda item: item[1])
        dependence_pct = (root_amount / income_total) * 100.0
        add_message(
            "income_dependence",
            "info",
            _t(
                "El {pct:.1f}% de tus ingresos proviene de '{name}'.",
                "{pct:.1f}% of your income comes from '{name}'.",
                params={"pct": dependence_pct, "name": root_name},
            ),
        )
    else:
        dependence_pct = None

    filtered_messages = [
        msg for msg in messages if msg["always"] or msg.get("pct") is None or float(msg["pct"]) >= threshold_pct
    ]
    filtered_messages.sort(key=lambda msg: (_message_level_priority(str(msg["level"])), str(msg["code"])))

    days_in_month = max(1, calendar.monthrange(year, month)[1])
    daily_living_cost = total_expense / days_in_month
    goal_completion_index_pct = _build_goal_completion_index(goal_rows, active_goals)
    previous_year, previous_month = shift_month(year, month, -1)
    previous_days_in_month = max(1, calendar.monthrange(previous_year, previous_month)[1])

    income_series = [float(summary["income"]) for summary in historical_6_summaries]
    expense_series = [float(summary["expense_operational"]) for summary in historical_6_summaries]
    net_series = [float(summary["net"]) for summary in historical_6_summaries]

    income_trend_metric = _build_trend_metric(current_summary["income"], previous_summary["income"])
    expense_trend_metric = _build_trend_metric(
        current_summary["expense_operational"], previous_summary["expense_operational"]
    )
    gap_trend_metric = _build_trend_metric(current_summary["net"], previous_summary["net"])
    financial_balance_metric = _build_financial_balance_metric(income_total, total_expense)
    cashflow_stability_metric = _build_cashflow_stability_metric(net_series, income_series)
    spending_efficiency_metric = _build_spending_efficiency_metric(income_total, total_expense)
    expense_drift_metric = _build_expense_drift_metric(expense_series)
    cashflow_projection_metric = _build_cashflow_projection_metric(income_series, expense_series)
    deficit_risk_metric = _build_deficit_risk_metric(
        current_net=current_summary["net"],
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
    week_spread_metric = _build_week_spread_metric(total_expense, daily_expense_totals)
    spending_pattern_metric = _build_spending_pattern_metric(
        total_expense=total_expense,
        daily_expense_totals=daily_expense_totals,
        expense_trend=expense_trend_metric,
    )
    runway_trend_metric = _build_runway_trend_metric(
        account_balance_total=account_balance_total,
        current_expense_total=total_expense,
        previous_expense_total=previous_summary["expense_operational"],
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

    history_hints = []
    if len(trailing_3) < 3 or len([item for _y, _m, item in comparison_trailing_6 if item]) < 6:
        history_hints.append(
            _t(
                "Se requiere un mayor período de transacciones para completar comparativas de 3 y 6 meses.",
                "A longer transaction history is required to complete 3-month and 6-month comparisons.",
            )
        )

    top_total = round(sum(amount for _name, amount in top_categories), 2)
    net_after_expenses = round(current_summary["net"], 2)
    waterfall_steps: list[dict[str, Any]] = [
        {
            "label": _t("Ingreso total neto", "Total net income"),
            "kind": "income_total",
            "value": round(current_summary["income"], 2),
            "start": 0.0,
            "end": round(current_summary["income"], 2),
            "baseline": 0.0,
        }
    ]

    running_balance = round(current_summary["income"], 2)
    for category_name, amount in displayed_waterfall_categories:
        next_balance = round(running_balance - amount, 2)
        is_grouped = category_name == other_expenses_label and bool(remaining_waterfall_categories)
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
                "label": _t("Deuda / uso de ahorro", "Debt / prior savings"),
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
                    _t("Balance del mes", "Month balance")
                    if waterfall_status == "surplus"
                    else _t("Cierre del flujo mensual", "Monthly flow close")
                ),
                "kind": "month_balance" if waterfall_status == "surplus" else "final_total",
                "value": final_balance,
                "start": final_balance,
                "end": final_balance,
                "baseline": 0.0,
            }
        )

    return {
        "period": {"year": year, "month": month},
        "kpis": current_summary,
        "comparisons": comparisons,
        "budget": budget_context,
        "history_hints": history_hints,
        "consistency": {
            "operational_expense_total": total_expense,
            "top5_total": top_total,
            "top5_le_total": top_total <= total_expense + 1e-9,
        },
        "ytd": ytd,
        "allocation": {
            "top_expense_categories": [
                {
                    "name": name,
                    "amount": round(amount, 2),
                    "children": [
                        {"name": child, "amount": round(child_amount, 2)}
                        for child, child_amount in sorted(children.items(), key=lambda item: item[1], reverse=True)
                    ],
                }
                for name, amount in top_categories
                for children in [top_category_children[name]]
            ],
            "top_tags": [
                {
                    "name": name,
                    "amount": round(amount, 2),
                    "children": [
                        {"name": child, "amount": round(child_amount, 2)}
                        for child, child_amount in sorted(children.items(), key=lambda item: item[1], reverse=True)
                    ],
                }
                for name, amount in top_tags
                for children in [tag_children[name]]
            ],
        },
        "waterfall": {
            "steps": waterfall_steps,
            "summary": {
                "status": waterfall_status,
                "net_after_expenses": net_after_expenses,
                "financing_amount": financing_amount,
                "savings_allocation": savings_allocation,
                "final_balance": final_balance,
                "expense_categories_count": len(waterfall_category_totals),
                "displayed_expense_categories_count": min(
                    len(normal_waterfall_categories), _MAX_WATERFALL_EXPENSE_STEPS
                ),
                "displayed_expense_steps_count": len(displayed_waterfall_categories),
                "grouped_other_expenses_count": len(remaining_waterfall_categories),
                "has_grouped_other_expenses": bool(remaining_waterfall_categories),
                "inconsistent_bucket_present": inconsistent_waterfall_entry is not None,
            },
        },
        "historical_stacked": stacked_6,
        "advisor": {"threshold": relevance_threshold, "messages": filtered_messages},
        "goals_summary": goals_summary,
        "metrics": {
            "burn_rate_days": round(burn_days, 2) if burn_days is not None else None,
            "daily_living_cost": round(daily_living_cost, 2),
            "goal_completion_index_pct": goal_completion_index_pct,
            "savings_rate_pct": round(savings_rate, 2) if savings_rate is not None else None,
            "debt_payment_income_pct": (
                round(debt_payment_income_pct, 2) if debt_payment_income_pct is not None else None
            ),
            "debt_payment_expense_pct": (
                round(debt_payment_expense_pct, 2) if debt_payment_expense_pct is not None else None
            ),
            "credit_card_expense_count": credit_card_expense_count,
            "credit_card_expense_amount": round(credit_card_expense_amount, 2),
            "credit_card_payment_count": credit_card_payment_count,
            "credit_card_payment_amount": round(credit_card_payment_amount, 2),
            "credit_card_gap_amount": credit_card_gap_amount,
            "expense_income_ratio": round(expense_income_ratio, 2) if expense_income_ratio is not None else None,
            "expense_concentration_pct": round(concentration_pct, 2) if concentration_pct is not None else None,
            "income_dependence_pct": round(dependence_pct, 2) if dependence_pct is not None else None,
            "freedom_margin": freedom_margin_metrics,
            "lifestyle_inflation": lifestyle_inflation_metrics,
            "savings_efficiency": savings_efficiency_metrics,
            "goal_contributions": goal_contribution_metrics,
            "generic_analysis": generic_analysis,
            "mira_50_30_20": {
                "needs_pct": round(needs_pct, 2),
                "wants_pct": round(wants_pct, 2),
                "savings_pct": round(savings_pct, 2),
                "deviation_pct": round(deviation_pct, 2),
            },
        },
    }
