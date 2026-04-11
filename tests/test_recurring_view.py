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
        pytest.xfail(f"Qt runtime unavailable for recurring view test: {exc}")

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "recurring-view.db")
    database.connect()
    database.setting.set("language", "es")
    yield database
    database.close()


def test_recurring_view_warns_when_apply_is_requested_without_rules(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.recurring")

    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        views_module, "_notify_warning", lambda _parent, title, message: warnings.append((title, message))
    )

    class _DialogShouldNotOpen:
        def __init__(self, *_args, **_kwargs) -> None:
            raise AssertionError("apply dialog should not open when there are no recurring rules")

    monkeypatch.setattr(views_module, "_RecurringApplyDialog", _DialogShouldNotOpen)

    view = views_module.RecurringView(db)
    try:
        view.refresh()
        view._on_apply()

        assert warnings == [
            (
                "Aplicar transacciones recurrentes",
                "Primero debes crear transacciones recurrentes antes de aplicarlas al mes.",
            )
        ]
    finally:
        view.close()


def test_recurring_view_reports_already_applied_when_rules_exist(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.recurring")

    account = db.account.get_or_create("General")
    category = db.category.create("Internet", "expense")
    db.recurring.create(
        account_id=account["id"],
        tx_type="expense",
        amount=40.0,
        description="Internet",
        category=None,
        category_id=category["id"],
        tag_ids=[],
        note="monthly",
        day_of_month=5,
    )

    infos: list[tuple[str, str]] = []
    monkeypatch.setattr(views_module, "_notify_info", lambda _parent, title, message: infos.append((title, message)))

    class _Dialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exec(self) -> int:
            return self.DialogCode.Accepted

        def get_period(self) -> tuple[int, int]:
            return 2026, 4

    monkeypatch.setattr(views_module, "_RecurringApplyDialog", _Dialog)

    view = views_module.RecurringView(db)
    try:
        view.refresh()
        view._on_apply()
        view._on_apply()

        assert infos[0] == ("Applied", "Created 1 recurring transaction(s) for 2026-04.")
        assert infos[1] == ("Already Applied", "Recurring transactions have already been applied for 2026-04.")
    finally:
        view.close()


def test_recurring_view_delete_confirmation_warns_that_action_is_irreversible(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.recurring")
    qtwidgets = importlib.import_module("PySide6.QtWidgets")

    account = db.account.get_or_create("General")
    category = db.category.create("Internet", "expense")
    recurring = db.recurring.create(
        account_id=account["id"],
        tx_type="expense",
        amount=40.0,
        description="Internet",
        category=None,
        category_id=category["id"],
        tag_ids=[],
        note="monthly",
        day_of_month=5,
    )
    prompts: list[tuple[str, str]] = []

    monkeypatch.setattr(
        qtwidgets.QMessageBox,
        "question",
        lambda _parent, title, message, *_args, **_kwargs: prompts.append((str(title), str(message)))
        or qtwidgets.QMessageBox.StandardButton.No,
    )

    view = views_module.RecurringView(db)
    try:
        view.refresh()
        view._table.selectRow(0)
        view._table.setCurrentCell(0, 0)
        view._on_delete()

        assert prompts
        assert prompts[0][0] == "Eliminar transacción recurrente"
        assert "Esta acción no se puede revertir." in prompts[0][1]
        assert db.recurring.get(int(recurring["id"])) is not None
    finally:
        view.close()
