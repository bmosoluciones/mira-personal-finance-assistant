# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from mira.db.database import Database
from mira.db.errors import DuplicateCategoryNameError


def _get_qapplication_or_xfail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        qtwidgets = importlib.import_module("PySide6.QtWidgets")
    except (ImportError, OSError) as exc:
        pytest.xfail(f"Qt runtime unavailable for categories view test: {exc}")

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "categories-view.db")
    database.connect()
    yield database
    database.close()


def _find_item_by_category_id(tree, category_id: int):
    qtcore = importlib.import_module("PySide6.QtCore")
    pending = [tree.topLevelItem(index) for index in range(tree.topLevelItemCount())]
    while pending:
        item = pending.pop(0)
        if item.data(0, qtcore.Qt.ItemDataRole.UserRole) == category_id:
            return item
        pending.extend(item.child(index) for index in range(item.childCount()))
    return None


def test_categories_view_refresh_uses_report_category_transaction_counts(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.categories")

    food = db.category.create("Food", "expense")

    monkeypatch.setattr(db.report, "category_transaction_counts", lambda **_kwargs: {"Food": 7})
    monkeypatch.setattr(
        db.transaction,
        "list",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy transaction listing should not be used")),
    )

    view = views_module.CategoriesView(db)

    try:
        item = _find_item_by_category_id(view._expense_table, int(food["id"]))
        assert item is not None
        assert item.text(1) == "7"
    finally:
        view.close()


def test_parent_categories_show_expand_collapse_indicator(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.categories")

    parent = db.category.create("Visual Parent", "income", icon="P")
    db.category.create("Visual Child", "income", parent_id=parent["id"], icon="C")

    view = views_module.CategoriesView(db)

    try:
        view.refresh()
        app.processEvents()

        item = _find_item_by_category_id(view._income_table, int(parent["id"]))
        assert item is not None
        assert item.text(0).startswith("[-] ")

        view._income_table.collapseItem(item)
        app.processEvents()
        assert item.text(0).startswith("[+] ")

        view._income_table.expandItem(item)
        app.processEvents()
        assert item.text(0).startswith("[-] ")
    finally:
        view.close()


def test_category_tree_uses_single_click_for_expand_collapse(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.categories")
    qtcore = importlib.import_module("PySide6.QtCore")
    qtest = importlib.import_module("PySide6.QtTest")

    parent = db.category.create("Click Parent", "expense")
    db.category.create("Click Child", "expense", parent_id=parent["id"])

    view = views_module.CategoriesView(db)

    try:
        view.show()
        view.refresh()
        app.processEvents()

        tree = view._expense_table
        item = _find_item_by_category_id(tree, int(parent["id"]))
        assert item is not None
        assert tree.itemsExpandable() is True
        assert tree.expandsOnDoubleClick() is False
        assert item.isExpanded() is True

        click_point = tree.visualItemRect(item).center()
        qtest.QTest.mouseClick(
            tree.viewport(),
            qtcore.Qt.MouseButton.LeftButton,
            qtcore.Qt.KeyboardModifier.NoModifier,
            click_point,
        )
        app.processEvents()
        assert item.isExpanded() is False

        qtest.QTest.mouseClick(
            tree.viewport(),
            qtcore.Qt.MouseButton.LeftButton,
            qtcore.Qt.KeyboardModifier.NoModifier,
            click_point,
        )
        app.processEvents()
        assert item.isExpanded() is True
    finally:
        view.close()


def test_first_visible_category_uses_single_click_for_expand_collapse(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.categories")
    qtcore = importlib.import_module("PySide6.QtCore")
    qtest = importlib.import_module("PySide6.QtTest")

    first_parent = db.category.create("Alpha Parent", "expense")
    db.category.create("Alpha Child", "expense", parent_id=first_parent["id"])
    second_parent = db.category.create("Beta Parent", "expense")
    db.category.create("Beta Child", "expense", parent_id=second_parent["id"])

    view = views_module.CategoriesView(db)

    try:
        view.show()
        view.refresh()
        app.processEvents()

        tree = view._expense_table
        first_item = tree.topLevelItem(0)
        assert first_item is not None
        assert first_item.data(0, qtcore.Qt.ItemDataRole.UserRole) == int(first_parent["id"])
        assert first_item.isExpanded() is True

        click_point = tree.visualItemRect(first_item).center()
        qtest.QTest.mouseClick(
            tree.viewport(),
            qtcore.Qt.MouseButton.LeftButton,
            qtcore.Qt.KeyboardModifier.NoModifier,
            click_point,
        )
        app.processEvents()
        assert first_item.isExpanded() is False

        qtest.QTest.mouseClick(
            tree.viewport(),
            qtcore.Qt.MouseButton.LeftButton,
            qtcore.Qt.KeyboardModifier.NoModifier,
            click_point,
        )
        app.processEvents()
        assert first_item.isExpanded() is True
        assert tree.currentItem() == first_item
    finally:
        view.close()


def test_category_dialog_uses_icon_dropdown(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    dialog = dialogs_module.CategoryDialog(db)
    existing = dialogs_module.CategoryDialog(
        db,
        category={"id": 99, "name": "Viajes", "type": "expense", "color": "#445566", "icon": "🧪", "parent_id": None},
    )

    try:
        assert not hasattr(dialog, "_icon_edit")
        assert dialog._icon_combo.isEditable() is False
        assert dialog._icon_combo.count() > 5
        assert dialog._icon_combo.findData("🏠") >= 0

        shopping_index = dialog._icon_combo.findData("🛒")
        assert shopping_index >= 0
        dialog._icon_combo.setCurrentIndex(shopping_index)
        assert dialog.get_data()["icon"] == "🛒"

        assert existing._icon_combo.findData("🧪") >= 0
        assert existing._icon_combo.currentText() == "🧪"
        assert existing.get_data()["icon"] == "🧪"
    finally:
        dialog.close()
        existing.close()


def test_category_dialog_uses_color_picker(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")
    qtgui = importlib.import_module("PySide6.QtGui")

    monkeypatch.setattr(
        dialogs_module.QColorDialog,
        "getColor",
        lambda *args, **kwargs: qtgui.QColor("#123456"),
    )

    dialog = dialogs_module.CategoryDialog(db)

    try:
        dialog._choose_color()

        assert not hasattr(dialog, "_color_edit")
        assert dialog.get_data()["color"] == "#123456"
        assert dialog._color_value_label.text() == "#123456"
    finally:
        dialog.close()


def test_category_dialog_filters_parent_options_by_type_and_excludes_current_category(
    monkeypatch: pytest.MonkeyPatch,
    db: Database,
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    expense_parent = db.category.create("Housing", "expense")
    expense_child = db.category.create("Rent", "expense", parent_id=expense_parent["id"])
    expense_current = db.category.create("Food", "expense")
    income_parent = db.category.create("Salary", "income")

    dialog = dialogs_module.CategoryDialog(
        db,
        category={
            "id": int(expense_current["id"]),
            "name": "Food",
            "type": "expense",
            "color": "#445566",
            "icon": "",
            "parent_id": None,
        },
    )

    try:
        expense_parent_ids = {dialog._parent_combo.itemData(index) for index in range(dialog._parent_combo.count())}
        assert None in expense_parent_ids
        assert int(expense_parent["id"]) in expense_parent_ids
        assert int(expense_child["id"]) not in expense_parent_ids
        assert int(income_parent["id"]) not in expense_parent_ids
        assert int(expense_current["id"]) not in expense_parent_ids

        income_index = dialog._type_combo.findData("income")
        assert income_index >= 0
        dialog._type_combo.setCurrentIndex(income_index)
        app.processEvents()

        income_parent_ids = {dialog._parent_combo.itemData(index) for index in range(dialog._parent_combo.count())}
        assert None in income_parent_ids
        assert int(income_parent["id"]) in income_parent_ids
        assert int(expense_parent["id"]) not in income_parent_ids
        assert int(expense_child["id"]) not in income_parent_ids
        assert int(expense_current["id"]) not in income_parent_ids
    finally:
        dialog.close()


def test_category_dialog_create_only_lists_root_categories_as_parents(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    parent = db.category.create("Utilities", "expense")
    child = db.category.create("Power", "expense", parent_id=parent["id"])

    dialog = dialogs_module.CategoryDialog(db, default_type="expense")

    try:
        parent_ids = {dialog._parent_combo.itemData(index) for index in range(dialog._parent_combo.count())}
        assert int(parent["id"]) in parent_ids
        assert int(child["id"]) not in parent_ids
    finally:
        dialog.close()


def test_categories_view_delete_confirmation_warns_that_action_is_irreversible(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.categories")
    qtwidgets = importlib.import_module("PySide6.QtWidgets")

    category = db.category.create("Food", "expense")
    prompts: list[tuple[str, str]] = []

    def _fake_question(_parent, title, message, *_args, **_kwargs):
        prompts.append((str(title), str(message)))
        return qtwidgets.QMessageBox.StandardButton.No

    monkeypatch.setattr(
        qtwidgets.QMessageBox,
        "question",
        _fake_question,
    )

    view = views_module.CategoriesView(db)
    try:
        view.refresh()
        app.processEvents()

        item = _find_item_by_category_id(view._expense_table, int(category["id"]))
        assert item is not None
        view._expense_table.setCurrentItem(item)
        view._on_delete("expense")

        assert prompts == [
            (
                view._t("categories.delete.title", "Delete Category"),
                view._t(
                    "categories.delete.body",
                    "Delete category '{name}'?\n\nThis action cannot be undone.",
                    params={"name": category["name"]},
                ),
            )
        ]
        assert db.category.get(int(category["id"])) is not None
    finally:
        view.close()


def test_categories_view_add_maps_duplicate_domain_error(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.categories")
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    class _Dialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, _db, default_type=None, parent=None):
            self._default_type = default_type

        def exec(self):
            return self.DialogCode.Accepted

        def get_data(self):
            return {
                "name": "Cafe",
                "cat_type": self._default_type or "expense",
                "color": "#445566",
                "icon": "",
                "parent_id": None,
            }

    captured: list[tuple[str, str]] = []
    refresh_calls: list[str] = []

    monkeypatch.setattr(dialogs_module, "CategoryDialog", _Dialog)
    monkeypatch.setattr(
        views_module, "_notify_warning", lambda _parent, title, message: captured.append((title, message))
    )

    view = views_module.CategoriesView(db)
    try:
        monkeypatch.setattr(view, "refresh", lambda: refresh_calls.append("refresh"))
        monkeypatch.setattr(
            db.category,
            "create",
            lambda *args, **kwargs: (_ for _ in ()).throw(DuplicateCategoryNameError("dup")),
        )

        view._on_add("expense")

        assert captured == [("Validation", "Category already exists.")]
        assert refresh_calls == []
    finally:
        view.close()


def test_categories_view_edit_maps_duplicate_domain_error_without_find_by_name(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.categories")
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    class _Dialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, _db, category=None, parent=None):
            self._category = category or {}

        def exec(self):
            return self.DialogCode.Accepted

        def get_data(self):
            return {
                "name": "Duplicated",
                "cat_type": self._category.get("type", "expense"),
                "color": "#445566",
                "icon": "",
                "parent_id": None,
            }

    selected = {"id": 7, "name": "Original", "type": "expense", "color": "#112233", "icon": "", "parent_id": None}
    captured: list[tuple[str, str]] = []
    refresh_calls: list[str] = []

    monkeypatch.setattr(dialogs_module, "CategoryDialog", _Dialog)
    monkeypatch.setattr(
        views_module, "_notify_warning", lambda _parent, title, message: captured.append((title, message))
    )

    view = views_module.CategoriesView(db)
    try:
        monkeypatch.setattr(view, "refresh", lambda: refresh_calls.append("refresh"))
        monkeypatch.setattr(view, "_selected_category", lambda _cat_type: selected)
        monkeypatch.setattr(
            db.category,
            "find_by_name",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("find_by_name should not be called")),
        )
        monkeypatch.setattr(
            db.category,
            "update",
            lambda *args, **kwargs: (_ for _ in ()).throw(DuplicateCategoryNameError("dup")),
        )

        view._on_edit("expense")

        assert captured == [("Validation", "Category already exists.")]
        assert refresh_calls == []
    finally:
        view.close()


def test_categories_view_edit_shows_validation_warning_for_value_error(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.categories")
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    class _Dialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, _db, category=None, parent=None):
            self._category = category or {}

        def exec(self):
            return self.DialogCode.Accepted

        def get_data(self):
            return {
                "name": self._category.get("name", "Original"),
                "cat_type": self._category.get("type", "expense"),
                "color": "#445566",
                "icon": "",
                "parent_id": None,
            }

    selected = {"id": 9, "name": "Original", "type": "expense", "color": "#112233", "icon": "", "parent_id": None}
    captured: list[tuple[str, str]] = []
    refresh_calls: list[str] = []

    monkeypatch.setattr(dialogs_module, "CategoryDialog", _Dialog)
    monkeypatch.setattr(
        views_module, "_notify_warning", lambda _parent, title, message: captured.append((title, message))
    )

    view = views_module.CategoriesView(db)
    try:
        monkeypatch.setattr(view, "refresh", lambda: refresh_calls.append("refresh"))
        monkeypatch.setattr(view, "_selected_category", lambda _cat_type: selected)
        monkeypatch.setattr(
            db.category,
            "update",
            lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad parent")),
        )

        view._on_edit("expense")

        assert captured == [("Validation", "bad parent")]
        assert refresh_calls == []
    finally:
        view.close()
