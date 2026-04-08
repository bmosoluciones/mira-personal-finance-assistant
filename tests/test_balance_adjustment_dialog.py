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
        pytest.xfail(f"Qt runtime unavailable for balance adjustment dialog test: {exc}")

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "balance-adjustment-dialog.db")
    database.connect()
    database.setting.set("language", "es")
    yield database
    database.close()


def test_balance_adjustment_dialog_updates_preview_in_real_time(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")
    qtcore = importlib.import_module("PySide6.QtCore")

    account = db.account.create("Banco", "bank", 100.0, "USD")
    db.transaction.create(account_id=account["id"], tx_type="income", amount=25.0, tx_date="2026-04-03")

    dialog = dialogs_module.BalanceAdjustmentDialog(db, account_id=int(account["id"]))
    try:
        dialog._date_edit.setDate(qtcore.QDate(2026, 4, 2))
        dialog._signed_amount_spin.setValue(10.0)
        dialog._refresh_preview()

        assert dialog._currency_value.text() == "USD"
        assert dialog._balance_as_of_value.text() == "USD 100.00"
        assert dialog._projected_balance_value.text() == "USD 110.00"
    finally:
        dialog.close()


def test_balance_adjustment_dialog_edit_mode_excludes_current_adjustment_from_preview(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    account = db.account.create("Banco", "bank", 100.0, "USD")
    adjustment = db.transaction.record_balance_adjustment(account["id"], 25.0, tx_date="2026-04-01")
    db.transaction.create(account_id=account["id"], tx_type="expense", amount=10.0, tx_date="2026-04-03")

    dialog = dialogs_module.BalanceAdjustmentDialog(db, tx=adjustment)
    try:
        assert dialog._signed_amount_spin.value() == pytest.approx(25.0)
        assert dialog._balance_as_of_value.text() == "USD 100.00"
        assert dialog._projected_balance_value.text() == "USD 125.00"
    finally:
        dialog.close()


def test_balance_adjustment_dialog_warns_before_account_creation_and_requires_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")
    qtcore = importlib.import_module("PySide6.QtCore")
    qtwidgets = importlib.import_module("PySide6.QtWidgets")

    account = db.account.create("Banco", "bank", 100.0, "USD")
    dialog = dialogs_module.BalanceAdjustmentDialog(db, account_id=int(account["id"]))
    accepted: list[bool] = []
    questions: list[str] = []

    try:
        dialog._date_edit.setDate(qtcore.QDate(2000, 1, 1))
        dialog._signed_amount_spin.setValue(5.0)
        dialog._refresh_preview()

        monkeypatch.setattr(
            qtwidgets.QMessageBox,
            "question",
            lambda *_args, **_kwargs: questions.append(str(_args[2])) or qtwidgets.QMessageBox.StandardButton.No,
        )
        monkeypatch.setattr(dialog, "accept", lambda: accepted.append(True))

        dialog._on_accept()
        assert questions
        assert accepted == []

        monkeypatch.setattr(
            qtwidgets.QMessageBox,
            "question",
            lambda *_args, **_kwargs: qtwidgets.QMessageBox.StandardButton.Yes,
        )
        dialog._on_accept()
        assert accepted == [True]
    finally:
        dialog.close()
