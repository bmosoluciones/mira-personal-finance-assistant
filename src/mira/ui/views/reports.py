# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Reports feature view."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from PySide6.QtGui import QCloseEvent

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QLineSeries,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mira.app.view_services import (
    PresentationCell,
    PresentationRow,
    ReportsLoadedState,
    ReportsPresentationState,
    ReportsViewService,
    ReportsViewStateBuilder,
)
from mira.app.view_services._common import ANALYTICS_PALETTE, AnalyticsSemanticRole
from mira.db.database import Database
from mira.ui.i18n import normalize_language, tr
from mira.ui.views.report_types import (
    REPORT_ACCOUNT_BALANCE,
    REPORT_ACCOUNT_TREND,
    REPORT_BUDGET,
    REPORT_CATEGORY,
    REPORT_CASH_FLOW,
    REPORT_TAG,
    REPORT_TOTAL,
)
from mira.ui.views._shared import (
    _COMBO_STYLE,
    _DATE_STYLE,
    _SIGNAL_CELL_ROLE,
    _TABLE_STYLE,
    _TYPE_BADGE_ROLE,
    _build_scrollable_container,
    _configure_chart_view,
    _date_to_qdate,
    _make_toolbar_btn,
    _section_title,
    _sub_title,
)
from mira.ui.delegates.cell_delegates import _SignalCellDelegate, _TypeBadgeDelegate

_ReportRequestSnapshot = tuple[
    str,
    str,
    int | None,
    str | None,
    str | None,
    int | None,
    bool,
]


class _ReportWorker(QThread):
    """Load report state in the background so the GUI stays responsive."""

    loaded = Signal(object, object)
    failed = Signal(object, str)

    def __init__(
        self,
        service: ReportsViewService,
        since: str,
        until: str,
        filters: dict[str, Any],
        request_snapshot: _ReportRequestSnapshot,
    ) -> None:
        super().__init__()
        self._service = service
        self._since = since
        self._until = until
        self._filters = filters
        self._request_snapshot = request_snapshot

    def run(self) -> None:
        try:
            state = self._service.load_report_state(since=self._since, until=self._until, filters=self._filters)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(self._request_snapshot, str(exc))
            return
        self.loaded.emit(self._request_snapshot, state)


