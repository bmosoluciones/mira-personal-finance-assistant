# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Compound interest utility dialog."""

from __future__ import annotations

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mira.finance.compound_interest import CompoundInterestInput, calculate_compound_interest_projection
from mira.finance.enums import PaymentFrequency
from mira.ui.i18n import tr


class CompoundInterestDialog(QDialog):
    """Compound interest calculator for personal finance scenarios."""

    def __init__(self, language: str, currency: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._language = language
        self._currency = currency.strip().upper() or "USD"
        self.setWindowTitle(
            tr(
                "tools.compound_interest.title",
                self._language,
                default="Compound Interest Calculator",
            )
        )
        self.resize(980, 760)
        self._build_ui()
        self._recalculate()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(scroll)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(10)
        scroll.setWidget(content)

        self._message = QLabel()
        self._message.setWordWrap(True)
        self._message.setStyleSheet("color:#9FB3C8;")
        content_layout.addWidget(self._message)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self._initial_fund = QDoubleSpinBox()
        self._initial_fund.setRange(0.0, 1_000_000_000_000.0)
        self._initial_fund.setDecimals(2)
        form.addRow(
            tr("tools.compound_interest.initial_fund", self._language, default="Initial fund"), self._initial_fund
        )

        self._annual_rate = QDoubleSpinBox()
        self._annual_rate.setRange(0.0, 1000.0)
        self._annual_rate.setDecimals(4)
        self._annual_rate.setSuffix(" %")
        self._annual_rate.setValue(5.0)
        form.addRow(tr("tools.compound_interest.annual_rate", self._language, default="Annual rate"), self._annual_rate)

        self._capitalization = QComboBox()
        for freq in PaymentFrequency:
            self._capitalization.addItem(
                tr(f"tools.freq.{freq.name.lower()}", self._language, default=freq.name.capitalize()),
                freq,
            )
        form.addRow(
            tr("tools.compound_interest.capitalization", self._language, default="Compounding frequency"),
            self._capitalization,
        )

        self._years = QDoubleSpinBox()
        self._years.setRange(0.01, 100.0)
        self._years.setDecimals(2)
        self._years.setValue(10.0)
        form.addRow(tr("tools.compound_interest.years", self._language, default="Term (years)"), self._years)

        self._periodic_contribution = QDoubleSpinBox()
        self._periodic_contribution.setRange(0.0, 1_000_000_000_000.0)
        self._periodic_contribution.setDecimals(2)
        form.addRow(
            tr(
                "tools.compound_interest.periodic_contribution",
                self._language,
                default="Additional contribution per period",
            ),
            self._periodic_contribution,
        )
        content_layout.addLayout(form)

        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet("font-weight:600;")
        content_layout.addWidget(self._summary)

        self._chart_view = QChartView()
        self._chart_view.setMinimumHeight(250)
        content_layout.addWidget(self._chart_view)

        self._table = QTableWidget()
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            [
                tr("tools.compound_interest.col.period", self._language, default="Period"),
                tr("tools.compound_interest.col.label", self._language, default="Label"),
                tr("tools.compound_interest.col.initial_balance", self._language, default="Initial balance"),
                tr("tools.compound_interest.col.interest", self._language, default="Interest"),
                tr("tools.compound_interest.col.contribution", self._language, default="Contribution"),
                tr("tools.compound_interest.col.final_balance", self._language, default="Final balance"),
                tr(
                    "tools.compound_interest.col.cumulative_contribution",
                    self._language,
                    default="Cumulative contribution",
                ),
                tr("tools.compound_interest.col.cumulative_interest", self._language, default="Cumulative interest"),
            ]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setMinimumHeight(260)
        content_layout.addWidget(self._table)

        for widget in (
            self._initial_fund,
            self._annual_rate,
            self._capitalization,
            self._years,
            self._periodic_contribution,
        ):
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._recalculate)
            else:
                widget.valueChanged.connect(self._recalculate)

    def _recalculate(self) -> None:
        projection = calculate_compound_interest_projection(
            CompoundInterestInput(
                initial_fund=self._initial_fund.value(),
                annual_rate_percent=self._annual_rate.value(),
                capitalization=self._capitalization.currentData(),
                years=self._years.value(),
                periodic_contribution=self._periodic_contribution.value(),
            )
        )

        contribution_share = (
            0.0 if projection.final_balance == 0 else (projection.interest_earned / projection.final_balance) * 100
        )
        self._summary.setText(
            tr(
                "tools.compound_interest.summary",
                self._language,
                default="Final amount: {final} | Own capital: {principal} | Interest earned: {interest} ({share:.2f}% of total)",
                params={
                    "final": self._fmt_currency(projection.final_balance),
                    "principal": self._fmt_currency(projection.own_capital),
                    "interest": self._fmt_currency(projection.interest_earned),
                    "share": contribution_share,
                },
            )
        )
        self._message.setText(
            tr(
                "tools.compound_interest.message",
                self._language,
                default="In this scenario you would contribute {contribution} and end up with {final}. If you invest instead of spending, the opportunity cost would be {final}.",
                params={
                    "contribution": self._fmt_currency(projection.total_contributed - projection.initial_fund),
                    "final": self._fmt_currency(projection.final_balance),
                },
            )
        )

        self._table.setRowCount(len(projection.rows))
        for row_index, row in enumerate(projection.rows):
            cells = [
                str(row.period),
                row.label,
                self._fmt_currency(row.initial_balance),
                self._fmt_currency(row.interest),
                self._fmt_currency(row.periodic_contribution),
                self._fmt_currency(row.final_balance),
                self._fmt_currency(row.cumulative_contribution),
                self._fmt_currency(row.cumulative_interest),
            ]
            for col, value in enumerate(cells):
                self._table.setItem(row_index, col, QTableWidgetItem(value))

        chart = QChart()
        chart.legend().setVisible(True)
        chart.setTitle(tr("tools.compound_interest.chart.title", self._language, default="Capital growth"))

        series_balance = QLineSeries()
        series_balance.setName(
            tr("tools.compound_interest.chart.balance", self._language, default="Cumulative balance")
        )
        series_contribution = QLineSeries()
        series_contribution.setName(
            tr("tools.compound_interest.chart.contribution", self._language, default="Contributed capital")
        )
        series_interest = QLineSeries()
        series_interest.setName(
            tr("tools.compound_interest.chart.interest", self._language, default="Cumulative interest")
        )

        for row in projection.rows:
            period = float(row.period)
            series_balance.append(period, row.final_balance)
            series_contribution.append(period, row.cumulative_contribution)
            series_interest.append(period, row.cumulative_interest)

        axis_x = QValueAxis()
        axis_x.setLabelFormat("%.0f")
        axis_x.setTitleText(tr("tools.compound_interest.chart.axis_x", self._language, default="Periods"))
        axis_x.setRange(1.0, float(max(1, projection.total_periods)))
        axis_y = QValueAxis()
        axis_y.setLabelFormat("%.2f")
        axis_y.setTitleText(tr("tools.compound_interest.chart.axis_y", self._language, default="Cumulative amount"))

        chart.addSeries(series_balance)
        chart.addSeries(series_contribution)
        chart.addSeries(series_interest)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        for series in (series_balance, series_contribution, series_interest):
            series.attachAxis(axis_x)
            series.attachAxis(axis_y)

        self._chart_view.setChart(chart)

    def _fmt_currency(self, value: float) -> str:
        return f"{self._currency} {value:,.2f}"
