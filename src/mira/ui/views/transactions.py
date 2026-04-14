# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Transactions feature view."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mira.app.view_services import (
    TransactionsFilterOptions,
    TransactionsViewService,
    TransactionsViewState,
)
from mira.db.database import Database
from mira.transaction_kinds import is_balance_adjustment_transaction
from mira.ui.views._shared import (
    _COMBO_STYLE,
    _DATE_STYLE,
    _INPUT_STYLE,
    _TABLE_STYLE,
    _date_to_qdate,
    _fmt_amount,
    _make_tag_badge,
    _make_toolbar_btn,
    _make_tx_type_item,
    _notify_info,
    _notify_warning,
    _section_title,
    _select_row_at_pos,
    _tr_db,
)
from mira.ui.delegates.cell_delegates import _TypeBadgeDelegate


class TransactionsView(QWidget):
    """Full transactions list with CRUD toolbar and filters."""

    def __init__(
        self,
        db: Database,
        parent: QWidget | None = None,
        service: TransactionsViewService | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._service = service or TransactionsViewService(db)
        self._tx_data: list[dict] = []
        self._filter_options = TransactionsFilterOptions(accounts=[], categories=[], tags=[])
        self._tags_by_transaction: dict[int, list[dict]] = {}
        self._savings_categories: set[str] = set()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        layout.addWidget(_section_title(_tr_db(self._db, "view.transactions.title", "Transactions")))

        # --- Toolbar ---
        tb = QHBoxLayout()
        self._btn_add = _make_toolbar_btn(_tr_db(self._db, "btn.add", "+ Add"))
        self._btn_edit = _make_toolbar_btn(_tr_db(self._db, "btn.edit", "✏ Edit"))
        self._btn_delete = _make_toolbar_btn(_tr_db(self._db, "btn.delete", "🗑 Delete"))
        self._btn_dup = _make_toolbar_btn(_tr_db(self._db, "btn.duplicate", "⧉ Duplicate"))
        self._btn_transfer = _make_toolbar_btn(_tr_db(self._db, "btn.transfer", "↔ Transfer"))
        self._btn_credit_payment = _make_toolbar_btn(_tr_db(self._db, "btn.credit_payment", "💳 Card Payment"))
        for btn in [
            self._btn_add,
            self._btn_edit,
            self._btn_delete,
            self._btn_dup,
            self._btn_transfer,
            self._btn_credit_payment,
        ]:
            tb.addWidget(btn)
        tb.addStretch()
        layout.addLayout(tb)

        # --- Filter bar ---
        fbar = QHBoxLayout()
        fbar.setSpacing(6)

        fbar.addWidget(QLabel(_tr_db(self._db, "filter.from", "From:")))
        self._from_date = QDateEdit()
        self._from_date.setCalendarPopup(True)
        self._from_date.setDisplayFormat("yyyy-MM-dd")
        first_of_month = date.today().replace(day=1)
        self._from_date.setDate(_date_to_qdate(first_of_month))
        self._from_date.setStyleSheet(_DATE_STYLE)
        fbar.addWidget(self._from_date)

        fbar.addWidget(QLabel(_tr_db(self._db, "filter.to", "To:")))
        self._to_date = QDateEdit()
        self._to_date.setCalendarPopup(True)
        self._to_date.setDisplayFormat("yyyy-MM-dd")
        today = date.today()
        self._to_date.setDate(_date_to_qdate(today))
        self._to_date.setStyleSheet(_DATE_STYLE)
        fbar.addWidget(self._to_date)

        fbar.addWidget(QLabel(_tr_db(self._db, "filter.account", "Account:")))
        self._acc_filter = QComboBox()
        self._acc_filter.setStyleSheet(_COMBO_STYLE)
        fbar.addWidget(self._acc_filter)

        fbar.addWidget(QLabel(_tr_db(self._db, "filter.category", "Category:")))
        self._cat_filter = QComboBox()
        self._cat_filter.setStyleSheet(_COMBO_STYLE)
        fbar.addWidget(self._cat_filter)

        fbar.addWidget(QLabel(_tr_db(self._db, "filter.search", "Search:")))
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(_tr_db(self._db, "filter.search.placeholder", "description / note..."))
        self._search_input.setStyleSheet(_INPUT_STYLE)
        self._search_input.setMaximumWidth(160)
        fbar.addWidget(self._search_input)

        fbar.addWidget(QLabel(_tr_db(self._db, "filter.tag", "Tag:")))
        self._tag_filter = QComboBox()
        self._tag_filter.setStyleSheet(_COMBO_STYLE)
        self._tag_filter.blockSignals(True)
        self._tag_filter.addItem(_tr_db(self._db, "filter.all_tags", "All Tags"), None)
        for tag in self._db.tag.list():
            self._tag_filter.addItem(tag["name"], tag["id"])
        self._tag_filter.blockSignals(False)
        fbar.addWidget(self._tag_filter)

        self._btn_apply = _make_toolbar_btn(_tr_db(self._db, "filter.apply", "Apply Filter"))
        self._btn_clear = _make_toolbar_btn(_tr_db(self._db, "filter.clear", "Clear"))
        fbar.addWidget(self._btn_apply)
        fbar.addWidget(self._btn_clear)
        fbar.addStretch()
        layout.addLayout(fbar)

        # --- Table ---
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            [
                _tr_db(self._db, "col.date", "Date"),
                _tr_db(self._db, "col.type", "Type"),
                _tr_db(self._db, "col.amount", "Amount"),
                _tr_db(self._db, "col.category", "Category"),
                _tr_db(self._db, "col.description", "Description"),
                _tr_db(self._db, "col.account", "Account"),
                _tr_db(self._db, "col.note", "Note"),
            ]
        )
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Date
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Type
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Amount
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Category
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)  # Description
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Account
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)  # Note
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.setStyleSheet(_TABLE_STYLE)
        self._table.setItemDelegateForColumn(1, _TypeBadgeDelegate(self._table))
        layout.addWidget(self._table, 1)

        # --- Totals KPI row ---
        self._totals_bar = QFrame()
        self._totals_bar.setStyleSheet(
            "QFrame{background:palette(alternate-base);border:1px solid palette(mid);border-radius:8px;}"
        )
        totals_layout = QHBoxLayout(self._totals_bar)
        totals_layout.setContentsMargins(14, 10, 14, 10)
        totals_layout.setSpacing(18)

        self._totals_income_lbl = QLabel()
        self._totals_income_lbl.setStyleSheet("color:#4EC9B0;background:transparent;font-size:20px;font-weight:700;")
        totals_layout.addWidget(self._totals_income_lbl)

        self._totals_expense_lbl = QLabel()
        self._totals_expense_lbl.setStyleSheet("color:#F48771;background:transparent;font-size:20px;font-weight:700;")
        totals_layout.addWidget(self._totals_expense_lbl)

        self._totals_net_lbl = QLabel()
        self._totals_net_lbl.setStyleSheet("color:#4EC9B0;background:transparent;font-size:20px;font-weight:700;")
        totals_layout.addWidget(self._totals_net_lbl)

        self._totals_savings_lbl = QLabel()
        self._totals_savings_lbl.setStyleSheet("color:#569CD6;background:transparent;font-size:20px;font-weight:700;")
        totals_layout.addWidget(self._totals_savings_lbl)
        totals_layout.addStretch()

        layout.addWidget(self._totals_bar)

        self._btn_add.clicked.connect(self._on_add)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_dup.clicked.connect(self._on_duplicate)
        self._btn_transfer.clicked.connect(self._on_transfer)
        self._btn_credit_payment.clicked.connect(self._on_credit_payment)
        self._btn_apply.clicked.connect(self.refresh)
        self._btn_clear.clicked.connect(self._on_clear_filter)
        self._table.doubleClicked.connect(self._on_edit)
        self._table.customContextMenuRequested.connect(self._open_context_menu)

    def _apply_filter_options(self, options: TransactionsFilterOptions) -> None:
        self._filter_options = options
        self._acc_filter.blockSignals(True)
        self._cat_filter.blockSignals(True)
        self._tag_filter.blockSignals(True)
        cur_acc = self._acc_filter.currentData()
        cur_cat = self._cat_filter.currentText()
        cur_tag = self._tag_filter.currentData()

        self._acc_filter.clear()
        self._acc_filter.addItem(_tr_db(self._db, "filter.all_accounts", "All Accounts"), None)
        for acc in options.accounts:
            self._acc_filter.addItem(acc["name"], acc["id"])

        self._cat_filter.clear()
        self._cat_filter.addItem(_tr_db(self._db, "filter.all_categories", "All Categories"), None)
        for cat in options.categories:
            self._cat_filter.addItem(cat["name"])

        self._tag_filter.clear()
        self._tag_filter.addItem(_tr_db(self._db, "filter.all_tags", "All Tags"), None)
        for tag in options.tags:
            self._tag_filter.addItem(tag["name"], tag["id"])

        # Restore selections
        for i in range(self._acc_filter.count()):
            if self._acc_filter.itemData(i) == cur_acc:
                self._acc_filter.setCurrentIndex(i)
                break
        idx = self._cat_filter.findText(cur_cat)
        if idx >= 0:
            self._cat_filter.setCurrentIndex(idx)
        for i in range(self._tag_filter.count()):
            if self._tag_filter.itemData(i) == cur_tag:
                self._tag_filter.setCurrentIndex(i)
                break

        self._acc_filter.blockSignals(False)
        self._cat_filter.blockSignals(False)
        self._tag_filter.blockSignals(False)

    def _on_clear_filter(self) -> None:
        first = date.today().replace(day=1)
        self._from_date.setDate(_date_to_qdate(first))
        today = date.today()
        self._to_date.setDate(_date_to_qdate(today))
        self._acc_filter.setCurrentIndex(0)
        self._cat_filter.setCurrentIndex(0)
        self._tag_filter.setCurrentIndex(0)
        self._search_input.clear()
        self.refresh()

    def _get_selected_tx(self) -> dict | None:
        rows = self._table.selectedItems()
        if not rows:
            return None
        row = self._table.currentRow()
        if row < 0 or row >= len(self._tx_data):
            return None
        return self._tx_data[row]

    def _adjustment_action_blocked_message(self) -> str:
        return _tr_db(
            self._db,
            "transactions.balance_adjustment.blocked",
            "Balance adjustments keep their own workflow. Edit the adjustment directly instead.",
        )

    def _is_balance_adjustment_selected(self, tx: dict | None) -> bool:
        return tx is not None and is_balance_adjustment_transaction(tx)

    def _on_add(self) -> None:
        from mira.ui.dialogs import TransactionDialog

        dlg = TransactionDialog(self._db, parent=self)
        if dlg.exec() == TransactionDialog.DialogCode.Accepted:
            data = dlg.get_data()
            feedback = self._service.create(data)
            self.refresh()
            highlighted_message = feedback.payload.get("highlighted_message")
            if isinstance(highlighted_message, dict) and str(highlighted_message.get("message") or "").strip():
                _notify_info(
                    self,
                    _tr_db(self._db, "mira.analysis.dialog_title", "Análisis MIRA"),
                    str(highlighted_message["message"]),
                )

    def _on_edit(self) -> None:
        tx = self._get_selected_tx()
        if tx is None:
            return
        if self._is_balance_adjustment_selected(tx):
            from mira.ui.dialogs import BalanceAdjustmentDialog

            dlg = BalanceAdjustmentDialog(self._db, tx=tx, parent=self)
            if dlg.exec() == BalanceAdjustmentDialog.DialogCode.Accepted:
                data = dlg.get_data()
                self._service.update_balance_adjustment(int(tx["id"]), data)
                self.refresh()
            return
        from mira.ui.dialogs import TransactionDialog

        dlg = TransactionDialog(self._db, tx=tx, parent=self)
        if dlg.exec() == TransactionDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self._service.update(int(tx["id"]), data)
            self.refresh()

    def _on_delete(self) -> None:
        tx = self._get_selected_tx()
        if tx is None:
            return
        reply = QMessageBox.question(
            self,
            "Delete Transaction",
            f"Delete transaction of {_fmt_amount(self._db, tx['amount'])} on {tx['date']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._service.delete(int(tx["id"]))
            self.refresh()

    def _on_duplicate(self) -> None:
        from mira.ui.dialogs import TransactionDialog

        tx = self._get_selected_tx()
        if tx is None:
            return
        if self._is_balance_adjustment_selected(tx):
            _notify_info(
                self,
                _tr_db(self._db, "transactions.balance_adjustment.title", "Balance adjustment"),
                self._adjustment_action_blocked_message(),
            )
            return
        # Open dialog pre-filled but without the id (creates new)
        dlg = TransactionDialog(self._db, tx=tx, parent=self)
        if dlg.exec() == TransactionDialog.DialogCode.Accepted:
            data = dlg.get_data()
            feedback = self._service.duplicate(data)
            self.refresh()
            highlighted_message = feedback.payload.get("highlighted_message")
            if isinstance(highlighted_message, dict) and str(highlighted_message.get("message") or "").strip():
                _notify_info(
                    self,
                    _tr_db(self._db, "mira.analysis.dialog_title", "Análisis MIRA"),
                    str(highlighted_message["message"]),
                )

    def _on_transfer(self) -> None:
        from mira.ui.dialogs import TransferDialog

        dlg = TransferDialog(self._db, parent=self)
        if dlg.exec() == TransferDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self._service.transfer(data)
            self.refresh()

    def _on_credit_payment(self) -> None:
        from mira.ui.dialogs import TransferDialog

        dlg = TransferDialog(self._db, parent=self, credit_payment=True)
        if dlg.exec() == TransferDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self._service.record_credit_payment(data)
            self.refresh()

    def open_transfer_dialog(self) -> None:
        """Public helper used by the main menu to open transfer dialog."""
        self._on_transfer()

    def open_credit_payment_dialog(self) -> None:
        """Public helper used by the main menu to open the card-payment dialog."""
        self._on_credit_payment()

    def _on_change_account_quick(self) -> None:
        tx = self._get_selected_tx()
        if tx is None:
            _notify_info(
                self,
                _tr_db(self._db, "transactions.change_account.title", "Change Account"),
                _tr_db(self._db, "selection.transaction_required", "Select a transaction first."),
            )
            return
        if self._is_balance_adjustment_selected(tx):
            _notify_info(
                self,
                _tr_db(self._db, "transactions.balance_adjustment.title", "Balance adjustment"),
                self._adjustment_action_blocked_message(),
            )
            return

        accounts = list(self._filter_options.accounts)
        if not accounts:
            _notify_warning(
                self,
                _tr_db(self._db, "transactions.change_account.title", "Change Account"),
                _tr_db(self._db, "accounts.none_available", "No accounts available."),
            )
            return

        names = [acc["name"] for acc in accounts]
        current_name = tx.get("account_name") or ""
        current_idx = names.index(current_name) if current_name in names else 0
        chosen_name, ok = QInputDialog.getItem(
            self,
            "Change Account",
            "Move transaction to account:",
            names,
            current_idx,
            False,
        )
        if not ok:
            return
        selected_account = next((acc for acc in accounts if acc["name"] == chosen_name), None)
        if selected_account is None:
            return
        if int(selected_account["id"]) == int(tx.get("account_id") or -1):
            return

        reply = QMessageBox.question(
            self,
            "Change Account",
            f"Move this transaction to account '{selected_account['name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._service.update_account(int(tx["id"]), int(selected_account["id"]))
        self.refresh()

    def _on_change_category_quick(self) -> None:
        tx = self._get_selected_tx()
        if tx is None:
            _notify_info(
                self,
                _tr_db(self._db, "transactions.change_category.title", "Change Category"),
                _tr_db(self._db, "selection.transaction_required", "Select a transaction first."),
            )
            return
        if self._is_balance_adjustment_selected(tx):
            _notify_info(
                self,
                _tr_db(self._db, "transactions.balance_adjustment.title", "Balance adjustment"),
                self._adjustment_action_blocked_message(),
            )
            return
        categories = [cat["name"] for cat in self._filter_options.categories]
        if not categories:
            _notify_warning(
                self,
                _tr_db(self._db, "transactions.change_category.title", "Change Category"),
                _tr_db(self._db, "categories.none_available", "No categories available."),
            )
            return

        current = tx.get("category") or ""
        idx = categories.index(current) if current in categories else 0
        new_category, ok = QInputDialog.getItem(
            self,
            "Change Category",
            "Select category:",
            categories,
            idx,
            False,
        )
        if not ok:
            return
        if new_category == current:
            return

        reply = QMessageBox.question(
            self,
            "Change Category",
            f"Change category to '{new_category}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._service.update_category(int(tx["id"]), new_category)
        self.refresh()

    def _open_context_menu(self, pos: QPoint) -> None:
        if not _select_row_at_pos(self._table, pos):
            return
        menu = QMenu(self)
        act_edit = menu.addAction("Edit")
        act_delete = menu.addAction("Delete")
        act_dup = menu.addAction("Duplicate")
        menu.addSeparator()
        act_change_acc = menu.addAction("Cambiar de cuenta")
        act_change_cat = menu.addAction("Cambiar de categoria")

        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is act_edit:
            self._on_edit()
        elif chosen is act_delete:
            self._on_delete()
        elif chosen is act_dup:
            self._on_duplicate()
        elif chosen is act_change_acc:
            self._on_change_account_quick()
        elif chosen is act_change_cat:
            self._on_change_category_quick()

    def open_add_dialog(self) -> None:
        """Public helper used by the main menu to add a transaction."""
        self._on_add()

    def refresh(self) -> None:
        since = self._from_date.date().toString("yyyy-MM-dd")
        until = self._to_date.date().toString("yyyy-MM-dd")
        acc_id = self._acc_filter.currentData()
        cat_text = self._cat_filter.currentText()
        category = None if cat_text in (_tr_db(self._db, "filter.all_categories", "All Categories"), "") else cat_text
        search = self._search_input.text().strip() or None

        tag_id = self._tag_filter.currentData()
        state = self._service.load_state(
            since_date=since,
            until_date=until,
            account_id=acc_id,
            category=category,
            search=search,
            tag_id=tag_id,
            limit=1_000,
        )
        self._apply_filter_options(state.options)
        self._apply_state(state)

    def _apply_state(self, state: TransactionsViewState) -> None:
        self._tx_data = list(state.transactions)
        self._tags_by_transaction = dict(state.tags_by_transaction)
        self._savings_categories = set(state.savings_categories)

        self._table.setRowCount(len(self._tx_data))
        for row, tx in enumerate(self._tx_data):
            self._table.setItem(row, 0, QTableWidgetItem(tx.get("date", "")))
            ti = _make_tx_type_item(tx, self._savings_categories)
            self._table.setItem(row, 1, ti)
            amt = tx.get("amount", 0)
            ai = QTableWidgetItem(_fmt_amount(self._db, amt))
            ai.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 2, ai)
            self._table.setItem(row, 3, QTableWidgetItem(tx.get("category") or ""))
            desc = tx.get("description") or ""
            tag_badges = []
            for tag in self._tags_by_transaction.get(int(tx["id"]), []):
                tag_badges.append(_make_tag_badge(tag))
            desc_widget = QWidget()
            desc_layout = QHBoxLayout(desc_widget)
            desc_layout.setContentsMargins(0, 0, 0, 0)
            desc_layout.setSpacing(2)
            desc_layout.addWidget(QLabel(desc))
            for badge in tag_badges:
                desc_layout.addWidget(badge)
            self._table.setCellWidget(row, 4, desc_widget)
            self._table.setItem(row, 5, QTableWidgetItem(tx.get("account_name") or ""))
            self._table.setItem(row, 6, QTableWidgetItem(tx.get("note") or ""))

        total_income = float(state.summary["income"])
        total_expense = float(state.summary["expense"])
        total_savings = float(state.summary["savings"])
        net = float(state.summary["net"])
        self._totals_income_lbl.setText(
            f"{_tr_db(self._db, 'dashboard.card.income', 'Income')}: {_fmt_amount(self._db, total_income)}"
        )
        self._totals_expense_lbl.setText(
            f"{_tr_db(self._db, 'dashboard.card.expense', 'Expense')}: {_fmt_amount(self._db, total_expense)}"
        )
        self._totals_net_lbl.setText(f"{_tr_db(self._db, 'dashboard.card.net', 'Net')}: {_fmt_amount(self._db, net)}")
        self._totals_savings_lbl.setText(
            f"{_tr_db(self._db, 'dashboard.card.savings', 'Savings')}: {_fmt_amount(self._db, total_savings)}"
        )
        self._totals_net_lbl.setStyleSheet(
            "background:transparent;font-size:20px;font-weight:700;"
            + ("color:#4EC9B0;" if net >= 0 else "color:#F48771;")
        )


# ---------------------------------------------------------------------------
# AccountsView
# ---------------------------------------------------------------------------
