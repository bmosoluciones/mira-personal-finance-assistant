# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""CRUD dialog classes for MIRA Personal Finance.

Dialogs inherit their surfaces from the active qt-material theme so they
follow the current application stylesheet instead of forcing local dialog
backgrounds or text colors.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QColorDialog,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from mira.db.database import CURRENCY_CODES, Database
from mira.ui.i18n import normalize_language, tr
from mira.ui.notifications import show_user_message
from mira.ui.number_format import NumberMaskedSpinBox, separator_options, validate_number_format_config

# ---------------------------------------------------------------------------
# Shared style
# ---------------------------------------------------------------------------

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
    here = Path(__file__).resolve()
    candidates = (
        here.parent.parent / "icons" / filename,
        here.parent / "icons" / filename,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def _hero_amount_spin_style(color: str) -> str:
    return "QDoubleSpinBox{border-radius:10px;" f"padding:12px 16px;font-size:38px;font-weight:700;color:{color};}}"


def _make_amount_spin(db: Database) -> QDoubleSpinBox:
    spin = NumberMaskedSpinBox(db.setting)
    spin.setRange(0.01, 9_999_999.99)
    spin.setDecimals(2)
    spin.setValue(0.00)
    return spin


def _notify(widget: QWidget, *args: object, level: str = "warning") -> None:
    if len(args) == 3 and isinstance(args[0], QWidget):
        _, title, message = args
    elif len(args) == 2:
        title, message = args
    else:
        raise TypeError("_notify expects (title, message) or (widget, title, message)")
    show_user_message(widget, str(title), str(message), level=level)


def _notify_warning(widget: QWidget, *args: object) -> None:
    _notify(widget, *args, level="warning")


def _make_balance_spin(db: Database) -> QDoubleSpinBox:
    spin = NumberMaskedSpinBox(db.setting)
    spin.setRange(-9_999_999.99, 9_999_999.99)
    spin.setDecimals(2)
    spin.setValue(0.00)
    return spin


def _make_date_edit(default: date | None = None) -> QDateEdit:
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
        self._tags = list(tags)
        valid_ids = {int(tag["id"]) for tag in self._tags}
        if selected_ids is not None:
            self._selected_ids = [int(tag_id) for tag_id in selected_ids if int(tag_id) in valid_ids]
        else:
            self._selected_ids = [tag_id for tag_id in self._selected_ids if tag_id in valid_ids]
        self._rebuild_popup()
        self._update_text()

    def set_selected_ids(self, selected_ids: list[int] | set[int]) -> None:
        valid_ids = {int(tag["id"]) for tag in self._tags}
        self._selected_ids = [int(tag_id) for tag_id in selected_ids if int(tag_id) in valid_ids]
        self._rebuild_popup()
        self._update_text()

    def selected_ids(self) -> list[int]:
        return list(self._selected_ids)

    def option_ids(self) -> list[int]:
        return [int(tag["id"]) for tag in self._tags]

    def popup_list(self) -> QListWidget:
        return self._list

    def _toggle_popup(self) -> None:
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
    normalized_value = icon_value.strip()
    index = combo.findData(normalized_value)
    if index >= 0:
        combo.setCurrentIndex(index)
        return
    if normalized_value:
        combo.addItem(normalized_value, normalized_value)
        combo.setCurrentIndex(combo.count() - 1)


# ---------------------------------------------------------------------------
# TransactionDialog
# ---------------------------------------------------------------------------


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
        self._is_expense = True
        self.setWindowTitle("Editar Transacción" if tx else "Nueva Transacción")
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

        title = QLabel("Editar Transacción" if self._tx else "Nueva Transacción")
        title.setStyleSheet("font-size:28px;font-weight:700;padding-bottom:4px;")
        layout.addWidget(title)

        type_row = QHBoxLayout()
        self._btn_expense = QPushButton("Gasto")
        self._btn_income = QPushButton("Ingreso")
        self._btn_expense.clicked.connect(lambda: self._set_type("expense"))
        self._btn_income.clicked.connect(lambda: self._set_type("income"))
        type_row.addWidget(self._btn_expense)
        type_row.addWidget(self._btn_income)
        layout.addLayout(type_row)

        self._type_combo = QComboBox()
        self._type_combo.addItems(["expense", "income"])
        self._type_combo.hide()

        amount_lbl = QLabel("Monto original")
        layout.addWidget(amount_lbl)
        self._amount_spin = _make_amount_spin(self._db)
        self._amount_spin.setPrefix("$")
        self._amount_spin.setDecimals(2)
        self._amount_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._amount_spin.setStyleSheet(_hero_amount_spin_style("#F48771"))
        layout.addWidget(self._amount_spin)

        grid = QHBoxLayout()

        left = QFormLayout()
        left.setSpacing(10)
        self._date_edit = _make_date_edit()
        left.addRow("Fecha:", self._date_edit)

        self._account_combo = QComboBox()
        self._account_combo.setEditable(False)
        self._populate_accounts()
        self._account_combo.currentIndexChanged.connect(self._sync_fx_state)
        left.addRow("Cuenta:", self._account_combo)

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
        right.addRow("Categoría:", self._category_combo)

        self._tag_selector = _TagMultiSelectButton(self, lang=normalize_language(self._db.setting.get("language")))
        right.addRow("Etiquetas:", self._tag_selector)
        self._refresh_tag_selector()
        grid.addLayout(right, 1)

        self._payment_method_form = QFormLayout()
        self._payment_method_form.setSpacing(10)
        self._payment_method_combo = QComboBox()
        self._payment_method_combo.addItems(["cash", "credit_card", "debit_card", "transfer", "other"])
        layout.addLayout(grid)
        self._payment_method_form.addRow("Método:", self._payment_method_combo)
        layout.addLayout(self._payment_method_form)

        self._fx_check = QCheckBox("Ingresar en moneda distinta a la cuenta")
        self._fx_check.toggled.connect(self._sync_fx_state)
        layout.addWidget(self._fx_check)

        fx_form = QFormLayout()
        fx_form.setSpacing(8)
        self._source_currency_combo = QComboBox()
        self._source_currency_combo.setEditable(False)
        self._populate_source_currencies()
        self._source_currency_combo.currentTextChanged.connect(self._sync_fx_state)
        fx_form.addRow("Moneda original:", self._source_currency_combo)

        self._rate_spin = NumberMaskedSpinBox(self._db.setting)
        self._rate_spin.setRange(0.000001, 9_999_999.99)
        self._rate_spin.setDecimals(6)
        self._rate_spin.setValue(1.0)
        self._rate_spin.valueChanged.connect(self._recompute_converted_amount)
        fx_form.addRow("Tipo de cambio:", self._rate_spin)

        self._converted_amount_spin = _make_amount_spin(self._db)
        self._converted_amount_spin.setPrefix("$")
        self._converted_amount_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._converted_amount_spin.setReadOnly(False)
        fx_form.addRow("Monto convertido:", self._converted_amount_spin)

        layout.addLayout(fx_form)

        self._amount_spin.valueChanged.connect(self._recompute_converted_amount)

        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("Descripción")
        layout.addWidget(QLabel("Descripción"))
        layout.addWidget(self._desc_edit)

        self._details_check = QCheckBox("Añadir más detalles... (opcional)")
        self._details_check.toggled.connect(self._toggle_optional)
        layout.addWidget(self._details_check)

        self._optional_container = QWidget()
        optional_layout = QFormLayout(self._optional_container)
        optional_layout.setSpacing(8)
        self._note_edit = QTextEdit()
        self._note_edit.setMaximumHeight(90)
        self._note_edit.setPlaceholderText("Notas adicionales")
        optional_layout.addRow("Notas:", self._note_edit)

        receipt_row = QHBoxLayout()
        self._receipt_path_edit = QLineEdit()
        self._receipt_path_edit.setPlaceholderText("Ruta del comprobante")
        self._receipt_path_edit.setReadOnly(True)
        browse_btn = QPushButton("Buscar…")
        browse_btn.clicked.connect(self._browse_receipt)
        receipt_row.addWidget(self._receipt_path_edit)
        receipt_row.addWidget(browse_btn)
        optional_layout.addRow("Comprobante:", receipt_row)

        self._optional_container.hide()
        layout.addWidget(self._optional_container)

        action_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Actualizar Transacción" if self._tx else "Guardar Transacción")
        save_btn.clicked.connect(self._on_accept)
        cancel_btn.setStyleSheet(_SECONDARY_ACTION_BUTTON_STYLE)
        save_btn.setStyleSheet(_PRIMARY_ACTION_BUTTON_STYLE)
        action_row.addWidget(cancel_btn)
        action_row.addWidget(save_btn)
        layout.addLayout(action_row)

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
        self._account_currency_lbl.setText(f"Moneda de la cuenta: {account_currency}")

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
        inactive = "QPushButton{background:transparent;" "border-radius:18px;padding:6px 20px;font-size:18px;}"
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
        # Build id->cat map for parent lookup
        id_map = {cat["id"]: cat for cat in cats}
        for cat in cats:
            icon = cat.get("icon", "")
            name = cat["name"]
            parent_id = cat.get("parent_id")
            parent = id_map.get(parent_id) if parent_id in id_map else None
            # Show as: [icon] name (parent)
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
            "Seleccionar comprobante",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.pdf);;All Files (*)",
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

        pm_idx = self._payment_method_combo.findText(tx.get("payment_method") or "cash")
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
            _notify_warning(self, "Validación", "La cantidad debe ser mayor que cero.")
            return
        if self._account_combo.count() == 0:
            _notify_warning(self, "Validación", "No hay cuentas disponibles.")
            return
        if self._fx_check.isChecked():
            if not self._source_currency_combo.currentText().strip():
                _notify_warning(self, "Validación", "Ingrese la moneda original del monto.")
                return
            if self._rate_spin.value() <= 0:
                _notify_warning(self, "Validación", "El tipo de cambio debe ser mayor que cero.")
                return
            if self._converted_amount_spin.value() <= 0:
                _notify_warning(self, "Validación", "El monto convertido debe ser mayor que cero.")
                return
        max_tags = int(self._db.setting.get("max_tags_per_transaction") or 10)
        if len(self._get_selected_tag_ids()) > max_tags:
            _notify_warning(
                self,
                "Validación",
                f"No puedes asignar más de {max_tags} etiquetas a una transacción.",
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
            "payment_method": self._payment_method_combo.currentText(),
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


# ---------------------------------------------------------------------------
# AccountDialog
# ---------------------------------------------------------------------------


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
        self.setWindowTitle("Edit Account" if account else "Add Account")
        self.setMinimumWidth(340)
        self._build_ui()
        if account:
            self._prefill(account)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Account name…")
        form.addRow("Name:", self._name_edit)

        self._type_combo = QComboBox()
        self._type_combo.addItem("bank", "bank")
        self._type_combo.addItem("cash", "cash")
        self._type_combo.addItem("credit", "credit")
        self._type_combo.currentIndexChanged.connect(self._sync_balance_range)
        form.addRow("Type:", self._type_combo)

        self._currency_combo = QComboBox()
        self._currency_combo.setEditable(False)
        self._currency_combo.setMaxVisibleItems(20)
        for cur in self._db.setting.list_currencies(region=None):
            code = str(cur.get("code") or "").strip().upper()
            if code and self._currency_combo.findData(code) < 0:
                self._currency_combo.addItem(code, code)
        default_currency = self._db.setting.get_default_currency()
        current_idx = self._currency_combo.findData(default_currency)
        if current_idx >= 0:
            self._currency_combo.setCurrentIndex(current_idx)
        form.addRow("Currency:", self._currency_combo)

        self._balance_spin = _make_balance_spin(self._db)
        self._balance_spin.setValue(0.00)
        self._balance_row_label = QLabel("Opening Balance:")
        form.addRow(self._balance_row_label, self._balance_spin)

        # Hide opening balance when editing
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
        idx = self._type_combo.findData(account_type)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        cidx = self._currency_combo.findData(
            str(account.get("currency") or self._db.setting.get_default_currency()).upper()
        )
        if cidx >= 0:
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
            _notify_warning(self, "Validation", "Account name cannot be empty.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "name": self._name_edit.text().strip(),
            "account_type": self._selected_account_type(),
            "opening_balance": self._balance_spin.value() if not self._account else 0.0,
            "currency": str(self._currency_combo.currentData() or self._db.setting.get_default_currency()).upper(),
        }


class InitialSetupDialog(QWizard):
    """Multi-page first-run setup wizard.

    Pages
    -----
    0 – Welcome (Bienvenida)
    1 – Profile / display name
    2 – Language & Theme
    3 – Currency & Number format
    4 – Accounts
    """

    _PAGE_WELCOME = 0
    _PAGE_PROFILE = 1
    _PAGE_LANGUAGE = 2
    _PAGE_CURRENCY = 3
    _PAGE_ACCOUNTS = 4

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._wizard_language = "en"
        self.setWindowTitle("MIRA - Initial setup")
        self.setMinimumWidth(560)
        self.setMinimumHeight(520)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setButtonText(QWizard.WizardButton.NextButton, "Next ->")
        self.setButtonText(QWizard.WizardButton.BackButton, "<- Back")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Start")
        self.setButtonText(QWizard.WizardButton.CancelButton, "Cancel")

        self._page_welcome = _WelcomePage()
        self._page_profile = _ProfilePage(db)
        self._page_language = _LanguageThemePage()
        self._page_currency = _CurrencyFormatPage(db)
        self._page_accounts = _AccountsPage()

        self.addPage(self._page_welcome)
        self.addPage(self._page_profile)
        self.addPage(self._page_language)
        self.addPage(self._page_currency)
        self.addPage(self._page_accounts)

        self._page_language.language_changed.connect(self._apply_language)
        self._apply_language(self._page_language.get_language())

    def _apply_language(self, language: str) -> None:
        lang = normalize_language(language)
        self._wizard_language = lang

        self.setWindowTitle(tr("setup.wizard.title", lang))
        self.setButtonText(QWizard.WizardButton.NextButton, tr("setup.wizard.btn.next", lang))
        self.setButtonText(QWizard.WizardButton.BackButton, tr("setup.wizard.btn.back", lang))
        self.setButtonText(QWizard.WizardButton.FinishButton, tr("setup.wizard.btn.finish", lang))
        self.setButtonText(QWizard.WizardButton.CancelButton, tr("setup.wizard.btn.cancel", lang))

        self._page_welcome.apply_language(lang)
        self._page_profile.apply_language(lang)
        self._page_language.apply_language(lang)
        self._page_currency.apply_language(lang)
        self._page_accounts.apply_language(lang)

    def get_data(self) -> dict:
        """Return all wizard selections as a plain dictionary."""
        language = self._page_language.get_language()
        return {
            "username": self._page_profile.get_username(language),
            "language": language,
            "theme": self._page_language.get_theme(),
            "default_currency": self._page_currency.get_currency(),
            "decimal_sep": self._page_currency.get_decimal_sep(),
            "thousands_sep": self._page_currency.get_thousands_sep(),
            "account_names": self._page_accounts.get_account_names(),
            "account_specs": self._page_accounts.get_account_specs(),
        }


# ---------------------------------------------------------------------------
# Wizard page styles
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Page 0 – Welcome
# ---------------------------------------------------------------------------


class _WelcomePage(QWizardPage):
    """Página 1: Pantalla de bienvenida."""

    _ICON_SIZE = 75
    _BMO_LOGO_HEIGHT = 66

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle(" ")  # hide default title bar so we control layout

        layout = QVBoxLayout(self)
        layout.setSpacing(18)
        layout.setContentsMargins(30, 20, 30, 20)

        logo_lbl = QLabel()
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        logo_lbl.setMinimumSize(self._ICON_SIZE, self._ICON_SIZE)
        logo_lbl.setStyleSheet("background:transparent;")
        icon_path = _resolve_ui_icon_path("256x256.png")
        pixmap = QPixmap(str(icon_path))
        if not pixmap.isNull():
            logo_lbl.setPixmap(
                pixmap.scaled(
                    self._ICON_SIZE,
                    self._ICON_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            logo_font = QFont()
            logo_font.setPointSize(28)
            logo_font.setBold(True)
            logo_lbl.setFont(logo_font)
            logo_lbl.setText("MIRA")
        layout.addWidget(logo_lbl)

        tagline_lbl = QLabel("Asistente de Finanzas Personales")
        tagline_font = QFont()
        tagline_font.setPointSize(13)
        tagline_lbl.setFont(tagline_font)
        tagline_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        tagline_lbl.setStyleSheet("background:transparent;")
        layout.addWidget(tagline_lbl)

        layout.addSpacing(10)

        welcome_text = QLabel(
            "¡Bienvenido a MIRA!\n\n"
            "Este asistente te guiará a través de la configuración inicial "
            "para que tengas la mejor experiencia desde el primer momento.\n\n"
            "Haz clic en <b>Siguiente</b> para comenzar."
        )
        welcome_text.setWordWrap(True)
        welcome_text.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        welcome_text.setStyleSheet("font-size:13px;background:transparent;")
        layout.addWidget(welcome_text)

        layout.addSpacing(10)

        features_box = QGroupBox("Lo que configuraremos juntos")
        features_layout = QVBoxLayout(features_box)
        for step in [
            "🌐  Idioma y tema visual",
            "💱  Moneda y formato de números",
            "📁  Categorías predeterminadas",
            "🏦  Tus cuentas financieras",
        ]:
            lbl = QLabel(step)
            lbl.setStyleSheet("font-size:12px;background:transparent;")
            features_layout.addWidget(lbl)
        layout.addWidget(features_box)

        layout.addStretch()

        note = QLabel("100 % offline – tus datos nunca salen de tu dispositivo.")
        note.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        note.setStyleSheet("font-size:11px;background:transparent;")
        layout.addWidget(note)

        bmo_logo_lbl = QLabel()
        bmo_logo_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        bmo_logo_lbl.setStyleSheet("background:transparent;padding-top:4px;")
        bmo_logo_path = _resolve_ui_icon_path("BMOLogoSmall.png")
        bmo_pixmap = QPixmap(str(bmo_logo_path))
        if not bmo_pixmap.isNull():
            bmo_logo_lbl.setPixmap(
                bmo_pixmap.scaledToHeight(
                    self._BMO_LOGO_HEIGHT,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            layout.addWidget(bmo_logo_lbl)

        self._logo_lbl = logo_lbl
        self._tagline_lbl = tagline_lbl
        self._welcome_text_lbl = welcome_text
        self._features_box = features_box
        self._feature_labels = features_box.findChildren(QLabel)
        self._note_lbl = note
        self._bmo_logo_lbl = bmo_logo_lbl
        self.apply_language("en")

    def apply_language(self, lang: str) -> None:
        self._tagline_lbl.setText(tr("setup.page.welcome.tagline", lang))
        self._welcome_text_lbl.setText(tr("setup.page.welcome.text", lang))
        self._features_box.setTitle(tr("setup.page.welcome.features_title", lang))
        items = [
            tr("setup.page.welcome.feature.language", lang),
            tr("setup.page.welcome.feature.currency", lang),
            tr("setup.page.welcome.feature.categories", lang),
            tr("setup.page.welcome.feature.accounts", lang),
        ]
        self._note_lbl.setText(tr("setup.page.welcome.note", lang))

        for lbl, text in zip(self._feature_labels, items):
            lbl.setText(text)


# ---------------------------------------------------------------------------
# Page 1 – Profile
# ---------------------------------------------------------------------------


class _ProfilePage(QWizardPage):
    """Page 2: ask how MIRA should address the user."""

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self.setTitle("Your name")
        self.setSubTitle("Tell MIRA how you want to be addressed during setup and in messages.")

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 10, 20, 10)

        intro = QLabel(
            "We will use your name in welcome messages, the assistant panel, and the status bar "
            "to make the experience feel more personal."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("background:transparent;")
        layout.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(12)

        self._name_label = QLabel("Name:")
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("How should MIRA call you?")
        current_username = str(self._db.setting.get("username") or "").strip()
        if current_username and current_username.casefold() not in {"usuario", "user"}:
            self._name_edit.setText(current_username)
        form.addRow(self._name_label, self._name_edit)
        layout.addLayout(form)

        self._hint_label = QLabel("You can change this later from Settings if you prefer another name or nickname.")
        self._hint_label.setWordWrap(True)
        self._hint_label.setStyleSheet("font-size:11px;background:transparent;")
        layout.addWidget(self._hint_label)
        layout.addStretch()

        self.apply_language("en")

    def apply_language(self, lang: str) -> None:
        self.setTitle(tr("setup.page.profile.title", lang))
        self.setSubTitle(tr("setup.page.profile.subtitle", lang))
        self._name_label.setText(tr("setup.page.profile.name_label", lang))
        self._name_edit.setPlaceholderText(tr("setup.page.profile.name_placeholder", lang))
        self._hint_label.setText(tr("setup.page.profile.hint", lang))

    def validatePage(self) -> bool:  # noqa: N802 – Qt method name convention
        if not self._name_edit.text().strip():
            from mira.ui.views._shared import _notify_warning

            lang = self.wizard()._wizard_language if self.wizard() else "en"
            msg = tr("setup.page.profile.validation.required", lang)
            _notify_warning(self, "Validation", msg)
            return False
        return True

    def get_username(self, language: str) -> str:
        return self._name_edit.text().strip() or tr("settings.saved_default_user", language)


# ---------------------------------------------------------------------------
# Page 2 – Language & Theme
# ---------------------------------------------------------------------------


class _LanguageThemePage(QWizardPage):
    """Página 2: Selector de idioma y tema."""

    language_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Idioma y Tema / Language & Theme")
        self.setSubTitle(
            "Elige el idioma de la interfaz y el tema visual que prefieras.\n"
            "Choose the interface language and your preferred visual theme."
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 10, 20, 10)

        form = QFormLayout()
        form.setSpacing(12)

        self._language_combo = QComboBox()
        self._language_combo.addItem("Español", "es")
        self._language_combo.addItem("English", "en")
        en_idx = self._language_combo.findData("en")
        if en_idx >= 0:
            self._language_combo.setCurrentIndex(en_idx)
        self._language_label = QLabel("Language:")
        form.addRow(self._language_label, self._language_combo)

        self._theme_combo = QComboBox()
        self._theme_combo.setMaxVisibleItems(15)
        try:
            import qt_material  # noqa: PLC0415

            for theme_file in qt_material.list_themes():
                label = theme_file.replace(".xml", "").replace("_", " ").title()
                self._theme_combo.addItem(label, theme_file)
        except ImportError:
            self._theme_combo.addItem("🌙  Oscuro / Dark", "dark_teal.xml")
            self._theme_combo.addItem("☀️  Claro / Light", "light_blue.xml")
        # First-run setup should start from the more legible light onboarding theme.
        default_idx = self._theme_combo.findData(_INITIAL_SETUP_THEME)
        if default_idx >= 0:
            self._theme_combo.setCurrentIndex(default_idx)
        self._theme_label = QLabel("Theme:")
        form.addRow(self._theme_label, self._theme_combo)

        layout.addLayout(form)
        layout.addStretch()
        self._language_combo.currentIndexChanged.connect(self._on_language_changed)
        self.apply_language("en")

    def _on_language_changed(self) -> None:
        lang = self.get_language()
        self.apply_language(lang)
        self.language_changed.emit(lang)

    def apply_language(self, lang: str) -> None:
        self.setTitle(tr("setup.page.language.title", lang))
        self.setSubTitle(tr("setup.page.language.subtitle", lang))
        self._language_label.setText(tr("setup.page.language.language_label", lang))
        self._theme_label.setText(tr("setup.page.language.theme_label", lang))

    def get_language(self) -> str:
        return self._language_combo.currentData() or "en"

    def get_theme(self) -> str:
        return self._theme_combo.currentData() or _INITIAL_SETUP_THEME


# ---------------------------------------------------------------------------
# Page 2 – Currency & Number format
# ---------------------------------------------------------------------------


class _CurrencyFormatPage(QWizardPage):
    """Página 3: Moneda predeterminada y separadores de número."""

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._language = "en"
        self.setTitle("Moneda y Formato de Números")
        self.setSubTitle("Selecciona la moneda principal y cómo se mostrarán los números.")

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 10, 20, 10)

        form = QFormLayout()
        form.setSpacing(12)

        # Currency
        self._currency_combo = QComboBox()
        self._currency_combo.setMaxVisibleItems(15)
        currencies = self._db.setting.list_currencies(region=None)
        for currency in currencies:
            code = currency.get("code", "").strip().upper()
            name = currency.get("name", "")
            if code:
                self._currency_combo.addItem(f"{code}  –  {name}", code)
        for code in CURRENCY_CODES:
            if self._currency_combo.findData(code) < 0:
                self._currency_combo.addItem(code, code)
        default_currency = (self._db.setting.get("default_currency") or "USD").strip().upper()
        idx = self._currency_combo.findData(default_currency)
        if idx >= 0:
            self._currency_combo.setCurrentIndex(idx)
        self._currency_label = QLabel("Default currency:")
        form.addRow(self._currency_label, self._currency_combo)

        # Separators
        sep_opts = separator_options()  # ((value, label), ...)

        self._thousands_combo = QComboBox()
        for value, label in sep_opts:
            self._thousands_combo.addItem(label, value)
        self._thousands_combo.setCurrentIndex(0)  # default ","
        self._thousands_label = QLabel("Thousands separator:")
        form.addRow(self._thousands_label, self._thousands_combo)

        self._decimal_combo = QComboBox()
        for value, label in sep_opts:
            self._decimal_combo.addItem(label, value)
        # default decimal = "."  (index 1 in _SEPARATOR_OPTIONS)
        dot_idx = self._decimal_combo.findData(".")
        if dot_idx >= 0:
            self._decimal_combo.setCurrentIndex(dot_idx)
        self._decimal_label = QLabel("Decimal separator:")
        form.addRow(self._decimal_label, self._decimal_combo)

        layout.addLayout(form)

        hint = QLabel(
            "Ejemplo: con separador de miles ',' y decimal '.' → 1,234.56\n"
            "         con separador de miles '.' y decimal ',' → 1.234,56"
        )
        hint.setStyleSheet("font-size:11px;background:transparent;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        self._hint_label = hint
        self.apply_language("en")

    def apply_language(self, lang: str) -> None:
        self._language = normalize_language(lang)
        self.setTitle(tr("setup.page.currency.title", lang))
        self.setSubTitle(tr("setup.page.currency.subtitle", lang))
        self._currency_label.setText(tr("setup.page.currency.currency_label", lang))
        self._thousands_label.setText(tr("setup.page.currency.thousands_label", lang))
        self._decimal_label.setText(tr("setup.page.currency.decimal_label", lang))
        self._hint_label.setText(tr("setup.page.currency.hint", lang))

    def get_currency(self) -> str:
        return self._currency_combo.currentData() or "USD"

    def get_thousands_sep(self) -> str:
        return self._thousands_combo.currentData() or ","

    def get_decimal_sep(self) -> str:
        return self._decimal_combo.currentData() or "."

    def validatePage(self) -> bool:
        try:
            validate_number_format_config(self.get_thousands_sep(), self.get_decimal_sep())
        except ValueError:
            show_user_message(
                self,
                tr("settings.title", self._language, default="Settings"),
                tr(
                    "settings.validation.number_separators_distinct",
                    self._language,
                    default="Thousands and decimal separators must be different.",
                ),
                level="warning",
            )
            return False
        return True


# ---------------------------------------------------------------------------
# Page 3 – Accounts
# ---------------------------------------------------------------------------


class _AccountsPage(QWizardPage):
    """Página 5: Creación de cuentas financieras.

    The user can enter N account names using "Agregar cuenta adicional".
    If the user finishes without adding any account names, a single
    default account is created automatically.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._account_rows: list[dict[str, object]] = []

        self.setTitle("Tus Cuentas")
        self.setSubTitle(
            "Agrega las cuentas que deseas gestionar (cuenta bancaria, efectivo, etc.).\n"
            "La primera cuenta se marcará como predeterminada."
        )

        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        outer.setContentsMargins(20, 10, 20, 10)

        # Scrollable area for dynamic account inputs
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border-radius:4px;}")
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background:transparent;")
        self._inputs_layout = QVBoxLayout(scroll_widget)
        self._inputs_layout.setSpacing(8)
        self._inputs_layout.setContentsMargins(10, 10, 10, 10)
        self._inputs_layout.addStretch()
        scroll.setWidget(scroll_widget)
        outer.addWidget(scroll, 1)

        # "Add account" button
        btn_add = QPushButton("➕  Agregar cuenta adicional")
        btn_add.clicked.connect(self._add_input_row)
        outer.addWidget(btn_add)
        self._btn_add = btn_add

        # Skip link-style button
        btn_skip = QPushButton("Saltar → crear cuenta predeterminada automáticamente")
        btn_skip.setStyleSheet(
            "QPushButton{background:transparent;" "border:none;text-decoration:underline;padding:2px;}"
        )
        btn_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_skip.clicked.connect(self._on_skip)
        outer.addWidget(btn_skip, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._btn_skip = btn_skip
        self._btn_skip.hide()

        self.apply_language("en")

    def initializePage(self) -> None:
        """Create the first account row only after the page is attached to its wizard."""
        super().initializePage()
        if not self._account_rows:
            self._add_input_row()
        else:
            self._sync_account_row_currency_defaults()

    def _add_input_row(self) -> None:
        idx = len(self._account_rows) + 1
        lang = getattr(self, "_lang", "en")
        currency_default = self._db_default_currency()

        card = QGroupBox()
        card.setStyleSheet("QGroupBox{margin-top:6px;}")
        form = QFormLayout(card)
        form.setSpacing(8)

        name_edit = QLineEdit()
        name_edit.setPlaceholderText(tr("setup.page.accounts.row.name_placeholder", lang, params={"idx": idx}))
        form.addRow(tr("setup.page.accounts.row.name_label", lang), name_edit)

        type_combo = QComboBox()
        type_combo.addItem(tr("setup.page.accounts.row.type.bank", lang), "bank")
        type_combo.addItem(tr("setup.page.accounts.row.type.cash", lang), "cash")
        type_combo.addItem(tr("setup.page.accounts.row.type.credit", lang), "credit")
        form.addRow(tr("setup.page.accounts.row.type_label", lang), type_combo)

        currency_combo = QComboBox()
        currency_combo.setEditable(True)
        for cur in self._db_currencies():
            code = str(cur["code"]).upper()
            currency_combo.addItem(code, code)
        idx_currency = currency_combo.findData(currency_default)
        if idx_currency >= 0:
            currency_combo.setCurrentIndex(idx_currency)
        else:
            currency_combo.setCurrentText(currency_default)
        form.addRow(tr("setup.page.accounts.row.currency_label", lang), currency_combo)

        balance_spin = _make_balance_spin(self._db_ref())
        balance_spin.setValue(0.0)
        form.addRow(tr("setup.page.accounts.row.balance_label", lang), balance_spin)

        row_spec: dict[str, object] = {
            "card": card,
            "name": name_edit,
            "type": type_combo,
            "currency": currency_combo,
            "opening_balance": balance_spin,
            "suggested_currency": currency_default,
        }
        self._account_rows.append(row_spec)
        self._apply_row_title(row_spec, idx)

        stretch_idx = self._inputs_layout.count() - 1
        self._inputs_layout.insertWidget(stretch_idx, card)

    def _db_ref(self) -> Database:
        wizard = self.wizard()
        if wizard is not None and hasattr(wizard, "_db"):
            return cast(Database, wizard._db)
        raise RuntimeError("Accounts page requires a database reference")

    def _db_default_currency(self) -> str:
        wizard = self.wizard()
        if wizard is not None and hasattr(wizard, "_page_currency"):
            return str(wizard._page_currency.get_currency()).upper()
        return self._db_ref().setting.get_default_currency()

    def _db_currencies(self) -> list[dict]:
        return self._db_ref().setting.list_currencies(region="americas")

    def _sync_account_row_currency_defaults(self) -> None:
        current_default = self._db_default_currency()
        for row_spec in self._account_rows:
            currency_combo = cast(QComboBox, row_spec["currency"])
            previous_default = str(row_spec.get("suggested_currency") or "").strip().upper()
            current_value = currency_combo.currentText().strip().upper()
            if not current_value or current_value == previous_default:
                idx_currency = currency_combo.findData(current_default)
                if idx_currency >= 0:
                    currency_combo.setCurrentIndex(idx_currency)
                else:
                    currency_combo.setCurrentText(current_default)
            row_spec["suggested_currency"] = current_default

    def _apply_row_title(self, row_spec: dict[str, object], idx: int) -> None:
        card = cast(QGroupBox, row_spec["card"])
        name_edit = cast(QLineEdit, row_spec["name"])
        lang = getattr(self, "_lang", "en")
        card.setTitle(tr("setup.page.accounts.row.title", lang, params={"idx": idx}))
        name_edit.setPlaceholderText(tr("setup.page.accounts.row.name_placeholder", lang, params={"idx": idx}))

    def _refresh_input_labels(self) -> None:
        for idx, row_spec in enumerate(self._account_rows, start=1):
            self._apply_row_title(row_spec, idx)

    def _on_skip(self) -> None:
        return

    def apply_language(self, lang: str) -> None:
        self._lang = lang
        self.setTitle(tr("setup.page.accounts.title", lang))
        self.setSubTitle(tr("setup.page.accounts.subtitle", lang))
        self._btn_add.setText(tr("setup.page.accounts.btn_add", lang))
        self._refresh_input_labels()

    def get_account_names(self) -> list[str]:
        """Return the list of account names the user entered.

        Returns ``[]`` when no account names were entered.
        """
        return [str(spec["name"]) for spec in self.get_account_specs()]

    def get_account_specs(self) -> list[dict[str, object]]:
        specs: list[dict[str, object]] = []
        for row_spec in self._account_rows:
            name_edit = cast(QLineEdit, row_spec["name"])
            type_combo = cast(QComboBox, row_spec["type"])
            currency_combo = cast(QComboBox, row_spec["currency"])
            balance_spin = cast(QDoubleSpinBox, row_spec["opening_balance"])
            name = name_edit.text().strip()
            if not name:
                continue
            specs.append(
                {
                    "name": name,
                    "account_type": str(type_combo.currentData() or "bank"),
                    "currency": currency_combo.currentText().strip().upper() or self._db_default_currency(),
                    "opening_balance": float(balance_spin.value()),
                }
            )
        return specs


# ---------------------------------------------------------------------------
# CategoryDialog
# ---------------------------------------------------------------------------


class CategoryDialog(QDialog):
    """Create or edit a category."""

    def __init__(
        self,
        db: Database,
        category: dict | None = None,
        default_type: str = "expense",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._category = category
        self._default_type = default_type
        self.setWindowTitle("Edit Category" if category else "Add Category")
        self.setMinimumWidth(320)
        self._build_ui()
        if category:
            self._prefill(category)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Category name…")
        form.addRow("Name:", self._name_edit)

        self._type_combo = QComboBox()
        self._type_combo.addItems(["expense", "income"])
        idx = self._type_combo.findText(self._default_type)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        self._type_combo.currentIndexChanged.connect(self._populate_parents)
        form.addRow("Type:", self._type_combo)

        # Color picker (reuses the same pattern as TagDialog)
        self._color_preview = QLabel()
        self._color_preview.setFixedSize(24, 24)
        self._color_preview.setStyleSheet("border:1px solid #888888;border-radius:4px;background:#888888;")
        self._color_value_label = QLabel()
        self._color_value_label.setMinimumWidth(84)
        self._color_value_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._color_btn = QPushButton("Choose color")
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
        form.addRow("Color:", color_container)

        self._icon_combo = _build_icon_combo(self, lang=normalize_language(self._db.setting.get("language")))
        form.addRow("Icon:", self._icon_combo)

        # Parent category selector (only one level)
        self._parent_combo = QComboBox()
        self._parent_combo.addItem("(None)", None)
        # Will be populated in _populate_parents()
        form.addRow("Parent:", self._parent_combo)

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
        color = QColor(color_value)
        if not color.isValid():
            color = QColor("#888888")
        self._selected_color = color.name()
        self._color_value_label.setText(self._selected_color.upper())
        self._color_preview.setStyleSheet(
            f"border:1px solid #888888;border-radius:4px;background:{self._selected_color};"
        )

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._selected_color), self, "Select Category Color")
        if color.isValid():
            self._update_color_preview(color.name())

    def _prefill(self, cat: dict) -> None:
        self._name_edit.setText(cat.get("name", ""))
        idx = self._type_combo.findText(cat.get("type", "expense"))
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        self._update_color_preview(str(cat.get("color") or "#888888"))
        _set_icon_combo_value(self._icon_combo, str(cat.get("icon") or ""))
        # Set parent combo
        parent_id = cat.get("parent_id")
        if parent_id is not None:
            idx = self._parent_combo.findData(parent_id)
            if idx >= 0:
                self._parent_combo.setCurrentIndex(idx)

    def _on_accept(self) -> None:
        if not self._name_edit.text().strip():
            _notify_warning(self, "Validation", "Category name cannot be empty.")
            return
        self.accept()

    def get_data(self) -> dict:
        """
        Returns category data. Only one parent level is supported in the UI, but the backend supports deeper hierarchies.
        The icon field is selected from a predefined dropdown, while preserving custom icons already stored in the DB.
        """
        icon_value = (self._icon_combo.currentData() or self._icon_combo.currentText()).strip()
        return {
            "name": self._name_edit.text().strip(),
            "cat_type": self._type_combo.currentText(),
            "color": self._selected_color,
            "icon": icon_value,
            "parent_id": self._parent_combo.currentData(),
        }

    def _populate_parents(self):
        # Only show categories of the same type, exclude self if editing
        cat_type = self._type_combo.currentText()
        all_cats = self._db.category.list(cat_type)
        current_id = self._category["id"] if self._category and "id" in self._category else None
        self._parent_combo.clear()
        self._parent_combo.addItem("(None)", None)
        for cat in all_cats:
            if current_id is not None and cat["id"] == current_id:
                continue
            label = f"{cat.get('icon', '')} {cat['name']}".strip()
            self._parent_combo.addItem(label, cat["id"])


class MergeCategoryDialog(QDialog):
    """Merge one category into another category of the same type."""

    def __init__(
        self,
        db: Database,
        cat_type: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._cat_type = cat_type
        self.setWindowTitle("Merge Categories")
        self.setMinimumWidth(380)
        self._categories = self._db.category.list(cat_type)
        self._build_ui()

    def _build_ui(self) -> None:
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

        form.addRow("Source category:", self._source_combo)
        form.addRow("Destination category:", self._target_combo)

        note = QLabel(
            "All transactions and recurring records from source category " "will be moved to the destination category."
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
        source_id = self._source_combo.currentData()
        target_id = self._target_combo.currentData()
        if source_id == target_id:
            _notify_warning(self, "Validation", "Source and destination categories must be different.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "source_id": int(self._source_combo.currentData()),
            "target_id": int(self._target_combo.currentData()),
            "cat_type": self._cat_type,
        }


class BudgetCreateDialog(QDialog):
    """Create a new annual budget."""

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self.setWindowTitle("Nuevo presupuesto")
        self.setMinimumWidth(360)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self._code_edit = QLineEdit()
        self._code_edit.setPlaceholderText("ppto2026, ppto_vacaciones, ppto_v2…")
        form.addRow("Código:", self._code_edit)

        self._year_spin = QSpinBox()
        self._year_spin.setRange(1900, 9999)
        self._year_spin.setValue(date.today().year)
        form.addRow("Año:", self._year_spin)

        self._currency_combo = QComboBox()
        self._currency_combo.setEditable(True)
        for currency in self._db.setting.list_currencies(region=None):
            code = str(currency["code"]).upper()
            self._currency_combo.addItem(code, code)
        default_currency = self._db.setting.get_default_currency()
        current_idx = self._currency_combo.findData(default_currency)
        if current_idx >= 0:
            self._currency_combo.setCurrentIndex(current_idx)
        else:
            self._currency_combo.setCurrentText(default_currency)
        form.addRow("Moneda:", self._currency_combo)

        help_lbl = QLabel(
            "El presupuesto es anual. Después de crearlo podrás editar los 12 meses, "
            "proponer un presupuesto inicial y compararlo contra lo real."
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
            _notify_warning(self, "Validación", "El código del presupuesto es obligatorio.")
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


# ---------------------------------------------------------------------------
# TransferDialog
# ---------------------------------------------------------------------------


def _transfer_tr(db: Database, key: str, default: str, **params: object) -> str:
    """Shortcut for translation inside TransferDialog."""
    lang = normalize_language(db.setting.get("language") if db else "en")
    return tr(key, lang, default=default, params=params if params else None)


class TransferDialog(QDialog):
    """Transfer money between two accounts — styled consistently with TransactionDialog."""

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

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # --- Title ---
        title = QLabel(self._dialog_title())
        title.setStyleSheet("font-size:28px;font-weight:700;padding-bottom:4px;")
        layout.addWidget(title)

        # --- Amount (large, styled) ---
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
        amount_lbl = QLabel(
            _transfer_tr(self._db, "dialog.transfer.source_amount", "Source amount ({currency}):", currency=from_cur)
        )
        amount_lbl.setObjectName("_amount_label")
        layout.addWidget(amount_lbl)
        self._amount_label = amount_lbl

        self._amount_spin = _make_amount_spin(self._db)
        self._amount_spin.setPrefix(f"{from_cur} ")
        self._amount_spin.setDecimals(2)
        self._amount_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._amount_spin.setStyleSheet(_hero_amount_spin_style("#569CD6"))
        layout.addWidget(self._amount_spin)

        # --- Account selectors ---
        grid = QHBoxLayout()

        left = QFormLayout()
        left.setSpacing(10)

        self._from_combo = QComboBox()
        self._from_combo.setEditable(False)
        for acc in self._from_accounts:
            label = f"{acc['name']} ({acc.get('currency', 'NIO')})"
            self._from_combo.addItem(label, acc["id"])
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
        left.addRow(
            _transfer_tr(self._db, "dialog.transfer.date", "Date:"),
            self._date_edit,
        )

        grid.addLayout(left, 1)

        right = QFormLayout()
        right.setSpacing(10)

        self._to_combo = QComboBox()
        self._to_combo.setEditable(False)
        for acc in self._to_accounts:
            label = f"{acc['name']} ({acc.get('currency', 'NIO')})"
            self._to_combo.addItem(label, acc["id"])
        right.addRow(
            _transfer_tr(
                self._db,
                "dialog.transfer.credit_payment.to_account" if self._credit_payment else "dialog.transfer.to_account",
                "Credit card:" if self._credit_payment else "To account:",
            ),
            self._to_combo,
        )

        right.addRow("", QLabel(""))  # spacer to align with left column

        grid.addLayout(right, 1)
        layout.addLayout(grid)

        # --- Currency / FX section ---
        self._fx_container = QWidget()
        fx_form = QFormLayout(self._fx_container)
        fx_form.setSpacing(8)

        self._from_currency_edit = QLineEdit()
        self._from_currency_edit.setReadOnly(True)
        fx_form.addRow(
            _transfer_tr(self._db, "dialog.transfer.source_currency", "Source currency:"),
            self._from_currency_edit,
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

        # --- Description ---
        desc_lbl = QLabel(_transfer_tr(self._db, "dialog.transfer.description", "Description:"))
        layout.addWidget(desc_lbl)
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

        # --- Optional details (collapsible) ---
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
        optional_layout.addRow(
            _transfer_tr(self._db, "dialog.transfer.note", "Note:"),
            self._note_edit,
        )
        self._optional_container.hide()
        layout.addWidget(self._optional_container)

        # --- Signal connections ---
        self._from_combo.currentIndexChanged.connect(self._sync_currency_transfer_fields)
        self._to_combo.currentIndexChanged.connect(self._sync_currency_transfer_fields)
        self._amount_spin.valueChanged.connect(self._recalculate_from_rate)
        self._rate_spin.valueChanged.connect(self._recalculate_from_rate)
        self._converted_amount_spin.valueChanged.connect(self._recalculate_rate_from_destination)
        self._sync_currency_transfer_fields()

        # --- Action buttons ---
        action_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton(self._dialog_title())
        save_btn.clicked.connect(self._on_accept)
        cancel_btn.setStyleSheet(_SECONDARY_ACTION_BUTTON_STYLE)
        save_btn.setStyleSheet(_PRIMARY_ACTION_BUTTON_STYLE)
        action_row.addWidget(cancel_btn)
        action_row.addWidget(save_btn)
        layout.addLayout(action_row)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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

        # Update the amount label to reflect source currency
        self._amount_label.setText(
            _transfer_tr(self._db, "dialog.transfer.source_amount", "Source amount ({currency}):", currency=from_cur)
        )
        self._amount_spin.setPrefix(f"{from_cur} ")

        # Update FX labels
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
        converted = self._amount_spin.value() * self._rate_spin.value()
        self._set_converted_amount(converted)

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


# ---------------------------------------------------------------------------
# RecurringDialog
# ---------------------------------------------------------------------------


class RecurringDialog(QDialog):
    """Create a recurring transaction rule."""

    def __init__(
        self,
        db: Database,
        recurring: dict | None = None,
        parent: QWidget | None = None,
    ) -> None:
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
        idx = self._type_combo.findText(rec.get("type", "expense"))
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        self._amount_spin.setValue(float(rec.get("amount", 0)))
        self._desc_edit.setText(rec.get("description") or "")
        category_id = rec.get("category_id")
        if category_id is not None:
            combo_idx = self._category_combo.findData(category_id)
            if combo_idx >= 0:
                self._category_combo.setCurrentIndex(combo_idx)
        elif rec.get("category"):
            combo_idx = self._category_combo.findText(rec.get("category") or "")
            if combo_idx >= 0:
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
            label = f"{category.get('icon', '')} {category['name']}".strip()
            self._category_combo.addItem(label, category["id"])

        if current_category_id is not None:
            idx = self._category_combo.findData(current_category_id)
            if idx >= 0:
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


# ---------------------------------------------------------------------------
# SavingsGoalDialog
# ---------------------------------------------------------------------------


class SavingsGoalDialog(QDialog):
    """Create a savings goal."""

    def __init__(
        self,
        db: Database,
        goal: dict | None = None,
        prefill: dict | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._goal = goal
        self._language = normalize_language(self._db.setting.get("language"))
        self.setWindowTitle(
            self._t("goals.dialog.title.edit", "Edit Goal")
            if goal
            else self._t("goals.dialog.title.add", "Add Savings Goal")
        )
        self.setMinimumWidth(340)
        self._build_ui()
        if goal:
            self._prefill(goal)
        elif prefill:
            self._prefill(prefill)
        self._update_notice()

    def _t(self, key: str, default: str, *, params: dict[str, object] | None = None) -> str:
        return tr(key, self._language, default=default, params=params)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Goal name… (e.g. Viaje a Europa)")
        self._name_edit.textChanged.connect(self._update_notice)
        form.addRow(self._t("goals.dialog.name", "Name:"), self._name_edit)

        self._target_spin = _make_amount_spin(self._db)
        form.addRow(self._t("goals.dialog.target_amount", "Target Amount:"), self._target_spin)

        self._date_edit = _make_date_edit()
        form.addRow(self._t("goals.dialog.target_date", "Target Date:"), self._date_edit)

        layout.addLayout(form)
        self._notice_lbl = QLabel("")
        self._notice_lbl.setWordWrap(True)
        self._notice_lbl.setStyleSheet(_NOTICE_LABEL_STYLE)
        layout.addWidget(self._notice_lbl)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _prefill(self, goal: dict) -> None:
        from PySide6.QtCore import QDate

        self._name_edit.setText(goal.get("name", ""))
        target_amount = goal.get("target_amount")
        if target_amount is not None:
            try:
                self._target_spin.setValue(float(target_amount))
            except (ValueError, TypeError):
                pass
        td = goal.get("target_date")
        if td:
            parts = td.split("-")
            if len(parts) == 3:
                try:
                    self._date_edit.setDate(QDate(int(parts[0]), int(parts[1]), int(parts[2])))
                except (ValueError, TypeError):
                    pass

    def _update_notice(self) -> None:
        goal_name = self._name_edit.text().strip()
        parent_name = self._db.setting.get_savings_goals_parent_name()
        if self._goal is None:
            key = "goals.dialog.notice.create.named" if goal_name else "goals.dialog.notice.create.generic"
            default = (
                "MIRA will link this goal to the savings expense category '{name}'. "
                "If it does not exist, it will be created automatically under '{parent}'."
                if goal_name
                else "MIRA will link this goal to a savings expense category with the same name. "
                "If it does not exist, it will be created automatically under '{parent}'."
            )
        else:
            key = "goals.dialog.notice.edit.named" if goal_name else "goals.dialog.notice.edit.generic"
            default = (
                "This goal is linked to a savings expense category. If you change its name to '{name}', "
                "MIRA will relink it to a category with that name under '{parent}'. Existing categories and history are not renamed."
                if goal_name
                else "This goal remains linked to a savings expense category. If you change its name, "
                "MIRA will relink it to a category with that new name under '{parent}'. Existing categories and history are not renamed."
            )
        self._notice_lbl.setText(self._t(key, default, params={"name": goal_name, "parent": parent_name}))

    def _on_accept(self) -> None:
        if not self._name_edit.text().strip():
            _notify_warning(
                self,
                self._t("validation.title", "Validation"),
                self._t("goals.dialog.validation.name", "Goal name cannot be empty."),
            )
            return
        if self._target_spin.value() <= 0:
            _notify_warning(
                self,
                self._t("validation.title", "Validation"),
                self._t("goals.dialog.validation.target", "Target amount must be greater than zero."),
            )
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "name": self._name_edit.text().strip(),
            "target_amount": self._target_spin.value(),
            "target_date": self._date_edit.date().toString("yyyy-MM-dd"),
        }


# ---------------------------------------------------------------------------
# ContributeGoalDialog
# ---------------------------------------------------------------------------


class ContributeGoalDialog(QDialog):
    """Add a contribution to a savings goal."""

    def __init__(self, db: Database, goal_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self.setWindowTitle(f"Contribute to: {goal_name}")
        self.setMinimumWidth(300)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self._amount_spin = _make_amount_spin(self._db)
        form.addRow("Amount to Contribute:", self._amount_spin)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        if self._amount_spin.value() <= 0:
            _notify_warning(self, "Validation", "Amount must be greater than zero.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {"amount": self._amount_spin.value()}


# ---------------------------------------------------------------------------
# TagDialog
# ---------------------------------------------------------------------------


class TagDialog(QDialog):
    """Create or edit a tag (etiqueta transversal)."""

    def __init__(self, db: Database, tag: dict | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._tag = tag
        self.setWindowTitle("Edit Tag" if tag else "Add Tag")
        self.setMinimumWidth(320)
        self._build_ui()
        if tag:
            self._prefill(tag)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Tag name…")
        form.addRow("Name:", self._name_edit)

        self._color_preview = QLabel()
        self._color_preview.setFixedSize(24, 24)
        self._color_preview.setStyleSheet("border:1px solid #888888;border-radius:4px;background:#888888;")
        self._color_value_label = QLabel()
        self._color_value_label.setMinimumWidth(84)
        self._color_value_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._color_btn = QPushButton("Choose color")
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
        form.addRow("Color:", color_container)

        self._icon_combo = _build_icon_combo(self, lang=normalize_language(self._db.setting.get("language")))
        form.addRow("Icon:", self._icon_combo)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _prefill(self, tag: dict) -> None:
        self._name_edit.setText(tag.get("name", ""))
        self._update_color_preview(str(tag.get("color") or "#888888"))
        _set_icon_combo_value(self._icon_combo, str(tag.get("icon") or ""))

    def _update_color_preview(self, color_value: str) -> None:
        color = QColor(color_value)
        if not color.isValid():
            color = QColor("#888888")
        self._selected_color = color.name()
        self._color_value_label.setText(self._selected_color.upper())
        self._color_preview.setStyleSheet(
            f"border:1px solid #888888;border-radius:4px;background:{self._selected_color};"
        )

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._selected_color), self, "Select Tag Color")
        if color.isValid():
            self._update_color_preview(color.name())

    def _on_accept(self) -> None:
        if not self._name_edit.text().strip():
            _notify_warning(self, "Validation", "Tag name cannot be empty.")
            return
        self.accept()

    def get_data(self) -> dict:
        icon_value = (self._icon_combo.currentData() or self._icon_combo.currentText()).strip()
        return {
            "name": self._name_edit.text().strip(),
            "color": self._selected_color,
            "icon": icon_value,
        }
