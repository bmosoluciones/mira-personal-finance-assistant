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
        pytest.xfail(f"Qt runtime unavailable for transactions view test: {exc}")

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "transactions-view.db")
    database.connect()
    yield database
    database.close()


def test_transactions_totals_bar_uses_theme_palette(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.transactions")

    view = views_module.TransactionsView(db)

    try:
        stylesheet = view._totals_bar.styleSheet()
        assert "#3C4C61" not in stylesheet
        assert "palette(alternate-base)" in stylesheet
        assert "palette(mid)" in stylesheet
    finally:
        view.close()


def test_transactions_view_edits_balance_adjustments_with_dedicated_dialog(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.transactions")
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    account = db.account.create("Banco", "bank", 100.0, "USD")
    adjustment = db.transaction.record_balance_adjustment(account["id"], 20.0, tx_date="2026-06-01")

    class FakeBalanceAdjustmentDialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, _db: Database, parent=None, *, account_id=None, tx=None, service=None) -> None:
            del _db, parent, account_id, service
            self._tx = tx

        def exec(self) -> int:
            return self.DialogCode.Accepted

        def get_data(self) -> dict:
            assert int(self._tx["id"]) == int(adjustment["id"])
            return {
                "account_id": account["id"],
                "tx_date": "2026-06-01",
                "signed_amount": 35.0,
                "note": "Ajustado",
            }

    monkeypatch.setattr(dialogs_module, "BalanceAdjustmentDialog", FakeBalanceAdjustmentDialog)

    view = views_module.TransactionsView(db)
    try:
        view.refresh()
        view._table.selectRow(0)
        view._table.setCurrentCell(0, 0)

        view._on_edit()

        updated = db.transaction.get(int(adjustment["id"]))
        assert updated is not None
        assert updated["payment_method"] == "balance_adjustment"
        assert updated["note"] == "Ajustado"
        assert updated["amount"] == pytest.approx(35.0)
    finally:
        view.close()


def test_transactions_view_blocks_duplicate_for_balance_adjustments(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.transactions")

    account = db.account.create("Banco", "bank", 100.0, "USD")
    db.transaction.record_balance_adjustment(account["id"], 20.0, tx_date="2026-06-01")
    notifications: list[tuple[str, str]] = []
    monkeypatch.setattr(views_module, "_notify_info", lambda _w, title, message: notifications.append((title, message)))

    view = views_module.TransactionsView(db)
    try:
        view.refresh()
        view._table.selectRow(0)
        view._table.setCurrentCell(0, 0)

        view._on_duplicate()

        assert notifications
        assert len(db.transaction.list(limit=10)) == 1
    finally:
        view.close()
