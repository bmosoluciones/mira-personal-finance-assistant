# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Application service and presentation builders for the Reports view."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, cast

from mira.app.view_services._common import PresentationContext
from mira.db.database import Database
from mira.db.errors import BudgetError
from mira.finance_summary import build_savings_lookup, is_savings_transaction
from mira.transaction_kinds import is_analytics_excluded_transaction, is_balance_adjustment_transaction

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


@dataclass(frozen=True)
class ReportFilterOptions:
    accounts: list[dict[str, Any]]
    categories: list[dict[str, Any]]
    tags: list[dict[str, Any]]


@dataclass(frozen=True)
class ReportsComparisons:
    current: dict[str, float]
    previous: dict[str, float]
    yoy: dict[str, float]


@dataclass(frozen=True)
class ReportsLoadedState:
    transactions: list[dict[str, Any]]
    tags_by_tx: dict[int, list[dict[str, Any]]]
    by_month: dict[str, dict[str, float]]
    by_month_account: dict[tuple[str, str], dict[str, float]]
    by_tag_amount: dict[str, float]
    by_tag_count: dict[str, int]
    by_tag_category: dict[str, dict[str, float]]
    category_root_data: dict[str, float]
    category_children_data: dict[str, dict[str, float]]
    comparisons: ReportsComparisons | None
    budget_comparison: dict[str, Any] | None
    account_balance_report: dict[str, Any]
    savings_categories: set[str]


@dataclass(frozen=True)
class PresentationCell:
    text: str
    signal: str | None = None
    badge_kind: str | None = None
    align_right: bool = False


@dataclass(frozen=True)
class PresentationRow:
    cells: tuple[PresentationCell, ...]


@dataclass(frozen=True)
class BarChartSeries:
    name: str
    values: tuple[float, ...]
    color_key: str


@dataclass(frozen=True)
class LineChartSeries:
    name: str
    points: tuple[tuple[float, float], ...]
    color_key: str


@dataclass(frozen=True)
class PieChartSlice:
    label: str
    value: float
    color: str


@dataclass(frozen=True)
class BarChartState:
    title: str
    categories: tuple[str, ...]
    series: tuple[BarChartSeries, ...]


@dataclass(frozen=True)
class BarLineChartState:
    title: str
    categories: tuple[str, ...]
    bar_series: tuple[BarChartSeries, ...]
    line_series: tuple[LineChartSeries, ...]


@dataclass(frozen=True)
class PieChartState:
    title: str
    slices: tuple[PieChartSlice, ...]
    hole_size: float = 0.0


@dataclass(frozen=True)
class ReportsComparisonState:
    previous_text: str
    yoy_text: str


@dataclass(frozen=True)
class ReportsTableSection:
    rows: tuple[PresentationRow, ...]
    chart: BarChartState


@dataclass(frozen=True)
class ReportsCategorySection:
    title: str
    back_enabled: bool
    rows: tuple[PresentationRow, ...]
    top_rows: tuple[PresentationRow, ...]
    chart: PieChartState


@dataclass(frozen=True)
class ReportsCashFlowSection:
    rows: tuple[PresentationRow, ...]
    chart: BarLineChartState


@dataclass(frozen=True)
class ReportsTagSection:
    rows: tuple[PresentationRow, ...]
    matrix_headers: tuple[str, ...]
    matrix_rows: tuple[PresentationRow, ...]
    chart: PieChartState


@dataclass(frozen=True)
class ReportsBudgetSection:
    rows: tuple[PresentationRow, ...]
    chart: BarChartState


@dataclass(frozen=True)
class ReportsAccountBalanceSection:
    summary_text: str
    rows: tuple[PresentationRow, ...]


@dataclass(frozen=True)
class ReportsTransactionItem:
    row: PresentationRow
    detail_fields: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ReportsTransactionPage:
    items: tuple[ReportsTransactionItem, ...]
    page_text: str
    previous_enabled: bool
    next_enabled: bool


@dataclass(frozen=True)
class ReportsPresentationState:
    comparisons: ReportsComparisonState
    total: ReportsTableSection
    category: ReportsCategorySection
    account_trend: ReportsTableSection
    cash_flow: ReportsCashFlowSection
    tag: ReportsTagSection
    budget: ReportsBudgetSection
    account_balance: ReportsAccountBalanceSection
    transactions: ReportsTransactionPage


