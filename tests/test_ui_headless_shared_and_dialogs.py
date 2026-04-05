# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.qt_stubs import fresh_import, install_fake_pyside, load_module_from_path

_ROOT = Path(__file__).resolve().parents[1]


def _load_financial_dialog_module(monkeypatch, filename: str):
    return load_module_from_path(
        monkeypatch,
        f"tests._headless_{filename.replace('.py', '')}",
        str(_ROOT / "src" / "mira" / "ui" / "dialogs" / "financial" / filename),
    )


def test_shared_helpers_cover_notifications_formatting_and_selection(monkeypatch) -> None:
    qt = install_fake_pyside(monkeypatch)
    module = fresh_import(
        monkeypatch,
        "mira.ui.views._shared",
        clear_prefixes=("mira.ui.views._shared", "mira.ui.notifications"),
    )

    calls: list[tuple[object, str, str, str]] = []
    monkeypatch.setattr(
        module,
        "show_user_message",
        lambda widget, title, message, level="info": calls.append((widget, title, message, level)),
    )
    monkeypatch.setattr(module, "get_number_format_config", lambda _setting: {"decimal": "."})
    monkeypatch.setattr(
        module,
        "format_number",
        lambda amount, _cfg, *, decimals, grouping: f"{amount:.{decimals}f}|grouping={grouping}",
    )

    badge = module._make_tag_badge({"name": "Food", "color": "#FF0"})
    widget = qt.QtWidgets.QWidget()
    module._notify(widget, "Title", "Message", level="warning")
    module._notify(widget, qt.QtWidgets.QWidget(), "Alt", "Message 2", level="error")

    with pytest.raises(TypeError):
        module._notify(widget, "only title")

    class Setting:
        def get(self, key: str) -> str:
            return {"language": "en"}.get(key, "")

    db = SimpleNamespace(setting=Setting())
    amount = module._fmt_amount(db, 12.5)
    amount_with_currency = module._fmt_amount_with_currency(db, 12.5, " usd ")

    class Cell:
        def __init__(self) -> None:
            self._row = 3
            self._column = 1

        def row(self) -> int:
            return self._row

        def column(self) -> int:
            return self._column

    table = qt.QtWidgets.QTableWidget()
    table.item_at = Cell()
    selected = module._select_row_at_pos(table, qt.QtCore.QPoint(4, 5))

    transfer_text, transfer_color = module._tx_type_indicator({"is_transfer": 1}, {"savings"})
    savings_item = module._make_tx_type_item({"type": "expense", "category": "savings"}, {"savings"})
    qdate = module._date_to_qdate(date(2026, 4, 1))
    scroll, content, layout = module._build_scrollable_container(widget)
    chart_view = qt.QtCharts.QChartView()
    module._configure_chart_view(chart_view, minimum_height=420)

    assert badge.text() == "Food"
    assert calls == [
        (widget, "Title", "Message", "warning"),
        (widget, "Alt", "Message 2", "error"),
    ]
    assert amount == "12.50|grouping=True"
    assert amount_with_currency == "USD 12.50|grouping=True"
    assert selected is True
    assert table.current_cell == (3, 1)
    assert table.selected_row == 3
    assert transfer_text == "↔ transfer"
    assert transfer_color.value == "#D7BA7D"
    assert savings_item.text() == "@ savings"
    assert savings_item.data(module._TYPE_BADGE_ROLE) == "savings"
    assert savings_item.foreground.color.value == "#569CD6"
    assert (qdate.year, qdate.month, qdate.day) == (2026, 4, 1)
    assert scroll.widget is content
    assert layout.spacing == 10
    assert chart_view.minimum_height == 420
    assert chart_view.render_hints == [qt.QtGui.QPainter.RenderHint.Antialiasing]
    assert module._account_type_label(db, "card") == "credit"


def test_cell_delegates_draw_semantic_cells_and_badges(monkeypatch) -> None:
    qt = install_fake_pyside(monkeypatch)
    module = fresh_import(
        monkeypatch,
        "mira.ui.delegates.cell_delegates",
        clear_prefixes=("mira.ui.delegates.cell_delegates", "mira.ui.views._shared", "mira.ui.notifications"),
    )

    class Index:
        def __init__(self, mapping: dict[int, object]) -> None:
            self.mapping = mapping

        def data(self, role: int):
            return self.mapping.get(role)

    option = SimpleNamespace(state=0, rect=qt.Rect(0, 0, 100, 30), font=qt.QtGui.QFont())

    signal_delegate = module._SignalCellDelegate()
    painter = qt.QtGui.QPainter()
    signal_delegate.paint(painter, option, Index({module._SIGNAL_CELL_ROLE: "other"}))
    assert signal_delegate.super_paint_calls == 1

    selected_option = SimpleNamespace(
        state=module.QStyle.StateFlag.State_Selected,
        rect=qt.Rect(0, 0, 100, 30),
        font=qt.QtGui.QFont(),
    )
    painter = qt.QtGui.QPainter()
    signal_delegate.paint(
        painter,
        selected_option,
        Index(
            {
                module._SIGNAL_CELL_ROLE: "positive",
                module.Qt.ItemDataRole.DisplayRole: "42",
            }
        ),
    )
    assert any(operation[-1] == "42" for operation in painter.operations if operation[0] == "drawText")
    assert any(operation[-1] == "▲" for operation in painter.operations if operation[0] == "drawText")

    badge_delegate = module._TypeBadgeDelegate()
    painter = qt.QtGui.QPainter()
    badge_delegate.paint(
        painter,
        option,
        Index(
            {
                module._TYPE_BADGE_ROLE: "income",
                module.Qt.ItemDataRole.DisplayRole: "Income",
            }
        ),
    )
    assert any(operation[0] == "drawRoundedRect" for operation in painter.operations)
    assert any(operation[-1] == "Income" for operation in painter.operations if operation[0] == "drawText")


