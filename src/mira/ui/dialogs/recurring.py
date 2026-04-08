# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Recurring transaction dialogs."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QSpinBox, QVBoxLayout

from mira.db.database import Database
from mira.ui.dialogs._shared import _TagMultiSelectButton, _make_amount_spin, _notify_warning
from mira.ui.i18n import normalize_language


class RecurringDialog(QDialog):
    """Create a recurring transaction rule."""

    def __init__(self, db: Database, recurring: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._recurring = recurring
        self.setWindowTitle("Edit Recurring" if recurring else "Add Recurring")
        self.setMinimumWidth(400)
        self._build_ui()
        if recurring:
            self._prefill(recurring)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)
        self._account_combo = QComboBox()
        for acc in self._db.account.list():
            self._account_combo.addItem(acc["name"], acc["id"])
        form.addRow("Account:", self._account_combo)
        self._type_combo = QComboBox()
        self._type_combo.addItems(["income", "expense"])
        form.addRow("Type:", self._type_combo)
        self._amount_spin = _make_amount_spin(self._db)
        form.addRow("Amount:", self._amount_spin)
        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("Description…")
        form.addRow("Description:", self._desc_edit)
        self._category_combo = QComboBox()
        form.addRow("Category:", self._category_combo)
        self._tag_selector = _TagMultiSelectButton(self, lang=normalize_language(self._db.setting.get("language")))
        form.addRow("Tags:", self._tag_selector)
        self._note_edit = QLineEdit()
        self._note_edit.setPlaceholderText("Note…")
        form.addRow("Note:", self._note_edit)
        self._day_spin = QSpinBox()
        self._day_spin.setRange(1, 28)
        self._day_spin.setValue(1)
        form.addRow("Day of Month:", self._day_spin)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._type_combo.currentIndexChanged.connect(self._populate_categories)
        self._populate_categories()
        self._refresh_tag_selector()

    def _prefill(self, rec: dict) -> None:
        acc_id = rec.get("account_id")
        for i in range(self._account_combo.count()):
            if self._account_combo.itemData(i) == acc_id:
                self._account_combo.setCurrentIndex(i)
                break
        if (idx := self._type_combo.findText(rec.get("type", "expense"))) >= 0:
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
        current_category_id = self._category_combo.currentData()
        current_type = self._type_combo.currentText()
        self._category_combo.clear()
        self._category_combo.addItem("", None)
        for category in self._db.category.list(current_type):
            self._category_combo.addItem(f"{category.get('icon', '')} {category['name']}".strip(), category["id"])
        if current_category_id is not None and (idx := self._category_combo.findData(current_category_id)) >= 0:
            self._category_combo.setCurrentIndex(idx)

    def _refresh_tag_selector(self, selected_ids: list[int] | set[int] | None = None) -> None:
        self._tag_selector.set_tags(self._db.tag.list(), selected_ids=selected_ids)

    def _on_accept(self) -> None:
        if self._amount_spin.value() <= 0:
            _notify_warning(self, "Validation", "Amount must be greater than zero.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "account_id": self._account_combo.currentData(),
            "tx_type": self._type_combo.currentText(),
            "amount": self._amount_spin.value(),
            "description": self._desc_edit.text().strip() or None,
            "category_id": self._category_combo.currentData(),
            "tag_ids": self._tag_selector.selected_ids(),
            "note": self._note_edit.text().strip() or None,
            "day_of_month": self._day_spin.value(),
        }


__all__ = ["RecurringDialog"]
