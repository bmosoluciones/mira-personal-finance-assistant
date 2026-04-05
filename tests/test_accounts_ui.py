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
        pytest.xfail(f"Qt runtime unavailable for accounts UI test: {exc}")

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "accounts-ui.db")
    database.connect()
    database.setting.set("language", "es")
    database.setting.set("onboarding_completed", "1")
    yield database
    database.close()


def _find_row_by_user_role(table, value: int) -> int:
    qtcore = importlib.import_module("PySide6.QtCore")
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        if item is not None and item.data(qtcore.Qt.ItemDataRole.UserRole) == value:
            return row
    return -1


def test_accounts_view_refresh_formats_created_at_without_crashing(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.accounts")

    created = db.account.create("Tarjeta", "credit", -120.0, "USD")
    view = views_module.AccountsView(db)

    try:
        view.refresh()

        row = _find_row_by_user_role(view._table, int(created["id"]))
        assert row >= 0
        assert view._table.item(row, 0).text() == "Tarjeta"
        assert view._table.item(row, 2).text() == "USD"
        assert view._table.item(row, 5).text() == created["created_at"].strftime("%Y-%m-%d")
    finally:
        view.close()


def test_accounts_view_add_edit_set_default_and_delete_keep_table_in_sync(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.accounts")
    dialogs_module = importlib.import_module("mira.ui.dialogs")
    qtwidgets = importlib.import_module("PySide6.QtWidgets")

    class FakeAccountDialog:
        class DialogCode:
            Accepted = 1

        payloads = [
            {
                "name": "Wallet",
                "account_type": "cash",
                "opening_balance": 25.0,
                "currency": "USD",
            },
            {
                "name": "Wallet Premium",
                "account_type": "credit",
                "opening_balance": 0.0,
                "currency": "USD",
            },
        ]
        seen_accounts: list[dict | None] = []

        def __init__(self, _db: Database, account: dict | None = None, parent=None) -> None:
            del parent
            self._account = account
            self._payload = type(self).payloads.pop(0)
            type(self).seen_accounts.append(account)

        def exec(self) -> int:
            return self.DialogCode.Accepted

        def get_data(self) -> dict:
            return dict(self._payload)

    monkeypatch.setattr(dialogs_module, "AccountDialog", FakeAccountDialog)
    monkeypatch.setattr(
        qtwidgets.QMessageBox,
        "question",
        lambda *_args, **_kwargs: qtwidgets.QMessageBox.StandardButton.Yes,
    )

    view = views_module.AccountsView(db)

    try:
        view.refresh()

        view._on_add()

        wallet = db.account.find_by_name("Wallet")
        assert wallet is not None
        wallet_row = _find_row_by_user_role(view._table, int(wallet["id"]))
        assert wallet_row >= 0
        assert view._table.currentRow() == wallet_row
        assert view._table.item(wallet_row, 3).text() == views_module._fmt_amount(db, 25.0)

        view._on_edit()

        updated = db.account.get(int(wallet["id"]))
        assert updated is not None
        assert updated["name"] == "Wallet Premium"
        assert updated["account_type"] == "credit"
        updated_row = _find_row_by_user_role(view._table, int(updated["id"]))
        assert updated_row >= 0
        assert view._table.currentRow() == updated_row
        assert view._table.item(updated_row, 0).text() == "Wallet Premium"
        assert view._table.item(updated_row, 1).text() == views_module._account_type_label(db, "credit")

        view._on_set_default()

        assert db.account.get_default()["id"] == updated["id"]
        assert view._table.item(updated_row, 4).text() == "⭐"

        view._on_delete()

        assert db.account.get(int(updated["id"])) is None
        assert _find_row_by_user_role(view._table, int(updated["id"])) == -1
        assert view._table.rowCount() == len(db.account.list())
        assert FakeAccountDialog.seen_accounts == [None, wallet]
    finally:
        view.close()
