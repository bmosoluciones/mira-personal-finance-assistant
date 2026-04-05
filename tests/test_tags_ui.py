# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import importlib
from datetime import date
from pathlib import Path

import pytest

from mira.db.database import Database
from mira.db.errors import DuplicateTagNameError


def _get_qapplication_or_xfail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        qtwidgets = importlib.import_module("PySide6.QtWidgets")
    except (ImportError, OSError) as exc:
        pytest.xfail(f"Qt runtime unavailable for tags UI test: {exc}")

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "tags-ui.db")
    database.connect()
    database.setting.set("language", "es")
    database.setting.set("onboarding_completed", "1")
    database.setting.set("model_download_offer_shown", "1")
    database.setting.set("theme", "dark_teal.xml")
    yield database
    database.close()


def _find_row_by_user_role(table, value: int) -> int:
    qtcore = importlib.import_module("PySide6.QtCore")
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        if item is not None and item.data(qtcore.Qt.ItemDataRole.UserRole) == value:
            return row
    return -1


class _DummyPipeline:
    def __init__(self) -> None:
        self.llm_ready = False
        self.engine = object()
        self._model_path = None

    def reload_engine(self, model_path: str | None = None) -> None:
        self._model_path = model_path

    def shutdown(self) -> None:
        return None


def test_tags_view_shows_monthly_transaction_counts(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.tags")

    account = db.account.get_or_create("General")
    fixed = db.tag.create("Fijo", color="#336699", icon="F")
    family = db.tag.create("Familia", color="#884422", icon="H")
    today = date.today().isoformat()

    tx1 = db.transaction.create(
        account_id=account["id"], tx_type="expense", amount=25, description="uno", tx_date=today
    )
    tx2 = db.transaction.create(
        account_id=account["id"], tx_type="expense", amount=40, description="dos", tx_date=today
    )
    db.tag.set_for_transaction(tx1["id"], [fixed["id"], family["id"]])
    db.tag.set_for_transaction(tx2["id"], [fixed["id"]])

    view = views_module.TagsView(db)

    try:
        view.refresh()

        fixed_row = _find_row_by_user_role(view._table, int(fixed["id"]))
        family_row = _find_row_by_user_role(view._table, int(family["id"]))

        assert fixed_row >= 0
        assert family_row >= 0
        assert view._table.item(fixed_row, 1).text() == "2"
        assert view._table.item(family_row, 1).text() == "1"
    finally:
        view.close()


def test_tags_view_refresh_uses_report_tag_transaction_counts(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.tags")

    fixed = db.tag.create("Fijo", color="#336699", icon="F")

    monkeypatch.setattr(db.report, "tag_transaction_counts", lambda **_kwargs: {int(fixed["id"]): 3})
    monkeypatch.setattr(
        db.transaction,
        "list",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy transaction listing should not be used")),
    )

    view = views_module.TagsView(db)

    try:
        fixed_row = _find_row_by_user_role(view._table, int(fixed["id"]))
        assert fixed_row >= 0
        assert view._table.item(fixed_row, 1).text() == "3"
    finally:
        view.close()


def test_tags_view_add_maps_duplicate_domain_error(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.tags")
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    class _Dialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, _db, parent=None):
            return None

        def exec(self):
            return self.DialogCode.Accepted

        def get_data(self):
            return {"name": "Fijo", "color": "#336699", "icon": ""}

    captured: list[tuple[str, str]] = []
    refresh_calls: list[str] = []

    monkeypatch.setattr(dialogs_module, "TagDialog", _Dialog)
    monkeypatch.setattr(
        views_module, "_notify_warning", lambda _parent, title, message: captured.append((title, message))
    )

    view = views_module.TagsView(db)
    try:
        monkeypatch.setattr(view, "refresh", lambda: refresh_calls.append("refresh"))
        monkeypatch.setattr(
            db.tag,
            "create",
            lambda *args, **kwargs: (_ for _ in ()).throw(DuplicateTagNameError("dup")),
        )

        view._on_add()

        assert captured == [("Validación", "La etiqueta ya existe.")]
        assert refresh_calls == []
    finally:
        view.close()


def test_tags_view_edit_maps_duplicate_domain_error_without_find_by_name(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.tags")
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    class _Dialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, _db, tag=None, parent=None):
            self._tag = tag or {}

        def exec(self):
            return self.DialogCode.Accepted

        def get_data(self):
            return {
                "name": "Duplicated",
                "color": self._tag.get("color", "#336699"),
                "icon": self._tag.get("icon", ""),
            }

    selected = {"id": 5, "name": "Original", "color": "#336699", "icon": ""}
    captured: list[tuple[str, str]] = []
    refresh_calls: list[str] = []

    monkeypatch.setattr(dialogs_module, "TagDialog", _Dialog)
    monkeypatch.setattr(
        views_module, "_notify_warning", lambda _parent, title, message: captured.append((title, message))
    )

    view = views_module.TagsView(db)
    try:
        monkeypatch.setattr(view, "refresh", lambda: refresh_calls.append("refresh"))
        monkeypatch.setattr(view, "_selected_tag", lambda: selected)
        monkeypatch.setattr(
            db.tag,
            "find_by_name",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("find_by_name should not be called")),
        )
        monkeypatch.setattr(
            db.tag,
            "update",
            lambda *args, **kwargs: (_ for _ in ()).throw(DuplicateTagNameError("dup")),
        )

        view._on_edit()

        assert captured == [("Validación", "La etiqueta ya existe.")]
        assert refresh_calls == []
    finally:
        view.close()


def test_tags_view_edit_shows_validation_warning_for_value_error(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.tags")
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    class _Dialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, _db, tag=None, parent=None):
            self._tag = tag or {}

        def exec(self):
            return self.DialogCode.Accepted

        def get_data(self):
            return {
                "name": self._tag.get("name", "Original"),
                "color": self._tag.get("color", "#336699"),
                "icon": self._tag.get("icon", ""),
            }

    selected = {"id": 6, "name": "Original", "color": "#336699", "icon": ""}
    captured: list[tuple[str, str]] = []
    refresh_calls: list[str] = []

    monkeypatch.setattr(dialogs_module, "TagDialog", _Dialog)
    monkeypatch.setattr(
        views_module, "_notify_warning", lambda _parent, title, message: captured.append((title, message))
    )

    view = views_module.TagsView(db)
    try:
        monkeypatch.setattr(view, "refresh", lambda: refresh_calls.append("refresh"))
        monkeypatch.setattr(view, "_selected_tag", lambda: selected)
        monkeypatch.setattr(
            db.tag,
            "update",
            lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad icon")),
        )

        view._on_edit()

        assert captured == [("Validación", "bad icon")]
        assert refresh_calls == []
    finally:
        view.close()


def test_transaction_dialog_uses_existing_tags_dropdown(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    home = db.tag.create("Hogar", color="#228833")
    travel = db.tag.create("Viaje", color="#3355AA")
    work = db.tag.create("Trabajo", color="#AA5533")

    dialog = dialogs_module.TransactionDialog(db)

    try:
        assert hasattr(dialog, "_tag_selector")
        assert not hasattr(dialog, "tag_manager_btn")
        assert not hasattr(dialog, "_tags_list")
        assert not hasattr(dialog, "_subcategory_edit")
        assert set(dialog._tag_selector.option_ids()) == {int(home["id"]), int(travel["id"]), int(work["id"])}

        dialog._tag_selector.set_selected_ids([int(home["id"]), int(work["id"])])
        app.processEvents()

        assert set(dialog._get_selected_tag_ids()) == {int(home["id"]), int(work["id"])}
        assert set(dialog.get_data()["tags"]) == {int(home["id"]), int(work["id"])}
    finally:
        dialog.close()


def test_transaction_dialog_uses_category_dropdown_and_places_tags_next_to_it(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    db.category.create("Comida", "expense", icon="F")
    db.tag.create("Hogar", color="#228833")

    dialog = dialogs_module.TransactionDialog(db)

    try:
        assert dialog._category_combo.isEditable() is False
        assert dialog.styleSheet() == ""
        assert "background:" not in dialog._amount_spin.styleSheet().lower()
        assert dialog._classification_form.labelForField(dialog._category_combo).text().startswith("Categor")
        assert dialog._classification_form.labelForField(dialog._tag_selector).text() == "Etiquetas:"

        category_row, _category_role = dialog._classification_form.getWidgetPosition(dialog._category_combo)
        tags_row, _tags_role = dialog._classification_form.getWidgetPosition(dialog._tag_selector)
        assert tags_row == category_row + 1
        dialog.show()
        app.processEvents()
        assert dialog._payment_method_combo.width() > dialog._account_combo.width() * 2
    finally:
        dialog.close()


def test_transaction_dialog_switches_category_list_when_type_changes(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    db.category.create("Comida", "expense", icon="F")
    db.category.create("Salario", "income", icon="S")

    dialog = dialogs_module.TransactionDialog(db)

    try:
        expense_values = {
            dialog._category_combo.itemData(index)
            for index in range(dialog._category_combo.count())
            if dialog._category_combo.itemData(index)
        }
        assert "Comida" in expense_values
        assert "Salario" not in expense_values

        dialog._btn_income.click()
        app.processEvents()

        income_values = {
            dialog._category_combo.itemData(index)
            for index in range(dialog._category_combo.count())
            if dialog._category_combo.itemData(index)
        }
        assert "Salario" in income_values
        assert "Comida" not in income_values
    finally:
        dialog.close()


def test_transaction_dialog_uses_existing_currencies_for_original_currency(
    monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    dialog = dialogs_module.TransactionDialog(db)

    try:
        assert not hasattr(dialog, "_source_currency_edit")
        assert dialog._source_currency_combo.isEditable() is False
        assert dialog._source_currency_combo.findData("USD") >= 0
        assert dialog._source_currency_combo.findData("NIO") >= 0

        dialog._fx_check.setChecked(True)
        dialog._set_source_currency_value("EUR")
        assert dialog.get_data()["base_currency"] == "EUR"
    finally:
        dialog.close()


def test_account_dialog_uses_non_editable_seeded_currency_list(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    db.setting.set("default_currency", "USD")
    dialog = dialogs_module.AccountDialog(db)

    try:
        assert dialog._currency_combo.isEditable() is False
        assert dialog._currency_combo.findData("USD") >= 0
        assert dialog._currency_combo.findData("NIO") >= 0

        usd_idx = dialog._currency_combo.findData("USD")
        dialog._currency_combo.setCurrentIndex(usd_idx)

        assert dialog.get_data()["currency"] == "USD"
    finally:
        dialog.close()


def test_recurring_dialog_uses_existing_tags_dropdown(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    account = db.account.get_or_create("General")
    category = db.category.create("Servicios", "expense")
    home = db.tag.create("Hogar", color="#228833")
    fixed = db.tag.create("Fijo", color="#3355AA")

    dialog = dialogs_module.RecurringDialog(
        db,
        recurring={
            "account_id": account["id"],
            "type": "expense",
            "amount": 25.0,
            "description": "Internet",
            "category_id": category["id"],
            "tag_ids": [int(home["id"])],
            "note": "mensual",
            "day_of_month": 10,
        },
    )

    try:
        assert hasattr(dialog, "_tag_selector")
        assert set(dialog._tag_selector.option_ids()) == {int(home["id"]), int(fixed["id"])}
        assert set(dialog._tag_selector.selected_ids()) == {int(home["id"])}

        dialog._tag_selector.set_selected_ids([int(home["id"]), int(fixed["id"])])
        app.processEvents()

        assert set(dialog.get_data()["tag_ids"]) == {int(home["id"]), int(fixed["id"])}
    finally:
        dialog.close()


def test_tag_selector_toggles_an_item_with_single_click(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    app = _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")
    qtcore = importlib.import_module("PySide6.QtCore")
    qtest = importlib.import_module("PySide6.QtTest")

    home = db.tag.create("Hogar", color="#228833")
    db.tag.create("Viaje", color="#3355AA")

    dialog = dialogs_module.TransactionDialog(db)

    try:
        dialog.show()
        app.processEvents()
        dialog._tag_selector._toggle_popup()
        app.processEvents()

        popup_list = dialog._tag_selector.popup_list()
        first_item = popup_list.item(0)
        click_point = popup_list.visualItemRect(first_item).center()
        qtest.QTest.mouseClick(
            popup_list.viewport(),
            qtcore.Qt.MouseButton.LeftButton,
            qtcore.Qt.KeyboardModifier.NoModifier,
            click_point,
        )
        app.processEvents()

        assert int(first_item.data(qtcore.Qt.ItemDataRole.UserRole)) in dialog._tag_selector.selected_ids()
        assert int(home["id"]) in dialog._tag_selector.option_ids()
    finally:
        dialog.close()


def test_main_window_exposes_tags_in_sidebar_and_menu(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    main_window_module = importlib.import_module("mira.ui.main_window")

    monkeypatch.setattr(main_window_module.MainWindow, "_qt_material_themes", staticmethod(lambda: ["dark_teal.xml"]))
    monkeypatch.setattr(main_window_module.MainWindow, "_apply_theme", staticmethod(lambda _theme: None))
    monkeypatch.setattr(main_window_module.MainWindow, "_run_initial_setup_if_needed", lambda self: None)

    window = main_window_module.MainWindow(db, _DummyPipeline())

    try:
        nav_labels = [window._nav_list.item(index).text() for index in range(window._nav_list.count())]
        menu_labels = [action.text() for action in window.menuBar().actions()]

        assert any("Etiquetas" in label for label in nav_labels)
        assert "Etiquetas" in menu_labels

        window._menu_open_tags()

        assert window._stack.currentWidget() is window._view_tags
        assert window._stack.currentIndex() == main_window_module.MainWindow.VIEW_TAGS
    finally:
        window.close()


def test_tag_dialog_uses_color_picker(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")
    qtgui = importlib.import_module("PySide6.QtGui")

    monkeypatch.setattr(
        dialogs_module.QColorDialog,
        "getColor",
        lambda *args, **kwargs: qtgui.QColor("#123456"),
    )

    dialog = dialogs_module.TagDialog(db)

    try:
        dialog._choose_color()

        assert not hasattr(dialog, "_color_edit")
        assert dialog.get_data()["color"] == "#123456"
        assert dialog._color_value_label.text() == "#123456"
    finally:
        dialog.close()


def test_tag_dialog_uses_icon_dropdown(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    dialog = dialogs_module.TagDialog(db)
    existing = dialogs_module.TagDialog(db, tag={"name": "Viaje", "color": "#445566", "icon": "🧪"})

    try:
        assert not hasattr(dialog, "_icon_edit")
        assert dialog._icon_combo.isEditable() is False
        assert dialog._icon_combo.count() > 5
        assert dialog._icon_combo.findData("🏷️") >= 0

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


def test_tag_dialog_icon_dropdown_localizes_labels_to_english(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    dialogs_module = importlib.import_module("mira.ui.dialogs")

    db.setting.set("language", "en")
    dialog = dialogs_module.TagDialog(db)

    try:
        assert dialog._icon_combo.placeholderText() == "Select an icon"
        assert dialog._icon_combo.findText("🛒 Shopping") >= 0
        assert dialog._icon_combo.findText("🛒 Compras") < 0
    finally:
        dialog.close()


def test_tags_view_shows_color_swatch_instead_of_hex(monkeypatch: pytest.MonkeyPatch, db: Database) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    views_module = importlib.import_module("mira.ui.views.tags")

    tag = db.tag.create("Compras", color="#A1B2C3")
    view = views_module.TagsView(db)

    try:
        view.refresh()

        row = _find_row_by_user_role(view._table, int(tag["id"]))
        assert row >= 0
        assert view._table.item(row, 2).text() == ""
        swatch = view._table.cellWidget(row, 2)
        assert swatch is not None
        assert swatch.layout().itemAt(0).widget().toolTip() == "#A1B2C3"
    finally:
        view.close()