def test_compound_interest_dialog_recalculate_formats_projection(monkeypatch) -> None:
    qt = install_fake_pyside(monkeypatch)
    module = _load_financial_dialog_module(monkeypatch, "compound_interest.py")

    projection = SimpleNamespace(
        final_balance=115.0,
        own_capital=110.0,
        interest_earned=5.0,
        total_contributed=110.0,
        initial_fund=100.0,
        total_periods=1,
        rows=[
            SimpleNamespace(
                period=1,
                label="Periodo 1",
                initial_balance=100.0,
                interest=5.0,
                periodic_contribution=10.0,
                final_balance=115.0,
                cumulative_contribution=10.0,
                cumulative_interest=5.0,
            )
        ],
    )
    monkeypatch.setattr(module, "calculate_compound_interest_projection", lambda _input: projection)

    dialog = SimpleNamespace(
        _language="es",
        _currency="USD",
        _initial_fund=SimpleNamespace(value=lambda: 100.0),
        _annual_rate=SimpleNamespace(value=lambda: 5.0),
        _capitalization=SimpleNamespace(
            currentData=lambda: module.PaymentFrequency.MONTHLY,
            currentText=lambda: "Mensual",
        ),
        _years=SimpleNamespace(value=lambda: 1.0),
        _periodic_contribution=SimpleNamespace(value=lambda: 10.0),
        _summary=qt.QtWidgets.QLabel(),
        _message=qt.QtWidgets.QLabel(),
        _table=qt.QtWidgets.QTableWidget(),
        _chart_view=qt.QtCharts.QChartView(),
    )
    dialog._fmt_currency = module.CompoundInterestDialog._fmt_currency.__get__(dialog, object)

    module.CompoundInterestDialog._recalculate(dialog)

    assert "Monto final: USD 115.00" in dialog._summary.text()
    assert "En este escenario aportarías USD 10.00" in dialog._message.text()
    assert dialog._table.row_count == 1
    assert dialog._table.items[(0, 1)].text() == "Periodo 1"
    assert dialog._chart_view.chart.title == "Crecimiento del capital"
    assert dialog._fmt_currency(12.5) == "USD 12.50"