class ReportsView(QWidget):
    """Financial dashboards focused on visual insights and auditability."""

    assistant_message_requested = Signal(str, str)

    REPORT_TOTAL = REPORT_TOTAL
    REPORT_CATEGORY = REPORT_CATEGORY
    REPORT_ACCOUNT_TREND = REPORT_ACCOUNT_TREND
    REPORT_CASH_FLOW = REPORT_CASH_FLOW
    REPORT_TAG = REPORT_TAG
    REPORT_BUDGET = REPORT_BUDGET
    REPORT_ACCOUNT_BALANCE = REPORT_ACCOUNT_BALANCE

    def __init__(
        self,
        db: Database,
        parent: QWidget | None = None,
        service: ReportsViewService | None = None,
        state_builder: ReportsViewStateBuilder | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._service = service or ReportsViewService(db)
        self._state_builder = state_builder or ReportsViewStateBuilder(db)
        self._language = normalize_language(self._db.setting.get("language"))
        self._current_report_payload: dict[str, Any] | None = None
        self._loaded_state: ReportsLoadedState | None = None
        self._presentation_state: ReportsPresentationState | None = None
        self._report_has_loaded_data = False
        self._report_dirty = False
        self._category_drill_root: str | None = None
        self._tx_page = 0
        self._tx_page_size = 100
        self._worker: _ReportWorker | None = None
        self._inflight_request_snapshot: _ReportRequestSnapshot | None = None
        self._build_ui()

    def _set_report_status(self, text: str, *, color: str = "#9FB3C8") -> None:
        self._report_status_lbl.setText(text)
        self._report_status_lbl.setStyleSheet(f"font-size:11px;color:{color};padding:2px 0 0 0;")

    def _mark_report_pending(self) -> None:
        self._report_dirty = True
        if self._report_has_loaded_data:
            self._set_report_status(
                tr(
                    "reports.pending.loaded",
                    self._language,
                    default="Los filtros cambiaron. Se muestra el último reporte cargado hasta que pulses Apply.",
                )
            )
            return
        self._set_report_status(
            tr(
                "reports.pending.empty",
                self._language,
                default="La vista está lista. Ajusta filtros y pulsa Apply para consultar la base de datos.",
            )
        )

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(20, 16, 20, 16)
        outer_layout.setSpacing(10)

        outer_layout.addWidget(_section_title(tr("reports.title", self._language, default="MIRA Reports")))

        self._report_scroll, _content, layout = _build_scrollable_container(self)
        outer_layout.addWidget(self._report_scroll, 1)

        filters = QFrame()
        filters.setStyleSheet("QFrame{border:1px solid palette(mid);border-radius:8px;}")
        filters_layout = QVBoxLayout(filters)
        filters_layout.setContentsMargins(10, 10, 10, 10)

        top_filters = QHBoxLayout()
        self._report_type = QComboBox()
        self._report_type.setStyleSheet(_COMBO_STYLE)
        self._report_type.addItems(
            [
                tr(
                    "menu.reports.total",
                    self._language,
                    default="Total Income and Expenses",
                ),
                tr(
                    "menu.reports.category",
                    self._language,
                    default="Category Breakdown",
                ),
                tr(
                    "menu.reports.account_trend",
                    self._language,
                    default="Account Trend",
                ),
                tr("menu.reports.cash_flow", self._language, default="Cash Flow"),
                tr("reports.by_tag", self._language, default="Tag Overview"),
                tr("reports.by_budget", self._language, default="Budget vs Actual"),
                tr("menu.reports.account_balance", self._language, default="Account and Credit Card Balance"),
            ]
        )
        self._report_type.currentIndexChanged.connect(self._on_report_type_changed)
        top_filters.addWidget(QLabel(tr("reports.filter.type", self._language, default="Report Type")))
        top_filters.addWidget(self._report_type, 1)

        top_filters.addSpacing(14)
        top_filters.addWidget(QLabel(tr("reports.filter.range", self._language, default="Date Range")))
        self._from_date = QDateEdit()
        self._from_date.setCalendarPopup(True)
        self._from_date.setDisplayFormat("yyyy-MM-dd")
        self._from_date.setStyleSheet(_DATE_STYLE)
        self._to_date = QDateEdit()
        self._to_date.setCalendarPopup(True)
        self._to_date.setDisplayFormat("yyyy-MM-dd")
        self._to_date.setStyleSheet(_DATE_STYLE)
        top_filters.addWidget(self._from_date)
        top_filters.addWidget(self._to_date)

        self._btn_apply = _make_toolbar_btn(tr("reports.apply", self._language, default="Apply"))
        self._btn_apply.clicked.connect(self._apply_report)
        top_filters.addWidget(self._btn_apply)
        filters_layout.addLayout(top_filters)

        cross_filters = QHBoxLayout()
        self._account_filter = QComboBox()
        self._account_filter.setStyleSheet(_COMBO_STYLE)
        self._tx_type_filter = QComboBox()
        self._tx_type_filter.setStyleSheet(_COMBO_STYLE)
        self._category_filter = QComboBox()
        self._category_filter.setStyleSheet(_COMBO_STYLE)
        self._tag_filter = QComboBox()
        self._tag_filter.setStyleSheet(_COMBO_STYLE)
        self._include_children = QCheckBox(
            tr(
                "reports.filter.include_children",
                self._language,
                default="Include children",
            )
        )
        for label, widget in [
            (
                tr("reports.filter.account", self._language, default="Account"),
                self._account_filter,
            ),
            (
                tr("reports.filter.tx_type", self._language, default="Type"),
                self._tx_type_filter,
            ),
            (
                tr("reports.filter.category", self._language, default="Category"),
                self._category_filter,
            ),
            (tr("reports.filter.tag", self._language, default="Tag"), self._tag_filter),
        ]:
            cross_filters.addWidget(QLabel(label))
            cross_filters.addWidget(widget)
        cross_filters.addWidget(self._include_children)
        self._btn_clear_filters = _make_toolbar_btn(tr("reports.filter.clear", self._language, default="Clear Filters"))
        self._btn_clear_filters.clicked.connect(self._reset_cross_filters)
        cross_filters.addWidget(self._btn_clear_filters)
        filters_layout.addLayout(cross_filters)

        pills = QHBoxLayout()
        self._pill_month = _make_toolbar_btn(tr("reports.period.month", self._language, default="This Month"))
        self._pill_3m = _make_toolbar_btn(tr("reports.period.3m", self._language, default="Last 3 Months"))
        self._pill_year = _make_toolbar_btn(tr("reports.period.year", self._language, default="This Year"))
        self._pill_custom = _make_toolbar_btn(tr("reports.period.custom", self._language, default="Custom Range..."))
        self._pill_month.clicked.connect(lambda: self._set_period("month"))
        self._pill_3m.clicked.connect(lambda: self._set_period("3m"))
        self._pill_year.clicked.connect(lambda: self._set_period("year"))
        self._pill_custom.clicked.connect(lambda: self._set_period("custom"))
        for btn in [
            self._pill_month,
            self._pill_3m,
            self._pill_year,
            self._pill_custom,
        ]:
            pills.addWidget(btn)
        pills.addStretch()
        filters_layout.addLayout(pills)
        layout.addWidget(filters)

        self._report_status_lbl = QLabel("")
        self._report_status_lbl.setWordWrap(True)
        layout.addWidget(self._report_status_lbl)

        cmp_row = QHBoxLayout()
        self._cmp_prev_lbl = QLabel()
        self._cmp_yoy_lbl = QLabel()
        self._cmp_prev_lbl.setStyleSheet("font-size:11px;color:palette(midlight);")
        self._cmp_yoy_lbl.setStyleSheet("font-size:11px;color:palette(midlight);")
        cmp_row.addWidget(self._cmp_prev_lbl)
        cmp_row.addWidget(self._cmp_yoy_lbl)
        cmp_row.addStretch()
        layout.addLayout(cmp_row)

        self._report_stack = QStackedWidget()
        self._report_stack.addWidget(self._build_total_page())
        self._report_stack.addWidget(self._build_category_page())
        self._report_stack.addWidget(self._build_account_page())
        self._report_stack.addWidget(self._build_cash_page())
        self._report_stack.addWidget(self._build_tag_page())
        self._report_stack.addWidget(self._build_budget_page())
        self._report_stack.addWidget(self._build_account_balance_page())
        self._report_stack.setMinimumHeight(660)
        layout.addWidget(self._report_stack, 2)

        layout.addWidget(
            _sub_title(
                tr(
                    "reports.audit.title",
                    self._language,
                    default="Transactions (Audit Trail)",
                )
            )
        )
        self._tx_table = QTableWidget(0, 8)
        self._tx_table.setHorizontalHeaderLabels(
            [
                tr("transactions.col.date", self._language, default="Date"),
                tr("transactions.col.type", self._language, default="Type"),
                tr("transactions.col.category", self._language, default="Category"),
                tr(
                    "transactions.col.subcategory",
                    self._language,
                    default="Subcategory",
                ),
                tr("reports.col.tags", self._language, default="Tags"),
                tr("transactions.col.account", self._language, default="Account"),
                tr("transactions.col.amount", self._language, default="Amount"),
                tr(
                    "transactions.col.description",
                    self._language,
                    default="Description",
                ),
            ]
        )
        self._tx_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self._tx_table.verticalHeader().setVisible(False)
        self._tx_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tx_table.setAlternatingRowColors(True)
        self._tx_table.setStyleSheet(_TABLE_STYLE)
        self._tx_table.setItemDelegateForColumn(1, _TypeBadgeDelegate(self._tx_table))
        self._tx_table.setMinimumHeight(220)
        self._tx_table.cellDoubleClicked.connect(self._open_tx_detail)
        layout.addWidget(self._tx_table, 1)

        pager = QHBoxLayout()
        self._btn_prev_page = _make_toolbar_btn("←")
        self._btn_next_page = _make_toolbar_btn("→")
        self._page_info = QLabel("0/0")
        self._btn_prev_page.clicked.connect(lambda: self._change_tx_page(-1))
        self._btn_next_page.clicked.connect(lambda: self._change_tx_page(1))
        pager.addWidget(self._btn_prev_page)
        pager.addWidget(self._btn_next_page)
        pager.addWidget(self._page_info)
        pager.addStretch()
        layout.addLayout(pager)
        layout.addStretch()

        self._refresh_filter_options()
        self._set_period("year")
        self._from_date.dateChanged.connect(lambda _date: self._mark_report_pending())
        self._to_date.dateChanged.connect(lambda _date: self._mark_report_pending())
        self._account_filter.currentIndexChanged.connect(lambda _index: self._mark_report_pending())
        self._tx_type_filter.currentIndexChanged.connect(lambda _index: self._mark_report_pending())
        self._category_filter.currentIndexChanged.connect(lambda _index: self._mark_report_pending())
        self._tag_filter.currentIndexChanged.connect(lambda _index: self._mark_report_pending())
        self._include_children.stateChanged.connect(lambda _state: self._mark_report_pending())
        self._mark_report_pending()

    def _build_total_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(
            _sub_title(
                tr(
                    "menu.reports.total",
                    self._language,
                    default="Total Income and Expenses",
                )
            )
        )
        self._total_chart = QChartView()
        _configure_chart_view(self._total_chart, minimum_height=420)
        page_layout.addWidget(self._total_chart, 3)
        self._income_expense_table = QTableWidget(0, 5)
        self._income_expense_table.setHorizontalHeaderLabels(
            [
                tr("reports.col.month", self._language, default="Month"),
                tr("reports.col.income", self._language, default="Income"),
                tr("reports.col.expense", self._language, default="Expense"),
                tr("reports.col.net", self._language, default="Net"),
                tr("reports.col.variance", self._language, default="Vs Prev %"),
            ]
        )
        self._income_expense_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column_idx in range(1, self._income_expense_table.columnCount()):
            self._income_expense_table.horizontalHeader().setSectionResizeMode(
                column_idx,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        self._income_expense_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._income_expense_table.verticalHeader().setVisible(False)
        self._income_expense_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._income_expense_table.setAlternatingRowColors(True)
        self._income_expense_table.setStyleSheet(_TABLE_STYLE)
        self._income_expense_table.setItemDelegate(_SignalCellDelegate(self._income_expense_table))
        self._income_expense_table.setMinimumHeight(240)
        page_layout.addWidget(self._income_expense_table, 2)
        return page

    def _build_category_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(
            _sub_title(
                tr(
                    "menu.reports.category",
                    self._language,
                    default="Category Breakdown",
                )
            )
        )

        drill = QHBoxLayout()
        self._category_drill_lbl = QLabel()
        self._btn_category_back = _make_toolbar_btn(tr("reports.back", self._language, default="Back"))
        self._btn_category_back.clicked.connect(self._category_drill_up)
        drill.addWidget(self._category_drill_lbl)
        drill.addWidget(self._btn_category_back)
        drill.addStretch()
        page_layout.addLayout(drill)

        top = QHBoxLayout()
        self._category_chart = QChartView()
        _configure_chart_view(self._category_chart, minimum_height=420)
        top.addWidget(self._category_chart, 2)

        self._top5_table = QTableWidget(0, 3)
        self._top5_table.setHorizontalHeaderLabels(
            [
                tr("reports.col.category", self._language, default="Category"),
                tr("reports.col.total", self._language, default="Total"),
                "%",
            ]
        )
        self._top5_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._top5_table.verticalHeader().setVisible(False)
        self._top5_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._top5_table.setStyleSheet(_TABLE_STYLE)
        self._top5_table.setMinimumHeight(240)
        top.addWidget(self._top5_table, 1)
        page_layout.addLayout(top, 3)

        self._category_table = QTableWidget(0, 3)
        self._category_table.setHorizontalHeaderLabels(
            [
                tr("reports.col.category", self._language, default="Category"),
                "%",
                tr("reports.col.amount", self._language, default="Amount"),
            ]
        )
        self._category_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._category_table.verticalHeader().setVisible(False)
        self._category_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._category_table.setStyleSheet(_TABLE_STYLE)
        self._category_table.setMinimumHeight(240)
        page_layout.addWidget(self._category_table, 2)
        return page

    def _build_account_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(
            _sub_title(
                tr(
                    "menu.reports.account_trend",
                    self._language,
                    default="Account Trend",
                )
            )
        )
        self._account_chart = QChartView()
        _configure_chart_view(self._account_chart, minimum_height=420)
        page_layout.addWidget(self._account_chart, 3)
        self._account_trend_table = QTableWidget(0, 5)
        self._account_trend_table.setHorizontalHeaderLabels(
            [
                tr("reports.col.month", self._language, default="Month"),
                tr("reports.col.account", self._language, default="Account"),
                tr("reports.col.income", self._language, default="Income"),
                tr("reports.col.expense", self._language, default="Expense"),
                tr("reports.col.net", self._language, default="Net"),
            ]
        )
        self._account_trend_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._account_trend_table.verticalHeader().setVisible(False)
        self._account_trend_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._account_trend_table.setAlternatingRowColors(True)
        self._account_trend_table.setStyleSheet(_TABLE_STYLE)
        self._account_trend_table.setMinimumHeight(240)
        page_layout.addWidget(self._account_trend_table, 2)
        return page

    def _build_cash_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(_sub_title(tr("menu.reports.cash_flow", self._language, default="Cash Flow")))
        self._cash_chart = QChartView()
        _configure_chart_view(self._cash_chart, minimum_height=420)
        page_layout.addWidget(self._cash_chart, 3)
        self._cash_flow_table = QTableWidget(0, 5)
        self._cash_flow_table.setHorizontalHeaderLabels(
            [
                tr("reports.col.month", self._language, default="Month"),
                tr("reports.col.income", self._language, default="Income"),
                tr("reports.col.expense", self._language, default="Expense"),
                tr("reports.col.net_flow", self._language, default="Net Flow"),
                tr("reports.col.cumulative", self._language, default="Cumulative"),
            ]
        )
        self._cash_flow_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._cash_flow_table.verticalHeader().setVisible(False)
        self._cash_flow_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._cash_flow_table.setAlternatingRowColors(True)
        self._cash_flow_table.setStyleSheet(_TABLE_STYLE)
        self._cash_flow_table.setMinimumHeight(240)
        page_layout.addWidget(self._cash_flow_table, 2)
        return page

    def _build_tag_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(_sub_title(tr("reports.by_tag", self._language, default="Tag Overview")))
        self._tag_chart = QChartView()
        _configure_chart_view(self._tag_chart, minimum_height=380)
        page_layout.addWidget(self._tag_chart, 2)

        row = QHBoxLayout()
        self._tag_table = QTableWidget(0, 3)
        self._tag_table.setHorizontalHeaderLabels(
            [
                tr("reports.col.tags", self._language, default="Tags"),
                tr("reports.col.amount", self._language, default="Amount"),
                tr("reports.col.transactions", self._language, default="Transactions"),
            ]
        )
        self._tag_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tag_table.verticalHeader().setVisible(False)
        self._tag_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tag_table.setAlternatingRowColors(True)
        self._tag_table.setStyleSheet(_TABLE_STYLE)
        self._tag_table.setMinimumHeight(260)
        row.addWidget(self._tag_table, 1)

        self._tag_matrix_table = QTableWidget(0, 0)
        self._tag_matrix_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tag_matrix_table.setAlternatingRowColors(True)
        self._tag_matrix_table.setStyleSheet(_TABLE_STYLE)
        self._tag_matrix_table.setMinimumHeight(260)
        row.addWidget(self._tag_matrix_table, 2)
        page_layout.addLayout(row, 2)
        return page

    def _build_budget_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(_sub_title(tr("reports.by_budget", self._language, default="Budget vs Actual")))
        self._budget_chart = QChartView()
        _configure_chart_view(self._budget_chart, minimum_height=420)
        page_layout.addWidget(self._budget_chart, 2)
        self._budget_table = QTableWidget(0, 4)
        self._budget_table.setHorizontalHeaderLabels(
            [
                tr("reports.col.category", self._language, default="Category"),
                tr("reports.col.budget", self._language, default="Budget"),
                tr("reports.col.real", self._language, default="Real"),
                tr("reports.col.variance", self._language, default="Variance"),
            ]
        )
        self._budget_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column_idx in range(1, self._budget_table.columnCount()):
            self._budget_table.horizontalHeader().setSectionResizeMode(
                column_idx,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        self._budget_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._budget_table.verticalHeader().setVisible(False)
        self._budget_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._budget_table.setAlternatingRowColors(True)
        self._budget_table.setStyleSheet(_TABLE_STYLE)
        self._budget_table.setItemDelegate(_SignalCellDelegate(self._budget_table))
        self._budget_table.setMinimumHeight(260)
        page_layout.addWidget(self._budget_table, 2)
        return page

    def _build_account_balance_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(
            _sub_title(
                tr(
                    "menu.reports.account_balance",
                    self._language,
                    default="Account and Credit Card Balance",
                )
            )
        )

        self._account_balance_summary_lbl = QLabel()
        self._account_balance_summary_lbl.setWordWrap(True)
        self._account_balance_summary_lbl.setStyleSheet("font-size:11px;color:palette(midlight);padding:2px 0 6px 0;")
        page_layout.addWidget(self._account_balance_summary_lbl)

        self._account_balance_table = QTableWidget(0, 5)
        self._account_balance_table.setHorizontalHeaderLabels(
            [
                tr("reports.col.account", self._language, default="Account"),
                tr("reports.col.type", self._language, default="Type"),
                tr("reports.col.currency", self._language, default="Currency"),
                tr("reports.col.balance", self._language, default="Balance"),
                tr("reports.col.consolidated", self._language, default="Consolidated"),
            ]
        )
        self._account_balance_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._account_balance_table.verticalHeader().setVisible(False)
        self._account_balance_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._account_balance_table.setAlternatingRowColors(True)
        self._account_balance_table.setStyleSheet(_TABLE_STYLE)
        self._account_balance_table.setMinimumHeight(320)
        page_layout.addWidget(self._account_balance_table, 1)
        return page

    def _theme_color(self, role: QPalette.ColorRole, fallback: str) -> QColor:
        col = self.palette().color(role)
        if not col.isValid():
            return QColor(fallback)
        return col

    def _semantic_chart_color(self, key: str, fallback: str = "#9FB3C8") -> QColor:
        try:
            role = AnalyticsSemanticRole(str(key).strip().lower())
        except ValueError:
            return QColor(fallback)
        return QColor(ANALYTICS_PALETTE.semantic_hex(role))

    def _base_chart(self, title: str) -> QChart:
        chart = QChart()
        chart.setTitle(title)
        chart.setBackgroundVisible(False)
        chart.legend().setVisible(True)
        chart.legend().setLabelColor(self._theme_color(self.foregroundRole(), "#DDD"))
        return chart

    def _refresh_filter_options(self) -> None:
        options = self._service.load_filter_options()
        selected_account = self._account_filter.currentData() if hasattr(self, "_account_filter") else None
        selected_type = self._tx_type_filter.currentData() if hasattr(self, "_tx_type_filter") else None
        selected_category = self._category_filter.currentData() if hasattr(self, "_category_filter") else None
        selected_tag = self._tag_filter.currentData() if hasattr(self, "_tag_filter") else None

        for combo in [self._account_filter, self._tx_type_filter, self._category_filter, self._tag_filter]:
            combo.blockSignals(True)

        self._account_filter.clear()
        self._account_filter.addItem(tr("reports.filter.all", self._language, default="All"), None)
        for account in options.accounts:
            self._account_filter.addItem(str(account.get("name") or ""), int(account["id"]))

        self._tx_type_filter.clear()
        self._tx_type_filter.addItem(tr("reports.filter.all", self._language, default="All"), None)
        self._tx_type_filter.addItem(tr("reports.type.income", self._language, default="Income"), "income")
        self._tx_type_filter.addItem(tr("reports.type.expense", self._language, default="Expense"), "expense")

        self._category_filter.clear()
        self._category_filter.addItem(tr("reports.filter.all", self._language, default="All"), None)
        for category in options.categories:
            self._category_filter.addItem(str(category.get("name") or ""), str(category.get("name") or ""))

        self._tag_filter.clear()
        self._tag_filter.addItem(tr("reports.filter.all", self._language, default="All"), None)
        for tag in options.tags:
            self._tag_filter.addItem(str(tag.get("name") or ""), int(tag["id"]))

        for combo, value in [
            (self._account_filter, selected_account),
            (self._tx_type_filter, selected_type),
            (self._category_filter, selected_category),
            (self._tag_filter, selected_tag),
        ]:
            idx = combo.findData(value)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

    def _reset_cross_filters(self) -> None:
        self._account_filter.setCurrentIndex(0)
        self._tx_type_filter.setCurrentIndex(0)
        self._category_filter.setCurrentIndex(0)
        self._tag_filter.setCurrentIndex(0)
        self._include_children.setChecked(False)
        self._mark_report_pending()

    def _on_report_type_changed(self, index: int) -> None:
        self._report_stack.setCurrentIndex(index)

    def _set_period(self, period: str) -> None:
        today = date.today()
        if period == "month":
            start = today.replace(day=1)
            end = today
        elif period == "3m":
            month = today.month - 2
            year = today.year
            while month <= 0:
                month += 12
                year -= 1
            start = date(year, month, 1)
            end = today
        elif period == "year":
            start = date(today.year, 1, 1)
            end = today
        else:
            return
        self._from_date.setDate(_date_to_qdate(start))
        self._to_date.setDate(_date_to_qdate(end))
        self._mark_report_pending()

    def _current_filters(self) -> dict[str, Any]:
        return {
            "account_id": self._account_filter.currentData(),
            "tx_type": self._tx_type_filter.currentData(),
            "category": self._category_filter.currentData(),
            "tag_id": self._tag_filter.currentData(),
            "include_children": self._include_children.isChecked(),
        }

    def _build_request_snapshot(
        self,
        since: str,
        until: str,
        filters: dict[str, Any],
    ) -> _ReportRequestSnapshot:
        return (
            since,
            until,
            filters.get("account_id"),
            filters.get("tx_type"),
            filters.get("category"),
            filters.get("tag_id"),
            bool(filters.get("include_children")),
        )

    def _current_request_snapshot(self) -> _ReportRequestSnapshot:
        return self._build_request_snapshot(
            self._from_date.date().toString("yyyy-MM-dd"),
            self._to_date.date().toString("yyyy-MM-dd"),
            self._current_filters(),
        )

    def _should_apply_completed_request(self, request_snapshot: _ReportRequestSnapshot) -> bool:
        return (
            request_snapshot == self._inflight_request_snapshot and request_snapshot == self._current_request_snapshot()
        )

    def _apply_report(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        since = self._from_date.date().toString("yyyy-MM-dd")
        until = self._to_date.date().toString("yyyy-MM-dd")
        params = self._current_filters()
        request_snapshot = self._build_request_snapshot(since, until, params)
        self._category_drill_root = None
        self._tx_page = 0
        self._set_report_status(
            tr("reports.loading", self._language, default="Cargando reporte…"),
            color="#F7C16B",
        )
        self._inflight_request_snapshot = request_snapshot
        self._worker = _ReportWorker(self._service, since, until, params, request_snapshot)
        self._worker.loaded.connect(self._on_report_loaded, Qt.ConnectionType.QueuedConnection)
        self._worker.failed.connect(self._on_report_failed, Qt.ConnectionType.QueuedConnection)
        self._worker.finished.connect(self._on_report_finished, Qt.ConnectionType.QueuedConnection)
        self._worker.start()

    def _on_report_loaded(self, request_snapshot: object, state: object) -> None:
        snapshot = cast(_ReportRequestSnapshot, request_snapshot)
        if not self._should_apply_completed_request(snapshot):
            self._mark_report_pending()
            return
        self._set_loaded_state(state)  # type: ignore[arg-type]
        self._report_has_loaded_data = True
        self._report_dirty = False
        self._set_report_status(
            tr("reports.loaded", self._language, default="Reporte cargado con los filtros seleccionados."),
            color="#4EC9B0",
        )

    def _on_report_failed(self, request_snapshot: object, message: str) -> None:
        snapshot = cast(_ReportRequestSnapshot, request_snapshot)
        if not self._should_apply_completed_request(snapshot):
            self._mark_report_pending()
            return
        status_message = message or tr(
            "reports.load_error",
            self._language,
            default="The report could not be loaded. Review the filters and try again.",
        )
        self._set_report_status(
            status_message,
            color="#F48771",
        )

    def _on_report_finished(self) -> None:
        self._worker = None
        self._inflight_request_snapshot = None

    def _stop_worker(self) -> None:
        """Disconnect signals and wait for the running worker to finish.

        The worker is created fresh in ``_apply_report`` and only this view
        connects to its signals, so disconnecting all slots is safe here.
        """
        if self._worker is not None:
            if self._worker.isRunning():
                try:
                    self._worker.loaded.disconnect()
                    self._worker.failed.disconnect()
                    self._worker.finished.disconnect()
                except RuntimeError:
                    pass
                self._worker.wait()
            self._worker = None
        self._inflight_request_snapshot = None

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        self._stop_worker()
        super().closeEvent(event)

    def _set_loaded_state(self, state: ReportsLoadedState) -> None:
        self._loaded_state = state
        self._rebuild_presentation_state()

    def _rebuild_presentation_state(self) -> None:
        if self._loaded_state is None:
            return
        self._presentation_state = self._state_builder.build_state(
            self._loaded_state,
            category_drill_root=self._category_drill_root,
            tx_page=self._tx_page,
            tx_page_size=self._tx_page_size,
        )
        self._bind_presentation_state(self._presentation_state)

    def _on_category_slice_clicked(self, slice_item) -> None:  # type: ignore[no-untyped-def]
        label = str(slice_item.label())
        if (
            self._loaded_state is not None
            and self._category_drill_root is None
            and label in self._loaded_state.category_children_data
        ):
            self._category_drill_root = label
            self._rebuild_presentation_state()

    def _category_drill_up(self) -> None:
        self._category_drill_root = None
        self._rebuild_presentation_state()

    def _change_tx_page(self, delta: int) -> None:
        if self._loaded_state is None:
            return
        total_pages = max(1, (len(self._loaded_state.transactions) + self._tx_page_size - 1) // self._tx_page_size)
        self._tx_page = max(0, min(total_pages - 1, self._tx_page + delta))
        self._rebuild_presentation_state()

    def _open_tx_detail(self, row: int, _col: int) -> None:
        if self._presentation_state is None:
            return
        items = self._presentation_state.transactions.items
        if row < 0 or row >= len(items):
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(tr("reports.tx_detail", self._language, default="Transaction detail"))
        vbox = QVBoxLayout(dlg)
        form = QFormLayout()
        for label, value in items[row].detail_fields:
            form.addRow(label, QLabel(value))
        vbox.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.reject)
        btns.accepted.connect(dlg.accept)
        btns.button(QDialogButtonBox.StandardButton.Close).clicked.connect(dlg.reject)
        vbox.addWidget(btns)
        dlg.exec()

    def _bind_presentation_state(self, state: ReportsPresentationState) -> None:
        self._cmp_prev_lbl.setText(state.comparisons.previous_text)
        self._cmp_yoy_lbl.setText(state.comparisons.yoy_text)

        self._bind_table_rows(self._income_expense_table, state.total.rows)
        self._bind_bar_chart(self._total_chart, state.total.chart)

        self._category_drill_lbl.setText(state.category.title)
        self._btn_category_back.setEnabled(state.category.back_enabled)
        self._bind_table_rows(self._category_table, state.category.rows)
        self._bind_table_rows(self._top5_table, state.category.top_rows)
        self._bind_pie_chart(self._category_chart, state.category.chart, on_clicked=self._on_category_slice_clicked)

        self._bind_table_rows(self._account_trend_table, state.account_trend.rows)
        self._bind_bar_chart(self._account_chart, state.account_trend.chart)

        self._bind_table_rows(self._cash_flow_table, state.cash_flow.rows)
        self._bind_bar_line_chart(self._cash_chart, state.cash_flow.chart)

        self._bind_table_rows(self._tag_table, state.tag.rows)
        self._bind_pie_chart(self._tag_chart, state.tag.chart)
        self._tag_matrix_table.setColumnCount(len(state.tag.matrix_headers))
        self._tag_matrix_table.setHorizontalHeaderLabels(list(state.tag.matrix_headers))
        self._bind_table_rows(self._tag_matrix_table, state.tag.matrix_rows)

        self._bind_table_rows(self._budget_table, state.budget.rows)
        self._bind_bar_chart(self._budget_chart, state.budget.chart)

        self._account_balance_summary_lbl.setText(state.account_balance.summary_text)
        self._bind_table_rows(self._account_balance_table, state.account_balance.rows)

        self._bind_table_rows(self._tx_table, tuple(item.row for item in state.transactions.items))
        self._page_info.setText(state.transactions.page_text)
        self._btn_prev_page.setEnabled(state.transactions.previous_enabled)
        self._btn_next_page.setEnabled(state.transactions.next_enabled)

    def _bind_account_balance_preview(self) -> None:
        section = self._state_builder.build_account_balance_preview(self._service.load_account_balance_report())
        self._account_balance_summary_lbl.setText(section.summary_text)
        self._bind_table_rows(self._account_balance_table, section.rows)

    def _bind_table_rows(self, table: QTableWidget, rows: tuple[PresentationRow, ...]) -> None:
        table.clearContents()
        table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            for col_idx, cell in enumerate(row.cells):
                table.setItem(row_idx, col_idx, self._make_table_item(cell))

    def _make_table_item(self, cell: PresentationCell) -> QTableWidgetItem:
        item = QTableWidgetItem(cell.text)
        if cell.signal:
            item.setData(_SIGNAL_CELL_ROLE, cell.signal)
        if cell.badge_kind:
            item.setData(_TYPE_BADGE_ROLE, cell.badge_kind)
        if cell.align_right:
            item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        return item

    def _chart_color(self, color_key: str) -> QColor:
        if color_key.startswith("#"):
            return QColor(color_key)
        return self._semantic_chart_color(color_key)

    def _bind_bar_chart(self, chart_view: QChartView, chart_state: Any) -> None:
        chart = self._base_chart(chart_state.title)
        series = QBarSeries()
        for series_state in chart_state.series:
            bar_set = QBarSet(series_state.name)
            bar_set.setColor(self._chart_color(series_state.color_key))
            for value in series_state.values:
                bar_set.append(float(value))
            series.append(bar_set)
        chart.addSeries(series)
        axis_x = QBarCategoryAxis()
        axis_x.append(list(chart_state.categories))
        axis_y = QValueAxis()
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)
        chart_view.setChart(chart)

    def _bind_bar_line_chart(self, chart_view: QChartView, chart_state: Any) -> None:
        chart = self._base_chart(chart_state.title)
        bars = QBarSeries()
        for series_state in chart_state.bar_series:
            bar_set = QBarSet(series_state.name)
            bar_set.setColor(self._chart_color(series_state.color_key))
            for value in series_state.values:
                bar_set.append(float(value))
            bars.append(bar_set)
        chart.addSeries(bars)
        line_x = QValueAxis()
        line_x.setRange(0, max(0, len(chart_state.categories) - 1))
        line_x.setTickCount(max(2, len(chart_state.categories)))
        line_x.setVisible(False)
        for series_state in chart_state.line_series:
            line = QLineSeries()
            line.setName(series_state.name)
            line.setColor(self._chart_color(series_state.color_key))
            for x_value, y_value in series_state.points:
                line.append(float(x_value), float(y_value))
            chart.addSeries(line)

        axis_x = QBarCategoryAxis()
        axis_x.append(list(chart_state.categories))
        axis_y = QValueAxis()
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        chart.addAxis(line_x, Qt.AlignmentFlag.AlignBottom)
        bars.attachAxis(axis_x)
        bars.attachAxis(axis_y)
        for series in chart.series():
            if isinstance(series, QLineSeries):
                series.attachAxis(line_x)
                series.attachAxis(axis_y)
        chart_view.setChart(chart)

    def _bind_pie_chart(self, chart_view: QChartView, chart_state: Any, *, on_clicked=None) -> None:
        chart = self._base_chart(chart_state.title)
        series = QPieSeries()
        if getattr(chart_state, "hole_size", 0.0) > 0:
            series.setHoleSize(chart_state.hole_size)
        for slice_state in chart_state.slices:
            piece = series.append(slice_state.label, float(slice_state.value))
            piece.setColor(QColor(slice_state.color))
        if on_clicked is not None:
            series.clicked.connect(on_clicked)
        chart.addSeries(series)
        chart_view.setChart(chart)

    def set_report_payload(self, payload: dict[str, Any]) -> None:
        self._current_report_payload = payload
        txs = payload.get("transactions") if isinstance(payload, dict) else None
        if isinstance(txs, list):
            period = (payload or {}).get("period") or {}
            year = int(period.get("year") or self._from_date.date().year())
            self._category_drill_root = None
            self._tx_page = 0
            self._set_loaded_state(self._service.build_state_from_transactions(txs, year=year))
            self._report_has_loaded_data = True
            self._report_dirty = False
            self._set_report_status(
                tr("reports.loaded.assistant", self._language, default="Reporte cargado desde el asistente."),
                color="#4EC9B0",
            )

        summary = (payload or {}).get("summary") or {}
        preset = ((payload or {}).get("period") or {}).get("preset") or tr(
            "reports.summary.default_period", self._language, default="selected period"
        )
        msg = tr(
            "reports.summary.template",
            self._language,
            default="Summary requested ({preset}). Income: {income} | Expense: {expense} | Net: {net}.",
            params={
                "preset": preset,
                "income": float(summary.get("total_income", 0.0)),
                "expense": float(summary.get("total_expenses", 0.0)),
                "net": float(summary.get("net", 0.0)),
            },
        )
        self.assistant_message_requested.emit(msg, tr("reports.title", self._language, default="MIRA Reports"))

    def set_report_type(self, index: int) -> None:
        """Public helper used by the main menu to switch report type."""
        if index < 0 or index >= self._report_type.count():
            return
        if self._report_type.currentIndex() != index:
            self._report_type.setCurrentIndex(index)
        else:
            self._report_stack.setCurrentIndex(index)
        if not self._report_has_loaded_data and index == self.REPORT_ACCOUNT_BALANCE:
            self._bind_account_balance_preview()
        if not self._report_has_loaded_data:
            self._mark_report_pending()

    def refresh(self) -> None:
        self._language = normalize_language(self._db.setting.get("language"))
        self._refresh_filter_options()
        if self._loaded_state is not None:
            self._rebuild_presentation_state()
        if self._report_dirty:
            if not self._report_has_loaded_data and self._report_type.currentIndex() == self.REPORT_ACCOUNT_BALANCE:
                self._bind_account_balance_preview()
            self._mark_report_pending()
            return
        if self._report_has_loaded_data:
            self._set_report_status(
                tr(
                    "reports.loaded.current",
                    self._language,
                    default="Mostrando el último reporte cargado. Pulsa Apply para actualizarlo.",
                ),
                color="#4EC9B0",
            )
            return
        if self._report_type.currentIndex() == self.REPORT_ACCOUNT_BALANCE:
            self._bind_account_balance_preview()
        self._mark_report_pending()


# ---------------------------------------------------------------------------
# Recurring apply period dialog
# ---------------------------------------------------------------------------
