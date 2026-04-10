# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import importlib
from datetime import date
from pathlib import Path

import pytest

from mira.db.database import Database
from mira.db.errors import BudgetValidationError, DuplicateBudgetCodeError


def _get_qapplication_or_xfail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        qtwidgets = importlib.import_module("PySide6.QtWidgets")
    except (ImportError, OSError) as exc:
        pytest.xfail(f"Qt runtime unavailable for budget view test: {exc}")

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


def _find_row_by_text(table, text: str) -> int:
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        if item is not None and item.text() == text:
            return row
    return -1


def _set_table_item_text(table, row: int, column: int, text: str) -> None:
    table.blockSignals(True)
    table.item(row, column).setText(text)
    table.blockSignals(False)


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "budget-view.db")
    database.connect()
    yield database
    database.close()


def test_budget_view_switches_between_edit_and_comparison_modes(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.budget")

    db.budget.create("PRESUPUESTO_2026", 2026, "NIO")
    view = views_module.BudgetView(db)

    try:
        view.show()
        view.refresh()
        app.processEvents()

        assert view._btn_compare.isChecked() is False
        assert view._content_stack.currentWidget() == view._editor_panel
        assert view._editor_panel.isVisible() is True
        assert view._comparison_panel.isVisible() is False
        assert view._granularity_combo.isVisible() is False
        assert view._btn_export_excel.isVisible() is False

        view._btn_compare.click()
        app.processEvents()

        assert view._btn_compare.isChecked() is True
        assert view._content_stack.currentWidget() == view._comparison_panel
        assert view._comparison_panel.isVisible() is True
        assert view._editor_panel.isVisible() is False
        assert view._granularity_combo.isVisible() is True
        assert view._btn_export_excel.isVisible() is True

        view._btn_compare.click()
        app.processEvents()

        assert view._btn_compare.isChecked() is False
        assert view._content_stack.currentWidget() == view._editor_panel
        assert view._editor_panel.isVisible() is True
        assert view._comparison_panel.isVisible() is False
        assert view._granularity_combo.isVisible() is False
        assert view._btn_export_excel.isVisible() is False
    finally:
        view.close()


def test_budget_view_switches_to_monthly_tracking_mode(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.budget")
    qtcore = importlib.import_module("PySide6.QtCore")
    qtwidgets = importlib.import_module("PySide6.QtWidgets")

    db.budget.create("PRESUPUESTO_2026", 2026, "NIO")
    view = views_module.BudgetView(db)

    try:
        view.show()
        view.refresh()
        app.processEvents()

        assert view._btn_monthly_tracking.isChecked() is False
        assert view._content_stack.currentWidget() == view._editor_panel
        assert view._monthly_tracking_panel.isVisible() is False

        view._btn_monthly_tracking.click()
        app.processEvents()

        assert view._btn_monthly_tracking.isChecked() is True
        assert view._btn_compare.isChecked() is False
        assert view._content_stack.currentWidget() == view._monthly_tracking_panel
        assert isinstance(view._monthly_tracking_panel, qtwidgets.QScrollArea)
        assert view._monthly_tracking_panel.isVisible() is True
        assert view._monthly_tracking_panel.verticalScrollBarPolicy() == qtcore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        assert view._granularity_combo.isVisible() is False
        assert view._btn_export_excel.isVisible() is False

        view._btn_monthly_tracking.click()
        app.processEvents()

        assert view._btn_monthly_tracking.isChecked() is False
        assert view._content_stack.currentWidget() == view._editor_panel
        assert view._monthly_tracking_panel.isVisible() is False
    finally:
        view.close()


def test_budget_view_monthly_tracking_uses_selected_budget_year(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.budget")

    food = db.category.create("Comida", "expense")
    budget_2026 = db.budget.create("PRESUPUESTO_2026", 2026, "NIO")
    budget_2027 = db.budget.create("PRESUPUESTO_2027", 2027, "NIO")
    db.budget.upsert_amount(int(budget_2026["id"]), int(food["id"]), 2026, 1, 100.0)
    db.budget.upsert_amount(int(budget_2027["id"]), int(food["id"]), 2027, 1, 300.0)

    view = views_module.BudgetView(db)

    try:
        view.show()
        view.refresh()
        app.processEvents()

        view._tracking_month_combo.setCurrentIndex(0)
        view._tracking_year_spin.setValue(1900)
        view._btn_monthly_tracking.click()
        app.processEvents()

        assert view._tracking_year_spin.value() == 2026
        assert view._tracking_assigned_card._value_lbl.text() == "NIO 100.00"

        idx_2027 = view._budget_combo.findData(int(budget_2027["id"]))
        assert idx_2027 >= 0
        view._budget_combo.setCurrentIndex(idx_2027)
        app.processEvents()

        assert view._tracking_year_spin.value() == 2027
        assert view._tracking_assigned_card._value_lbl.text() == "NIO 300.00"
    finally:
        view.close()


def test_budget_view_reassignment_refreshes_loaded_budget_and_tracking(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.budget")

    current = date.today()
    food = db.category.create("Comida", "expense")
    transport = db.category.create("Transporte", "expense")
    budget = db.budget.create("PRESUPUESTO_REASIGNACION", current.year, "NIO")
    db.budget.upsert_amount(int(budget["id"]), int(food["id"]), current.year, current.month, 200.0)
    db.budget.upsert_amount(int(budget["id"]), int(transport["id"]), current.year, current.month, 100.0)

    view = views_module.BudgetView(db)

    try:
        view.show()
        view.refresh()
        view._load_budget()
        app.processEvents()

        view._btn_monthly_tracking.click()
        view._tracking_month_combo.setCurrentIndex(current.month - 1)
        view._tracking_year_spin.setValue(current.year)
        view._refresh_monthly_tracking()
        app.processEvents()

        source_idx = view._reassign_source_combo.findData(int(food["id"]))
        target_idx = view._reassign_target_combo.findData(int(transport["id"]))
        assert source_idx >= 0
        assert target_idx >= 0
        view._reassign_source_combo.setCurrentIndex(source_idx)
        view._reassign_target_combo.setCurrentIndex(target_idx)
        view._reassign_amount_input.setText("50")

        view._on_apply_reassignment()
        app.processEvents()

        food_tracking_row = _find_row_by_text(view._monthly_tracking_table, "Comida")
        transport_tracking_row = _find_row_by_text(view._monthly_tracking_table, "Transporte")
        assert food_tracking_row >= 0
        assert transport_tracking_row >= 0
        assert view._monthly_tracking_table.item(food_tracking_row, 1).text() == "150.00"
        assert view._monthly_tracking_table.item(transport_tracking_row, 1).text() == "150.00"

        food_budget_row = _find_row_by_text(view._budget_table, "Comida")
        transport_budget_row = _find_row_by_text(view._budget_table, "Transporte")
        assert food_budget_row >= 0
        assert transport_budget_row >= 0
        assert view._budget_table.item(food_budget_row, current.month).text() == "150.00"
        assert view._budget_table.item(transport_budget_row, current.month).text() == "150.00"
    finally:
        view.close()


def test_budget_view_open_create_dialog_maps_duplicate_code_error(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.budget")

    class _Dialog:
        def __init__(self, _db, parent=None):
            self._db = _db
            self._parent = parent

        def exec(self):
            return 1

        def get_data(self):
            return {"code": "B-2026", "year": 2026, "currency": "NIO"}

    captured: list[tuple[str, str]] = []

    def _fake_notify(_parent, title, message):
        captured.append((title, message))

    monkeypatch.setattr(importlib.import_module("mira.ui.dialogs"), "BudgetCreateDialog", _Dialog)
    monkeypatch.setattr(views_module, "_notify_warning", _fake_notify)

    view = views_module.BudgetView(db)
    try:
        monkeypatch.setattr(
            db.budget,
            "create",
            lambda *args, **kwargs: (_ for _ in ()).throw(DuplicateBudgetCodeError("dup")),
        )
        view.open_create_dialog()
        assert captured == [
            (
                "Budgets",
                "A budget with that code already exists.",
            )
        ]
    finally:
        view.close()


def test_budget_view_open_create_dialog_maps_invalid_year_error(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.budget")

    class _Dialog:
        def __init__(self, _db, parent=None):
            self._db = _db
            self._parent = parent

        def exec(self):
            return 1

        def get_data(self):
            return {"code": "B-2026", "year": 1800, "currency": "NIO"}

    captured: list[tuple[str, str]] = []

    def _fake_notify(_parent, title, message):
        captured.append((title, message))

    monkeypatch.setattr(importlib.import_module("mira.ui.dialogs"), "BudgetCreateDialog", _Dialog)
    monkeypatch.setattr(views_module, "_notify_warning", _fake_notify)

    view = views_module.BudgetView(db)
    try:
        monkeypatch.setattr(
            db.budget,
            "create",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                BudgetValidationError("Budget year must be between 1900 and 9999")
            ),
        )
        view.open_create_dialog()
        assert captured == [
            (
                "Budgets",
                "Budget year must be between 1900 and 9999",
            )
        ]
    finally:
        view.close()


def test_budget_view_invalid_cell_edit_shows_feedback_and_restores_previous_value(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.budget")

    food = db.category.create("Food", "expense")
    budget = db.budget.create("BUDGET_2026", 2026, "USD")
    db.budget.upsert_amount(int(budget["id"]), int(food["id"]), 2026, 1, 125.0)

    captured: list[tuple[str, str]] = []
    upsert_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def _fake_notify(_parent, title, message):
        captured.append((str(title), str(message)))

    monkeypatch.setattr(views_module, "_notify_warning", _fake_notify)
    monkeypatch.setattr(db.budget, "upsert_amount", lambda *args, **kwargs: upsert_calls.append((args, kwargs)))

    view = views_module.BudgetView(db)
    try:
        view.show()
        view.refresh()
        view._load_budget()
        app.processEvents()
        upsert_calls.clear()

        row = _find_row_by_text(view._budget_table, "Food")
        assert row >= 0

        _set_table_item_text(view._budget_table, row, 1, "not-a-number")

        view._on_budget_cell_changed(row, 1)
        app.processEvents()

        expected_message = (
            "Invalid value: 'not-a-number'. Enter a positive number or a formula starting with '=' "
            "(e.g. '=100+200')."
        )
        assert captured == [
            (
                "Budgets",
                expected_message,
            )
        ]
        assert upsert_calls == []
        loaded_status = view._t(
            "budget.status.loaded",
            "Presupuesto cargado. Ahora puedes consultar comparativos o seguimiento sin bloquear la navegación al entrar.",
        )
        assert view._budget_status_lbl.text() in (
            expected_message,
            loaded_status,
        )
        assert view._budget_table.item(row, 1).text() == "125.00"
        assert view._budget_table.item(row, 1).toolTip() in ("", expected_message)
        assert view._budget_table.currentRow() == row
        assert view._budget_table.currentColumn() == 1
    finally:
        view.close()


def test_budget_view_rejects_negative_cell_edit_and_restores_previous_value(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.budget")

    food = db.category.create("Food", "expense")
    budget = db.budget.create("NEGATIVE_BUDGET_2026", 2026, "USD")
    db.budget.upsert_amount(int(budget["id"]), int(food["id"]), 2026, 1, 125.0)

    captured: list[tuple[str, str]] = []
    upsert_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    monkeypatch.setattr(
        views_module,
        "_notify_warning",
        lambda _parent, title, message: captured.append((str(title), str(message))),
    )
    monkeypatch.setattr(db.budget, "upsert_amount", lambda *args, **kwargs: upsert_calls.append((args, kwargs)))

    view = views_module.BudgetView(db)
    try:
        view.show()
        view.refresh()
        view._load_budget()
        app.processEvents()

        row = _find_row_by_text(view._budget_table, "Food")
        assert row >= 0

        _set_table_item_text(view._budget_table, row, 1, "-400")
        view._on_budget_cell_changed(row, 1)
        app.processEvents()

        expected_message = "Only positive values are allowed in budget cells. Got: -400.0."
        assert captured == [("Budgets", expected_message)]
        assert upsert_calls == []
        assert view._budget_table.item(row, 1).text() == "125.00"
        assert view._budget_table.item(row, 1).toolTip() in ("", expected_message)
    finally:
        view.close()


def test_budget_view_rejects_division_by_zero_formula_and_restores_previous_value(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.budget")

    food = db.category.create("Food", "expense")
    budget = db.budget.create("ZERO_DIVISION_BUDGET_2026", 2026, "USD")
    db.budget.upsert_amount(int(budget["id"]), int(food["id"]), 2026, 1, 125.0)

    captured: list[tuple[str, str]] = []
    upsert_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    monkeypatch.setattr(
        views_module,
        "_notify_warning",
        lambda _parent, title, message: captured.append((str(title), str(message))),
    )
    monkeypatch.setattr(db.budget, "upsert_amount", lambda *args, **kwargs: upsert_calls.append((args, kwargs)))

    view = views_module.BudgetView(db)
    try:
        view.show()
        view.refresh()
        view._load_budget()
        app.processEvents()

        row = _find_row_by_text(view._budget_table, "Food")
        assert row >= 0

        _set_table_item_text(view._budget_table, row, 1, "=100/0")
        view._on_budget_cell_changed(row, 1)
        app.processEvents()

        expected_message = "Division by zero is not allowed in budget formulas."
        assert captured == [("Budgets", expected_message)]
        assert upsert_calls == []
        assert view._budget_table.item(row, 1).text() == "125.00"
        assert view._budget_table.item(row, 1).toolTip() in ("", expected_message)
    finally:
        view.close()


def test_budget_view_accepts_formula_and_persists_numeric_result(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.budget")

    db.category.create("Food", "expense")
    budget = db.budget.create("FORMULA_BUDGET_2026", 2026, "USD")

    view = views_module.BudgetView(db)
    try:
        view.show()
        view.refresh()
        view._load_budget()
        app.processEvents()

        row = _find_row_by_text(view._budget_table, "Food")
        assert row >= 0

        _set_table_item_text(view._budget_table, row, 1, "=100+200")
        view._on_budget_cell_changed(row, 1)
        app.processEvents()

        assert view._budget_table.item(row, 1).text() == "300.00"
        matrix = db.budget.get_matrix(int(budget["id"]))
        assert float(matrix["rows"][0]["months"][0]) == pytest.approx(300.0)
    finally:
        view.close()


def test_budget_view_accepts_grouped_formula_and_persists_numeric_result(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.budget")

    db.category.create("Food", "expense")
    budget = db.budget.create("GROUPED_FORMULA_BUDGET_2026", 2026, "USD")

    view = views_module.BudgetView(db)
    try:
        view.show()
        view.refresh()
        view._load_budget()
        app.processEvents()

        row = _find_row_by_text(view._budget_table, "Food")
        assert row >= 0

        _set_table_item_text(view._budget_table, row, 1, "=(50*2)*20")
        view._on_budget_cell_changed(row, 1)
        app.processEvents()

        assert view._budget_table.item(row, 1).text() == "2,000.00"
        matrix = db.budget.get_matrix(int(budget["id"]))
        assert float(matrix["rows"][0]["months"][0]) == pytest.approx(2000.0)
    finally:
        view.close()


def test_budget_view_rejects_formula_with_non_parentheses_groupers_and_keeps_previous_value(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.budget")

    food = db.category.create("Food", "expense")
    budget = db.budget.create("GROUPER_BUDGET_2026", 2026, "USD")
    db.budget.upsert_amount(int(budget["id"]), int(food["id"]), 2026, 1, 125.0)

    captured: list[tuple[str, str]] = []
    upsert_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    monkeypatch.setattr(
        views_module,
        "_notify_warning",
        lambda _parent, title, message: captured.append((str(title), str(message))),
    )
    monkeypatch.setattr(db.budget, "upsert_amount", lambda *args, **kwargs: upsert_calls.append((args, kwargs)))

    view = views_module.BudgetView(db)
    try:
        view.show()
        view.refresh()
        view._load_budget()
        app.processEvents()

        row = _find_row_by_text(view._budget_table, "Food")
        assert row >= 0

        _set_table_item_text(view._budget_table, row, 1, "=[100+200]*2")
        view._on_budget_cell_changed(row, 1)
        app.processEvents()

        expected_message = "Grouping symbol not allowed: '['. Only parentheses '()' are supported for grouping."
        assert captured == [("Budgets", expected_message)]
        assert upsert_calls == []
        assert view._budget_table.item(row, 1).text() == "125.00"
        assert view._budget_table.item(row, 1).toolTip() in ("", expected_message)
    finally:
        view.close()


def test_budget_view_rejects_invalid_grouped_formula_and_keeps_persisted_value(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.budget")

    food = db.category.create("Food", "expense")
    budget = db.budget.create("INVALID_GROUPED_FORMULA_BUDGET_2026", 2026, "USD")
    db.budget.upsert_amount(int(budget["id"]), int(food["id"]), 2026, 1, 125.0)

    captured: list[tuple[str, str]] = []

    monkeypatch.setattr(
        views_module,
        "_notify_warning",
        lambda _parent, title, message: captured.append((str(title), str(message))),
    )

    view = views_module.BudgetView(db)
    try:
        view.show()
        view.refresh()
        view._load_budget()
        app.processEvents()

        row = _find_row_by_text(view._budget_table, "Food")
        assert row >= 0

        _set_table_item_text(view._budget_table, row, 1, "=(50*2")
        view._on_budget_cell_changed(row, 1)
        app.processEvents()

        expected_message = (
            "Invalid formula: '(50*2'. Check that the formula contains only numbers and the operators +, -, *, /."
        )
        assert captured == [("Budgets", expected_message)]
        assert view._budget_table.item(row, 1).text() == "125.00"

        matrix = db.budget.get_matrix(int(budget["id"]))
        assert float(matrix["rows"][0]["months"][0]) == pytest.approx(125.0)
    finally:
        view.close()


def test_budget_view_accepts_localized_number_format_when_editing_cells(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.budget")

    db.setting.set("number_thousands_separator", ".")
    db.setting.set("number_decimal_separator", ",")

    db.category.create("Food", "expense")
    budget = db.budget.create("LOCALIZED_BUDGET_2026", 2026, "USD")

    view = views_module.BudgetView(db)
    try:
        view.show()
        view.refresh()
        view._load_budget()
        app.processEvents()

        row = _find_row_by_text(view._budget_table, "Food")
        assert row >= 0

        _set_table_item_text(view._budget_table, row, 1, "1.234,50")
        view._on_budget_cell_changed(row, 1)
        app.processEvents()

        assert view._budget_table.item(row, 1).text() == "1.234,50"
        matrix = db.budget.get_matrix(int(budget["id"]))
        assert float(matrix["rows"][0]["months"][0]) == pytest.approx(1234.5)
    finally:
        view.close()
