# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Application services and presentation builders for the MIRA analysis view."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from mira.app.view_services._common import PresentationContext
from mira.db.database import Database
from mira.ui.i18n import tr

_MULTICOLOR_PALETTE: tuple[str, ...] = (
    "#2EC4B6",
    "#4D96FF",
    "#FF6B6B",
    "#F4A261",
    "#8AC926",
    "#00B8D9",
    "#FF9F1C",
    "#FF4D8D",
)

_SEMANTIC_COLORS = {
    "income": "#2EC4B6",
    "expense": "#FF6B6B",
    "net": "#4D96FF",
    "secondary": "#00B8D9",
    "budget": "#4D96FF",
    "actual": "#FF6B6B",
    "financing": "#F4A261",
    "savings": "#8AC926",
    "flow_total": "#00B8D9",
}

_WATERFALL_COLORS = {
    "income_total": "#2EC4B6",
    "expense": "#FF6B6B",
    "financing": "#F4A261",
    "savings_allocation": "#8AC926",
    "deficit_total": "#FF9F1C",
    "surplus_total": "#4D96FF",
    "month_balance": "#4D96FF",
    "final_total": "#00B8D9",
}


@dataclass(frozen=True)
class MiraAnalysisComparisonBadge:
    text: str
    color: str


@dataclass(frozen=True)
class MiraAnalysisCardState:
    value: str
    color: str
    primary_text: str
    primary_color: str
    secondary_text: str
    secondary_color: str


@dataclass(frozen=True)
class MiraAnalysisAmountRow:
    name: str
    amount_text: str


@dataclass(frozen=True)
class MiraAnalysisDrilldownRow:
    name: str
    amount_text: str
    detail_title: str
    detail_rows: tuple[MiraAnalysisAmountRow, ...]


@dataclass(frozen=True)
class MiraAnalysisDrilldownSection:
    top_rows: tuple[MiraAnalysisDrilldownRow, ...]
    empty_title: str


@dataclass(frozen=True)
class MiraAnalysisWaterfallStep:
    label: str
    kind: str
    value: float
    start: float
    end: float
    baseline: float | None = None
    is_grouped: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "kind": self.kind,
            "value": self.value,
            "start": self.start,
            "end": self.end,
            "baseline": self.baseline,
            "is_grouped": self.is_grouped,
        }


@dataclass(frozen=True)
class MiraAnalysisWaterfallState:
    steps: tuple[MiraAnalysisWaterfallStep, ...]
    legend_html: str
    summary_text: str


@dataclass(frozen=True)
class MiraAnalysisLineSeries:
    name: str
    color: str
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class MiraAnalysisBarSeries:
    name: str
    color: str
    values: tuple[float, ...]


@dataclass(frozen=True)
class MiraAnalysisLineChartState:
    title: str
    labels: tuple[str, ...]
    series: tuple[MiraAnalysisLineSeries, ...]


@dataclass(frozen=True)
class MiraAnalysisStackedBarChartState:
    title: str
    labels: tuple[str, ...]
    series: tuple[MiraAnalysisBarSeries, ...]


@dataclass(frozen=True)
class MiraAnalysisViewState:
    income_card: MiraAnalysisCardState
    expense_card: MiraAnalysisCardState
    balance_card: MiraAnalysisCardState
    savings_card: MiraAnalysisCardState
    categories: MiraAnalysisDrilldownSection
    tags: MiraAnalysisDrilldownSection
    waterfall: MiraAnalysisWaterfallState
    ytd_chart: MiraAnalysisLineChartState
    trend_charts: dict[str, MiraAnalysisStackedBarChartState]


def _comparison_badge(
    context: PresentationContext,
    *,
    section: str,
    comparison: dict[str, Any] | None,
    label: str,
    missing_text: str,
) -> MiraAnalysisComparisonBadge:
    if not comparison or comparison.get("base") is None or comparison.get("pct") is None:
        return MiraAnalysisComparisonBadge(missing_text, "#9FB3C8")

    variance = float(comparison.get("variance") or 0.0)
    pct = abs(float(comparison.get("pct") or 0.0))
    if abs(variance) < 0.005:
        return MiraAnalysisComparisonBadge(f"→ 0.0% vs {label}", "#D6DEE8")

    arrow = "↑" if variance > 0 else "↓"
    trend = (
        context.translate("mira.analysis.less_more.more", "más")
        if variance > 0
        else context.translate("mira.analysis.less_more.less", "menos")
    )
    good = variance > 0 if section in {"income", "savings", "net"} else variance < 0
    return MiraAnalysisComparisonBadge(
        text=f"{arrow} {pct:.1f}% {trend} vs {label}",
        color="#4EC9B0" if good else "#F48771",
    )


