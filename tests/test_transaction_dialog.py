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


def test_transaction_dialog_minimum_width_is_at_least_720(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    db.account.get_or_create("General")
    dialog = dialogs_module.TransactionDialog(db)
    try:
        assert dialog.minimumWidth() >= 720
    finally:
        dialog.close()


def test_transaction_dialog_category_combo_is_searchable(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")
    qtwidgets = importlib.import_module("PySide6.QtWidgets")

    db.account.get_or_create("General")
    db.category.create("Food", "expense")
    db.category.create("Transport", "expense")

    dialog = dialogs_module.TransactionDialog(db)
    try:
        assert dialog._category_combo.isEditable()
        assert dialog._category_combo.insertPolicy() == qtwidgets.QComboBox.InsertPolicy.NoInsert
        completer = dialog._category_combo.completer()
        assert completer is not None
    finally:
        dialog.close()


def test_transaction_dialog_amount_spin_accepts_formula_via_fixup(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    db.account.get_or_create("General")
    dialog = dialogs_module.TransactionDialog(db)
    try:
        spin = dialog._amount_spin
        from mira.ui.number_format import FormulaAmountEdit

        assert isinstance(spin, FormulaAmountEdit)

        # Fixup should evaluate the formula and return a formatted number string.
        result = spin.fixup("$=100+50")
        # The result should be the prefix + formatted value + suffix.
        assert "150" in result

        # Zero-result formula (=50-50) should fall back to the current value.
        spin.setValue(42.0)
        fallback = spin.fixup("$=50-50")
        assert "42" in fallback

        # Negative-result formula (=10-20) should also fall back.
        fallback_neg = spin.fixup("$=10-20")
        assert "42" in fallback_neg
    finally:
        dialog.close()
