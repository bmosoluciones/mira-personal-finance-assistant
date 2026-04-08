# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Budget-related dialogs."""

from __future__ import annotations

from datetime import date

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
from mira.ui.dialogs._shared import _notify_warning
from mira.ui.i18n import normalize_language, tr


class BudgetCreateDialog(QDialog):
    """Create a new annual budget."""

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._language = normalize_language(self._db.setting.get("language"))
        self.setWindowTitle(tr("dialog.budget_create.title", self._language, default="New budget"))
        self.setMinimumWidth(360)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)
        self._code_edit = QLineEdit()
        self._code_edit.setPlaceholderText(
            tr(
                "dialog.budget_create.code.placeholder",
                self._language,
                default="budget2026, budget_holidays, budget_v2…",
            )
        )
        form.addRow(tr("dialog.budget_create.code", self._language, default="Code:"), self._code_edit)
        self._year_spin = QSpinBox()
        self._year_spin.setRange(1900, 9999)
        self._year_spin.setValue(date.today().year)
        form.addRow(tr("dialog.budget_create.year", self._language, default="Year:"), self._year_spin)
        self._currency_combo = QComboBox()
        self._currency_combo.setEditable(True)
        for currency in self._db.setting.list_currencies(region=None):
            code = str(currency["code"]).upper()
            self._currency_combo.addItem(code, code)
        default_currency = self._db.setting.get_default_currency()
        if (current_idx := self._currency_combo.findData(default_currency)) >= 0:
            self._currency_combo.setCurrentIndex(current_idx)
        else:
            self._currency_combo.setCurrentText(default_currency)
        form.addRow(tr("dialog.budget_create.currency", self._language, default="Currency:"), self._currency_combo)
        help_lbl = QLabel(
            tr(
                "dialog.budget_create.help",
                self._language,
                default="The budget is yearly. After creating it, you'll be able to edit all 12 months, propose an initial budget, and compare it with actuals.",
            )
        )
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("font-size:11px;")
        layout.addLayout(form)
        layout.addWidget(help_lbl)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        if not self._code_edit.text().strip():
            _notify_warning(
                self,
                tr("dialog.common.validation", self._language, default="Validation"),
                tr("dialog.budget_create.validation.code_required", self._language, default="Budget code is required."),
            )
            return
        if not self._currency_combo.currentText().strip():
            _notify_warning(self, "Validación", "La moneda del presupuesto es obligatoria.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "code": self._code_edit.text().strip(),
            "year": int(self._year_spin.value()),
            "currency": self._currency_combo.currentText().strip().upper() or self._db.setting.get_default_currency(),
        }


__all__ = ["BudgetCreateDialog"]