class MiraAnalysisService:
    """Load the MIRA master report payload outside the QWidget."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def load_payload(self, *, year: int, month: int) -> dict[str, Any]:
        return cast(dict[str, Any], self._db.report.get_mira_master_report(year=year, month=month))


class MiraAnalysisViewStateBuilder:
    """Build UI-facing state for the MIRA analysis workspace."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def build_state(self, payload: dict[str, Any]) -> MiraAnalysisViewState:
        context = PresentationContext.from_db(self._db)
        comparisons = cast(dict[str, Any], payload.get("comparisons") or {})
        allocation = cast(dict[str, Any], payload.get("allocation") or {})
        return MiraAnalysisViewState(
            income_card=self._build_income_card(payload, comparisons, context),
            expense_card=self._build_expense_card(payload, comparisons, context),
            balance_card=self._build_balance_card(payload, comparisons, context),
            savings_card=self._build_savings_card(payload, comparisons, context),
            categories=self._build_category_section(allocation, context),
            tags=self._build_tag_section(allocation, context),
            waterfall=self._build_waterfall_state(payload, context),
            ytd_chart=self._build_ytd_chart(payload, context),
            trend_charts=self._build_trend_charts(payload, context),
        )

    def _build_income_card(
        self,
        payload: dict[str, Any],
        comparisons: dict[str, Any],
        context: PresentationContext,
    ) -> MiraAnalysisCardState:
        kpis = cast(dict[str, Any], payload.get("kpis") or {})
        income_cmp = cast(dict[str, Any], comparisons.get("income") or {})
        primary = _comparison_badge(
            context,
            section="income",
            comparison=cast(dict[str, Any] | None, income_cmp.get("vs_previous")),
            label=context.translate("mira.analysis.label.previous", "mes anterior"),
            missing_text=context.translate("mira.analysis.label.no_previous", "sin historial mensual"),
        )
        secondary = _comparison_badge(
            context,
            section="income",
            comparison=cast(dict[str, Any] | None, income_cmp.get("vs_budget")),
            label=context.translate("mira.analysis.label.budget", "presupuesto"),
            missing_text=context.translate("mira.analysis.label.no_budget_period", "sin presupuesto del periodo"),
        )
        return MiraAnalysisCardState(
            value=context.format_amount(float(kpis.get("income") or 0.0)),
            color="#4EC9B0",
            primary_text=primary.text,
            primary_color=primary.color,
            secondary_text=secondary.text,
            secondary_color=secondary.color,
        )

    def _build_expense_card(
        self,
        payload: dict[str, Any],
        comparisons: dict[str, Any],
        context: PresentationContext,
    ) -> MiraAnalysisCardState:
        kpis = cast(dict[str, Any], payload.get("kpis") or {})
        expense_cmp = cast(dict[str, Any], comparisons.get("expense_operational") or {})
        primary = _comparison_badge(
            context,
            section="expense",
            comparison=cast(dict[str, Any] | None, expense_cmp.get("vs_previous")),
            label=context.translate("mira.analysis.label.previous", "mes anterior"),
            missing_text=context.translate("mira.analysis.label.no_previous", "sin historial mensual"),
        )
        secondary = _comparison_badge(
            context,
            section="expense",
            comparison=cast(dict[str, Any] | None, expense_cmp.get("vs_budget")),
            label=context.translate("mira.analysis.label.budget", "presupuesto"),
            missing_text=context.translate("mira.analysis.label.no_budget_period", "sin presupuesto del periodo"),
        )
        return MiraAnalysisCardState(
            value=context.format_amount(float(kpis.get("expense_operational") or 0.0)),
            color="#F48771",
            primary_text=primary.text,
            primary_color=primary.color,
            secondary_text=secondary.text,
            secondary_color=secondary.color,
        )

    def _build_balance_card(
        self,
        payload: dict[str, Any],
        comparisons: dict[str, Any],
        context: PresentationContext,
    ) -> MiraAnalysisCardState:
        kpis = cast(dict[str, Any], payload.get("kpis") or {})
        net = float(kpis.get("net") or 0.0)
        net_cmp = cast(dict[str, Any], comparisons.get("net") or {})
        primary = _comparison_badge(
            context,
            section="net",
            comparison=cast(dict[str, Any] | None, net_cmp.get("vs_previous")),
            label=context.translate("mira.analysis.label.previous", "mes anterior"),
            missing_text=context.translate("mira.analysis.label.no_previous", "sin historial mensual"),
        )
        secondary = _comparison_badge(
            context,
            section="net",
            comparison=cast(dict[str, Any] | None, net_cmp.get("vs_avg_3")),
            label=context.translate("mira.analysis.label.avg3", "prom. 3m"),
            missing_text=context.translate("mira.analysis.label.no_avg3", "sin promedio 3m"),
        )
        if abs(net) < 0.005:
            color = "#D6DEE8"
        else:
            color = "#4EC9B0" if net > 0 else "#F48771"
        return MiraAnalysisCardState(
            value=context.format_amount(net),
            color=color,
            primary_text=primary.text,
            primary_color=primary.color,
            secondary_text=secondary.text,
            secondary_color=secondary.color,
        )

    def _build_savings_card(
        self,
        payload: dict[str, Any],
        comparisons: dict[str, Any],
        context: PresentationContext,
    ) -> MiraAnalysisCardState:
        kpis = cast(dict[str, Any], payload.get("kpis") or {})
        savings_cmp = cast(dict[str, Any], comparisons.get("savings") or {})
        primary = _comparison_badge(
            context,
            section="savings",
            comparison=cast(dict[str, Any] | None, savings_cmp.get("vs_previous")),
            label=context.translate("mira.analysis.label.previous", "mes anterior"),
            missing_text=context.translate("mira.analysis.label.no_previous", "sin historial mensual"),
        )
        secondary = _comparison_badge(
            context,
            section="savings",
            comparison=cast(dict[str, Any] | None, savings_cmp.get("vs_avg_3")),
            label=context.translate("mira.analysis.label.avg3", "prom. 3m"),
            missing_text=context.translate("mira.analysis.label.no_avg3", "sin promedio 3m"),
        )
        return MiraAnalysisCardState(
            value=context.format_amount(float(kpis.get("savings") or 0.0)),
            color="#86A9FF",
            primary_text=primary.text,
            primary_color=primary.color,
            secondary_text=secondary.text,
            secondary_color=secondary.color,
        )

    def _build_category_section(
        self,
        allocation: dict[str, Any],
        context: PresentationContext,
    ) -> MiraAnalysisDrilldownSection:
        empty_title = context.translate(
            "mira.analysis.category_detail.empty",
            "Selecciona una categoría para ver el desglose.",
        )
        rows = []
        for row in list(allocation.get("top_expense_categories") or []):
            name = str(row.get("name") or "")
            children = tuple(
                MiraAnalysisAmountRow(
                    name=str(child.get("name") or ""),
                    amount_text=context.format_amount(float(child.get("amount") or 0.0)),
                )
                for child in list(row.get("children") or [])
            )
            detail_title = (
                context.translate(
                    "mira.analysis.category_detail.selected",
                    "Desglose de {name}",
                    params={"name": name},
                )
                if children
                else context.translate(
                    "mira.analysis.category_detail.none",
                    "La categoría {name} no tiene desglose adicional.",
                    params={"name": name},
                )
            )
            rows.append(
                MiraAnalysisDrilldownRow(
                    name=name,
                    amount_text=context.format_amount(float(row.get("amount") or 0.0)),
                    detail_title=detail_title,
                    detail_rows=children,
                )
            )
        return MiraAnalysisDrilldownSection(top_rows=tuple(rows), empty_title=empty_title)

    def _build_tag_section(
        self,
        allocation: dict[str, Any],
        context: PresentationContext,
    ) -> MiraAnalysisDrilldownSection:
        empty_title = context.translate(
            "mira.analysis.tag_detail.empty",
            "Selecciona una etiqueta para ver su composición.",
        )
        rows = []
        for row in list(allocation.get("top_tags") or []):
            name = str(row.get("name") or "")
            children = tuple(
                MiraAnalysisAmountRow(
                    name=str(child.get("name") or ""),
                    amount_text=context.format_amount(float(child.get("amount") or 0.0)),
                )
                for child in list(row.get("children") or [])
            )
            detail_title = (
                context.translate(
                    "mira.analysis.tag_detail.selected",
                    "Composición de #{name}",
                    params={"name": name},
                )
                if children
                else context.translate(
                    "mira.analysis.tag_detail.none",
                    "La etiqueta #{name} no tiene desglose adicional.",
                    params={"name": name},
                )
            )
            rows.append(
                MiraAnalysisDrilldownRow(
                    name=name,
                    amount_text=context.format_amount(float(row.get("amount") or 0.0)),
                    detail_title=detail_title,
                    detail_rows=children,
                )
            )
        return MiraAnalysisDrilldownSection(top_rows=tuple(rows), empty_title=empty_title)

    def _build_waterfall_state(
        self,
        payload: dict[str, Any],
        context: PresentationContext,
    ) -> MiraAnalysisWaterfallState:
        waterfall = cast(dict[str, Any], payload.get("waterfall") or {})
        summary = cast(dict[str, Any], waterfall.get("summary") or {})
        steps: list[MiraAnalysisWaterfallStep] = []
        present_kinds: set[str] = set()
        for raw_step in list(waterfall.get("steps") or []):
            kind = str(raw_step.get("kind") or "")
            present_kinds.add(kind)
            steps.append(
                MiraAnalysisWaterfallStep(
                    label=self._waterfall_label(raw_step, context),
                    kind=kind,
                    value=float(raw_step.get("value") or 0.0),
                    start=float(raw_step.get("start") or 0.0),
                    end=float(raw_step.get("end") or 0.0),
                    baseline=(None if raw_step.get("baseline") is None else float(raw_step.get("baseline") or 0.0)),
                    is_grouped=bool(raw_step.get("is_grouped")),
                )
            )

        legend_entries: list[str] = []
        if "income_total" in present_kinds:
            legend_entries.append(
                f"<span style='color:{_WATERFALL_COLORS['income_total']};'>●</span> "
                f"{context.translate('dashboard.card.income', 'Ingreso')}"
            )
        if "expense" in present_kinds:
            legend_entries.append(
                f"<span style='color:{_WATERFALL_COLORS['expense']};'>●</span> "
                f"{context.translate('dashboard.card.expense', 'Gasto')}"
            )
        if "financing" in present_kinds:
            legend_entries.append(
                f"<span style='color:{_WATERFALL_COLORS['financing']};'>●</span> "
                f"{context.translate('mira.analysis.waterfall.legend.financing', 'Financiamiento')}"
            )
        if "savings_allocation" in present_kinds:
            legend_entries.append(
                f"<span style='color:{_WATERFALL_COLORS['savings_allocation']};'>●</span> "
                f"{context.translate('dashboard.card.savings', 'Ahorro')}"
            )
        if "month_balance" in present_kinds:
            legend_entries.append(
                f"<span style='color:{_WATERFALL_COLORS['month_balance']};'>●</span> "
                f"{context.translate('dashboard.card.net', 'Balance')}"
            )
        elif present_kinds.intersection({"deficit_total", "surplus_total", "final_total"}):
            legend_entries.append(
                f"<span style='color:{_WATERFALL_COLORS['final_total']};'>●</span> "
                f"{context.translate('mira.analysis.waterfall.legend.flow_total', 'Totales del flujo')}"
            )

        status = str(summary.get("status") or "balanced")
        net_after_expenses = float(summary.get("net_after_expenses") or 0.0)
        financing_amount = float(summary.get("financing_amount") or 0.0)
        final_balance = float(summary.get("final_balance") or 0.0)
        if status == "deficit":
            summary_text = context.translate(
                "mira.analysis.waterfall.deficit",
                "El mes cerró con déficit operativo de {net}. El gráfico muestra cómo {financing} de deuda o ahorro previo cubrieron el faltante para llevar el flujo neto a cero.",
                params={
                    "net": context.format_amount(abs(net_after_expenses)),
                    "financing": context.format_amount(financing_amount),
                },
            )
        elif status == "surplus":
            summary_text = context.translate(
                "mira.analysis.waterfall.surplus",
                "El mes cerró con superávit operativo de {net}. El gráfico termina mostrando un balance del mes de {balance}, sin normalizar el cierre a cero.",
                params={
                    "net": context.format_amount(net_after_expenses),
                    "balance": context.format_amount(final_balance),
                },
            )
        else:
            summary_text = context.translate(
                "mira.analysis.waterfall.balanced",
                "El mes quedó balanceado: ingresos y gastos operativos se compensaron sin necesitar financiamiento adicional ni excedente para ahorrar.",
            )

        return MiraAnalysisWaterfallState(
            steps=tuple(steps),
            legend_html=" · ".join(legend_entries),
            summary_text=summary_text,
        )

    def _waterfall_label(self, step: dict[str, Any], context: PresentationContext) -> str:
        kind = str(step.get("kind") or "")
        if kind == "income_total":
            return context.translate("mira.analysis.waterfall.label.income_total", "Ingreso total neto")
        if kind == "deficit_total":
            return context.translate("mira.analysis.waterfall.label.deficit", "Déficit mensual")
        if kind == "surplus_total":
            return context.translate("mira.analysis.waterfall.label.surplus", "Superávit mensual")
        if kind == "month_balance":
            return context.translate("mira.analysis.waterfall.label.month_balance", "Balance del mes")
        if kind == "financing":
            return context.translate("mira.analysis.waterfall.label.financing", "Deuda / uso de ahorro")
        if kind == "savings_allocation":
            return context.translate("mira.analysis.waterfall.label.savings_allocation", "Ahorro asignado")
        if kind == "final_total":
            return context.translate("mira.analysis.waterfall.label.final_flow", "Cierre del flujo mensual")
        if kind == "expense" and bool(step.get("is_grouped")):
            return context.translate("mira.analysis.waterfall.label.other_expenses", "Otros gastos")
        if kind == "expense" and str(step.get("label") or "") == "Gastos con categoría inconsistente":
            return context.translate(
                "mira.analysis.waterfall.label.inconsistent_expense",
                "Gastos con categoría inconsistente",
            )
        return str(step.get("label") or "")

    def _build_ytd_chart(
        self,
        payload: dict[str, Any],
        context: PresentationContext,
    ) -> MiraAnalysisLineChartState:
        ytd = list(payload.get("ytd") or [])
        labels = tuple(f"{int(item['month']):02d}/{int(item['year'])}" for item in ytd)
        return MiraAnalysisLineChartState(
            title=context.translate("mira.analysis.ytd.short", "YTD"),
            labels=labels,
            series=(
                MiraAnalysisLineSeries(
                    name=context.translate("dashboard.card.income", "Ingreso"),
                    color=_SEMANTIC_COLORS["income"],
                    points=tuple((float(idx), float(item.get("income") or 0.0)) for idx, item in enumerate(ytd)),
                ),
                MiraAnalysisLineSeries(
                    name=context.translate("dashboard.card.expense", "Gasto"),
                    color=_SEMANTIC_COLORS["expense"],
                    points=tuple(
                        (float(idx), float(item.get("expense_operational") or 0.0)) for idx, item in enumerate(ytd)
                    ),
                ),
                MiraAnalysisLineSeries(
                    name=context.translate("dashboard.card.net", "Balance"),
                    color=_SEMANTIC_COLORS["net"],
                    points=tuple((float(idx), float(item.get("net") or 0.0)) for idx, item in enumerate(ytd)),
                ),
                MiraAnalysisLineSeries(
                    name=context.translate("dashboard.card.savings", "Ahorro"),
                    color=_SEMANTIC_COLORS["savings"],
                    points=tuple((float(idx), float(item.get("savings") or 0.0)) for idx, item in enumerate(ytd)),
                ),
            ),
        )

    def _build_trend_charts(
        self,
        payload: dict[str, Any],
        context: PresentationContext,
    ) -> dict[str, MiraAnalysisStackedBarChartState]:
        charts: dict[str, MiraAnalysisStackedBarChartState] = {}
        stacked = cast(dict[str, Any], payload.get("historical_stacked") or {})
        for section, rows_obj in stacked.items():
            rows = list(rows_obj or [])
            labels = tuple(str(item.get("period") or "") for item in rows)
            segment_names: list[str] = []
            for row in rows:
                for seg_name in (row.get("segments") or {}).keys():
                    if seg_name not in segment_names:
                        segment_names.append(seg_name)

            series = []
            for idx, seg_name in enumerate(segment_names):
                series.append(
                    MiraAnalysisBarSeries(
                        name=seg_name,
                        color=_MULTICOLOR_PALETTE[idx % len(_MULTICOLOR_PALETTE)],
                        values=tuple(float((row.get("segments") or {}).get(seg_name) or 0.0) for row in rows),
                    )
                )
            charts[str(section)] = MiraAnalysisStackedBarChartState(
                title=context.translate("mira.analysis.trend.short", "Tendencia"),
                labels=labels,
                series=tuple(series),
            )
        charts.setdefault(
            "income",
            MiraAnalysisStackedBarChartState(
                title=context.translate("mira.analysis.trend.short", "Tendencia"),
                labels=(),
                series=(),
            ),
        )
        charts.setdefault(
            "expense",
            MiraAnalysisStackedBarChartState(
                title=context.translate("mira.analysis.trend.short", "Tendencia"),
                labels=(),
                series=(),
            ),
        )
        return charts


