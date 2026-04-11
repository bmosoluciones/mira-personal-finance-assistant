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
        pytest.xfail(f"Qt runtime unavailable for transaction dialog test: {exc}")

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "transaction-dialog.db")
    database.connect()
    yield database
    database.close()


def test_transaction_dialog_wraps_form_in_scroll_area_and_keeps_footer_fixed(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")
    qtcore = importlib.import_module("PySide6.QtCore")
    qtwidgets = importlib.import_module("PySide6.QtWidgets")

    db.account.get_or_create("General")
    db.category.create("Food", "expense")

    dialog = dialogs_module.TransactionDialog(db)

    try:
        assert isinstance(dialog._form_scroll, qtwidgets.QScrollArea)
        assert dialog._form_scroll.verticalScrollBarPolicy() == qtcore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        assert dialog._form_scroll.horizontalScrollBarPolicy() == qtcore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert dialog._form_scroll.widget() is dialog._scroll_content
        assert dialog._save_button.parentWidget() is dialog._footer_widget
        assert dialog._cancel_button.parentWidget() is dialog._footer_widget
        assert dialog._save_button.parentWidget() is not dialog._scroll_content
    finally:
        dialog.close()
