# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from conftest import opengl_import_error
from mira.db.database import Database


def _get_qapplication_or_xfail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        qtwidgets = importlib.import_module("PySide6.QtWidgets")
    except (ImportError, OSError) as exc:
        pytest.xfail(f"Qt runtime unavailable for reports view test: {exc}")

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "reports-view.db")
    database.connect()
    yield database
    database.close()


@pytest.mark.skipif(
    opengl_import_error(), reason="PySide6.QtCharts requires OpenGL (not available in headless environments)"
)
def test_account_balance_report_shows_balance_in_account_currency(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.reports")

    db.setting.set("default_currency", "NIO")
    db.account.create("Cuenta USD", "bank", 125.5, "USD")

    view = views_module.ReportsView(db)

    try:
        view.show()
        view._report_type.setCurrentIndex(view.REPORT_ACCOUNT_BALANCE)
        view.refresh()
        app.processEvents()

        assert view._account_balance_table.rowCount() >= 1

        row_index = next(
            row
            for row in range(view._account_balance_table.rowCount())
            if (item := view._account_balance_table.item(row, 0)) is not None and item.text() == "Cuenta USD"
        )

        currency_item = view._account_balance_table.item(row_index, 2)
        balance_item = view._account_balance_table.item(row_index, 3)
        consolidated_item = view._account_balance_table.item(row_index, 4)

        assert currency_item is not None
        assert balance_item is not None
        assert consolidated_item is not None
        assert currency_item.text() == "USD"
        assert balance_item.text() == "USD 125.50"
        assert consolidated_item.text() == "NIO 125.50"
    finally:
        view.close()


@pytest.mark.skipif(
    opengl_import_error(), reason="PySide6.QtCharts requires OpenGL (not available in headless environments)"
)
def test_reports_view_apply_binds_presentation_state(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.reports")
    qtcore = importlib.import_module("PySide6.QtCore")

    account = db.account.create("Wallet", "bank", 0.0, "USD")
    food = db.category.create("Food", "expense")
    db.transaction.create(
        account_id=account["id"],
        tx_type="income",
        amount=100.0,
        description="Salary",
        category=None,
        tx_date="2026-03-05",
        note="",
    )
    db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=40.0,
        description="Groceries",
        category=food["name"],
        tx_date="2026-03-06",
        note="",
    )

    view = views_module.ReportsView(db)
    try:
        view.show()
        view._from_date.setDate(qtcore.QDate.fromString("2026-03-01", "yyyy-MM-dd"))
        view._to_date.setDate(qtcore.QDate.fromString("2026-03-31", "yyyy-MM-dd"))
        view._apply_report()
        app.processEvents()

        assert view._presentation_state is not None
        assert view._income_expense_table.rowCount() == 1
        assert view._tx_table.rowCount() == 2
        assert view._page_info.text() == "1/1"
    finally:
        view.close()


@pytest.mark.skipif(
    opengl_import_error(), reason="PySide6.QtCharts requires OpenGL (not available in headless environments)"
)
def test_reports_view_set_report_payload_binds_presentation_state(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.reports")

    account = db.account.create("Wallet", "bank", 0.0, "USD")
    food = db.category.create("Food", "expense")
    tx = db.transaction.create(
        account_id=account["id"],
        tx_type="expense",
        amount=30.0,
        description="Groceries",
        category=food["name"],
        tx_date="2026-03-10",
        note="",
    )

    view = views_module.ReportsView(db)
    try:
        view.show()
        view.set_report_payload(
            {
                "transactions": [tx],
                "period": {"year": 2026, "preset": "custom"},
                "summary": {"total_income": 0.0, "total_expenses": 30.0, "net": -30.0},
            }
        )
        app.processEvents()

        assert view._presentation_state is not None
        assert view._tx_table.rowCount() == 1
        assert view._page_info.text() == "1/1"
    finally:
        view.close()