@dataclass(frozen=True)
class _TransactionPresentation:
    type_text: str
    badge_kind: str


class ReportsViewService:
    """Move report data loading and aggregation out of the QWidget."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def load_filter_options(self) -> ReportFilterOptions:
        return ReportFilterOptions(
            accounts=self._db.account.list(),
            categories=self._db.category.list(),
            tags=self._db.tag.list(),
        )

    def load_account_balance_report(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._db.account.get_balance_report())

    def load_budget_comparison(self, year: int) -> dict[str, Any] | None:
        selected = self._db.budget.get_default_for_year(year)
        if selected is None:
            return None
        try:
            return cast(dict[str, Any], self._db.budget.compare(int(selected["id"]), granularity="monthly"))
        except (BudgetError, RuntimeError, TypeError, ValueError):
            return None

    def load_report_state(self, *, since: str, until: str, filters: dict[str, Any]) -> ReportsLoadedState:
        start_d = date.fromisoformat(since)
        end_d = date.fromisoformat(until)
        span = (end_d - start_d).days + 1
        prev_end = start_d - timedelta(days=1)
        prev_start = prev_end - timedelta(days=max(0, span - 1))
        yoy_start = start_d - timedelta(days=365)
        yoy_end = end_d - timedelta(days=365)

        current = self._db.transaction.list(limit=20_000, since_date=since, until_date=until, **filters)
        previous = self._db.transaction.list(
            limit=20_000,
            since_date=prev_start.isoformat(),
            until_date=prev_end.isoformat(),
            **filters,
        )
        yoy = self._db.transaction.list(
            limit=20_000,
            since_date=yoy_start.isoformat(),
            until_date=yoy_end.isoformat(),
            **filters,
        )

        return self._build_loaded_state(
            current,
            comparisons=ReportsComparisons(
                current=self._summary_from_transactions(current),
                previous=self._summary_from_transactions(previous),
                yoy=self._summary_from_transactions(yoy),
            ),
            year=start_d.year,
        )

    def build_state_from_transactions(self, txs: list[dict[str, Any]], *, year: int) -> ReportsLoadedState:
        return self._build_loaded_state(txs, comparisons=None, year=year)

    def _summary_from_transactions(self, txs: list[dict[str, Any]]) -> dict[str, float]:
        summary = self._db.report.summarize_financials(txs)
        return {
            "income": float(summary["income"]),
            "expense": float(summary["expense"]),
            "net": float(summary["net"]),
        }

    def _build_loaded_state(
        self,
        txs: list[dict[str, Any]],
        *,
        comparisons: ReportsComparisons | None,
        year: int,
    ) -> ReportsLoadedState:
        report_txs = [tx for tx in txs if not is_analytics_excluded_transaction(tx)]
        by_month: dict[str, dict[str, float]] = {}
        by_month_account: dict[tuple[str, str], dict[str, float]] = {}
        by_tag_amount: dict[str, float] = {}
        by_tag_count: dict[str, int] = {}
        by_tag_category: dict[str, dict[str, float]] = {}

        categories = self._db.category.list()
        savings_lookup = build_savings_lookup(categories)
        savings_categories = savings_lookup[1]
        id_map = {int(c["id"]): c for c in categories}
        root_by_name: dict[str, str] = {}
        for cat in categories:
            name = str(cat.get("name") or "")
            parent_id = cat.get("parent_id")
            root = name
            if parent_id is not None and int(parent_id) in id_map:
                root = str(id_map[int(parent_id)].get("name") or name)
            root_by_name[name.casefold()] = root

        by_category_root: dict[str, float] = {}
        by_category_child: dict[str, dict[str, float]] = {}

        tx_ids = [int(tx["id"]) for tx in txs if tx.get("id") is not None]
        tx_tags = self._db.tag.list_bulk_for_transactions(tx_ids)
        no_tag = "(untagged)"

        for tx in report_txs:
            month = str(tx.get("date") or "")[:7]
            if not month:
                continue

            amount = float(tx.get("amount") or 0.0)
            tx_type = str(tx.get("type") or "")
            no_account = "No account"
            account_name = str(tx.get("account_name") or no_account).strip() or no_account
            month_bucket = by_month.setdefault(month, {"income": 0.0, "expense": 0.0})
            account_bucket = by_month_account.setdefault((month, account_name), {"income": 0.0, "expense": 0.0})

            if tx_type == "income":
                month_bucket["income"] += amount
                account_bucket["income"] += amount
            elif tx_type == "expense":
                if is_savings_transaction(tx, savings_lookup):
                    continue
                month_bucket["expense"] += amount
                account_bucket["expense"] += amount
                category = str(tx.get("category") or "(uncategorized)")
                subcategory = str(tx.get("subcategory") or "").strip()
                root = root_by_name.get(category.casefold(), category)
                child = f"{category} › {subcategory}" if subcategory else category
                by_category_root[root] = by_category_root.get(root, 0.0) + amount
                child_map = by_category_child.setdefault(root, {})
                child_map[child] = child_map.get(child, 0.0) + amount
            else:
                continue

            current_tx_tags = tx_tags.get(int(tx.get("id") or 0), [])
            if not current_tx_tags:
                by_tag_amount[no_tag] = by_tag_amount.get(no_tag, 0.0) + amount
                by_tag_count[no_tag] = by_tag_count.get(no_tag, 0) + 1
                bucket = by_tag_category.setdefault(no_tag, {})
                category = str(tx.get("category") or "(uncategorized)")
                bucket[category] = bucket.get(category, 0.0) + amount
            else:
                split = amount / max(1, len(current_tx_tags))
                for tag in current_tx_tags:
                    tag_name = str(tag.get("name") or no_tag)
                    by_tag_amount[tag_name] = by_tag_amount.get(tag_name, 0.0) + split
                    by_tag_count[tag_name] = by_tag_count.get(tag_name, 0) + 1
                    bucket = by_tag_category.setdefault(tag_name, {})
                    category = str(tx.get("category") or "(uncategorized)")
                    bucket[category] = bucket.get(category, 0.0) + split

        return ReportsLoadedState(
            transactions=txs,
            tags_by_tx=tx_tags,
            by_month=by_month,
            by_month_account=by_month_account,
            by_tag_amount=by_tag_amount,
            by_tag_count=by_tag_count,
            by_tag_category=by_tag_category,
            category_root_data=by_category_root,
            category_children_data=by_category_child,
            comparisons=comparisons,
            budget_comparison=self.load_budget_comparison(year),
            account_balance_report=self.load_account_balance_report(),
            savings_categories=savings_categories,
        )


class ReportsViewStateBuilder:
    """Build table-ready and chart-ready presentation state for reports."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def build_state(
        self,
        state: ReportsLoadedState,
        *,
        category_drill_root: str | None,
        tx_page: int,
        tx_page_size: int,
    ) -> ReportsPresentationState:
        context = PresentationContext.from_db(self._db)
        return ReportsPresentationState(
            comparisons=self._build_comparisons(state.comparisons, context),
            total=self._build_total_section(state, context),
            category=self._build_category_section(state, context, category_drill_root=category_drill_root),
            account_trend=self._build_account_trend_section(state, context),
            cash_flow=self._build_cash_flow_section(state, context),
            tag=self._build_tag_section(state, context),
            budget=self._build_budget_section(state.budget_comparison, context),
            account_balance=self._build_account_balance_section(state.account_balance_report, context),
            transactions=self._build_transactions_page(state, context, tx_page=tx_page, tx_page_size=tx_page_size),
        )

    def build_account_balance_preview(self, report: dict[str, Any]) -> ReportsAccountBalanceSection:
        return self._build_account_balance_section(report, PresentationContext.from_db(self._db))

    def _build_comparisons(
        self,
        comparisons: ReportsComparisons | None,
        context: PresentationContext,
    ) -> ReportsComparisonState:
        if comparisons is None:
            return ReportsComparisonState(previous_text="", yoy_text="")

        def _pct(cur: float, base: float) -> float:
            if abs(base) < 1e-9:
                return 0.0
            return ((cur - base) / abs(base)) * 100

        c_income = float(comparisons.current.get("income") or 0.0)
        c_expense = float(comparisons.current.get("expense") or 0.0)
        c_net = float(comparisons.current.get("net") or 0.0)
        p_income = float(comparisons.previous.get("income") or 0.0)
        p_expense = float(comparisons.previous.get("expense") or 0.0)
        p_net = float(comparisons.previous.get("net") or 0.0)
        y_income = float(comparisons.yoy.get("income") or 0.0)
        y_expense = float(comparisons.yoy.get("expense") or 0.0)
        y_net = float(comparisons.yoy.get("net") or 0.0)
        prev_text = context.translate(
            "reports.comparison.previous",
            "Vs prev | Income {income} | Expense {expense} | Net {net}",
            params={
                "income": f"{_pct(c_income, p_income):+.1f}%",
                "expense": f"{_pct(c_expense, p_expense):+.1f}%",
                "net": f"{_pct(c_net, p_net):+.1f}%",
            },
        )
        yoy_text = context.translate(
            "reports.comparison.yoy",
            "Vs YoY | Income {income} | Expense {expense} | Net {net}",
            params={
                "income": f"{_pct(c_income, y_income):+.1f}%",
                "expense": f"{_pct(c_expense, y_expense):+.1f}%",
                "net": f"{_pct(c_net, y_net):+.1f}%",
            },
        )
        return ReportsComparisonState(previous_text=prev_text, yoy_text=yoy_text)

    def _build_total_section(self, state: ReportsLoadedState, context: PresentationContext) -> ReportsTableSection:
        months = tuple(sorted(state.by_month.keys()))
        rows: list[PresentationRow] = []
        income_values: list[float] = []
        expense_values: list[float] = []
        net_values: list[float] = []

        prev_net: float | None = None
        for month in months:
            income = float(state.by_month[month]["income"])
            expense = float(state.by_month[month]["expense"])
            net = income - expense
            income_values.append(income)
            expense_values.append(expense)
            net_values.append(net)
            variance = 0.0 if prev_net is None or abs(prev_net) < 1e-9 else ((net - prev_net) / abs(prev_net)) * 100
            signal = "positive" if variance > 0 else "negative" if variance < 0 else "neutral"
            rows.append(
                PresentationRow(
                    cells=(
                        PresentationCell(month),
                        PresentationCell(context.format_amount(income)),
                        PresentationCell(context.format_amount(expense)),
                        PresentationCell(context.format_amount(net)),
                        PresentationCell(f"{variance:+.1f}%", signal=signal),
                    )
                )
            )
            prev_net = net

        chart = BarChartState(
            title=context.translate("menu.reports.total", "Total Income and Expenses"),
            categories=months,
            series=(
                BarChartSeries(
                    name=context.translate("reports.col.income", "Income"),
                    values=tuple(income_values),
                    color_key="income",
                ),
                BarChartSeries(
                    name=context.translate("reports.col.expense", "Expense"),
                    values=tuple(expense_values),
                    color_key="expense",
                ),
                BarChartSeries(
                    name=context.translate("reports.col.net", "Net"),
                    values=tuple(net_values),
                    color_key="net",
                ),
            ),
        )
        return ReportsTableSection(rows=tuple(rows), chart=chart)

    def _build_category_section(
        self,
        state: ReportsLoadedState,
        context: PresentationContext,
        *,
        category_drill_root: str | None,
    ) -> ReportsCategorySection:
        if category_drill_root is None:
            data = state.category_root_data
            title = context.translate("reports.category.root", "Level: Parent categories")
            back_enabled = False
        else:
            data = state.category_children_data.get(category_drill_root, {})
            title = context.translate(
                "reports.category.child",
                "Level: children of {name}",
                params={"name": category_drill_root},
            )
            back_enabled = True

        total_exp = sum(data.values()) or 1.0
        ranked = sorted(data.items(), key=lambda item: item[1], reverse=True)
        rows: list[PresentationRow] = []
        top_rows: list[PresentationRow] = []
        slices: list[PieChartSlice] = []
        for idx, (category, amount) in enumerate(ranked):
            pct_text = f"{(amount / total_exp) * 100:.1f}%"
            row = PresentationRow(
                cells=(
                    PresentationCell(category),
                    PresentationCell(pct_text),
                    PresentationCell(context.format_amount(amount)),
                )
            )
            rows.append(row)
            if idx < 5:
                top_rows.append(
                    PresentationRow(
                        cells=(
                            PresentationCell(category),
                            PresentationCell(context.format_amount(amount)),
                            PresentationCell(pct_text),
                        )
                    )
                )
            slices.append(PieChartSlice(category, float(amount), _MULTICOLOR_PALETTE[idx % len(_MULTICOLOR_PALETTE)]))

        chart = PieChartState(
            title=context.translate("menu.reports.category", "Category Breakdown"),
            slices=tuple(slices),
        )
        return ReportsCategorySection(
            title=title,
            back_enabled=back_enabled,
            rows=tuple(rows),
            top_rows=tuple(top_rows),
            chart=chart,
        )

    def _build_account_trend_section(
        self,
        state: ReportsLoadedState,
        context: PresentationContext,
    ) -> ReportsTableSection:
        keys = tuple(sorted(state.by_month_account.keys()))
        rows: list[PresentationRow] = []
        by_account_total: dict[str, float] = {}
        for month, account_name in keys:
            income = float(state.by_month_account[(month, account_name)]["income"])
            expense = float(state.by_month_account[(month, account_name)]["expense"])
            net = income - expense
            by_account_total[account_name] = by_account_total.get(account_name, 0.0) + net
            rows.append(
                PresentationRow(
                    cells=(
                        PresentationCell(month),
                        PresentationCell(account_name),
                        PresentationCell(context.format_amount(income)),
                        PresentationCell(context.format_amount(expense)),
                        PresentationCell(context.format_amount(net)),
                    )
                )
            )

        labels = tuple(by_account_total.keys())
        chart = BarChartState(
            title=context.translate("menu.reports.account_trend", "Account Trend"),
            categories=labels,
            series=(
                BarChartSeries(
                    name=context.translate("reports.col.net", "Net"),
                    values=tuple(by_account_total[label] for label in labels),
                    color_key="net",
                ),
            ),
        )
        return ReportsTableSection(rows=tuple(rows), chart=chart)

    def _build_cash_flow_section(
        self,
        state: ReportsLoadedState,
        context: PresentationContext,
    ) -> ReportsCashFlowSection:
        months = tuple(sorted(state.by_month.keys()))
        rows: list[PresentationRow] = []
        flow_values: list[float] = []
        cumulative_points: list[tuple[float, float]] = []
        cumulative = 0.0
        for idx, month in enumerate(months):
            income = float(state.by_month[month]["income"])
            expense = float(state.by_month[month]["expense"])
            flow = income - expense
            cumulative += flow
            flow_values.append(flow)
            cumulative_points.append((float(idx), cumulative))
            rows.append(
                PresentationRow(
                    cells=(
                        PresentationCell(month),
                        PresentationCell(context.format_amount(income)),
                        PresentationCell(context.format_amount(expense)),
                        PresentationCell(context.format_amount(flow)),
                        PresentationCell(context.format_amount(cumulative)),
                    )
                )
            )

        chart = BarLineChartState(
            title=context.translate("menu.reports.cash_flow", "Cash Flow"),
            categories=months,
            bar_series=(
                BarChartSeries(
                    name=context.translate("reports.col.net_flow", "Net Flow"),
                    values=tuple(flow_values),
                    color_key="net",
                ),
            ),
            line_series=(
                LineChartSeries(
                    name=context.translate("reports.col.cumulative", "Cumulative"),
                    points=tuple(cumulative_points),
                    color_key="secondary",
                ),
            ),
        )
        return ReportsCashFlowSection(rows=tuple(rows), chart=chart)

    def _build_tag_section(self, state: ReportsLoadedState, context: PresentationContext) -> ReportsTagSection:
        ranked = sorted(state.by_tag_amount.items(), key=lambda item: item[1], reverse=True)
        rows: list[PresentationRow] = []
        slices: list[PieChartSlice] = []
        for idx, (tag_name, amount) in enumerate(ranked):
            rows.append(
                PresentationRow(
                    cells=(
                        PresentationCell(tag_name),
                        PresentationCell(context.format_amount(amount)),
                        PresentationCell(str(state.by_tag_count.get(tag_name, 0))),
                    )
                )
            )
            if idx < 8:
                slices.append(
                    PieChartSlice(tag_name, float(amount), _MULTICOLOR_PALETTE[idx % len(_MULTICOLOR_PALETTE)])
                )

        category_totals: dict[str, float] = {}
        for cats in state.by_tag_category.values():
            for cat_name, amount in cats.items():
                category_totals[cat_name] = category_totals.get(cat_name, 0.0) + amount
        top_categories = tuple(
            name for name, _ in sorted(category_totals.items(), key=lambda item: item[1], reverse=True)[:6]
        )
        matrix_rows = []
        for tag_name, _amount in ranked:
            matrix_rows.append(
                PresentationRow(
                    cells=(
                        PresentationCell(tag_name),
                        *(
                            PresentationCell(
                                context.format_amount(state.by_tag_category.get(tag_name, {}).get(cat, 0.0))
                            )
                            for cat in top_categories
                        ),
                    )
                )
            )

        return ReportsTagSection(
            rows=tuple(rows),
            matrix_headers=(context.translate("reports.col.tags", "Tags"), *top_categories),
            matrix_rows=tuple(matrix_rows),
            chart=PieChartState(
                title=context.translate("reports.by_tag", "Tag Overview"),
                slices=tuple(slices),
                hole_size=0.4,
            ),
        )

    def _build_budget_section(
        self,
        comparison: dict[str, Any] | None,
        context: PresentationContext,
    ) -> ReportsBudgetSection:
        rows: list[PresentationRow] = []
        labels: list[str] = []
        budget_values: list[float] = []
        real_values: list[float] = []

        if comparison:
            budget_rows = cast(list[dict[str, Any]], comparison.get("rows") or [])
            for row in budget_rows:
                variance = float(row.get("annual_variance") or 0.0)
                signal = "positive" if variance > 0 else "negative" if variance < 0 else "neutral"
                rows.append(
                    PresentationRow(
                        cells=(
                            PresentationCell(str(row.get("name") or "")),
                            PresentationCell(context.format_amount(float(row.get("annual_budget") or 0.0))),
                            PresentationCell(context.format_amount(float(row.get("annual_real") or 0.0))),
                            PresentationCell(context.format_amount(variance), signal=signal),
                        )
                    )
                )

            totals = cast(dict[str, Any], comparison.get("totals") or {})
            expense_periods = cast(list[dict[str, Any]], totals.get("expense") or [])
            labels = [str(item.get("label") or "") for item in expense_periods]
            budget_values = [float(item.get("budget") or 0.0) for item in expense_periods]
            real_values = [float(item.get("real") or 0.0) for item in expense_periods]

        return ReportsBudgetSection(
            rows=tuple(rows),
            chart=BarChartState(
                title=context.translate("reports.by_budget", "Budget vs Actual"),
                categories=tuple(labels),
                series=(
                    BarChartSeries(
                        name=context.translate("reports.col.budget", "Budget"),
                        values=tuple(budget_values),
                        color_key="budget",
                    ),
                    BarChartSeries(
                        name=context.translate("reports.col.real", "Real"),
                        values=tuple(real_values),
                        color_key="actual",
                    ),
                ),
            ),
        )

    def _build_account_balance_section(
        self,
        report: dict[str, Any],
        context: PresentationContext,
    ) -> ReportsAccountBalanceSection:
        rows_data = cast(list[dict[str, Any]], report.get("rows") or [])
        currency = str(report.get("default_currency") or context.default_currency).upper()
        consolidated_total = float(report.get("consolidated_total") or 0.0)
        rows = tuple(
            PresentationRow(
                cells=(
                    PresentationCell(str(row.get("name") or "")),
                    PresentationCell(context.account_type_label(str(row.get("account_type") or "bank"))),
                    PresentationCell(str(row.get("currency") or currency).upper()),
                    PresentationCell(
                        context.format_amount_with_currency(
                            float(row.get("balance") or 0.0),
                            str(row.get("currency") or currency).upper(),
                        ),
                        align_right=True,
                    ),
                    PresentationCell(
                        context.format_amount_with_currency(float(row.get("consolidated_balance") or 0.0), currency),
                        align_right=True,
                    ),
                )
            )
            for row in rows_data
        )
        summary_text = context.translate(
            "reports.account_balance.summary",
            "Consolidated total ({currency}): {total}",
            params={
                "currency": currency,
                "total": context.format_amount_with_currency(consolidated_total, currency),
            },
        )
        return ReportsAccountBalanceSection(summary_text=summary_text, rows=rows)

    def _build_transactions_page(
        self,
        state: ReportsLoadedState,
        context: PresentationContext,
        *,
        tx_page: int,
        tx_page_size: int,
    ) -> ReportsTransactionPage:
        total_pages = max(1, (len(state.transactions) + tx_page_size - 1) // tx_page_size)
        current_page = max(0, min(total_pages - 1, tx_page))
        start = current_page * tx_page_size
        end = start + tx_page_size
        items: list[ReportsTransactionItem] = []

        no_account = context.translate("reports.unknown_account", "No account")
        for tx in state.transactions[start:end]:
            tx_id = int(tx.get("id") or 0)
            tags = ", ".join(str(tag.get("name") or "") for tag in state.tags_by_tx.get(tx_id, []))
            account_name = str(tx.get("account_name") or no_account).strip() or no_account
            type_presentation = self._transaction_type(tx, state.savings_categories)
            detail_fields = (
                ("ID", str(tx.get("id") or "")),
                (context.translate("transactions.col.date", "Date"), str(tx.get("date") or "")),
                (context.translate("transactions.col.type", "Type"), str(tx.get("type") or "")),
                (context.translate("transactions.col.account", "Account"), str(tx.get("account_name") or "")),
                (context.translate("transactions.col.category", "Category"), str(tx.get("category") or "")),
                (
                    context.translate("transactions.col.subcategory", "Subcategory"),
                    str(tx.get("subcategory") or ""),
                ),
                (context.translate("reports.col.tags", "Tags"), tags),
                (
                    context.translate("transactions.col.amount", "Amount"),
                    context.format_amount(float(tx.get("amount") or 0.0)),
                ),
                (
                    context.translate("transactions.col.description", "Description"),
                    str(tx.get("description") or ""),
                ),
            )
            items.append(
                ReportsTransactionItem(
                    row=PresentationRow(
                        cells=(
                            PresentationCell(str(tx.get("date") or "")),
                            PresentationCell(type_presentation.type_text, badge_kind=type_presentation.badge_kind),
                            PresentationCell(str(tx.get("category") or "")),
                            PresentationCell(str(tx.get("subcategory") or "")),
                            PresentationCell(tags),
                            PresentationCell(account_name),
                            PresentationCell(context.format_amount(float(tx.get("amount") or 0.0))),
                            PresentationCell(str(tx.get("description") or "")),
                        )
                    ),
                    detail_fields=detail_fields,
                )
            )

        return ReportsTransactionPage(
            items=tuple(items),
            page_text=f"{current_page + 1}/{total_pages}",
            previous_enabled=current_page > 0,
            next_enabled=current_page + 1 < total_pages,
        )

    def _transaction_type(self, tx: dict[str, Any], savings_categories: set[str]) -> _TransactionPresentation:
        if is_balance_adjustment_transaction(tx):
            return _TransactionPresentation(type_text="~ adjustment", badge_kind="adjustment")
        if int(tx.get("is_transfer") or 0) == 1:
            return _TransactionPresentation(type_text="↔ transfer", badge_kind="transfer")

        tx_type = str(tx.get("type") or "").strip().casefold()
        if tx_type == "income":
            return _TransactionPresentation(type_text="+ income", badge_kind="income")
        if tx_type == "expense":
            category_key = str(tx.get("category") or "").strip().casefold()
            if category_key in savings_categories:
                return _TransactionPresentation(type_text="@ savings", badge_kind="savings")
            return _TransactionPresentation(type_text="- expense", badge_kind="expense")
        return _TransactionPresentation(type_text=tx_type, badge_kind="other")
