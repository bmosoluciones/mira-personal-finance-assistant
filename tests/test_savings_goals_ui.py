# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

# SPDX-FileCopyrightText: 2026 BMO Soluciones, S.A.

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
        pytest.xfail(f"Qt runtime unavailable for savings goals UI test: {exc}")

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


def _find_item_by_category_id(tree, category_id: int):
    qtcore = importlib.import_module("PySide6.QtCore")
    pending = [tree.topLevelItem(index) for index in range(tree.topLevelItemCount())]
    while pending:
        item = pending.pop(0)
        if item.data(0, qtcore.Qt.ItemDataRole.UserRole) == category_id:
            return item
        pending.extend(item.child(index) for index in range(item.childCount()))
    return None


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "savings-goals-ui.db")
    database.connect()
    yield database
    database.close()


def test_savings_goal_dialog_notice_updates_on_create(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    dialog = dialogs_module.SavingsGoalDialog(db)

    try:
        initial_notice = dialog._notice_lbl.text()
        assert "Savings Goals" in initial_notice

        dialog._name_edit.setText("Vacation Fund")
        app.processEvents()

        assert "Vacation Fund" in dialog._notice_lbl.text()
    finally:
        dialog.close()


def test_savings_goal_dialog_notice_updates_on_edit(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")
    goal = db.savings_goal.create("Original Goal", 500.0, "2026-12-31")

    dialog = dialogs_module.SavingsGoalDialog(db, goal=goal)

    try:
        dialog._name_edit.setText("Updated Goal")
        app.processEvents()

        notice = dialog._notice_lbl.text()
        assert "Updated Goal" in notice
        assert "not renamed" in notice
    finally:
        dialog.close()


def test_savings_goal_dialog_prefills_amount_and_target_date(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    dialog = dialogs_module.SavingsGoalDialog(
        db,
        prefill={
            "target_amount": 4321.75,
            "target_date": "2029-08-15",
        },
    )

    try:
        assert dialog._target_spin.value() == pytest.approx(4321.75)
        assert dialog._date_edit.date().toString("yyyy-MM-dd") == "2029-08-15"
    finally:
        dialog.close()


def test_savings_goals_view_shows_warning_on_add_collision(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.savings_goals")
    dialogs_module = importlib.import_module("mira.ui.dialogs")
    qtwidgets = importlib.import_module("PySide6.QtWidgets")

    db.category.create("Conflicting Goal", "income")
    warnings: list[str] = []

    class DummySavingsGoalDialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exec(self) -> int:
            return self.DialogCode.Accepted

        def get_data(self) -> dict:
            return {
                "name": "Conflicting Goal",
                "target_amount": 100.0,
                "target_date": "2026-12-31",
            }

    monkeypatch.setattr(dialogs_module, "SavingsGoalDialog", DummySavingsGoalDialog)
    monkeypatch.setattr(
        qtwidgets.QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(str(message)) or qtwidgets.QMessageBox.StandardButton.Ok,
    )

    view = views_module.SavingsGoalsView(db)
    try:
        view._on_add()
        assert warnings
        assert "not an expense category" in warnings[0]
        assert db.savings_goal.find_by_name("Conflicting Goal") is None
    finally:
        view.close()


def test_savings_goals_view_passes_prefill_to_add_dialog(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.savings_goals")
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    captured_prefill: list[dict | None] = []

    class DummySavingsGoalDialog:
        class DialogCode:
            Accepted = 1
            Rejected = 0

        def __init__(self, _db: Database, goal: dict | None = None, prefill: dict | None = None, parent=None) -> None:
            captured_prefill.append(prefill)

        def exec(self) -> int:
            return self.DialogCode.Rejected

    monkeypatch.setattr(dialogs_module, "SavingsGoalDialog", DummySavingsGoalDialog)

    view = views_module.SavingsGoalsView(db)
    try:
        prefill = {"target_amount": 2500.0, "target_date": "2027-02-14"}
        view.open_add_dialog(prefill=prefill)
        assert captured_prefill == [prefill]
    finally:
        view.close()


def test_savings_goals_view_shows_warning_when_delete_is_blocked(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.savings_goals")
    qtwidgets = importlib.import_module("PySide6.QtWidgets")

    acc = db.account.get_or_create("General")
    goal = db.savings_goal.create("Protected UI Goal", 800.0)
    db.transaction.create(
        account_id=acc["id"],
        tx_type="expense",
        amount=60.0,
        description="protected",
        category="Protected UI Goal",
    )
    warnings: list[str] = []

    monkeypatch.setattr(
        qtwidgets.QMessageBox,
        "question",
        lambda *_args, **_kwargs: qtwidgets.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        qtwidgets.QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(str(message)) or qtwidgets.QMessageBox.StandardButton.Ok,
    )

    view = views_module.SavingsGoalsView(db)
    try:
        view.refresh()
        view._selected_id = int(goal["id"])
        view._on_delete()

        assert warnings
        assert "transaction history" in warnings[0]
        assert db.savings_goal.get(goal["id"])["name"] == "Protected UI Goal"
    finally:
        view.close()


def test_savings_goals_view_delete_confirmation_warns_that_action_is_irreversible(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.savings_goals")
    qtwidgets = importlib.import_module("PySide6.QtWidgets")

    goal = db.savings_goal.create("Vacation", 800.0)
    prompts: list[tuple[str, str]] = []

    monkeypatch.setattr(
        qtwidgets.QMessageBox,
        "question",
        lambda _parent, title, message, *_args, **_kwargs: prompts.append((str(title), str(message)))
        or qtwidgets.QMessageBox.StandardButton.No,
    )

    view = views_module.SavingsGoalsView(db)
    try:
        view.refresh()
        view._selected_id = int(goal["id"])
        view._on_delete()

        assert prompts == [
            (
                views_module._tr_db(db, "goals.delete.title", "Delete Goal"),
                views_module._tr_db(
                    db,
                    "goals.delete.body",
                    "Delete savings goal '{name}'?\n\nThis action cannot be undone.",
                    params={"name": goal["name"]},
                ),
            )
        ]
        assert db.savings_goal.get(int(goal["id"])) is not None
    finally:
        view.close()


def test_categories_view_shows_warning_when_linked_category_delete_is_blocked(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.categories")
    qtwidgets = importlib.import_module("PySide6.QtWidgets")

    db.savings_goal.create("Protected Category", 450.0)
    category = db.category.find_by_name("Protected Category", "expense")
    warnings: list[str] = []

    monkeypatch.setattr(
        qtwidgets.QMessageBox,
        "question",
        lambda *_args, **_kwargs: qtwidgets.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        qtwidgets.QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(str(message)) or qtwidgets.QMessageBox.StandardButton.Ok,
    )

    view = views_module.CategoriesView(db)
    try:
        view.refresh()
        app.processEvents()

        item = _find_item_by_category_id(view._expense_table, int(category["id"]))
        assert item is not None
        view._expense_table.setCurrentItem(item)
        view._on_delete("expense")

        assert warnings
        assert "cannot be deleted" in warnings[0]
    finally:
        view.close()


def test_contribute_goal_dialog_shows_goal_dropdown_with_multiple_goals(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    """ContributeGoalDialog must expose a goal combobox when multiple goals exist."""
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    goal1 = db.savings_goal.create("Vacation", 1000.0)
    goal2 = db.savings_goal.create("Emergency Fund", 5000.0)

    goals = [goal1, goal2]
    dialog = dialogs_module.ContributeGoalDialog(
        db,
        goal_name="Vacation",
        goals=goals,
        selected_goal_id=int(goal1["id"]),
    )
    try:
        assert dialog._goal_combo is not None
        assert dialog._goal_combo.count() == 2
        # The first goal must be pre-selected.
        assert dialog._goal_combo.currentText() == "Vacation"
    finally:
        dialog.close()


def test_contribute_goal_dialog_preselects_by_goal_name_fallback(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    """When selected_goal_id is None the dialog falls back to matching by name."""
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    goal1 = db.savings_goal.create("Trip", 800.0)
    goal2 = db.savings_goal.create("Car", 3000.0)
    goals = [goal1, goal2]

    dialog = dialogs_module.ContributeGoalDialog(
        db,
        goal_name="Car",
        goals=goals,
        selected_goal_id=None,
    )
    try:
        assert dialog._goal_combo.currentText() == "Car"
    finally:
        dialog.close()


def test_contribute_goal_dialog_no_dropdown_for_single_call(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    """ContributeGoalDialog without a goals list must not show a goal combobox."""
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    dialog = dialogs_module.ContributeGoalDialog(db, goal_name="Solo Goal")
    try:
        assert dialog._goal_combo is None
        data = dialog.get_data()
        assert "goal_id" not in data
    finally:
        dialog.close()


def test_contribute_goal_dialog_returns_selected_goal_id(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    """get_data() must include goal_id matching the selected combobox entry."""
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    goal1 = db.savings_goal.create("Alpha", 200.0)
    goal2 = db.savings_goal.create("Beta", 400.0)
    goals = [goal1, goal2]

    dialog = dialogs_module.ContributeGoalDialog(
        db,
        goal_name="Beta",
        goals=goals,
        selected_goal_id=int(goal2["id"]),
    )
    try:
        dialog._goal_combo.setCurrentIndex(1)  # select Beta
        data = dialog.get_data()
        assert data["goal_id"] == goal2["id"]
    finally:
        dialog.close()
