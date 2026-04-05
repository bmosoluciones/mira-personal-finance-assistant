# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Savings goal simulator dialog."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mira.finance.enums import PaymentFrequency
from mira.finance.savings_goal_simulator import SavingsGoalSimulation, SavingsGoalSimulationInput, simulate_savings_goal
from mira.ui.i18n import tr
from mira.ui.notifications import show_user_message


class GoalScenarioDialog(QDialog):
    """Simulate savings scenarios and optionally open the goal creation flow."""

    def __init__(self, language: str, currency: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._language = language
        self._currency = currency.strip().upper() or "USD"
        self._request_open_goal_form = False
        self._goal_prefill: dict[str, object] | None = None
        self.setWindowTitle(
            tr(
                "tools.goal_simulator.title",
                self._language,
                default="Savings Goal Simulator",
            )
        )
        self.resize(1080, 780)
        self._latest: SavingsGoalSimulation | None = None
        self._build_ui()
        self._recalculate()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        self._message = QLabel()
        self._message.setWordWrap(True)
        self._message.setStyleSheet("color:#9FB3C8;")
        root.addWidget(self._message)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self._target_amount = QDoubleSpinBox()
        self._target_amount.setRange(0.01, 1_000_000_000_000.0)
        self._target_amount.setDecimals(2)
        self._target_amount.setValue(5000.0)
        form.addRow(
            tr("tools.goal_simulator.target_amount", self._language, default="Target amount"), self._target_amount
        )

        self._years = QDoubleSpinBox()
        self._years.setRange(0.01, 100.0)
        self._years.setDecimals(2)
        self._years.setValue(2.0)
        form.addRow(tr("tools.goal_simulator.years", self._language, default="Term (years)"), self._years)

        self._frequency = QComboBox()
        for freq in PaymentFrequency:
            self._frequency.addItem(
                tr(f"tools.freq.{freq.name.lower()}", self._language, default=freq.name.capitalize()),
                freq,
            )
        form.addRow(tr("tools.goal_simulator.frequency", self._language, default="Savings frequency"), self._frequency)

        self._initial_amount = QDoubleSpinBox()
        self._initial_amount.setRange(0.0, 1_000_000_000_000.0)
        self._initial_amount.setDecimals(2)
        self._initial_amount.setValue(0.0)
        form.addRow(
            tr("tools.goal_simulator.initial_amount", self._language, default="Initial amount"), self._initial_amount
        )

        self._annual_rate = QDoubleSpinBox()
        self._annual_rate.setRange(0.0, 1000.0)
        self._annual_rate.setDecimals(4)
        self._annual_rate.setSuffix(" %")
        self._annual_rate.setValue(0.0)
        form.addRow(
            tr("tools.goal_simulator.annual_rate", self._language, default="Estimated annual rate"), self._annual_rate
        )

        self._auto_contribution = QCheckBox(
            tr(
                "tools.goal_simulator.auto_contribution",
                self._language,
                default="Calculate required contribution automatically",
            )
        )
        self._auto_contribution.setChecked(True)
        form.addRow("", self._auto_contribution)

        self._periodic_contribution = QDoubleSpinBox()
        self._periodic_contribution.setRange(0.0, 1_000_000_000_000.0)
        self._periodic_contribution.setDecimals(2)
        self._periodic_contribution.setValue(150.0)
        form.addRow(
            tr("tools.goal_simulator.periodic_contribution", self._language, default="Contribution per period"),
            self._periodic_contribution,
        )

        root.addLayout(form)

        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet("font-weight:600;")
        root.addWidget(self._summary)

        self._chart_view = QChartView()
        self._chart_view.setMinimumHeight(240)
        root.addWidget(self._chart_view)

        self._table = QTableWidget()
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            [
                tr("tools.goal_simulator.col.period", self._language, default="Period"),
                tr("tools.goal_simulator.col.label", self._language, default="Label"),
                tr("tools.goal_simulator.col.initial_balance", self._language, default="Initial balance"),
                tr("tools.goal_simulator.col.interest", self._language, default="Interest"),
                tr("tools.goal_simulator.col.contribution", self._language, default="Contribution"),
                tr("tools.goal_simulator.col.final_balance", self._language, default="Final balance"),
                tr("tools.goal_simulator.col.progress", self._language, default="Progress %"),
            ]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self._table, 1)

        self._btn_create_goal = QPushButton(
            tr("tools.goal_simulator.btn_create_goal", self._language, default="Create savings goal with this scenario")
        )
        self._btn_create_goal.clicked.connect(self._create_goal_from_scenario)
        root.addWidget(self._btn_create_goal)

        for widget in (
            self._target_amount,
            self._years,
            self._frequency,
            self._initial_amount,
            self._annual_rate,
            self._periodic_contribution,
            self._auto_contribution,
        ):
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._recalculate)
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(self._recalculate)
            else:
                widget.valueChanged.connect(self._recalculate)

    def _recalculate(self) -> None:
        using_auto = self._auto_contribution.isChecked()
        self._periodic_contribution.setEnabled(not using_auto)

        projection = simulate_savings_goal(
            SavingsGoalSimulationInput(
                target_amount=self._target_amount.value(),
                years=self._years.value(),
                frequency=self._frequency.currentData(),
                initial_amount=self._initial_amount.value(),
                annual_rate_percent=self._annual_rate.value(),
                periodic_contribution=None if using_auto else self._periodic_contribution.value(),
            )
        )
        self._latest = projection

        status = tr(
            (
                "tools.goal_simulator.status.reachable"
                if projection.is_reachable
                else "tools.goal_simulator.status.unreachable"
            ),
            self._language,
            default="reachable" if projection.is_reachable else "not reachable",
        )
        difference_text = (
            self._fmt_currency(abs(projection.gap_amount))
            if projection.is_reachable
            else f"-{self._fmt_currency(abs(projection.gap_amount))}"
        )
        self._summary.setText(
            tr(
                "tools.goal_simulator.summary",
                self._language,
                default="Required contribution: {required} | Used contribution: {used} | Final amount: {final} | Difference vs goal: {diff} | Completion: {pct:.2f}% | Status: {status}",
                params={
                    "required": self._fmt_currency(projection.required_contribution),
                    "used": self._fmt_currency(projection.periodic_contribution),
                    "final": self._fmt_currency(projection.final_amount),
                    "diff": difference_text,
                    "pct": projection.completion_percent,
                    "status": status,
                },
            )
        )

        if using_auto:
            self._message.setText(
                tr(
                    "tools.goal_simulator.message.auto",
                    self._language,
                    default="You need to save approximately {amount} per period to reach the goal.",
                    params={"amount": self._fmt_currency(projection.required_contribution)},
                )
            )
        elif projection.is_reachable:
            self._message.setText(
                tr(
                    "tools.goal_simulator.message.reachable",
                    self._language,
                    default="With this contribution you would reach {amount}. You can save this plan as a goal.",
                    params={"amount": self._fmt_currency(projection.final_amount)},
                )
            )
        else:
            self._message.setText(
                tr(
                    "tools.goal_simulator.message.unreachable",
                    self._language,
                    default="With this contribution you would reach {amount}. You would need {gap} more to meet your goal.",
                    params={
                        "amount": self._fmt_currency(projection.final_amount),
                        "gap": self._fmt_currency(abs(projection.gap_amount)),
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
                self._fmt_currency(row.contribution),
                self._fmt_currency(row.ending_balance),
                f"{row.progress_percent:.2f}%",
            ]
            for col, value in enumerate(cells):
                self._table.setItem(row_index, col, QTableWidgetItem(value))

        chart = QChart()
        chart.legend().setVisible(True)
        chart.setTitle(tr("tools.goal_simulator.chart.title", self._language, default="Savings projection"))

        series_balance = QLineSeries()
        series_balance.setName(tr("tools.goal_simulator.chart.balance", self._language, default="Cumulative savings"))
        series_target = QLineSeries()
        series_target.setName(tr("tools.goal_simulator.chart.target", self._language, default="Target goal"))
        for row in projection.rows:
            period = float(row.period)
            series_balance.append(period, row.ending_balance)
            series_target.append(period, projection.target_amount)

        axis_x = QValueAxis()
        axis_x.setLabelFormat("%.0f")
        axis_x.setTitleText(tr("tools.goal_simulator.chart.axis_x", self._language, default="Periods"))
        axis_x.setRange(1.0, float(max(1, projection.total_periods)))
        axis_y = QValueAxis()
        axis_y.setLabelFormat("%.2f")
        axis_y.setTitleText(tr("tools.goal_simulator.chart.axis_y", self._language, default="Amount"))

        chart.addSeries(series_balance)
        chart.addSeries(series_target)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series_balance.attachAxis(axis_x)
        series_balance.attachAxis(axis_y)
        series_target.attachAxis(axis_x)
        series_target.attachAxis(axis_y)

        self._chart_view.setChart(chart)

    def _create_goal_from_scenario(self) -> None:
        if self._latest is None:
            return

        if not self._latest.is_reachable:
            reply = QMessageBox.question(
                self,
                tr("tools.goal_simulator.dialog.unreachable_title", self._language, default="Unreachable scenario"),
                tr(
                    "tools.goal_simulator.dialog.unreachable_body",
                    self._language,
                    default="With this scenario you will not reach the goal. Do you want to create it anyway?",
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        show_user_message(
            self,
            tr("tools.goal_simulator.dialog.create_title", self._language, default="Create goal"),
            tr(
                "tools.goal_simulator.dialog.create_body",
                self._language,
                default="The goal form will open with the simulated target amount and term so you can complete and save it manually.",
            ),
        )
        self._goal_prefill = {
            "target_amount": round(self._latest.target_amount, 2),
            "target_date": self._target_date_from_years(self._latest.years),
        }
        self._request_open_goal_form = True
        self.accept()

    @property
    def should_open_goal_form(self) -> bool:
        return self._request_open_goal_form

    @property
    def goal_prefill(self) -> dict[str, object] | None:
        return self._goal_prefill

    @staticmethod
    def _target_date_from_years(years: float) -> str:
        days = max(1, int(round(years * 365)))
        return (date.today() + timedelta(days=days)).isoformat()

    def _fmt_currency(self, value: float) -> str:
        return f"{self._currency} {value:,.2f}"
