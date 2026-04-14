# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""MIRA analysis feature view."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, cast

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)
from PySide6.QtCore import QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mira.app.view_services import (
    MiraAnalysisDrilldownRow,
    MiraAnalysisMessageBuilder,
    MiraAnalysisService,
    MiraAnalysisViewState,
    MiraAnalysisViewStateBuilder,
)
from mira.app.view_services._common import ANALYTICS_PALETTE, try_parse_waterfall_step_kind
from mira.db.database import Database
from mira.ui.i18n import normalize_language, tr
from mira.ui.views._shared import (
    _COMBO_STYLE,
    _TABLE_STYLE,
    _build_scrollable_container,
    _configure_chart_view,
    _fmt_amount,
    _make_toolbar_btn,
    _notify_warning,
    _section_title,
    _sub_title,
)
from mira.ui.widgets.cards import CardWidget


class _WaterfallChartWidget(QWidget):
    """Custom waterfall chart tuned for the MIRA master report narrative."""

    _COLORS = {
        "background": "#2A394A",
        "border": "#6E8198",
        "grid": "#40556F",
        "text": "#D6DEE8",
        "value_text": "#F5F7FA",
        "connector": "#88A9C3",
        "default": "#9FB3C8",
    }

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._steps: list[dict[str, Any]] = []
        self._empty_state_text = "No data available for the waterfall chart."
        self.setMinimumHeight(420)

    def set_steps(self, steps: list[dict[str, Any]]) -> None:
        self._steps = steps
        self.setMinimumHeight(420 if len(steps) <= 8 else 480 if len(steps) <= 10 else 540)
        self.update()

    def set_empty_state_text(self, text: str) -> None:
        self._empty_state_text = text
        self.update()

    def _bar_color(self, step: dict[str, Any]) -> QColor:
        if (kind := try_parse_waterfall_step_kind(step.get("kind"))) is None:
            return QColor(self._COLORS["default"])
        return QColor(ANALYTICS_PALETTE.waterfall_hex(kind))

    def _wrap_label(self, label: str) -> str:
        words = label.split()
        if len(words) <= 1:
            return label
        midpoint = max(1, len(words) // 2)
        return " ".join(words[:midpoint]) + "\n" + " ".join(words[midpoint:])

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        outer_rect = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        painter.setPen(QPen(QColor(self._COLORS["border"]), 1))
        painter.setBrush(QColor(self._COLORS["background"]))
        painter.drawRoundedRect(outer_rect, 12, 12)

        if not self._steps:
            painter.setPen(QColor(self._COLORS["text"]))
            painter.drawText(
                outer_rect.adjusted(20, 20, -20, -20),
                Qt.AlignmentFlag.AlignCenter,
                self._empty_state_text,
            )
            painter.end()
            return

        plot_rect = outer_rect.adjusted(56, 26, -22, -104)
        label_top = outer_rect.top() + 10
        label_bottom = plot_rect.bottom() + 16

        values = [0.0]
        for step in self._steps:
            start = float(step.get("start") or 0.0)
            end = float(step.get("end") or 0.0)
            baseline = step.get("baseline")
            values.extend([start, end])
            if baseline is not None:
                values.append(float(baseline))

        minimum = min(values)
        maximum = max(values)
        span = max(1.0, maximum - minimum)
        padding = max(1.0, span * 0.12)
        y_min = min(minimum - padding, -padding * 0.35)
        y_max = max(maximum + padding, padding * 0.35)

        def map_y(value: float) -> float:
            usable = max(1.0, y_max - y_min)
            ratio = (y_max - value) / usable
            return plot_rect.top() + ratio * plot_rect.height()

        zero_y = map_y(0.0)
        painter.setPen(QPen(QColor(self._COLORS["grid"]), 1))
        grid_steps = 5
        axis_decimals = (
            2
            if any(abs(value - round(value)) >= 0.005 for value in values) or max(abs(y_min), abs(y_max)) < 1000
            else 0
        )
        label_font = QFont()
        label_font.setPointSize(9)
        painter.setFont(label_font)
        for idx in range(grid_steps + 1):
            value = y_min + ((y_max - y_min) / grid_steps) * idx
            y_pos = map_y(value)
            painter.drawLine(
                int(round(plot_rect.left())),
                int(round(y_pos)),
                int(round(plot_rect.right())),
                int(round(y_pos)),
            )
            painter.setPen(QColor(self._COLORS["default"]))
            painter.drawText(
                QRectF(outer_rect.left() + 6, y_pos - 10, 44, 20),
                Qt.AlignmentFlag.AlignRight,
                _fmt_amount(self._db, value, decimals=axis_decimals),
            )
            painter.setPen(QPen(QColor(self._COLORS["grid"]), 1))

        painter.setPen(QPen(QColor(self._COLORS["text"]), 1.6))
        painter.drawLine(
            int(round(plot_rect.left())),
            int(round(zero_y)),
            int(round(plot_rect.right())),
            int(round(zero_y)),
        )

        count = max(1, len(self._steps))
        slot_width = plot_rect.width() / count
        bar_width = min(72.0, slot_width * 0.58)
        prev_end: float | None = None
        value_font = QFont()
        value_font.setPointSize(9)
        value_font.setBold(True)
        category_font = QFont()
        category_font.setPointSize(9)

        for idx, step in enumerate(self._steps):
            center_x = plot_rect.left() + (slot_width * idx) + (slot_width / 2.0)
            start = float(step.get("start") or 0.0)
            end = float(step.get("end") or 0.0)
            baseline = step.get("baseline")
            draw_start = float(baseline) if baseline is not None else start
            draw_end = end

            if prev_end is not None:
                painter.setPen(QPen(QColor(self._COLORS["connector"]), 1.2, Qt.PenStyle.DashLine))
                painter.drawLine(
                    int(round(center_x - slot_width / 2.0)),
                    int(round(map_y(prev_end))),
                    int(round(center_x - bar_width / 2.0)),
                    int(round(map_y(start))),
                )

            # When `baseline` exists we render a total/checkpoint bar between baseline and end,
            # while connectors still follow the logical flow carried in `start`.
            top_value = max(draw_start, draw_end)
            bottom_value = min(draw_start, draw_end)
            top_y = map_y(top_value)
            bottom_y = map_y(bottom_value)
            height = max(2.0, bottom_y - top_y)
            bar_rect = QRectF(center_x - bar_width / 2.0, top_y, bar_width, height)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._bar_color(step))
            painter.drawRoundedRect(bar_rect, 6, 6)

            painter.setFont(value_font)
            painter.setPen(QColor(self._COLORS["value_text"]))
            value = float(step.get("value") or 0.0)
            value_text = _fmt_amount(self._db, value)
            if value > 0:
                value_rect = QRectF(center_x - slot_width / 2.0, max(label_top, top_y - 28), slot_width, 20)
            elif value < 0:
                value_rect = QRectF(
                    center_x - slot_width / 2.0, min(plot_rect.bottom() - 10, bottom_y + 6), slot_width, 20
                )
            else:
                value_rect = QRectF(center_x - slot_width / 2.0, zero_y - 28, slot_width, 20)
            painter.drawText(value_rect, Qt.AlignmentFlag.AlignCenter, value_text)

            painter.setFont(category_font)
            painter.setPen(QColor(self._COLORS["text"]))
            label_rect = QRectF(
                center_x - slot_width / 2.0, label_bottom, slot_width, outer_rect.bottom() - label_bottom - 10
            )
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                self._wrap_label(str(step.get("label") or "")),
            )
            prev_end = end

        painter.end()


