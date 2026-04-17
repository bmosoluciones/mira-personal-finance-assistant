# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Recurring transaction dialogs."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from mira.db.database import Database
from mira.ui.dialogs._shared import _NOTICE_LABEL_STYLE, _TagMultiSelectButton, _make_amount_spin, _notify_warning
from mira.ui.i18n import normalize_language, tr
from mira.ui.widgets.searchable_combo import SearchableComboBox


class RecurringDialog(QDialog):
    """Create a recurring transaction rule."""

    def __init__(self, db: Database, recurring: dict | None = None, parent=None) -> None:
        """Initialize the RecurringDialog instance."""
        super().__init__(parent)
        self._db = db
        self._recurring = recurring
        self._language = normalize_language(self._db.setting.get("language"))
        self.setWindowTitle(
            tr(
                "dialog.recurring.title.edit" if recurring else "dialog.recurring.title.add",
                self._language,
                default="Edit Recurring" if recurring else "Add Recurring",
            )
        )
        self.setMinimumWidth(400)
        self._build_ui()
        if recurring:
            self._prefill(recurring)

    def _build_ui(self) -> None:
        """Return build ui."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)
        self._account_combo = QComboBox()
        for acc in self._db.account.list():
            self._account_combo.addItem(acc["name"], acc["id"])
        form.addRow(tr("dialog.recurring.account", self._language, default="Account:"), self._account_combo)
        self._type_combo = QComboBox()
        self._type_combo.addItem(
            tr("dialog.recurring.type.income", self._language, default="Income"),
            "income",
        )
        self._type_combo.addItem(
            tr("dialog.recurring.type.expense", self._language, default="Expense"),
            "expense",
        )
        form.addRow(tr("dialog.recurring.type", self._language, default="Type:"), self._type_combo)
        self._amount_spin = _make_amount_spin(self._db)
        form.addRow(tr("dialog.recurring.amount", self._language, default="Amount:"), self._amount_spin)
        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText(
            tr("dialog.recurring.description.placeholder", self._language, default="Description…")
        )
        form.addRow(tr("dialog.recurring.description", self._language, default="Description:"), self._desc_edit)
        self._category_combo = SearchableComboBox()
        self._category_combo.setPlaceholderText(
            tr("dialog.transaction.category.search", self._language, default="Search categories...")
        )
        form.addRow(tr("dialog.recurring.category", self._language, default="Category:"), self._category_combo)
        self._tag_selector = _TagMultiSelectButton(self, lang=self._language)
        form.addRow(tr("dialog.recurring.tags", self._language, default="Tags:"), self._tag_selector)
        self._note_edit = QLineEdit()
        self._note_edit.setPlaceholderText(tr("dialog.recurring.note.placeholder", self._language, default="Note…"))
        form.addRow(tr("dialog.recurring.note", self._language, default="Note:"), self._note_edit)
        self._day_spin = QSpinBox()
        self._day_spin.setRange(1, 28)
        self._day_spin.setValue(1)
        form.addRow(tr("dialog.recurring.day_of_month", self._language, default="Day of month:"), self._day_spin)
        layout.addLayout(form)
        self._notice_lbl = QLabel("")
        self._notice_lbl.setWordWrap(True)
        self._notice_lbl.setStyleSheet(_NOTICE_LABEL_STYLE + "background:#472624;color:#FFB0A3;")
        self._notice_lbl.setVisible(self._recurring is not None)
        if self._recurring is not None:
            self._notice_lbl.setText(
                tr(
                    "dialog.recurring.notice.edit",
                    self._language,
                    default="Editing this recurring rule is a destructive change and cannot be undone automatically.",
                )
            )
        layout.addWidget(self._notice_lbl)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._type_combo.currentIndexChanged.connect(self._populate_categories)
        self._populate_categories()
        self._refresh_tag_selector()

    def _prefill(self, rec: dict) -> None:
        """Return prefill."""
        acc_id = rec.get("account_id")
        for i in range(self._account_combo.count()):
            if self._account_combo.itemData(i) == acc_id:
                self._account_combo.setCurrentIndex(i)
                break
        if (idx := self._type_combo.findData(rec.get("type", "expense"))) >= 0:
            self._type_combo.setCurrentIndex(idx)
        self._amount_spin.setValue(float(rec.get("amount", 0)))
        self._desc_edit.setText(rec.get("description") or "")
        category_id = rec.get("category_id")
        if category_id is not None:
            if (combo_idx := self._category_combo.findData(category_id)) >= 0:
                self._category_combo.setCurrentIndex(combo_idx)
        elif rec.get("category") and (combo_idx := self._category_combo.findText(rec.get("category") or "")) >= 0:
            self._category_combo.setCurrentIndex(combo_idx)
        tag_ids = rec.get("tag_ids") or [int(tag["id"]) for tag in rec.get("tags", [])]
        self._refresh_tag_selector(tag_ids)
        self._note_edit.setText(rec.get("note") or "")
        self._day_spin.setValue(int(rec.get("day_of_month", 1)))

    def _populate_categories(self) -> None:
        """Return populate categories."""
        current_category_id = self._category_combo.currentData()
        current_type = str(self._type_combo.currentData() or "expense")
        self._category_combo.clear()
        self._category_combo.addItem("", None)
        for category in self._db.category.list(current_type):
            self._category_combo.addItem(f"{category.get('icon', '')} {category['name']}".strip(), category["id"])
        if current_category_id is not None and (idx := self._category_combo.findData(current_category_id)) >= 0:
            self._category_combo.setCurrentIndex(idx)

    def _refresh_tag_selector(self, selected_ids: list[int] | set[int] | None = None) -> None:
        """Return refresh tag selector."""
        self._tag_selector.set_tags(self._db.tag.list(), selected_ids=selected_ids)

    def _on_accept(self) -> None:
        """Return on accept."""
        if self._amount_spin.value() <= 0:
            _notify_warning(
                self,
                tr("dialog.common.validation", self._language, default="Validation"),
                tr(
                    "dialog.recurring.validation.amount_positive",
                    self._language,
                    default="Amount must be greater than zero.",
                ),
            )
            return
        self.accept()

    def get_data(self) -> dict:
        """Return get data."""
        return {
            "account_id": self._account_combo.currentData(),
            "tx_type": str(self._type_combo.currentData() or "expense"),
            "amount": self._amount_spin.value(),
            "description": self._desc_edit.text().strip() or None,
            "category_id": self._category_combo.currentData(),
            "tag_ids": self._tag_selector.selected_ids(),
            "note": self._note_edit.text().strip() or None,
            "day_of_month": self._day_spin.value(),
        }


__all__ = ["RecurringDialog"]
