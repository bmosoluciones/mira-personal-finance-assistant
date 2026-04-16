# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Shared dialog helpers for CRUD and setup workflows."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QListWidget,
    QListWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mira.db.database import Database
from mira.ui.i18n import normalize_language, tr
from mira.ui.notifications import show_user_message
from mira.ui.number_format import FormulaAmountEdit, NumberMaskedSpinBox, format_number, get_number_format_config

_TAG_SELECTOR_POPUP_STYLE = "QFrame{border-radius:4px;}"
_TAG_SELECTOR_LIST_STYLE = "QListWidget{border:none;padding:2px;}"
_TAG_SELECTOR_BUTTON_STYLE = "QToolButton{" "border-radius:3px;padding:6px 10px;text-align:left;}"

_TAG_ICON_OPTIONS: list[tuple[str, str]] = [
    ("", "tag.icon.none"),
    ("🏷️", "tag.icon.label"),
    ("⭐", "tag.icon.featured"),
    ("💼", "tag.icon.work"),
    ("🏠", "tag.icon.home"),
    ("🛒", "tag.icon.shopping"),
    ("🚗", "tag.icon.transport"),
    ("✈️", "tag.icon.travel"),
    ("❤️", "tag.icon.health"),
    ("🎉", "tag.icon.leisure"),
    ("🍽️", "tag.icon.food"),
    ("📚", "tag.icon.study"),
    ("💡", "tag.icon.services"),
    ("💰", "tag.icon.savings"),
    ("📌", "tag.icon.priority"),
]

_NOTICE_LABEL_STYLE = "border-radius:6px;padding:8px 10px;"
_SECONDARY_ACTION_BUTTON_STYLE = "QPushButton{border-radius:8px;padding:8px 14px;font-size:16px;}"
_PRIMARY_ACTION_BUTTON_STYLE = "QPushButton{border-radius:8px;padding:8px 14px;font-size:16px;font-weight:600;}"
_INITIAL_SETUP_THEME = "light_blue.xml"


def _resolve_ui_icon_path(filename: str) -> Path:
    """Return resolve ui icon path."""
    here = Path(__file__).resolve()
    candidates = (here.parent.parent / "icons" / filename, here.parent / "icons" / filename)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def _hero_amount_spin_style(color: str) -> str:
    """Return hero amount spin style."""
    return "QDoubleSpinBox{border-radius:10px;" f"padding:12px 16px;font-size:38px;font-weight:700;color:{color};}}"


def _make_amount_spin(db: Database) -> QDoubleSpinBox:
    """Return make amount spin."""
    spin = NumberMaskedSpinBox(db.setting)
    spin.setRange(0.01, 9_999_999.99)
    spin.setDecimals(2)
    spin.setValue(0.00)
    return spin


def _make_formula_amount_spin(db: Database) -> FormulaAmountEdit:
    """Return an amount spinbox that also accepts ``=``-prefixed formulas."""
    spin = FormulaAmountEdit(db.setting)
    spin.setRange(0.01, 9_999_999.99)
    spin.setDecimals(2)
    spin.setValue(0.01)
    return spin


def _notify(widget: QWidget, *args: object, level: str = "warning") -> None:
    """Return notify."""
    if len(args) == 3 and isinstance(args[0], QWidget):
        _, title, message = args
    elif len(args) == 2:
        title, message = args
    else:
        raise TypeError("_notify expects (title, message) or (widget, title, message)")
    show_user_message(widget, str(title), str(message), level=level)


def _notify_warning(widget: QWidget, *args: object) -> None:
    """Return notify warning."""
    _notify(widget, *args, level="warning")


def _make_balance_spin(db: Database) -> QDoubleSpinBox:
    """Return make balance spin."""
    spin = NumberMaskedSpinBox(db.setting)
    spin.setRange(-9_999_999.99, 9_999_999.99)
    spin.setDecimals(2)
    spin.setValue(0.00)
    return spin


def _format_amount_label(db: Database, amount: float, currency: str | None = None) -> str:
    """Return format amount label."""
    formatted = format_number(float(amount), get_number_format_config(db.setting), decimals=2, grouping=True)
    normalized_currency = str(currency or "").strip().upper()
    return f"{normalized_currency} {formatted}" if normalized_currency else formatted


def _make_date_edit(default: date | None = None) -> QDateEdit:
    """Return make date edit."""
    from PySide6.QtCore import QDate

    de = QDateEdit()
    de.setCalendarPopup(True)
    target = default or date.today()
    de.setDate(QDate(target.year, target.month, target.day))
    de.setDisplayFormat("yyyy-MM-dd")
    return de


class _TagListWidget(QListWidget):
    """Single-click checkable list used by the tag dropdown popup."""

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        """Return mousePressEvent."""
        item = self.itemAt(event.position().toPoint())
        if item is not None and item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
            item.setCheckState(
                Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
            )
            event.accept()
            return
        super().mousePressEvent(event)


