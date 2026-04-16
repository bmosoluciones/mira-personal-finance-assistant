# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Account-related dialogs."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
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
        """Initialize the AccountDialog instance."""
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

    def _t(self, key: str, default: str, *, params: dict[str, object] | None = None) -> str:
        """Return t."""
        return tr(key, self._language, default=default, params=params)

    def _build_ui(self) -> None:
        """Return build ui."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(self._t("dialog.account.name.placeholder", "Account name…"))
        form.addRow(self._t("dialog.account.name", "Name:"), self._name_edit)

        self._type_combo = QComboBox()
        self._type_combo.addItem(self._t("dialog.account.type.bank", "Bank"), "bank")
        self._type_combo.addItem(self._t("dialog.account.type.cash", "Cash"), "cash")
        self._type_combo.addItem(self._t("dialog.account.type.credit", "Credit"), "credit")
        self._type_combo.currentIndexChanged.connect(self._sync_balance_range)
        form.addRow(self._t("dialog.account.type", "Type:"), self._type_combo)

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
        form.addRow(self._t("dialog.account.currency", "Currency:"), self._currency_combo)

        self._balance_spin = _make_balance_spin(self._db)
        self._balance_spin.setValue(0.00)
        self._balance_row_label = QLabel(self._t("dialog.account.opening_balance", "Opening Balance:"))
        form.addRow(self._balance_row_label, self._balance_spin)

        layout.addLayout(form)

        # "Set as default" checkbox — only relevant when creating a new account.
        if not self._account:
            has_existing_accounts = len(self._db.account.list()) > 0
            self._set_default_chk = QCheckBox(self._t("dialog.account.set_as_default", "Set as default account"))
            # Pre-check when there are no existing non-pristine accounts.
            self._set_default_chk.setChecked(not has_existing_accounts)
            hint_lbl = QLabel(
                self._t(
                    "dialog.account.set_as_default.hint",
                    "The default account is used automatically for new transactions.",
                )
            )
            hint_lbl.setWordWrap(True)
            hint_lbl.setStyleSheet("font-size:10px;color:#B7C3D0;")
            layout.addWidget(self._set_default_chk)
            layout.addWidget(hint_lbl)
        else:
            self._set_default_chk = None  # type: ignore[assignment]
            self._balance_spin.setVisible(False)
            self._balance_row_label.setVisible(False)

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
        """Return prefill."""
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
        """Return selected account type."""
        return str(self._type_combo.currentData() or self._type_combo.currentText() or "bank")

    def _sync_balance_range(self) -> None:
        """Return sync balance range."""
        current_value = float(self._balance_spin.value())
        if self._selected_account_type() == "credit":
            self._balance_spin.setRange(-9_999_999.99, 9_999_999.99)
            return
        self._balance_spin.setRange(0.0, 9_999_999.99)
        if current_value < 0:
            self._balance_spin.setValue(0.0)

    def _on_accept(self) -> None:
        """Return on accept."""
        if not self._name_edit.text().strip():
            _notify_warning(
                self,
                self._t("dialog.common.validation", "Validation"),
                self._t("dialog.account.validation.name_required", "Account name cannot be empty."),
            )
            return
        self.accept()

    def get_data(self) -> dict:
        """Return get data."""
        data: dict = {
            "name": self._name_edit.text().strip(),
            "account_type": self._selected_account_type(),
            "opening_balance": self._balance_spin.value() if not self._account else 0.0,
            "currency": str(self._currency_combo.currentData() or self._db.setting.get_default_currency()).upper(),
        }
        if self._set_default_chk is not None:
            data["set_as_default"] = self._set_default_chk.isChecked()
        return data


__all__ = ["AccountDialog"]
