# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Category-related dialogs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mira.db.database import Database
from mira.ui.dialogs._shared import (
    _NOTICE_LABEL_STYLE,
    _build_icon_combo,
    _notify_warning,
    _set_icon_combo_value,
)
from mira.ui.i18n import normalize_language, tr


class CategoryDialog(QDialog):
    """Create or edit a category."""

    def __init__(
        self,
        db: Database,
        category: dict | None = None,
        default_type: str = "expense",
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the CategoryDialog instance."""
        super().__init__(parent)
        self._db = db
        self._category = category
        self._default_type = default_type
        self._language = normalize_language(self._db.setting.get("language"))
        self.setWindowTitle(
            tr(
                "dialog.category.title.edit" if category else "dialog.category.title.new",
                self._language,
                default="Edit Category" if category else "Add Category",
            )
        )
        self.setMinimumWidth(320)
        self._build_ui()
        if category:
            self._prefill(category)

    def _build_ui(self) -> None:
        """Return build ui."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(
            tr("dialog.category.name.placeholder", self._language, default="Category name…")
        )
        form.addRow(tr("dialog.category.name", self._language, default="Name:"), self._name_edit)

        self._type_combo = QComboBox()
        self._type_combo.addItem(tr("dialog.category.type.expense", self._language, default="Expense"), "expense")
        self._type_combo.addItem(tr("dialog.category.type.income", self._language, default="Income"), "income")
        if (idx := self._type_combo.findData(self._default_type)) >= 0:
            self._type_combo.setCurrentIndex(idx)
        self._type_combo.currentIndexChanged.connect(self._populate_parents)
        form.addRow(tr("dialog.category.type", self._language, default="Type:"), self._type_combo)

        self._color_preview = QLabel()
        self._color_preview.setFixedSize(24, 24)
        self._color_preview.setStyleSheet("border:1px solid #888888;border-radius:4px;background:#888888;")
        self._color_value_label = QLabel()
        self._color_value_label.setMinimumWidth(84)
        self._color_value_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._color_btn = QPushButton(tr("dialog.category.color.choose", self._language, default="Choose color"))
        self._color_btn.clicked.connect(self._choose_color)
        color_container = QWidget()
        color_row = QHBoxLayout(color_container)
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.addWidget(self._color_preview)
        color_row.addWidget(self._color_value_label)
        color_row.addStretch()
        color_row.addWidget(self._color_btn)
        self._selected_color = "#888888"
        self._update_color_preview(self._selected_color)
        form.addRow(tr("dialog.category.color", self._language, default="Color:"), color_container)

        self._icon_combo = _build_icon_combo(self, lang=normalize_language(self._db.setting.get("language")))
        form.addRow(tr("dialog.category.icon", self._language, default="Icon:"), self._icon_combo)

        self._parent_combo = QComboBox()
        self._parent_combo.addItem(tr("dialog.category.parent.none", self._language, default="(None)"), None)
        form.addRow(tr("dialog.category.parent", self._language, default="Parent:"), self._parent_combo)

        layout.addLayout(form)
        self._notice_lbl = QLabel("")
        self._notice_lbl.setWordWrap(True)
        self._notice_lbl.setStyleSheet(_NOTICE_LABEL_STYLE)
        layout.addWidget(self._notice_lbl)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._populate_parents()

    def _update_color_preview(self, color_value: str) -> None:
        """Return update color preview."""
        color = QColor(color_value)
        if not color.isValid():
            color = QColor("#888888")
        self._selected_color = color.name()
        self._color_value_label.setText(self._selected_color.upper())
        self._color_preview.setStyleSheet(
            f"border:1px solid #888888;border-radius:4px;background:{self._selected_color};"
        )

    def _choose_color(self) -> None:
        """Return choose color."""
        color = QColorDialog.getColor(
            QColor(self._selected_color),
            self,
            tr("dialog.category.color.select_title", self._language, default="Select Category Color"),
        )
        if color.isValid():
            self._update_color_preview(color.name())

    def _prefill(self, cat: dict) -> None:
        """Return prefill."""
        self._name_edit.setText(cat.get("name", ""))
        if (idx := self._type_combo.findData(cat.get("type", "expense"))) >= 0:
            self._type_combo.setCurrentIndex(idx)
        self._update_color_preview(str(cat.get("color") or "#888888"))
        _set_icon_combo_value(self._icon_combo, str(cat.get("icon") or ""))
        if (parent_id := cat.get("parent_id")) is not None and (idx := self._parent_combo.findData(parent_id)) >= 0:
            self._parent_combo.setCurrentIndex(idx)

    def _on_accept(self) -> None:
        """Return on accept."""
        if not self._name_edit.text().strip():
            _notify_warning(
                self,
                tr("dialog.common.validation", self._language, default="Validation"),
                tr(
                    "dialog.category.validation.name_required", self._language, default="Category name cannot be empty."
                ),
            )
            return
        self.accept()

    def get_data(self) -> dict:
        """Return get data."""
        icon_value = (self._icon_combo.currentData() or self._icon_combo.currentText()).strip()
        return {
            "name": self._name_edit.text().strip(),
            "cat_type": str(self._type_combo.currentData() or "expense"),
            "color": self._selected_color,
            "icon": icon_value,
            "parent_id": self._parent_combo.currentData(),
        }

    def _populate_parents(self) -> None:
        """Return populate parents."""
        cat_type = str(self._type_combo.currentData() or "expense")
        all_cats = [cat for cat in self._db.category.list(cat_type) if cat.get("parent_id") is None]
        current_id = self._category["id"] if self._category and "id" in self._category else None
        self._parent_combo.clear()
        self._parent_combo.addItem(tr("dialog.category.parent.none", self._language, default="(None)"), None)
        for cat in all_cats:
            if current_id is not None and cat["id"] == current_id:
                continue
            self._parent_combo.addItem(f"{cat.get('icon', '')} {cat['name']}".strip(), cat["id"])


