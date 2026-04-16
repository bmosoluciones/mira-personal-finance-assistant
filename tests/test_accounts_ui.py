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
    prompts: list[tuple[str, str]] = []

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
        lambda _parent, title, message, *_args, **_kwargs: prompts.append((str(title), str(message)))
        or qtwidgets.QMessageBox.StandardButton.Yes,
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
        assert prompts == [
            ("Eliminar cuenta", "¿Eliminar la cuenta 'Wallet Premium'?\n\nEsta acción no se puede revertir.")
        ]
    finally:
        view.close()


def test_accounts_view_transfer_shortcuts_reuse_existing_transfer_dialog(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.accounts")
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    source = db.account.create("Banco", "bank", 500.0, "USD")
    destination = db.account.create("Ahorro", "bank", 50.0, "USD")
    credit = db.account.create("Visa", "credit", -25.0, "USD")
    valid_tx_date = credit["created_at"].strftime("%Y-%m-%d")
    dialog_calls: list[bool] = []

    class FakeTransferDialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, _db: Database, parent=None, *, credit_payment: bool = False) -> None:
            del parent
            self._credit_payment = credit_payment
            dialog_calls.append(credit_payment)

        def exec(self) -> int:
            return self.DialogCode.Accepted

        def get_data(self) -> dict:
            return {
                "from_account_id": source["id"],
                "to_account_id": credit["id"] if self._credit_payment else destination["id"],
                "amount": 20.0,
                "exchange_rate": 1.0,
                "converted_amount": 20.0,
                "tx_date": valid_tx_date,
                "description": "shortcut",
                "note": "nota",
            }

    monkeypatch.setattr(dialogs_module, "TransferDialog", FakeTransferDialog)

    view = views_module.AccountsView(db)
    try:
        view.refresh()
        view.open_transfer_dialog()
        view.open_credit_payment_dialog()

        transfers = [tx for tx in db.transaction.list(limit=20) if int(tx.get("is_transfer") or 0) == 1]
        assert dialog_calls == [False, True]
        assert len(transfers) == 4
    finally:
        view.close()


def test_accounts_view_balance_adjustment_button_records_transaction(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.accounts")
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    account = db.account.create("Banco", "bank", 100.0, "USD")
    cash = db.account.create("Caja", "cash", 20.0, "USD")

    class FakeBalanceAdjustmentDialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, _db: Database, parent=None, *, account_id=None, tx=None, service=None) -> None:
            del parent, tx, service
            self._payload = {
                "account_id": account_id or account["id"],
                "tx_date": "2026-04-01",
                "signed_amount": 35.0,
                "note": "Conciliacion",
            }

        def exec(self) -> int:
            return self.DialogCode.Accepted

        def get_data(self) -> dict:
            return dict(self._payload)

    monkeypatch.setattr(dialogs_module, "BalanceAdjustmentDialog", FakeBalanceAdjustmentDialog)

    view = views_module.AccountsView(db)

    try:
        view.refresh()
        cash_row = _find_row_by_user_role(view._table, int(cash["id"]))
        view._table.selectRow(cash_row)
        view._table.setCurrentCell(cash_row, 0)

        view._on_balance_adjustment()

        updated = db.account.get(int(account["id"]))
        txs = db.transaction.list(limit=10)
        assert updated is not None
        assert updated["balance"] == pytest.approx(135.0)
        assert len(txs) == 1
        assert txs[0]["payment_method"] == "balance_adjustment"
    finally:
        view.close()


def test_account_dialog_set_as_default_checked_when_no_accounts_exist(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    """The 'set as default' checkbox must be pre-checked when no accounts exist yet."""
    _get_qapplication_or_xfail(monkeypatch)
    # Remove the bootstrap "General" account so the DB is empty.
    for acc in db.account.list():
        db.account.delete(int(acc["id"]))

    dialogs_module = importlib.import_module("mira.ui.dialogs")
    dialog = dialogs_module.AccountDialog(db)
    try:
        assert dialog._set_default_chk is not None
        assert dialog._set_default_chk.isChecked() is True
        data = dialog.get_data()
        assert data.get("set_as_default") is True
    finally:
        dialog.close()


def test_account_dialog_set_as_default_unchecked_when_accounts_already_exist(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    """The checkbox must default to unchecked when there are already accounts in the DB."""
    _get_qapplication_or_xfail(monkeypatch)
    # The fixture DB already has a 'General' bootstrap account.
    dialogs_module = importlib.import_module("mira.ui.dialogs")
    dialog = dialogs_module.AccountDialog(db)
    try:
        assert dialog._set_default_chk is not None
        assert dialog._set_default_chk.isChecked() is False
    finally:
        dialog.close()


def test_account_dialog_no_set_as_default_in_edit_mode(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    """The 'set as default' checkbox must NOT appear when editing an existing account."""
    _get_qapplication_or_xfail(monkeypatch)
    account = db.account.get_or_create("Test Account")

    dialogs_module = importlib.import_module("mira.ui.dialogs")
    dialog = dialogs_module.AccountDialog(db, account=account)
    try:
        assert dialog._set_default_chk is None
        data = dialog.get_data()
        assert "set_as_default" not in data
    finally:
        dialog.close()


def test_accounts_view_create_account_with_set_as_default(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    """Adding an account via the view with set_as_default=True makes it the new default."""
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.accounts")
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    class FakeAccountDialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exec(self) -> int:
            return self.DialogCode.Accepted

        def get_data(self) -> dict:
            return {
                "name": "New Default",
                "account_type": "bank",
                "opening_balance": 0.0,
                "currency": "USD",
                "set_as_default": True,
            }

    monkeypatch.setattr(dialogs_module, "AccountDialog", FakeAccountDialog)

    view = views_module.AccountsView(db)
    try:
        view._on_add()
        defaults = [a for a in db.account.list() if a["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["name"] == "New Default"
    finally:
        view.close()