def test_goal_simulator_dialog_recalculate_and_create_goal(monkeypatch) -> None:
    qt = install_fake_pyside(monkeypatch)
    module = _load_financial_dialog_module(monkeypatch, "goal_simulator.py")

    projection = SimpleNamespace(
        is_reachable=False,
        gap_amount=-200.0,
        required_contribution=250.0,
        periodic_contribution=150.0,
        final_amount=800.0,
        completion_percent=80.0,
        target_amount=1000.0,
        total_periods=2,
        years=1.5,
        rows=[
            SimpleNamespace(
                period=1,
                label="Periodo 1",
                initial_balance=100.0,
                interest=5.0,
                contribution=150.0,
                ending_balance=255.0,
                progress_percent=25.5,
            )
        ],
    )
    monkeypatch.setattr(module, "simulate_savings_goal", lambda _input: projection)
    messages: list[tuple[object, str, str, str]] = []
    monkeypatch.setattr(
        module,
        "show_user_message",
        lambda widget, title, message, level="info": messages.append((widget, title, message, level)),
    )
    monkeypatch.setattr(
        module.GoalScenarioDialog, "_target_date_from_years", staticmethod(lambda years: f"date-for-{years}")
    )

    dialog = SimpleNamespace(
        _language="es",
        _currency="USD",
        _target_amount=SimpleNamespace(value=lambda: 1000.0),
        _years=SimpleNamespace(value=lambda: 1.5),
        _frequency=SimpleNamespace(
            currentData=lambda: module.PaymentFrequency.MONTHLY,
            currentText=lambda: "Mensual",
        ),
        _initial_amount=SimpleNamespace(value=lambda: 100.0),
        _annual_rate=SimpleNamespace(value=lambda: 5.0),
        _auto_contribution=SimpleNamespace(isChecked=lambda: False),
        _periodic_contribution=SimpleNamespace(
            value=lambda: 150.0, setEnabled=lambda value: setattr(dialog, "_enabled", value)
        ),
        _summary=qt.QtWidgets.QLabel(),
        _message=qt.QtWidgets.QLabel(),
        _table=qt.QtWidgets.QTableWidget(),
        _chart_view=qt.QtCharts.QChartView(),
        _latest=None,
        _request_open_goal_form=False,
        _goal_prefill=None,
        accept=lambda: setattr(dialog, "_accepted", True),
    )
    dialog._fmt_currency = module.GoalScenarioDialog._fmt_currency.__get__(dialog, object)
    dialog._target_date_from_years = module.GoalScenarioDialog._target_date_from_years

    module.GoalScenarioDialog._recalculate(dialog)

    assert dialog._enabled is True
    assert "Estado: no alcanzable" in dialog._summary.text()
    assert "Te faltarían USD 200.00" in dialog._message.text()
    assert dialog._table.row_count == 1
    assert dialog._chart_view.chart.title == "Proyección de ahorro"

    module.QMessageBox.question_result = module.QMessageBox.StandardButton.No
    module.GoalScenarioDialog._create_goal_from_scenario(dialog)
    assert getattr(dialog, "_accepted", False) is False

    module.QMessageBox.question_result = module.QMessageBox.StandardButton.Yes
    module.GoalScenarioDialog._create_goal_from_scenario(dialog)

    assert dialog._request_open_goal_form is True
    assert dialog._goal_prefill == {"target_amount": 1000.0, "target_date": "date-for-1.5"}
    assert messages[0][1] == "Crear meta"
    assert module.GoalScenarioDialog.should_open_goal_form.__get__(dialog, object) is True
    assert module.GoalScenarioDialog.goal_prefill.__get__(dialog, object) == dialog._goal_prefill


def test_goal_simulator_target_date_and_currency_helpers(monkeypatch) -> None:
    install_fake_pyside(monkeypatch)
    module = _load_financial_dialog_module(monkeypatch, "goal_simulator.py")

    class FakeDate(date):
        @classmethod
        def today(cls) -> "FakeDate":
            return cls(2026, 4, 1)

    monkeypatch.setattr(module, "date", FakeDate)

    assert module.GoalScenarioDialog._target_date_from_years(0.01) == "2026-04-05"
    assert module.GoalScenarioDialog._fmt_currency(SimpleNamespace(_currency="USD"), 99.5) == "USD 99.50"


def test_loan_amortization_dialog_recalculate_formats_projection(monkeypatch) -> None:
    qt = install_fake_pyside(monkeypatch)
    module = _load_financial_dialog_module(monkeypatch, "loan_amortization.py")

    projection = SimpleNamespace(
        payment_initial=220.0,
        payment_final=180.0,
        total_paid=5000.0,
        total_interest=600.0,
        method=module.AmortizationMethod.GERMAN,
        total_periods=1,
        rows=[
            SimpleNamespace(
                period=1,
                label="Periodo 1",
                initial_balance=1000.0,
                payment=220.0,
                interest=20.0,
                principal_amortization=200.0,
                ending_balance=800.0,
                cumulative_interest=20.0,
                cumulative_principal=200.0,
            )
        ],
    )
    monkeypatch.setattr(module, "calculate_loan_amortization", lambda _input: projection)

    dialog = SimpleNamespace(
        _language="es",
        _currency="USD",
        _loan_amount=SimpleNamespace(value=lambda: 1000.0),
        _annual_rate=SimpleNamespace(value=lambda: 12.0),
        _frequency=SimpleNamespace(
            currentData=lambda: module.PaymentFrequency.MONTHLY,
            currentText=lambda: "Mensual",
        ),
        _years=SimpleNamespace(value=lambda: 1.0),
        _method=SimpleNamespace(
            currentData=lambda: module.AmortizationMethod.GERMAN,
            currentText=lambda: "Alemán",
        ),
        _summary=qt.QtWidgets.QLabel(),
        _message=qt.QtWidgets.QLabel(),
        _table=qt.QtWidgets.QTableWidget(),
        _chart_view=qt.QtCharts.QChartView(),
    )
    dialog._fmt_currency = module.LoanAmortizationDialog._fmt_currency.__get__(dialog, object)

    module.LoanAmortizationDialog._recalculate(dialog)

    assert "Cuota inicial: USD 220.00" in dialog._summary.text()
    assert "las cuotas bajan con el tiempo" in dialog._message.text()
    assert dialog._table.row_count == 1
    assert dialog._chart_view.chart.title == "Evolución del préstamo"
    assert dialog._fmt_currency(1.5) == "USD 1.50"
