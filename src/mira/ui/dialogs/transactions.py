# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Transaction-related dialogs."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from mira.app.view_services import AccountsViewService
from mira.db.database import Database
from mira.ui.dialogs._shared import (
    _NOTICE_LABEL_STYLE,
    _PRIMARY_ACTION_BUTTON_STYLE,
    _SECONDARY_ACTION_BUTTON_STYLE,
    _TagMultiSelectButton,
    _format_amount_label,
    _hero_amount_spin_style,
    _make_amount_spin,
    _make_balance_spin,
    _make_date_edit,
    _notify_warning,
)
from mira.ui.i18n import normalize_language, tr
from mira.ui.number_format import NumberMaskedSpinBox


class TransactionDialog(QDialog):
    """Create or edit a transaction with a modern dark UI."""

    def __init__(
        self,
        db: Database,
        tx: dict | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._tx = tx
        self._language = normalize_language(self._db.setting.get("language"))
        self._is_expense = True
        self.setWindowTitle(
            tr(
                "dialog.transaction.title.edit" if tx else "dialog.transaction.title.new",
                self._language,
                default="Edit Transaction" if tx else "New Transaction",
            )
        )
        self.setMinimumWidth(660)
        self._build_ui()
        if tx:
            self._prefill(tx)
        else:
            self._set_type("expense")
            self._set_source_currency_value(self._db.setting.get_default_currency())
            self._sync_fx_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self._form_scroll = QScrollArea(self)
        self._form_scroll.setWidgetResizable(True)
        self._form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._form_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._form_scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        self._scroll_content = QWidget()
        content_layout = QVBoxLayout(self._scroll_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        self._form_scroll.setWidget(self._scroll_content)
        layout.addWidget(self._form_scroll, 1)

        title = QLabel(
            tr(
                "dialog.transaction.title.edit" if self._tx else "dialog.transaction.title.new",
                self._language,
                default="Edit Transaction" if self._tx else "New Transaction",
            )
        )
        title.setStyleSheet("font-size:28px;font-weight:700;padding-bottom:4px;")
        content_layout.addWidget(title)

        type_row = QHBoxLayout()
        self._btn_expense = QPushButton(tr("dialog.transaction.type.expense", self._language, default="Expense"))
        self._btn_income = QPushButton(tr("dialog.transaction.type.income", self._language, default="Income"))
        self._btn_expense.clicked.connect(lambda: self._set_type("expense"))
        self._btn_income.clicked.connect(lambda: self._set_type("income"))
        type_row.addWidget(self._btn_expense)
        type_row.addWidget(self._btn_income)
        content_layout.addLayout(type_row)

        self._type_combo = QComboBox()
        self._type_combo.addItems(["expense", "income"])
        self._type_combo.hide()

        amount_lbl = QLabel(tr("dialog.transaction.original_amount", self._language, default="Original amount"))
        content_layout.addWidget(amount_lbl)
        self._amount_spin = _make_amount_spin(self._db)
        self._amount_spin.setPrefix("$")
        self._amount_spin.setDecimals(2)
        self._amount_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._amount_spin.setStyleSheet(_hero_amount_spin_style("#F48771"))
        content_layout.addWidget(self._amount_spin)

        grid = QHBoxLayout()

        left = QFormLayout()
        left.setSpacing(10)
        self._date_edit = _make_date_edit()
        left.addRow(tr("dialog.transaction.date", self._language, default="Date:"), self._date_edit)

        self._account_combo = QComboBox()
        self._account_combo.setEditable(False)
        self._populate_accounts()
        self._account_combo.currentIndexChanged.connect(self._sync_fx_state)
        left.addRow(tr("dialog.transaction.account", self._language, default="Account:"), self._account_combo)

        self._account_currency_lbl = QLabel("")
        self._account_currency_lbl.setStyleSheet("font-size:11px;")
        left.addRow("", self._account_currency_lbl)
        grid.addLayout(left, 1)

        right = QFormLayout()
        right.setSpacing(10)
        self._classification_form = right
        self._category_combo = QComboBox()
        self._category_combo.setEditable(False)
        self._populate_categories()
        right.addRow(tr("dialog.transaction.category", self._language, default="Category:"), self._category_combo)

        self._tag_selector = _TagMultiSelectButton(self, lang=normalize_language(self._db.setting.get("language")))
        right.addRow(tr("dialog.transaction.tags", self._language, default="Tags:"), self._tag_selector)
        self._refresh_tag_selector()
        grid.addLayout(right, 1)

        self._payment_method_form = QFormLayout()
        self._payment_method_form.setSpacing(10)
        self._payment_method_combo = QComboBox()
        payment_methods = [
            ("dialog.transaction.payment_method.cash", "Cash", "cash"),
            ("dialog.transaction.payment_method.credit_card", "Credit card", "credit_card"),
            ("dialog.transaction.payment_method.debit_card", "Debit card", "debit_card"),
            ("dialog.transaction.payment_method.transfer", "Transfer", "transfer"),
            ("dialog.transaction.payment_method.other", "Other", "other"),
        ]
        for key, default, value in payment_methods:
            self._payment_method_combo.addItem(tr(key, self._language, default=default), value)
        content_layout.addLayout(grid)
        self._payment_method_form.addRow(
            tr("dialog.transaction.payment_method", self._language, default="Payment method:"),
            self._payment_method_combo,
        )
        content_layout.addLayout(self._payment_method_form)

        self._fx_check = QCheckBox(
            tr(
                "dialog.transaction.fx.enable",
                self._language,
                default="Enter amount in a different currency than the account",
            )
        )
        self._fx_check.toggled.connect(self._sync_fx_state)
        content_layout.addWidget(self._fx_check)

        fx_form = QFormLayout()
        fx_form.setSpacing(8)
        self._source_currency_combo = QComboBox()
        self._source_currency_combo.setEditable(False)
        self._populate_source_currencies()
        self._source_currency_combo.currentTextChanged.connect(self._sync_fx_state)
        fx_form.addRow(
            tr("dialog.transaction.fx.source_currency", self._language, default="Original currency:"),
            self._source_currency_combo,
        )

        self._rate_spin = NumberMaskedSpinBox(self._db.setting)
        self._rate_spin.setRange(0.000001, 9_999_999.99)
        self._rate_spin.setDecimals(6)
        self._rate_spin.setValue(1.0)
        self._rate_spin.valueChanged.connect(self._recompute_converted_amount)
        fx_form.addRow(tr("dialog.transaction.fx.rate", self._language, default="Exchange rate:"), self._rate_spin)

        self._converted_amount_spin = _make_amount_spin(self._db)
        self._converted_amount_spin.setPrefix("$")
        self._converted_amount_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._converted_amount_spin.setReadOnly(False)
        fx_form.addRow(
            tr("dialog.transaction.fx.converted_amount", self._language, default="Converted amount:"),
            self._converted_amount_spin,
        )

        content_layout.addLayout(fx_form)

        self._amount_spin.valueChanged.connect(self._recompute_converted_amount)

        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText(tr("dialog.transaction.description", self._language, default="Description"))
        content_layout.addWidget(QLabel(tr("dialog.transaction.description", self._language, default="Description")))
        content_layout.addWidget(self._desc_edit)

        self._details_check = QCheckBox(
            tr("dialog.transaction.more_details", self._language, default="Add more details... (optional)")
        )
        self._details_check.toggled.connect(self._toggle_optional)
        content_layout.addWidget(self._details_check)

        self._optional_container = QWidget()
        optional_layout = QFormLayout(self._optional_container)
        optional_layout.setSpacing(8)
        self._note_edit = QTextEdit()
        self._note_edit.setMaximumHeight(90)
        self._note_edit.setPlaceholderText(
            tr("dialog.transaction.notes.placeholder", self._language, default="Additional notes")
        )
        optional_layout.addRow(tr("dialog.transaction.notes", self._language, default="Notes:"), self._note_edit)

        receipt_row = QHBoxLayout()
        self._receipt_path_edit = QLineEdit()
        self._receipt_path_edit.setPlaceholderText(
            tr("dialog.transaction.receipt.path", self._language, default="Receipt file path")
        )
        self._receipt_path_edit.setReadOnly(True)
        browse_btn = QPushButton(tr("dialog.transaction.receipt.browse", self._language, default="Browse…"))
        browse_btn.clicked.connect(self._browse_receipt)
        receipt_row.addWidget(self._receipt_path_edit)
        receipt_row.addWidget(browse_btn)
        optional_layout.addRow(tr("dialog.transaction.receipt", self._language, default="Receipt:"), receipt_row)

        self._optional_container.hide()
        content_layout.addWidget(self._optional_container)

        self._footer_widget = QWidget(self)
        action_row = QHBoxLayout(self._footer_widget)
        action_row.setContentsMargins(0, 0, 0, 0)
        self._cancel_button = QPushButton(tr("dialog.common.cancel", self._language, default="Cancel"))
        self._cancel_button.clicked.connect(self.reject)
        self._save_button = QPushButton(
            tr(
                "dialog.transaction.save.edit" if self._tx else "dialog.transaction.save.new",
                self._language,
                default="Update Transaction" if self._tx else "Save Transaction",
            )
        )
        self._save_button.clicked.connect(self._on_accept)
        self._cancel_button.setStyleSheet(_SECONDARY_ACTION_BUTTON_STYLE)
        self._save_button.setStyleSheet(_PRIMARY_ACTION_BUTTON_STYLE)
        action_row.addWidget(self._cancel_button)
        action_row.addWidget(self._save_button)
        layout.addWidget(self._footer_widget)

    def _toggle_optional(self, checked: bool) -> None:
        self._optional_container.setVisible(checked)

    def _selected_account_currency(self) -> str:
        account_id = self._account_combo.currentData()
        for acc in getattr(self, "_accounts", []):
            if acc["id"] == account_id:
                return str(acc.get("currency") or self._db.setting.get_default_currency()).upper()
        return self._db.setting.get_default_currency()

    def _sync_fx_state(self) -> None:
        account_currency = self._selected_account_currency()
        self._account_currency_lbl.setText(
            tr(
                "dialog.transaction.account_currency",
                self._language,
                default="Account currency: {currency}",
                params={"currency": account_currency},
            )
        )

        enabled = self._fx_check.isChecked()
        self._source_currency_combo.setEnabled(enabled)
        self._rate_spin.setEnabled(enabled)
        self._converted_amount_spin.setEnabled(enabled)
        if not enabled:
            self._converted_amount_spin.setValue(self._amount_spin.value())
            self._rate_spin.setValue(1.0)
        else:
            if not self._source_currency_combo.currentText().strip():
                self._set_source_currency_value(self._db.setting.get_default_currency())
            self._recompute_converted_amount()

    def _recompute_converted_amount(self) -> None:
        if not self._fx_check.isChecked():
            return
        converted = self._amount_spin.value() * self._rate_spin.value()
        self._converted_amount_spin.setValue(round(converted, 2))

    def _set_type(self, tx_type: str) -> None:
        self._is_expense = tx_type == "expense"
        self._type_combo.setCurrentText(tx_type)
        active_expense = (
            "QPushButton{background:#D05757;color:white;"
            "border-radius:18px;padding:6px 20px;font-size:18px;font-weight:600;}"
        )
        inactive = "QPushButton{background:transparent;border-radius:18px;padding:6px 20px;font-size:18px;}"
        active_income = (
            "QPushButton{background:#4EC9B0;color:#15322E;"
            "border-radius:18px;padding:6px 20px;font-size:18px;font-weight:600;}"
        )
        self._btn_expense.setStyleSheet(active_expense if self._is_expense else inactive)
        self._btn_income.setStyleSheet(active_income if not self._is_expense else inactive)
        self._populate_categories()
        color = "#F48771" if self._is_expense else "#4EC9B0"
        self._amount_spin.setStyleSheet(_hero_amount_spin_style(color))

    def _populate_accounts(self) -> None:
        self._account_combo.clear()
        self._accounts = self._db.account.list()
        for acc in self._accounts:
            self._account_combo.addItem(acc["name"], acc["id"])

    def _populate_source_currencies(self) -> None:
        self._source_currency_combo.clear()
        for currency in self._db.setting.list_currencies(region=None):
            code = str(currency["code"]).strip().upper()
            self._source_currency_combo.addItem(code, code)
        default_currency = self._db.setting.get_default_currency()
        if self._source_currency_combo.findData(default_currency) < 0:
            self._source_currency_combo.addItem(default_currency, default_currency)

    def _set_source_currency_value(self, currency_code: str) -> None:
        normalized_code = currency_code.strip().upper()
        if not normalized_code:
            self._source_currency_combo.setCurrentIndex(-1)
            return
        idx = self._source_currency_combo.findData(normalized_code)
        if idx >= 0:
            self._source_currency_combo.setCurrentIndex(idx)
            return
        self._source_currency_combo.addItem(normalized_code, normalized_code)
        self._source_currency_combo.setCurrentIndex(self._source_currency_combo.count() - 1)

    def _populate_categories(self) -> None:
        current_category = self._normalized_category()
        current_type = self._type_combo.currentText() or "expense"
        self._category_combo.clear()
        self._category_combo.addItem("", None)
        cats = self._db.category.list(current_type)
        id_map = {cat["id"]: cat for cat in cats}
        for cat in cats:
            icon = cat.get("icon", "")
            name = cat["name"]
            parent_id = cat.get("parent_id")
            parent = id_map.get(parent_id) if parent_id in id_map else None
            label = f"{icon} {name}".strip()
            if parent:
                label += f"  ⟶  {parent.get('icon', '')} {parent['name']}"
            self._category_combo.addItem(label, name)
        if current_category:
            self._set_category_combo_value(current_category)

    def _set_category_combo_value(self, category: str) -> None:
        normalized_category = category.strip()
        if not normalized_category:
            self._category_combo.setCurrentIndex(0)
            return

        raw_idx = self._category_combo.findData(normalized_category)
        txt_idx = self._category_combo.findText(normalized_category)
        if raw_idx >= 0:
            self._category_combo.setCurrentIndex(raw_idx)
            return
        if txt_idx >= 0:
            self._category_combo.setCurrentIndex(txt_idx)
            return

        self._category_combo.addItem(normalized_category, normalized_category)
        self._category_combo.setCurrentIndex(self._category_combo.count() - 1)

    def _browse_receipt(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dialog.transaction.receipt.select", self._language, default="Select receipt"),
            "",
            tr(
                "dialog.transaction.receipt.filter",
                self._language,
                default="Images (*.png *.jpg *.jpeg *.gif *.bmp *.pdf);;All Files (*)",
            ),
        )
        if path:
            self._receipt_path_edit.setText(path)

    def _prefill(self, tx: dict) -> None:
        from PySide6.QtCore import QDate

        if tx.get("date"):
            parts = tx["date"].split("-")
            if len(parts) == 3:
                try:
                    self._date_edit.setDate(QDate(int(parts[0]), int(parts[1]), int(parts[2])))
                except (ValueError, TypeError):
                    pass

        self._set_type(tx.get("type", "expense"))
        self._amount_spin.setValue(float(tx.get("amount", 0)))

        acc_id = tx.get("account_id")
        for i in range(self._account_combo.count()):
            if self._account_combo.itemData(i) == acc_id:
                self._account_combo.setCurrentIndex(i)
                break

        self._set_category_combo_value(str(tx.get("category") or ""))

        pm_idx = self._payment_method_combo.findData(tx.get("payment_method") or "cash")
        if pm_idx >= 0:
            self._payment_method_combo.setCurrentIndex(pm_idx)
        self._desc_edit.setText(tx.get("description") or "")
        self._note_edit.setPlainText(tx.get("note") or "")
        self._receipt_path_edit.setText(tx.get("receipt_path") or "")

        exchange_rate = tx.get("exchange_rate")
        converted_amount = tx.get("converted_amount")
        fx_enabled = bool(exchange_rate and converted_amount)
        self._fx_check.setChecked(fx_enabled)
        if exchange_rate:
            self._rate_spin.setValue(float(exchange_rate))
        if converted_amount:
            self._converted_amount_spin.setValue(float(converted_amount))
        if fx_enabled:
            self._set_source_currency_value(self._db.setting.get_default_currency())
        self._sync_fx_state()

        self._refresh_tag_selector({int(tag["id"]) for tag in self._db.tag.list_for_transaction(int(tx["id"]))})

        has_optional = any(
            [
                self._note_edit.toPlainText().strip(),
                self._receipt_path_edit.text().strip(),
            ]
        )
        self._details_check.setChecked(has_optional)

    def _normalized_category(self) -> str | None:
        current_data = self._category_combo.currentData()
        if isinstance(current_data, str) and current_data.strip():
            return current_data.strip()
        value = self._category_combo.currentText().strip()
        if value.startswith("🏠"):
            value = value[1:].strip()
        return value or None

    def _on_accept(self) -> None:
        if self._amount_spin.value() <= 0:
            _notify_warning(
                self,
                tr("dialog.common.validation", self._language, default="Validation"),
                tr(
                    "dialog.transaction.validation.amount_positive",
                    self._language,
                    default="Amount must be greater than zero.",
                ),
            )
            return
        if self._account_combo.count() == 0:
            _notify_warning(
                self,
                tr("dialog.common.validation", self._language, default="Validation"),
                tr("dialog.transaction.validation.accounts_required", self._language, default="No accounts available."),
            )
            return
        if self._fx_check.isChecked():
            if not self._source_currency_combo.currentText().strip():
                _notify_warning(
                    self,
                    tr("dialog.common.validation", self._language, default="Validation"),
                    tr(
                        "dialog.transaction.validation.source_currency_required",
                        self._language,
                        default="Enter the source currency.",
                    ),
                )
                return
            if self._rate_spin.value() <= 0:
                _notify_warning(
                    self,
                    tr("dialog.common.validation", self._language, default="Validation"),
                    tr(
                        "dialog.transaction.validation.exchange_rate_positive",
                        self._language,
                        default="Exchange rate must be greater than zero.",
                    ),
                )
                return
            if self._converted_amount_spin.value() <= 0:
                _notify_warning(
                    self,
                    tr("dialog.common.validation", self._language, default="Validation"),
                    tr(
                        "dialog.transaction.validation.converted_amount_positive",
                        self._language,
                        default="Converted amount must be greater than zero.",
                    ),
                )
                return
        max_tags = int(self._db.setting.get("max_tags_per_transaction") or 10)
        if len(self._get_selected_tag_ids()) > max_tags:
            _notify_warning(
                self,
                tr("dialog.common.validation", self._language, default="Validation"),
                tr(
                    "dialog.transaction.validation.max_tags",
                    self._language,
                    default="You can assign at most {max_tags} tags to a transaction.",
                    params={"max_tags": max_tags},
                ),
            )
            return
        self.accept()

    def get_data(self) -> dict:
        original_amount = self._amount_spin.value()
        fx_enabled = self._fx_check.isChecked()
        stored_amount = self._converted_amount_spin.value() if fx_enabled else original_amount
        return {
            "tx_date": self._date_edit.date().toString("yyyy-MM-dd"),
            "tx_type": self._type_combo.currentText(),
            "amount": original_amount,
            "stored_amount": stored_amount,
            "base_currency": (self._source_currency_combo.currentText().strip().upper() if fx_enabled else None),
            "exchange_rate": self._rate_spin.value() if fx_enabled else None,
            "converted_amount": (self._converted_amount_spin.value() if fx_enabled else None),
            "account_id": self._account_combo.currentData(),
            "category": self._normalized_category(),
            "subcategory": None,
            "payment_method": self._payment_method_combo.currentData() or "cash",
            "description": self._desc_edit.text().strip() or None,
            "note": self._note_edit.toPlainText().strip() or None,
            "receipt_path": self._receipt_path_edit.text().strip() or None,
            "tags": self._get_selected_tag_ids(),
        }

    def _refresh_tag_selector(self, selected_ids: set[int] | list[int] | None = None) -> None:
        if selected_ids is None:
            selected_ids = self._tag_selector.selected_ids()
        self._tag_selector.set_tags(self._db.tag.list(), selected_ids)

    def _get_selected_tag_ids(self) -> list[int]:
        return self._tag_selector.selected_ids()


def _transfer_tr(db: Database, key: str, default: str, **params: object) -> str:
    """Shortcut for translation inside transfer dialogs."""
    lang = normalize_language(db.setting.get("language") if db else "en")
    return tr(key, lang, default=default, params=params if params else None)


class TransferDialog(QDialog):
    """Transfer money between two accounts, including credit card payments."""

    def __init__(self, db: Database, parent: QWidget | None = None, *, credit_payment: bool = False) -> None:
        super().__init__(parent)
        self._db = db
        self._credit_payment = credit_payment
        self._syncing_fx_fields = False
        self.setWindowTitle(self._dialog_title())
        self.setMinimumWidth(660)
        self._build_ui()

    def _dialog_title(self) -> str:
        if self._credit_payment:
            return _transfer_tr(self._db, "dialog.transfer.credit_payment", "Credit card payment")
        return _transfer_tr(self._db, "dialog.transfer.title", "Transfer between accounts")

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        title = QLabel(self._dialog_title())
        title.setStyleSheet("font-size:28px;font-weight:700;padding-bottom:4px;")
        layout.addWidget(title)

        self._accounts = self._db.account.list()
        if self._credit_payment:
            self._from_accounts = [
                acc for acc in self._accounts if str(acc.get("account_type") or "") in {"bank", "cash"}
            ]
            self._to_accounts = [acc for acc in self._accounts if str(acc.get("account_type") or "") == "credit"]
        else:
            self._from_accounts = [
                acc for acc in self._accounts if str(acc.get("account_type") or "") in {"bank", "cash"}
            ]
            self._to_accounts = [
                acc for acc in self._accounts if str(acc.get("account_type") or "") in {"bank", "cash"}
            ]

        from_cur = self._account_currency(self._from_accounts[0] if self._from_accounts else None)
        self._amount_label = QLabel(
            _transfer_tr(self._db, "dialog.transfer.source_amount", "Source amount ({currency}):", currency=from_cur)
        )
        self._amount_label.setObjectName("_amount_label")
        layout.addWidget(self._amount_label)
        self._amount_spin = _make_amount_spin(self._db)
        self._amount_spin.setPrefix(f"{from_cur} ")
        self._amount_spin.setDecimals(2)
        self._amount_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._amount_spin.setStyleSheet(_hero_amount_spin_style("#569CD6"))
        layout.addWidget(self._amount_spin)

        grid = QHBoxLayout()
        left = QFormLayout()
        left.setSpacing(10)
        self._from_combo = QComboBox()
        self._from_combo.setEditable(False)
        for acc in self._from_accounts:
            self._from_combo.addItem(f"{acc['name']} ({acc.get('currency', 'NIO')})", acc["id"])
        left.addRow(
            _transfer_tr(
                self._db,
                (
                    "dialog.transfer.credit_payment.from_account"
                    if self._credit_payment
                    else "dialog.transfer.from_account"
                ),
                "Pay from:" if self._credit_payment else "From account:",
            ),
            self._from_combo,
        )
        self._date_edit = _make_date_edit()
        left.addRow(_transfer_tr(self._db, "dialog.transfer.date", "Date:"), self._date_edit)
        grid.addLayout(left, 1)

        right = QFormLayout()
        right.setSpacing(10)
        self._to_combo = QComboBox()
        self._to_combo.setEditable(False)
        for acc in self._to_accounts:
            self._to_combo.addItem(f"{acc['name']} ({acc.get('currency', 'NIO')})", acc["id"])
        right.addRow(
            _transfer_tr(
                self._db,
                "dialog.transfer.credit_payment.to_account" if self._credit_payment else "dialog.transfer.to_account",
                "Credit card:" if self._credit_payment else "To account:",
            ),
            self._to_combo,
        )
        right.addRow("", QLabel(""))
        grid.addLayout(right, 1)
        layout.addLayout(grid)

        self._fx_container = QWidget()
        fx_form = QFormLayout(self._fx_container)
        fx_form.setSpacing(8)
        self._from_currency_edit = QLineEdit()
        self._from_currency_edit.setReadOnly(True)
        fx_form.addRow(
            _transfer_tr(self._db, "dialog.transfer.source_currency", "Source currency:"), self._from_currency_edit
        )
        self._to_currency_edit = QLineEdit()
        self._to_currency_edit.setReadOnly(True)
        fx_form.addRow(
            _transfer_tr(self._db, "dialog.transfer.destination_currency", "Destination currency:"),
            self._to_currency_edit,
        )
        self._rate_label = QLabel("")
        self._rate_spin = NumberMaskedSpinBox(self._db.setting)
        self._rate_spin.setRange(0.000001, 999999.0)
        self._rate_spin.setDecimals(6)
        self._rate_spin.setValue(1.0)
        fx_form.addRow(self._rate_label, self._rate_spin)
        self._converted_label = QLabel("")
        self._converted_amount_spin = _make_amount_spin(self._db)
        self._converted_amount_spin.setPrefix(f"{from_cur} ")
        self._converted_amount_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        fx_form.addRow(self._converted_label, self._converted_amount_spin)
        layout.addWidget(self._fx_container)

        layout.addWidget(QLabel(_transfer_tr(self._db, "dialog.transfer.description", "Description:")))
        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText(
            _transfer_tr(
                self._db,
                (
                    "dialog.transfer.credit_payment.description.placeholder"
                    if self._credit_payment
                    else "dialog.transfer.description.placeholder"
                ),
                "Card payment note…" if self._credit_payment else "Transfer description…",
            )
        )
        layout.addWidget(self._desc_edit)

        self._details_check = QCheckBox(_transfer_tr(self._db, "dialog.transfer.optional", "Optional details"))
        self._details_check.toggled.connect(self._toggle_optional)
        layout.addWidget(self._details_check)
        self._optional_container = QWidget()
        optional_layout = QFormLayout(self._optional_container)
        optional_layout.setSpacing(8)
        self._note_edit = QTextEdit()
        self._note_edit.setMaximumHeight(90)
        self._note_edit.setPlaceholderText(
            _transfer_tr(self._db, "dialog.transfer.note.placeholder", "Additional note…")
        )
        optional_layout.addRow(_transfer_tr(self._db, "dialog.transfer.note", "Note:"), self._note_edit)
        self._optional_container.hide()
        layout.addWidget(self._optional_container)

        self._from_combo.currentIndexChanged.connect(self._sync_currency_transfer_fields)
        self._to_combo.currentIndexChanged.connect(self._sync_currency_transfer_fields)
        self._amount_spin.valueChanged.connect(self._recalculate_from_rate)
        self._rate_spin.valueChanged.connect(self._recalculate_from_rate)
        self._converted_amount_spin.valueChanged.connect(self._recalculate_rate_from_destination)
        self._sync_currency_transfer_fields()

        action_row = QHBoxLayout()
        cancel_btn = QPushButton(_transfer_tr(self._db, "dialog.common.cancel", "Cancel"))
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton(self._dialog_title())
        save_btn.clicked.connect(self._on_accept)
        cancel_btn.setStyleSheet(_SECONDARY_ACTION_BUTTON_STYLE)
        save_btn.setStyleSheet(_PRIMARY_ACTION_BUTTON_STYLE)
        action_row.addWidget(cancel_btn)
        action_row.addWidget(save_btn)
        layout.addLayout(action_row)

    @staticmethod
    def _account_currency(acc: dict | None) -> str:
        return (acc or {}).get("currency", "NIO")

    def _selected_account(self, combo: QComboBox) -> dict | None:
        account_id = combo.currentData()
        for acc in self._accounts:
            if acc.get("id") == account_id:
                return acc
        return None

    def _toggle_optional(self, checked: bool) -> None:
        self._optional_container.setVisible(checked)

    def _sync_currency_transfer_fields(self) -> None:
        from_acc = self._selected_account(self._from_combo)
        to_acc = self._selected_account(self._to_combo)
        from_cur = self._account_currency(from_acc)
        to_cur = self._account_currency(to_acc)
        different = from_cur != to_cur

        self._from_currency_edit.setText(from_cur)
        self._to_currency_edit.setText(to_cur)
        self._amount_label.setText(
            _transfer_tr(self._db, "dialog.transfer.source_amount", "Source amount ({currency}):", currency=from_cur)
        )
        self._amount_spin.setPrefix(f"{from_cur} ")
        self._rate_label.setText(
            _transfer_tr(
                self._db,
                "dialog.transfer.exchange_rate",
                "Exchange rate ({from_cur} → {to_cur}):",
                from_cur=from_cur,
                to_cur=to_cur,
            )
        )
        self._converted_label.setText(
            _transfer_tr(
                self._db,
                "dialog.transfer.destination_amount",
                "Destination amount ({currency}):",
                currency=to_cur,
            )
        )
        self._converted_amount_spin.setPrefix(f"{to_cur} ")

        self._rate_spin.setEnabled(different)
        self._converted_amount_spin.setEnabled(True)
        if not different:
            self._set_rate_value(1.0)
            self._set_converted_amount(self._amount_spin.value())
            return
        self._recalculate_from_rate()

    def _recalculate_from_rate(self) -> None:
        if self._syncing_fx_fields:
            return
        from_acc = self._selected_account(self._from_combo)
        to_acc = self._selected_account(self._to_combo)
        if self._account_currency(from_acc) == self._account_currency(to_acc):
            self._set_rate_value(1.0)
            self._set_converted_amount(self._amount_spin.value())
            return
        self._set_converted_amount(self._amount_spin.value() * self._rate_spin.value())

    def _recalculate_rate_from_destination(self) -> None:
        if self._syncing_fx_fields:
            return
        from_acc = self._selected_account(self._from_combo)
        to_acc = self._selected_account(self._to_combo)
        if self._account_currency(from_acc) == self._account_currency(to_acc):
            self._set_rate_value(1.0)
            return
        amount = self._amount_spin.value()
        if amount <= 0:
            return
        self._set_rate_value(self._converted_amount_spin.value() / amount)

    def _set_rate_value(self, value: float) -> None:
        self._syncing_fx_fields = True
        self._rate_spin.setValue(round(value, 6))
        self._syncing_fx_fields = False

    def _set_converted_amount(self, value: float) -> None:
        self._syncing_fx_fields = True
        self._converted_amount_spin.setValue(round(value, 2))
        self._syncing_fx_fields = False

    def _on_accept(self) -> None:
        val_title = _transfer_tr(self._db, "dialog.transfer.validation.title", "Validation")
        if self._from_combo.count() == 0 or self._to_combo.count() == 0:
            _notify_warning(
                self,
                val_title,
                _transfer_tr(
                    self._db,
                    (
                        "dialog.transfer.credit_payment.validation.accounts"
                        if self._credit_payment
                        else "dialog.transfer.validation.accounts"
                    ),
                    "There are no eligible accounts for this operation.",
                ),
            )
            return
        if self._from_combo.currentData() == self._to_combo.currentData():
            _notify_warning(
                self,
                val_title,
                _transfer_tr(
                    self._db, "dialog.transfer.validation.same_account", "From and To accounts must be different."
                ),
            )
            return
        if self._amount_spin.value() <= 0:
            _notify_warning(
                self,
                val_title,
                _transfer_tr(self._db, "dialog.transfer.validation.amount", "Amount must be greater than zero."),
            )
            return
        from_acc = self._selected_account(self._from_combo)
        to_acc = self._selected_account(self._to_combo)
        if self._account_currency(from_acc) != self._account_currency(to_acc):
            if self._rate_spin.value() <= 0:
                _notify_warning(
                    self,
                    val_title,
                    _transfer_tr(
                        self._db, "dialog.transfer.validation.rate", "Exchange rate must be greater than zero."
                    ),
                )
                return
            if self._converted_amount_spin.value() <= 0:
                _notify_warning(
                    self,
                    val_title,
                    _transfer_tr(
                        self._db,
                        "dialog.transfer.validation.converted",
                        "Destination amount must be greater than zero.",
                    ),
                )
                return
        self.accept()

    def get_data(self) -> dict:
        return {
            "from_account_id": self._from_combo.currentData(),
            "to_account_id": self._to_combo.currentData(),
            "amount": self._amount_spin.value(),
            "exchange_rate": self._rate_spin.value(),
            "converted_amount": self._converted_amount_spin.value(),
            "tx_date": self._date_edit.date().toString("yyyy-MM-dd"),
            "description": self._desc_edit.text().strip() or None,
            "note": self._note_edit.toPlainText().strip() or None,
        }


class BalanceAdjustmentDialog(QDialog):
    """Create or edit a balance adjustment for eligible accounts."""

    def __init__(
        self,
        db: Database,
        parent: QWidget | None = None,
        *,
        account_id: int | None = None,
        tx: dict | None = None,
        service: AccountsViewService | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._service = service or AccountsViewService(db)
        self._tx = tx
        self._transaction_id = int(tx["id"]) if tx and tx.get("id") is not None else None
        self._requested_account_id = account_id
        self._warn_before_creation_date = False
        self._accounts = self._service.list_balance_adjustment_accounts()
        self.setWindowTitle(self._dialog_title())
        self.setMinimumWidth(620)
        self._build_ui()
        if self._tx is not None:
            self._prefill(self._tx)
        elif self._requested_account_id is not None:
            self._set_account(self._requested_account_id)
        self._refresh_preview()

    def _dialog_title(self) -> str:
        return _transfer_tr(self._db, "dialog.adjustment.title", "Balance adjustment")

    def _save_button_text(self) -> str:
        return (
            _transfer_tr(self._db, "dialog.adjustment.save.edit", "Update adjustment")
            if self._tx is not None
            else _transfer_tr(self._db, "dialog.adjustment.save.create", "Save adjustment")
        )

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        title = QLabel(self._dialog_title())
        title.setStyleSheet("font-size:28px;font-weight:700;padding-bottom:4px;")
        layout.addWidget(title)

        selectors = QHBoxLayout()
        left = QFormLayout()
        left.setSpacing(10)
        self._account_combo = QComboBox()
        self._account_combo.setEditable(False)
        for account in self._accounts:
            self._account_combo.addItem(f"{account['name']} ({account.get('currency', 'USD')})", int(account["id"]))
        left.addRow(_transfer_tr(self._db, "dialog.adjustment.account", "Account:"), self._account_combo)
        self._date_edit = _make_date_edit()
        left.addRow(_transfer_tr(self._db, "dialog.adjustment.date", "Date:"), self._date_edit)
        selectors.addLayout(left, 1)

        right = QFormLayout()
        right.setSpacing(10)
        self._currency_value = QLineEdit()
        self._currency_value.setReadOnly(True)
        right.addRow(_transfer_tr(self._db, "dialog.adjustment.currency", "Currency:"), self._currency_value)
        selectors.addLayout(right, 1)
        layout.addLayout(selectors)

        self._balance_as_of_label = QLabel(
            _transfer_tr(self._db, "dialog.adjustment.balance_as_of", "Balance at selected date:")
        )
        layout.addWidget(self._balance_as_of_label)
        self._balance_as_of_value = QLabel("")
        self._balance_as_of_value.setStyleSheet("font-size:24px;font-weight:700;color:#D7BA7D;")
        layout.addWidget(self._balance_as_of_value)

        self._amount_label = QLabel(_transfer_tr(self._db, "dialog.adjustment.amount", "Adjustment amount:"))
        layout.addWidget(self._amount_label)
        self._signed_amount_spin = _make_balance_spin(self._db)
        self._signed_amount_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._signed_amount_spin.setStyleSheet(_hero_amount_spin_style("#D7BA7D"))
        layout.addWidget(self._signed_amount_spin)

        self._projected_balance_label = QLabel(
            _transfer_tr(self._db, "dialog.adjustment.projected_balance", "Balance after adjustment:")
        )
        layout.addWidget(self._projected_balance_label)
        self._projected_balance_value = QLabel("")
        self._projected_balance_value.setStyleSheet("font-size:24px;font-weight:700;color:#4EC9B0;")
        layout.addWidget(self._projected_balance_value)

        self._warning_label = QLabel(
            _transfer_tr(
                self._db,
                "dialog.adjustment.warning.before_creation",
                "The selected date is earlier than this account's creation date in MIRA.",
            )
        )
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet(_NOTICE_LABEL_STYLE + "background:#472624;color:#FFB0A3;")
        self._warning_label.hide()
        layout.addWidget(self._warning_label)

        layout.addWidget(QLabel(_transfer_tr(self._db, "dialog.adjustment.note", "Note:")))
        self._note_edit = QTextEdit()
        self._note_edit.setMaximumHeight(90)
        self._note_edit.setPlaceholderText(
            _transfer_tr(self._db, "dialog.adjustment.note.placeholder", "Optional reconciliation note…")
        )
        layout.addWidget(self._note_edit)

        self._account_combo.currentIndexChanged.connect(lambda *_args: self._refresh_preview())
        self._date_edit.dateChanged.connect(lambda *_args: self._refresh_preview())
        self._signed_amount_spin.valueChanged.connect(lambda *_args: self._refresh_preview())

        action_row = QHBoxLayout()
        cancel_btn = QPushButton(_transfer_tr(self._db, "dialog.common.cancel", "Cancel"))
        cancel_btn.clicked.connect(self.reject)
        self._save_btn = QPushButton(self._save_button_text())
        self._save_btn.clicked.connect(self._on_accept)
        cancel_btn.setStyleSheet(_SECONDARY_ACTION_BUTTON_STYLE)
        self._save_btn.setStyleSheet(_PRIMARY_ACTION_BUTTON_STYLE)
        action_row.addWidget(cancel_btn)
        action_row.addWidget(self._save_btn)
        layout.addLayout(action_row)

    def _set_account(self, account_id: int) -> None:
        for index in range(self._account_combo.count()):
            if int(self._account_combo.itemData(index)) == int(account_id):
                self._account_combo.setCurrentIndex(index)
                return

    @staticmethod
    def _signed_amount_from_transaction(tx: dict) -> float:
        amount = float(tx.get("amount") or 0.0)
        return amount if str(tx.get("type") or "") == "income" else -amount

    def _prefill(self, tx: dict) -> None:
        self._set_account(int(tx.get("account_id") or 0))
        if tx.get("date"):
            tx_day = date.fromisoformat(str(tx["date"]))
            from PySide6.QtCore import QDate

            self._date_edit.setDate(QDate(tx_day.year, tx_day.month, tx_day.day))
        self._signed_amount_spin.setValue(self._signed_amount_from_transaction(tx))
        self._note_edit.setPlainText(str(tx.get("note") or ""))

    def _update_amount_style(self) -> None:
        amount = self._signed_amount_spin.value()
        color = "#4EC9B0" if amount > 0 else "#F48771" if amount < 0 else "#D7BA7D"
        self._signed_amount_spin.setStyleSheet(_hero_amount_spin_style(color))

    def _refresh_preview(self) -> None:
        self._update_amount_style()
        account_id = self._account_combo.currentData()
        tx_date = self._date_edit.date().toString("yyyy-MM-dd")
        preview = self._service.preview_balance_adjustment(
            int(account_id) if account_id is not None else None,
            tx_date,
            float(self._signed_amount_spin.value()),
            exclude_transaction_id=self._transaction_id,
        )
        currency = preview.currency
        self._currency_value.setText(currency)
        self._amount_label.setText(
            _transfer_tr(
                self._db,
                "dialog.adjustment.amount.currency",
                "Adjustment amount ({currency}):",
                currency=currency or str(self._db.setting.get_default_currency() or "USD"),
            )
        )
        self._balance_as_of_value.setText(_format_amount_label(self._db, preview.balance_as_of, currency))
        self._projected_balance_value.setText(_format_amount_label(self._db, preview.projected_balance, currency))
        self._warn_before_creation_date = bool(preview.warn_before_creation_date)
        self._warning_label.setVisible(self._warn_before_creation_date)

    def _on_accept(self) -> None:
        val_title = _transfer_tr(self._db, "dialog.adjustment.validation.title", "Validation")
        if self._account_combo.count() == 0:
            _notify_warning(
                self,
                val_title,
                _transfer_tr(
                    self._db,
                    "dialog.adjustment.validation.accounts",
                    "There are no eligible accounts for this operation.",
                ),
            )
            return
        if self._signed_amount_spin.value() == 0:
            _notify_warning(
                self,
                val_title,
                _transfer_tr(
                    self._db,
                    "dialog.adjustment.validation.amount",
                    "Adjustment amount must be different from zero.",
                ),
            )
            return
        if self._warn_before_creation_date:
            reply = QMessageBox.question(
                self,
                _transfer_tr(self._db, "dialog.adjustment.warning.title", "Confirm balance adjustment"),
                _transfer_tr(
                    self._db,
                    "dialog.adjustment.warning.confirm",
                    "The selected date is earlier than the account creation date in MIRA. Do you want to continue?",
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.accept()

    def get_data(self) -> dict[str, object]:
        return {
            "account_id": self._account_combo.currentData(),
            "tx_date": self._date_edit.date().toString("yyyy-MM-dd"),
            "signed_amount": float(self._signed_amount_spin.value()),
            "note": self._note_edit.toPlainText().strip() or None,
        }


__all__ = ["BalanceAdjustmentDialog", "TransactionDialog", "TransferDialog", "_transfer_tr"]