class MiraAnalysisMessageBuilder:
    """Build assistant-facing narrative strings from a MIRA payload."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def _t(self, language: str, key: str, default: str, *, params: dict[str, object] | None = None) -> str:
        return tr(key, language, default=default, params=params)

    def _context(self, language: str) -> PresentationContext:
        base = PresentationContext.from_db(self._db)
        return PresentationContext(
            language=language,
            number_format=base.number_format,
            default_currency=base.default_currency,
            account_type_labels={
                "bank": tr("accounts.type.bank", language, default="bank"),
                "cash": tr("accounts.type.cash", language, default="cash"),
                "credit": tr("accounts.type.credit", language, default="credit"),
            },
        )

    def _build_efficiency_context_lines(
        self,
        context: PresentationContext,
        *,
        comparisons: dict[str, Any],
        budget: dict[str, Any],
        metrics: dict[str, Any],
    ) -> list[str]:
        income_cmp = cast(dict[str, Any], comparisons.get("income") or {})
        expense_cmp = cast(dict[str, Any], comparisons.get("expense_operational") or {})

        income_prev = _comparison_badge(
            context,
            section="income",
            comparison=cast(dict[str, Any] | None, income_cmp.get("vs_previous")),
            label=context.translate("mira.analysis.label.previous", "previous month"),
            missing_text=context.translate("mira.analysis.label.no_previous", "no monthly history"),
        ).text
        income_3m = _comparison_badge(
            context,
            section="income",
            comparison=cast(dict[str, Any] | None, income_cmp.get("vs_avg_3")),
            label=context.translate("mira.analysis.label.avg3", "avg. 3m"),
            missing_text=context.translate("mira.analysis.label.no_avg3", "no 3m average"),
        ).text
        income_6m = _comparison_badge(
            context,
            section="income",
            comparison=cast(dict[str, Any] | None, income_cmp.get("vs_avg_6")),
            label=context.translate("mira.analysis.label.avg6", "avg. 6m"),
            missing_text=context.translate("mira.analysis.label.no_avg6", "no 6m average"),
        ).text
        expense_prev = _comparison_badge(
            context,
            section="expense",
            comparison=cast(dict[str, Any] | None, expense_cmp.get("vs_previous")),
            label=context.translate("mira.analysis.label.previous", "previous month"),
            missing_text=context.translate("mira.analysis.label.no_previous", "no monthly history"),
        ).text
        expense_3m = _comparison_badge(
            context,
            section="expense",
            comparison=cast(dict[str, Any] | None, expense_cmp.get("vs_avg_3")),
            label=context.translate("mira.analysis.label.avg3", "avg. 3m"),
            missing_text=context.translate("mira.analysis.label.no_avg3", "no 3m average"),
        ).text
        expense_6m = _comparison_badge(
            context,
            section="expense",
            comparison=cast(dict[str, Any] | None, expense_cmp.get("vs_avg_6")),
            label=context.translate("mira.analysis.label.avg6", "avg. 6m"),
            missing_text=context.translate("mira.analysis.label.no_avg6", "no 6m average"),
        ).text

        ratio = metrics.get("expense_income_ratio")
        daily_living_cost = metrics.get("daily_living_cost")
        mix = cast(dict[str, Any], metrics.get("mira_50_30_20") or {})
        lines = [context.translate("mira.analysis.context.efficiency", "Efficiency report")]
        lines.append(
            context.translate(
                "mira.analysis.context.efficiency.summary",
                "- Executive summary: How many of every 100 I earn disappear?",
            )
        )
        if ratio is not None:
            lines.append(
                context.translate(
                    "mira.analysis.context.efficiency.ratio",
                    "- Expense-to-income ratio: {ratio:.2f}.",
                    params={"ratio": float(ratio)},
                )
            )
        if mix:
            lines.append(
                context.translate(
                    "mira.analysis.context.efficiency.mix",
                    "- 50/30/20 mix: {needs:.1f}% needs / {wants:.1f}% wants / {savings:.1f}% savings.",
                    params={
                        "needs": float(mix.get("needs_pct") or 0.0),
                        "wants": float(mix.get("wants_pct") or 0.0),
                        "savings": float(mix.get("savings_pct") or 0.0),
                    },
                )
            )
        if daily_living_cost is not None:
            lines.append(
                context.translate(
                    "mira.analysis.context.efficiency.daily_cost",
                    "- Daily living cost: {amount}.",
                    params={"amount": context.format_amount(float(daily_living_cost))},
                )
            )
        lines.append(
            context.translate(
                "mira.analysis.context.income",
                "- Income: {previous}; {avg3}; {avg6}.",
                params={"previous": income_prev, "avg3": income_3m, "avg6": income_6m},
            )
        )
        lines.append(
            context.translate(
                "mira.analysis.context.expense",
                "- Operating expenses: {previous}; {avg3}; {avg6}.",
                params={"previous": expense_prev, "avg3": expense_3m, "avg6": expense_6m},
            )
        )
        if budget.get("has_budget"):
            code = str(budget.get("budget_code") or "")
            income_budget = _comparison_badge(
                context,
                section="income",
                comparison=cast(dict[str, Any] | None, income_cmp.get("vs_budget")),
                label=context.translate("mira.analysis.label.budget", "budget"),
                missing_text=context.translate("mira.analysis.label.no_budget", "no budget comparison"),
            ).text
            expense_budget = _comparison_badge(
                context,
                section="expense",
                comparison=cast(dict[str, Any] | None, expense_cmp.get("vs_budget")),
                label=context.translate("mira.analysis.label.budget", "budget"),
                missing_text=context.translate("mira.analysis.label.no_budget", "no budget comparison"),
            ).text
            lines.append(
                context.translate(
                    "mira.analysis.context.budget_code",
                    "- Applied budget: {code}.",
                    params={"code": code or "N/A"},
                )
            )
            lines.append(
                context.translate(
                    "mira.analysis.context.income_budget",
                    "- Income vs budget: {value}.",
                    params={"value": income_budget},
                )
            )
            lines.append(
                context.translate(
                    "mira.analysis.context.expense_budget",
                    "- Expense vs budget: {value}.",
                    params={"value": expense_budget},
                )
            )
            missing_income = [str(item) for item in list(budget.get("missing_income_categories") or []) if str(item)]
            if missing_income:
                lines.append(
                    context.translate(
                        "mira.analysis.context.missing_income",
                        "- Budgeted income not received: {items}.",
                        params={"items": ", ".join(missing_income)},
                    )
                )
            missing_expense = [str(item) for item in list(budget.get("missing_expense_categories") or []) if str(item)]
            if missing_expense:
                lines.append(
                    context.translate(
                        "mira.analysis.context.missing_expense",
                        "- Budgeted expenses not paid: {items}.",
                        params={"items": ", ".join(missing_expense)},
                    )
                )
        else:
            lines.append(
                context.translate(
                    "mira.analysis.context.no_budget",
                    "- There is no valid budget for this period.",
                )
            )
        return lines

    def _build_security_context_lines(
        self,
        context: PresentationContext,
        *,
        payload: dict[str, Any],
        metrics: dict[str, Any],
        history_hints: list[str],
    ) -> list[str]:
        kpis = cast(dict[str, Any], payload.get("kpis") or {})
        burn_days = metrics.get("burn_rate_days")
        net_amount = float(kpis.get("net") or 0.0)
        month_status = (
            context.translate("mira.analysis.context.security.deficit", "deficit")
            if net_amount < 0
            else (
                context.translate("mira.analysis.context.security.surplus", "surplus")
                if net_amount > 0
                else context.translate("mira.analysis.context.security.balanced", "balanced")
            )
        )
        lines = [context.translate("mira.analysis.context.security", "Security report")]
        lines.append(
            context.translate(
                "mira.analysis.context.security.summary",
                "- Executive summary: If I stop working today, how many days can I sustain my lifestyle?",
            )
        )
        if burn_days is not None:
            lines.append(
                context.translate(
                    "mira.analysis.context.security.autonomy",
                    "- Days of autonomy: {days:.1f}.",
                    params={"days": float(burn_days)},
                )
            )
        lines.append(
            context.translate(
                "mira.analysis.context.security.status",
                "- Month status: {status}. Net balance {amount}.",
                params={"status": month_status, "amount": context.format_amount(net_amount)},
            )
        )
        for hint in history_hints:
            lines.append(f"- {hint}")
        return lines

    def _build_purpose_context_lines(
        self,
        context: PresentationContext,
        *,
        metrics: dict[str, Any],
        goals_summary: dict[str, Any],
    ) -> list[str]:
        lines = [context.translate("mira.analysis.context.purpose", "Purpose report")]
        lines.append(
            context.translate(
                "mira.analysis.context.purpose.summary",
                "- Executive summary: Status of my Future Self.",
            )
        )
        goal_completion_index = metrics.get("goal_completion_index_pct")
        if goal_completion_index is not None:
            lines.append(
                context.translate(
                    "mira.analysis.context.purpose.completion_index",
                    "- Completion index: {pct:.1f}%.",
                    params={"pct": float(goal_completion_index)},
                )
            )
        goals_headline = str(goals_summary.get("headline") or "").strip()
        if goals_headline:
            lines.append(f"- {goals_headline}")
        goals_items = [str(item).strip() for item in list(goals_summary.get("items") or []) if str(item).strip()]
        for item in goals_items:
            lines.append(f"- {item}")
        return lines

    def build_context_message(self, payload: dict[str, Any], *, language: str) -> str:
        context = self._context(language)
        comparisons = cast(dict[str, Any], payload.get("comparisons") or {})
        budget = cast(dict[str, Any], payload.get("budget") or {})
        metrics = cast(dict[str, Any], payload.get("metrics") or {})
        history_hints = [str(item).strip() for item in list(payload.get("history_hints") or []) if str(item).strip()]
        goals_summary = cast(dict[str, Any], payload.get("goals_summary") or {})

        lines = [context.translate("mira.analysis.context.chat_title", "Comparisons and context")]
        lines.extend(
            self._build_efficiency_context_lines(context, comparisons=comparisons, budget=budget, metrics=metrics)
        )
        lines.append("")
        lines.extend(
            self._build_security_context_lines(context, payload=payload, metrics=metrics, history_hints=history_hints)
        )
        if (
            goals_summary.get("headline")
            or list(goals_summary.get("items") or [])
            or metrics.get("goal_completion_index_pct") is not None
        ):
            lines.append("")
            lines.extend(self._build_purpose_context_lines(context, metrics=metrics, goals_summary=goals_summary))

        return "\n".join(lines).strip()

    def build_assistant_messages(self, payload: dict[str, Any], *, language: str) -> list[tuple[str, str]]:
        messages: list[tuple[str, str]] = []
        context_text = self.build_context_message(payload, language=language)
        if context_text:
            messages.append(
                (context_text, self._t(language, "mira.analysis.context.chat_title", "Comparativas y contexto"))
            )

        period = payload.get("period") or {}
        advisor_messages = (payload.get("advisor") or {}).get("messages") or []
        if advisor_messages:
            header = self._t(
                language,
                "mira.analysis.assistant.messages_header",
                "Mensaje MIRA {year:04d}-{month:02d}",
                params={
                    "year": int(period.get("year") or 0),
                    "month": int(period.get("month") or 0),
                },
            )
            chat_title = self._t(language, "mira.analysis.assistant_title", "Análisis MIRA")
            for msg in advisor_messages:
                messages.append((f"{header}\n\n{msg.get('text')}", chat_title))

        return messages