class _MiraAnalysisWorker(QThread):
    loaded = Signal(object, bool, int, int)
    failed = Signal(str)

    def __init__(
        self,
        service: MiraAnalysisService,
        *,
        year: int,
        month: int,
        emit_to_assistant: bool,
    ) -> None:
        super().__init__()
        self._service = service
        self._year = year
        self._month = month
        self._emit_to_assistant = emit_to_assistant

    def run(self) -> None:
        try:
            payload = self._service.load_payload(year=self._year, month=self._month)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.loaded.emit(payload, self._emit_to_assistant, self._year, self._month)


class MiraAnalysisView(QWidget):
    """Release-candidate MIRA master report workspace."""

    assistant_message_requested = Signal(str, str)

    _MONTHS = [
        ("01", "mira.analysis.month.jan", "Enero"),
        ("02", "mira.analysis.month.feb", "Febrero"),
        ("03", "mira.analysis.month.mar", "Marzo"),
        ("04", "mira.analysis.month.apr", "Abril"),
        ("05", "mira.analysis.month.may", "Mayo"),
        ("06", "mira.analysis.month.jun", "Junio"),
        ("07", "mira.analysis.month.jul", "Julio"),
        ("08", "mira.analysis.month.aug", "Agosto"),
        ("09", "mira.analysis.month.sep", "Septiembre"),
        ("10", "mira.analysis.month.oct", "Octubre"),
        ("11", "mira.analysis.month.nov", "Noviembre"),
        ("12", "mira.analysis.month.dec", "Diciembre"),
    ]

    def __init__(
        self,
        db: Database,
        parent: QWidget | None = None,
        service: MiraAnalysisService | None = None,
        message_builder: MiraAnalysisMessageBuilder | None = None,
        view_state_builder: MiraAnalysisViewStateBuilder | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._service = service or MiraAnalysisService(db)
        self._message_builder = message_builder or MiraAnalysisMessageBuilder(db)
        self._view_state_builder = view_state_builder or MiraAnalysisViewStateBuilder(db)
        self._language = normalize_language(self._db.setting.get("language"))
        self._payload: dict[str, Any] | None = None
        self._view_state: MiraAnalysisViewState | None = None
        self._worker: _MiraAnalysisWorker | None = None
        self._last_loaded_period: tuple[int, int] | None = None
        self._report_dirty = False
        self._category_rows: list[MiraAnalysisDrilldownRow] = []
        self._tag_rows: list[MiraAnalysisDrilldownRow] = []
        self._build_ui()

    def _t(self, key: str, default: str, *, params: dict[str, object] | None = None) -> str:
        return tr(key, self._language, default=default, params=params)

    def _set_analysis_status(self, text: str, *, color: str = "#9FB3C8") -> None:
        self._report_status_lbl.setText(text)
        self._report_status_lbl.setStyleSheet(f"font-size:11px;color:{color};padding:0 2px 4px 2px;")

    def _selected_period(self) -> tuple[int, int]:
        return int(self._year_spin.value()), int(self._month_combo.currentData() or 1)

    def _mark_report_pending(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._set_analysis_status(
                self._t("mira.analysis.status.loading", "Analizando tus datos…"),
                color="#F7C16B",
            )
            return
        if self._payload is None:
            self._report_dirty = False
            self._set_analysis_status(
                self._t(
                    "mira.analysis.idle_hint",
                    "La vista está lista. Pulsa 'Actualizar reporte' para consultar el análisis MIRA.",
                )
            )
            return
        current_period = self._selected_period()
        self._report_dirty = current_period != self._last_loaded_period
        if self._report_dirty:
            self._set_analysis_status(
                self._t(
                    "mira.analysis.pending",
                    "El período cambió. Se muestra el último análisis cargado hasta que pulses 'Actualizar reporte'.",
                )
            )
            return
        self._set_analysis_status(
            self._t(
                "mira.analysis.loaded",
                "Mostrando el último análisis cargado. Puedes actualizarlo cuando quieras.",
            ),
            color="#4EC9B0",
        )

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(20, 16, 20, 16)
        outer_layout.setSpacing(10)

        outer_layout.addWidget(_section_title(self._t("mira.analysis.title", "📈 Análisis MIRA")))

        self._report_scroll, _content, layout = _build_scrollable_container(self)
        outer_layout.addWidget(self._report_scroll, 1)

        filters_row = QHBoxLayout()
        filters_row.addWidget(QLabel(self._t("mira.analysis.filter.month", "Mes:")))
        self._month_combo = QComboBox()
        self._month_combo.setStyleSheet(_COMBO_STYLE)
        for code, key, fallback in self._MONTHS:
            self._month_combo.addItem(self._t(key, fallback), int(code))
        filters_row.addWidget(self._month_combo)

        filters_row.addWidget(QLabel(self._t("mira.analysis.filter.year", "Año:")))
        self._year_spin = QSpinBox()
        self._year_spin.setRange(1900, 9999)
        self._year_spin.setStyleSheet("QSpinBox{border:1px solid palette(mid);border-radius:3px;padding:3px 8px;}")
        filters_row.addWidget(self._year_spin)

        self._btn_apply = _make_toolbar_btn(self._t("mira.analysis.update", "Actualizar reporte"))
        self._btn_apply.clicked.connect(self._on_apply_report)
        filters_row.addWidget(self._btn_apply)
        filters_row.addStretch()
        layout.addLayout(filters_row)

        self._report_status_lbl = QLabel("")
        self._report_status_lbl.setWordWrap(True)
        layout.addWidget(self._report_status_lbl)

        layout.addWidget(_sub_title(self._t("mira.analysis.waterfall", "Flujo del ingreso en cascada")))
        self._waterfall_chart = _WaterfallChartWidget(self._db, self)
        self._waterfall_chart.set_empty_state_text(
            self._t(
                "mira.analysis.waterfall.no_data",
                "No hay datos suficientes para graficar la cascada.",
            )
        )
        layout.addWidget(self._waterfall_chart, 2)

        self._waterfall_legend = QLabel("")
        self._waterfall_legend.setWordWrap(True)
        self._waterfall_legend.setStyleSheet("color:#D6DEE8;font-size:11px;padding:0 2px 0 2px;")
        layout.addWidget(self._waterfall_legend)

        self._waterfall_summary = QLabel(
            self._t(
                "mira.analysis.waterfall.empty",
                "Actualiza el reporte para ver cómo el ingreso fluye hacia gastos, ahorro o financiamiento.",
            )
        )
        self._waterfall_summary.setWordWrap(True)
        self._waterfall_summary.setStyleSheet("color:#D6DEE8;font-size:12px;padding:4px 2px 10px 2px;")
        layout.addWidget(self._waterfall_summary)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self._income_card = CardWidget(self._t("dashboard.card.income", "Ingreso"), "0.00", "#4EC9B0")
        self._expense_card = CardWidget(self._t("dashboard.card.expense", "Gasto"), "0.00", "#F48771")
        self._balance_card = CardWidget(self._t("dashboard.card.net", "Balance"), "0.00", "#D6DEE8")
        self._savings_card = CardWidget(self._t("dashboard.card.savings", "Ahorro"), "0.00", "#86A9FF")
        for card in [
            self._income_card,
            self._expense_card,
            self._balance_card,
            self._savings_card,
        ]:
            card.setMinimumHeight(152)
            kpi_row.addWidget(card)
        layout.addLayout(kpi_row)

        layout.addWidget(_sub_title(self._t("mira.analysis.ytd", "Tendencia acumulada YTD")))
        self._ytd_chart = QChartView()
        _configure_chart_view(self._ytd_chart, minimum_height=380)
        layout.addWidget(self._ytd_chart, 2)

        tables_row = QHBoxLayout()
        tables_row.setSpacing(12)

        categories_panel = QVBoxLayout()
        categories_panel.addWidget(_sub_title(self._t("mira.analysis.top_categories", "Top 5 gastos por categoría")))
        self._top_categories_table = QTableWidget(0, 2)
        self._top_categories_table.setHorizontalHeaderLabels(
            [
                self._t("reports.col.category", "Categoría"),
                self._t("reports.col.amount", "Monto"),
            ]
        )
        self._configure_summary_table(self._top_categories_table)
        self._top_categories_table.setMinimumHeight(220)
        self._top_categories_table.cellClicked.connect(self._on_top_category_selected)
        categories_panel.addWidget(self._top_categories_table, 1)

        self._category_detail_title = QLabel(
            self._t(
                "mira.analysis.category_detail.empty",
                "Selecciona una categoría para ver el desglose.",
            )
        )
        self._category_detail_title.setWordWrap(True)
        categories_panel.addWidget(self._category_detail_title)

        self._category_detail_table = QTableWidget(0, 2)
        self._category_detail_table.setHorizontalHeaderLabels(
            [
                self._t("mira.analysis.col.detail", "Detalle"),
                self._t("reports.col.amount", "Monto"),
            ]
        )
        self._configure_summary_table(self._category_detail_table)
        self._category_detail_table.setMinimumHeight(220)
        categories_panel.addWidget(self._category_detail_table, 1)
        tables_row.addLayout(categories_panel, 1)

        tags_panel = QVBoxLayout()
        tags_panel.addWidget(_sub_title(self._t("mira.analysis.top_tags", "Top 5 gastos por etiqueta")))
        self._top_tags_table = QTableWidget(0, 2)
        self._top_tags_table.setHorizontalHeaderLabels(
            [
                self._t("mira.analysis.col.tag", "Etiqueta"),
                self._t("reports.col.amount", "Monto"),
            ]
        )
        self._configure_summary_table(self._top_tags_table)
        self._top_tags_table.setMinimumHeight(220)
        self._top_tags_table.cellClicked.connect(self._on_top_tag_selected)
        tags_panel.addWidget(self._top_tags_table, 1)

        self._tag_detail_title = QLabel(
            self._t(
                "mira.analysis.tag_detail.empty",
                "Selecciona una etiqueta para ver su composición.",
            )
        )
        self._tag_detail_title.setWordWrap(True)
        tags_panel.addWidget(self._tag_detail_title)

        self._tag_detail_table = QTableWidget(0, 2)
        self._tag_detail_table.setHorizontalHeaderLabels(
            [
                self._t("mira.analysis.col.detail", "Detalle"),
                self._t("reports.col.amount", "Monto"),
            ]
        )
        self._configure_summary_table(self._tag_detail_table)
        self._tag_detail_table.setMinimumHeight(220)
        tags_panel.addWidget(self._tag_detail_table, 1)
        tables_row.addLayout(tags_panel, 1)
        layout.addLayout(tables_row, 2)

        trend_controls = QHBoxLayout()
        trend_controls.addWidget(_sub_title(self._t("mira.analysis.trend", "Tendencia de tiempo")))
        trend_controls.addSpacing(12)
        trend_controls.addWidget(QLabel(self._t("mira.analysis.view", "Ver:")))
        self._trend_switch = QComboBox()
        self._trend_switch.setStyleSheet(_COMBO_STYLE)
        self._trend_switch.setMaximumWidth(140)
        self._trend_switch.addItem(self._t("dashboard.card.income", "Ingresos"), "income")
        self._trend_switch.addItem(self._t("dashboard.card.expense", "Gastos"), "expense")
        self._trend_switch.currentIndexChanged.connect(self._render_trend_chart)
        trend_controls.addWidget(self._trend_switch)
        trend_controls.addStretch()
        layout.addLayout(trend_controls)

        self._trend_chart = QChartView()
        _configure_chart_view(self._trend_chart, minimum_height=380)
        layout.addWidget(self._trend_chart, 2)
        layout.addStretch()

        today = date.today()
        self._month_combo.setCurrentIndex(max(0, min(11, today.month - 1)))
        self._year_spin.setValue(today.year)
        self._month_combo.currentIndexChanged.connect(lambda _index: self._mark_report_pending())
        self._year_spin.valueChanged.connect(lambda _value: self._mark_report_pending())
        self._mark_report_pending()

    def _configure_summary_table(self, table: QTableWidget) -> None:
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setStyleSheet(_TABLE_STYLE)

    def _set_table_rows(self, table: QTableWidget, rows: list[Any] | tuple[Any, ...]) -> None:
        table.clearContents()
        table.setRowCount(len(rows))
        for idx, row in enumerate(rows):
            name_item = QTableWidgetItem(str(getattr(row, "name", "")))
            table.setItem(idx, 0, name_item)
            table.setItem(idx, 1, QTableWidgetItem(str(getattr(row, "amount_text", ""))))

    def _clear_category_drilldown(self) -> None:
        title = (
            self._view_state.categories.empty_title
            if self._view_state is not None
            else self._t("mira.analysis.category_detail.empty", "Selecciona una categoría para ver el desglose.")
        )
        self._category_detail_title.setText(title)
        self._category_detail_table.clearContents()
        self._category_detail_table.setRowCount(0)

    def _clear_tag_drilldown(self) -> None:
        title = (
            self._view_state.tags.empty_title
            if self._view_state is not None
            else self._t("mira.analysis.tag_detail.empty", "Selecciona una etiqueta para ver su composición.")
        )
        self._tag_detail_title.setText(title)
        self._tag_detail_table.clearContents()
        self._tag_detail_table.setRowCount(0)

    def _on_top_category_selected(self, row: int, _column: int) -> None:
        if row < 0 or row >= len(self._category_rows):
            self._clear_category_drilldown()
            return
        selected = self._category_rows[row]
        self._category_detail_title.setText(selected.detail_title)
        self._set_table_rows(self._category_detail_table, selected.detail_rows)

    def _on_top_tag_selected(self, row: int, _column: int) -> None:
        if row < 0 or row >= len(self._tag_rows):
            self._clear_tag_drilldown()
            return
        selected = self._tag_rows[row]
        self._tag_detail_title.setText(selected.detail_title)
        self._set_table_rows(self._tag_detail_table, selected.detail_rows)

    def _build_context_message(self) -> str:
        return self._message_builder.build_context_message(self._payload or {}, language=self._language)

    def _render_ytd_chart(self) -> None:
        if self._view_state is None:
            return
        chart = QChart()
        chart.setTitle(self._view_state.ytd_chart.title)
        chart.setBackgroundVisible(False)
        labels = list(self._view_state.ytd_chart.labels)
        qt_series: list[QLineSeries] = []
        for series_state in self._view_state.ytd_chart.series:
            series = QLineSeries()
            series.setName(series_state.name)
            series.setColor(QColor(series_state.color))
            for x_value, y_value in series_state.points:
                series.append(float(x_value), float(y_value))
            chart.addSeries(series)
            qt_series.append(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(labels)
        axis_y = QValueAxis()
        axis_y.setLabelFormat("%.0f")
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        for series in qt_series:
            series.attachAxis(axis_x)
            series.attachAxis(axis_y)

        self._ytd_chart.setChart(chart)

    def _render_waterfall_chart(self) -> None:
        if self._view_state is None:
            return
        self._waterfall_chart.set_steps([step.as_dict() for step in self._view_state.waterfall.steps])
        self._waterfall_legend.setText(self._view_state.waterfall.legend_html)
        self._waterfall_summary.setText(self._view_state.waterfall.summary_text)

    def _render_trend_chart(self) -> None:
        if self._view_state is None:
            return
        chart = QChart()
        section = str(self._trend_switch.currentData() or "income")
        chart_state = self._view_state.trend_charts.get(section)
        if chart_state is None:
            return
        chart.setTitle(chart_state.title)
        chart.setBackgroundVisible(False)

        series = QBarSeries()
        for series_state in chart_state.series:
            bar = QBarSet(series_state.name)
            bar.setColor(QColor(series_state.color))
            for value in series_state.values:
                bar.append(float(value))
            series.append(bar)

        chart.addSeries(series)
        axis_x = QBarCategoryAxis()
        axis_x.append(list(chart_state.labels))
        axis_y = QValueAxis()
        axis_y.setLabelFormat("%.0f")
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)

        self._trend_chart.setChart(chart)

    def _emit_context_to_assistant(self) -> None:
        for message, title in self._message_builder.build_assistant_messages(
            self._payload or {}, language=self._language
        ):
            self.assistant_message_requested.emit(message, title)

    def _emit_advisor_to_assistant(self) -> None:
        return

    def _emit_report_to_assistant(self) -> None:
        self._emit_context_to_assistant()

    def _bind_card(self, card: CardWidget, state: Any) -> None:
        card.set_value(state.value)
        card.set_color(state.color)
        card.set_context(
            state.primary_text,
            primary_color=state.primary_color,
            secondary=state.secondary_text,
            secondary_color=state.secondary_color,
        )

    def _render_payload(self) -> None:
        if self._payload is None:
            self._view_state = None
            return

        self._view_state = self._view_state_builder.build_state(self._payload)
        self._bind_card(self._income_card, self._view_state.income_card)
        self._bind_card(self._expense_card, self._view_state.expense_card)
        self._bind_card(self._balance_card, self._view_state.balance_card)
        self._bind_card(self._savings_card, self._view_state.savings_card)

        self._category_rows = list(self._view_state.categories.top_rows)
        self._tag_rows = list(self._view_state.tags.top_rows)
        self._set_table_rows(self._top_categories_table, self._category_rows)
        self._set_table_rows(self._top_tags_table, self._tag_rows)
        if self._category_rows:
            self._top_categories_table.selectRow(0)
            self._on_top_category_selected(0, 0)
        else:
            self._clear_category_drilldown()
        if self._tag_rows:
            self._top_tags_table.selectRow(0)
            self._on_top_tag_selected(0, 0)
        else:
            self._clear_tag_drilldown()

        self._render_ytd_chart()
        self._render_waterfall_chart()
        self._render_trend_chart()

    def _on_apply_report(self) -> None:
        self._load_report(emit_to_assistant=True)

    def run_report(self, *, emit_to_assistant: bool = False) -> None:
        self._load_report(emit_to_assistant=emit_to_assistant)

    def has_loaded_report(self) -> bool:
        return self._payload is not None

    def set_requested_period(self, period: dict[str, Any] | None) -> None:
        if not isinstance(period, dict):
            return

        preset = str(period.get("preset") or "").strip().lower()
        target_date = date.today()
        if preset == "last_month":
            target_date = target_date.replace(day=1) - timedelta(days=1)
        elif preset == "custom":
            candidate = str(period.get("to") or period.get("from") or "").strip()
            if candidate:
                try:
                    target_date = date.fromisoformat(candidate)
                except ValueError:
                    target_date = date.today()

        month_index = max(0, min(11, target_date.month - 1))
        self._month_combo.setCurrentIndex(month_index)
        self._year_spin.setValue(target_date.year)

    def _load_report(self, *, emit_to_assistant: bool) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._set_analysis_status(
                self._t("mira.analysis.status.loading", "Analizando tus datos…"),
                color="#F7C16B",
            )
            return
        year, month = self._selected_period()
        self._btn_apply.setEnabled(False)
        self._set_analysis_status(
            self._t("mira.analysis.status.loading", "Analizando tus datos…"),
            color="#F7C16B",
        )
        self._worker = _MiraAnalysisWorker(
            self._service,
            year=year,
            month=month,
            emit_to_assistant=emit_to_assistant,
        )
        self._worker.loaded.connect(self._on_report_loaded, Qt.ConnectionType.QueuedConnection)
        self._worker.failed.connect(self._on_report_error, Qt.ConnectionType.QueuedConnection)
        self._worker.finished.connect(self._on_report_finished, Qt.ConnectionType.QueuedConnection)
        self._worker.start()

    def _stop_worker(self) -> None:
        """Disconnect signals and wait for the running worker to finish.

        The worker is created fresh in ``_load_report`` and only this view
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

    def closeEvent(self, event: object) -> None:  # type: ignore[override]
        self._stop_worker()
        super().closeEvent(event)  # type: ignore[misc]

    def _on_report_loaded(self, payload: object, emit_to_assistant: bool, year: int, month: int) -> None:
        self._payload = cast(dict[str, Any], payload)
        self._last_loaded_period = (year, month)
        self._report_dirty = False
        self._render_payload()
        self._set_analysis_status(
            self._t("mira.analysis.status.loaded", "Analisis MIRA cargado."),
            color="#4EC9B0",
        )
        # Ensure the waterfall chart (top of the report) is visible after loading.
        QTimer.singleShot(0, lambda: self._report_scroll.verticalScrollBar().setValue(0))
        if emit_to_assistant:
            self._emit_report_to_assistant()

    def _on_report_error(self, message: str) -> None:
        _notify_warning(self, self._t("mira.analysis.dialog_title", "Análisis MIRA"), message)
        self._set_analysis_status(message, color="#F48771")

    def _on_report_finished(self) -> None:
        self._btn_apply.setEnabled(True)
        self._worker = None
        if self._payload is not None:
            self._mark_report_pending()

    def refresh(self) -> None:
        self._language = normalize_language(self._db.setting.get("language"))
        if self._payload is not None:
            self._render_payload()
        self._mark_report_pending()


# ---------------------------------------------------------------------------
# ReportsView
# ---------------------------------------------------------------------------
