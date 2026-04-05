# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from mira.db.database import Database


def _get_qapplication_or_xfail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        qtwidgets = importlib.import_module("PySide6.QtWidgets")
    except (ImportError, OSError) as exc:
        pytest.xfail(f"Qt runtime unavailable for dashboard view test: {exc}")

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "dashboard-view.db")
    database.connect()
    yield database
    database.close()


def _install_dashboard_stubs(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[str | None], list[dict[str, object]]]:
    summary_calls: list[str | None] = []
    tx_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        db.report,
        "get_summary",
        lambda since_date=None: summary_calls.append(since_date)
        or {
            "total_income": 1500.0,
            "total_expenses": -200.0,
            "net": 1300.0,
            "savings": 150.0,
        },
    )
    monkeypatch.setattr(
        db.transaction,
        "list",
        lambda **kwargs: tx_calls.append(kwargs)
        or [
            {
                "id": 1,
                "date": "2026-04-02",
                "type": "income",
                "amount": 1500.0,
                "category": "Salary",
                "description": "Payroll",
                "is_transfer": 0,
            }
        ],
    )
    monkeypatch.setattr(db.tag, "list_for_transaction", lambda _tx_id: [])
    return summary_calls, tx_calls


def test_dashboard_filters_are_exclusive_when_clicked(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.dashboard")

    _install_dashboard_stubs(db, monkeypatch)
    view = views_module.DashboardView(db)

    try:
        view.show()
        view.refresh()
        app.processEvents()

        assert [btn.isChecked() for btn in view._filter_btns] == [True, False, False]

        view._filter_btns[1].click()
        app.processEvents()
        assert [btn.isChecked() for btn in view._filter_btns] == [False, True, False]

        view._filter_btns[2].click()
        app.processEvents()
        assert [btn.isChecked() for btn in view._filter_btns] == [False, False, True]
    finally:
        view.close()


def test_dashboard_refresh_uses_same_since_date_for_summary_and_recent_transactions(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.dashboard")

    summary_calls, tx_calls = _install_dashboard_stubs(db, monkeypatch)
    view = views_module.DashboardView(db)

    try:
        view.show()
        view.refresh()
        app.processEvents()

        assert summary_calls == [view._get_since_date()]
        assert tx_calls == [{"limit": 10, "since_date": view._get_since_date()}]
        assert view._tx_table.rowCount() == 1

        view._filter_btns[2].click()
        app.processEvents()

        assert len(summary_calls) == 2
        assert len(tx_calls) == 2
        assert summary_calls[-1] == view._get_since_date()
        assert tx_calls[-1]["since_date"] == view._get_since_date()
        assert tx_calls[-1]["limit"] == 10
    finally:
        view.close()