class _TagMultiSelectButton(QToolButton):
    """Dropdown selector for applying multiple existing tags."""

    selection_changed = Signal()

    def __init__(self, parent: QWidget | None = None, *, lang: str = "en") -> None:
        """Initialize the _TagMultiSelectButton instance."""
        super().__init__(parent)
        self._language = normalize_language(lang)
        self._tags: list[dict] = []
        self._selected_ids: list[int] = []
        self._syncing_list = False
        self._popup = QFrame(None, Qt.WindowType.Popup)
        self._popup.setStyleSheet(_TAG_SELECTOR_POPUP_STYLE)
        popup_layout = QVBoxLayout(self._popup)
        popup_layout.setContentsMargins(6, 6, 6, 6)
        popup_layout.setSpacing(0)
        self._list = _TagListWidget(self._popup)
        self._list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._list.setStyleSheet(_TAG_SELECTOR_LIST_STYLE)
        self._list.itemChanged.connect(self._sync_selection_from_list)
        popup_layout.addWidget(self._list)

        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setArrowType(Qt.ArrowType.DownArrow)
        self.setStyleSheet(_TAG_SELECTOR_BUTTON_STYLE)
        self.clicked.connect(self._toggle_popup)
        self._update_text()

    def set_tags(self, tags: list[dict], selected_ids: list[int] | set[int] | None = None) -> None:
        """Return set tags."""
        self._tags = list(tags)
        valid_ids = {int(tag["id"]) for tag in self._tags}
        if selected_ids is not None:
            self._selected_ids = [int(tag_id) for tag_id in selected_ids if int(tag_id) in valid_ids]
        else:
            self._selected_ids = [tag_id for tag_id in self._selected_ids if tag_id in valid_ids]
        self._rebuild_popup()
        self._update_text()

    def set_selected_ids(self, selected_ids: list[int] | set[int]) -> None:
        """Return set selected ids."""
        valid_ids = {int(tag["id"]) for tag in self._tags}
        self._selected_ids = [int(tag_id) for tag_id in selected_ids if int(tag_id) in valid_ids]
        self._rebuild_popup()
        self._update_text()

    def selected_ids(self) -> list[int]:
        """Return selected ids."""
        return list(self._selected_ids)

    def option_ids(self) -> list[int]:
        """Return option ids."""
        return [int(tag["id"]) for tag in self._tags]

    def popup_list(self) -> QListWidget:
        """Return popup list."""
        return self._list

    def _toggle_popup(self) -> None:
        """Return toggle popup."""
        if self._popup.isVisible():
            self._popup.hide()
            return
        self._rebuild_popup()
        width = max(self.width(), 260)
        row_count = max(1, min(self._list.count(), 8))
        row_height = self._list.sizeHintForRow(0) if self._list.count() else 28
        self._list.setMinimumWidth(width - 12)
        self._list.setMinimumHeight((row_count * max(row_height, 28)) + 8)
        self._popup.adjustSize()
        self._popup.resize(width, self._popup.sizeHint().height())
        self._popup.move(self.mapToGlobal(self.rect().bottomLeft()))
        self._popup.show()
        self._popup.raise_()

    def _rebuild_popup(self) -> None:
        """Return rebuild popup."""
        self._syncing_list = True
        self._list.clear()
        if not self._tags:
            item = QListWidgetItem(tr("dialog.tags.none_available", self._language, default="No tags available"))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(item)
            self._syncing_list = False
            return

        selected_lookup = set(self._selected_ids)
        for tag in self._tags:
            tag_id = int(tag["id"])
            label = f"{tag.get('icon', '')} {tag['name']}".strip()
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, tag_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if tag_id in selected_lookup else Qt.CheckState.Unchecked)
            self._list.addItem(item)
        self._syncing_list = False

    def _sync_selection_from_list(self, _item: QListWidgetItem) -> None:
        """Return sync selection from list."""
        if self._syncing_list:
            return
        selected: list[int] = []
        for row in range(self._list.count()):
            item = self._list.item(row)
            tag_id = item.data(Qt.ItemDataRole.UserRole)
            if tag_id is None:
                continue
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(int(tag_id))
        self._selected_ids = selected
        self._update_text()
        self.selection_changed.emit()

    def _update_text(self) -> None:
        """Return update text."""
        if not self._tags:
            self.setText(tr("dialog.tags.no_options", self._language, default="Tags (no options)"))
            self.setEnabled(False)
            return
        self.setEnabled(True)
        selected_lookup = set(self._selected_ids)
        selected_names = [
            f"{tag.get('icon', '')} {tag['name']}".strip() for tag in self._tags if int(tag["id"]) in selected_lookup
        ]
        if not selected_names:
            self.setText(tr("dialog.tags.select", self._language, default="Tags (select)"))
            return
        if len(selected_names) <= 2:
            self.setText(", ".join(selected_names))
            return
        self.setText(f"{selected_names[0]}, {selected_names[1]} +{len(selected_names) - 2}")


def _build_icon_combo(parent: QWidget | None = None, *, lang: str = "en") -> QComboBox:
    """Return build icon combo."""
    language = normalize_language(lang)
    combo = QComboBox(parent)
    combo.setEditable(False)
    combo.setPlaceholderText(tr("dialog.tags.icon.placeholder", language, default="Select an icon"))
    combo.setCurrentIndex(-1)
    for icon_value, key in _TAG_ICON_OPTIONS:
        label = tr(key, language, default=icon_value)
        combo.addItem(label, icon_value)
    return combo


def _set_icon_combo_value(combo: QComboBox, icon_value: str) -> None:
    """Return set icon combo value."""
    normalized_value = icon_value.strip()
    index = combo.findData(normalized_value)
    if index >= 0:
        combo.setCurrentIndex(index)
        return
    if normalized_value:
        combo.addItem(normalized_value, normalized_value)
        combo.setCurrentIndex(combo.count() - 1)