class MergeCategoryDialog(QDialog):
    """Merge one category into another category of the same type."""

    def __init__(self, db: Database, cat_type: str, parent: QWidget | None = None) -> None:
        """Initialize the MergeCategoryDialog instance."""
        super().__init__(parent)
        self._db = db
        self._cat_type = cat_type
        self._language = normalize_language(self._db.setting.get("language"))
        self.setWindowTitle(tr("dialog.category.merge.title", self._language, default="Merge Categories"))
        self.setMinimumWidth(380)
        self._categories = self._db.category.list(cat_type)
        self._build_ui()

    def _build_ui(self) -> None:
        """Return build ui."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)
        self._source_combo = QComboBox()
        self._target_combo = QComboBox()
        for cat in self._categories:
            label = f"{cat['name']} ({cat['color']})"
            self._source_combo.addItem(label, cat["id"])
            self._target_combo.addItem(label, cat["id"])
        if self._target_combo.count() > 1:
            self._target_combo.setCurrentIndex(1)
        form.addRow(tr("dialog.category.merge.source", self._language, default="Source category:"), self._source_combo)
        form.addRow(
            tr("dialog.category.merge.target", self._language, default="Destination category:"),
            self._target_combo,
        )
        note = QLabel(
            tr(
                "dialog.category.merge.note",
                self._language,
                default="All transactions and recurring records from source category will be moved to the destination category.",
            )
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-size:11px;")
        layout.addLayout(form)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        """Return on accept."""
        if self._source_combo.currentData() == self._target_combo.currentData():
            _notify_warning(
                self,
                tr("dialog.common.validation", self._language, default="Validation"),
                tr(
                    "dialog.category.merge.validation.distinct",
                    self._language,
                    default="Source and destination categories must be different.",
                ),
            )
            return
        self.accept()

    def get_data(self) -> dict:
        """Return get data."""
        return {
            "source_id": int(self._source_combo.currentData()),
            "target_id": int(self._target_combo.currentData()),
            "cat_type": self._cat_type,
        }


__all__ = ["CategoryDialog", "MergeCategoryDialog"]
