# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Loan amortization utility dialog."""

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

from mira.finance.enums import AmortizationMethod, PaymentFrequency
from mira.finance.loan_amortization import LoanAmortizationInput, calculate_loan_amortization
from mira.ui.i18n import tr


class LoanAmortizationDialog(QDialog):
    """Loan amortization calculator."""

    def __init__(self, language: str, currency: str, parent: QWidget | None = None) -> None:
        """Initialize the LoanAmortizationDialog instance."""
        super().__init__(parent)
        self._language = language
        self._currency = currency.strip().upper() or "USD"
        self.setWindowTitle(
            tr(
                "tools.loan_amortization.title",
                self._language,
                default="Loan Calculator",
            )
        )
        self.resize(1080, 760)
        self._build_ui()
        self._recalculate()

    def _build_ui(self) -> None:
        """Return build ui."""
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

        self._loan_amount = QDoubleSpinBox()
        self._loan_amount.setRange(0.01, 1_000_000_000_000.0)
        self._loan_amount.setDecimals(2)
        self._loan_amount.setValue(10_000.0)
        form.addRow(tr("tools.loan_amortization.loan_amount", self._language, default="Loan amount"), self._loan_amount)

        self._annual_rate = QDoubleSpinBox()
        self._annual_rate.setRange(0.0, 1000.0)
        self._annual_rate.setDecimals(4)
        self._annual_rate.setSuffix(" %")
        self._annual_rate.setValue(12.0)
        form.addRow(tr("tools.loan_amortization.annual_rate", self._language, default="Annual rate"), self._annual_rate)

        self._frequency = QComboBox()
        for freq in PaymentFrequency:
            self._frequency.addItem(
                tr(f"tools.freq.{freq.name.lower()}", self._language, default=freq.name.capitalize()),
                freq,
            )
        form.addRow(
            tr("tools.loan_amortization.frequency", self._language, default="Payment frequency"), self._frequency
        )

        self._years = QDoubleSpinBox()
        self._years.setRange(0.01, 50.0)
        self._years.setDecimals(2)
        self._years.setValue(5.0)
        form.addRow(tr("tools.loan_amortization.years", self._language, default="Term (years)"), self._years)

        self._method = QComboBox()
        for method in AmortizationMethod:
            self._method.addItem(
                tr(f"tools.loan.method.{method.value}", self._language, default=method.value.capitalize()),
                method,
            )
        form.addRow(tr("tools.loan_amortization.method", self._language, default="Amortization method"), self._method)
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
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels(
            [
                tr("tools.loan_amortization.col.period", self._language, default="Period"),
                tr("tools.loan_amortization.col.label", self._language, default="Label"),
                tr("tools.loan_amortization.col.initial_balance", self._language, default="Initial balance"),
                tr("tools.loan_amortization.col.payment", self._language, default="Payment"),
                tr("tools.loan_amortization.col.interest", self._language, default="Interest"),
                tr("tools.loan_amortization.col.amortization", self._language, default="Amortization"),
                tr("tools.loan_amortization.col.final_balance", self._language, default="Ending balance"),
                tr("tools.loan_amortization.col.cumulative_interest", self._language, default="Cumulative interest"),
                tr("tools.loan_amortization.col.cumulative_principal", self._language, default="Cumulative principal"),
            ]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setMinimumHeight(260)
        content_layout.addWidget(self._table)

        for widget in (self._loan_amount, self._annual_rate, self._frequency, self._years, self._method):
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._recalculate)
            else:
                widget.valueChanged.connect(self._recalculate)

    def _recalculate(self) -> None:
        """Return recalculate."""
        projection = calculate_loan_amortization(
            LoanAmortizationInput(
                loan_amount=self._loan_amount.value(),
                annual_rate_percent=self._annual_rate.value(),
                payment_frequency=self._frequency.currentData(),
                years=self._years.value(),
                method=self._method.currentData(),
            )
        )

        self._summary.setText(
            tr(
                "tools.loan_amortization.summary",
                self._language,
                default="Initial payment: {payment_initial} | Final payment: {payment_final} | Total paid: {total_paid} | Total interest: {total_interest}",
                params={
                    "payment_initial": self._fmt_currency(projection.payment_initial),
                    "payment_final": self._fmt_currency(projection.payment_final),
                    "total_paid": self._fmt_currency(projection.total_paid),
                    "total_interest": self._fmt_currency(projection.total_interest),
                },
            )
        )

        if projection.method == AmortizationMethod.FRENCH:
            self._message.setText(
                tr(
                    "tools.loan_amortization.message.french",
                    self._language,
                    default="Your payment will be almost constant. At first you pay more interest and toward the end you amortize more principal.",
                )
            )
        else:
            self._message.setText(
                tr(
                    "tools.loan_amortization.message.german",
                    self._language,
                    default="Your principal amortization is constant and payments decrease over time as the balance falls.",
                )
            )

        self._table.setRowCount(len(projection.rows))
        for row_index, row in enumerate(projection.rows):
            cells = [
                str(row.period),
                row.label,
                self._fmt_currency(row.initial_balance),
                self._fmt_currency(row.payment),
                self._fmt_currency(row.interest),
                self._fmt_currency(row.principal_amortization),
                self._fmt_currency(row.ending_balance),
                self._fmt_currency(row.cumulative_interest),
                self._fmt_currency(row.cumulative_principal),
            ]
            for col, value in enumerate(cells):
                self._table.setItem(row_index, col, QTableWidgetItem(value))

        chart = QChart()
        chart.legend().setVisible(True)
        chart.setTitle(tr("tools.loan_amortization.chart.title", self._language, default="Loan evolution"))

        series_balance = QLineSeries()
        series_balance.setName(
            tr("tools.loan_amortization.chart.balance", self._language, default="Outstanding balance")
        )
        series_interest = QLineSeries()
        series_interest.setName(tr("tools.loan_amortization.chart.interest", self._language, default="Interest"))
        series_principal = QLineSeries()
        series_principal.setName(
            tr("tools.loan_amortization.chart.principal", self._language, default="Principal amortization")
        )

        for row in projection.rows:
            period = float(row.period)
            series_balance.append(period, row.ending_balance)
            series_interest.append(period, row.interest)
            series_principal.append(period, row.principal_amortization)

        axis_x = QValueAxis()
        axis_x.setLabelFormat("%.0f")
        axis_x.setTitleText(tr("tools.loan_amortization.chart.axis_x", self._language, default="Periods"))
        axis_x.setRange(1.0, float(max(1, projection.total_periods)))
        axis_y = QValueAxis()
        axis_y.setLabelFormat("%.2f")
        axis_y.setTitleText(tr("tools.loan_amortization.chart.axis_y", self._language, default="Amount"))

        chart.addSeries(series_balance)
        chart.addSeries(series_interest)
        chart.addSeries(series_principal)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        for series in (series_balance, series_interest, series_principal):
            series.attachAxis(axis_x)
            series.attachAxis(axis_y)

        self._chart_view.setChart(chart)

    def _fmt_currency(self, value: float) -> str:
        """Return fmt currency."""
        return f"{self._currency} {value:,.2f}"
