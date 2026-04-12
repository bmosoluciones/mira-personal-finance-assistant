# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Account-related dialogs."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from mira.db.database import Database
from mira.ui.i18n import normalize_language, tr
from mira.ui.dialogs._shared import _NOTICE_LABEL_STYLE, _make_balance_spin, _notify_warning


class AccountDialog(QDialog):
    """Create or edit an account."""

    def __init__(
        self,
        db: Database,
        account: dict | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._account = account
        self._language = normalize_language(self._db.setting.get("language"))
        self.setWindowTitle(
            tr(
                "dialog.account.title.edit" if account else "dialog.account.title.new",
                self._language,
                default="Edit Account" if account else "Add Account",
            )
        )
        self.setMinimumWidth(340)
        self._build_ui()
        if account:
            self._prefill(account)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(
            tr("dialog.account.name.placeholder", self._language, default="Account name…")
        )
        form.addRow(tr("dialog.account.name", self._language, default="Name:"), self._name_edit)

        self._type_combo = QComboBox()
        self._type_combo.addItem(tr("dialog.account.type.bank", self._language, default="Bank"), "bank")
        self._type_combo.addItem(tr("dialog.account.type.cash", self._language, default="Cash"), "cash")
        self._type_combo.addItem(tr("dialog.account.type.credit", self._language, default="Credit card"), "credit")
        self._type_combo.currentIndexChanged.connect(self._sync_balance_range)
        form.addRow(tr("dialog.account.type", self._language, default="Type:"), self._type_combo)

        self._currency_combo = QComboBox()
        self._currency_combo.setEditable(False)
        self._currency_combo.setMaxVisibleItems(20)
        for cur in self._db.setting.list_currencies(region=None):
            code = str(cur.get("code") or "").strip().upper()
            if code and self._currency_combo.findData(code) < 0:
                self._currency_combo.addItem(code, code)
        default_currency = self._db.setting.get_default_currency()
        if (current_idx := self._currency_combo.findData(default_currency)) >= 0:
            self._currency_combo.setCurrentIndex(current_idx)
        form.addRow(tr("dialog.account.currency", self._language, default="Currency:"), self._currency_combo)

        self._balance_spin = _make_balance_spin(self._db)
        self._balance_spin.setValue(0.00)
        self._balance_row_label = QLabel(
            tr("dialog.account.opening_balance", self._language, default="Opening Balance:")
        )
        form.addRow(self._balance_row_label, self._balance_spin)

        if self._account:
            self._balance_spin.setVisible(False)
            self._balance_row_label.setVisible(False)

        layout.addLayout(form)

        self._notice_lbl = QLabel("")
        self._notice_lbl.setWordWrap(True)
        self._notice_lbl.setStyleSheet(_NOTICE_LABEL_STYLE)
        layout.addWidget(self._notice_lbl)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._sync_balance_range()

    def _prefill(self, account: dict) -> None:
        self._name_edit.setText(account.get("name", ""))
        account_type = str(account.get("account_type", "bank"))
        if account_type == "card":
            account_type = "credit"
        if (idx := self._type_combo.findData(account_type)) >= 0:
            self._type_combo.setCurrentIndex(idx)
        if (
            cidx := self._currency_combo.findData(
                str(account.get("currency") or self._db.setting.get_default_currency()).upper()
            )
        ) >= 0:
            self._currency_combo.setCurrentIndex(cidx)
        self._sync_balance_range()

    def _selected_account_type(self) -> str:
        return str(self._type_combo.currentData() or self._type_combo.currentText() or "bank")

    def _sync_balance_range(self) -> None:
        current_value = float(self._balance_spin.value())
        if self._selected_account_type() == "credit":
            self._balance_spin.setRange(-9_999_999.99, 9_999_999.99)
            return
        self._balance_spin.setRange(0.0, 9_999_999.99)
        if current_value < 0:
            self._balance_spin.setValue(0.0)

    def _on_accept(self) -> None:
        if not self._name_edit.text().strip():
            _notify_warning(
                self,
                tr("dialog.common.validation", self._language, default="Validation"),
                tr("dialog.account.validation.name_required", self._language, default="Account name cannot be empty."),
            )
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "name": self._name_edit.text().strip(),
            "account_type": self._selected_account_type(),
            "opening_balance": self._balance_spin.value() if not self._account else 0.0,
            "currency": str(self._currency_combo.currentData() or self._db.setting.get_default_currency()).upper(),
        }


__all__ = ["AccountDialog"]
