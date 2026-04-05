# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Dashboard view for the main landing page."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mira.db.database import Database
from mira.ui.views._shared import (
    _TABLE_STYLE,
    _fmt_amount,
    _make_tag_badge,
    _make_tx_type_item,
    _notify_info,
    _savings_category_names,
    _section_title,
    _select_row_at_pos,
    _sub_title,
    _tr_db,
)
from mira.ui.widgets.cards import CardWidget
from mira.ui.delegates.cell_delegates import _TypeBadgeDelegate


class DashboardView(QWidget):
    """Landing page: KPI cards with time filters and recent transactions."""

    # Months to subtract from today's month start: 0 = current month, 3 = last 3 months, 6 = last 6 months
    _FILTER_MONTHS = [0, 3, 6]

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._filter_idx: int = 0  # 0=Este Mes, 1=Últimos 3 Meses, 2=Últimos 6 Meses
        self._recent_txs: list[dict] = []
        self._build_ui()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        layout.addWidget(_section_title(_tr_db(self._db, "view.dashboard.title", "Dashboard")))

        # Time-period filter tabs
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self._filter_btns: list[QPushButton] = []
        self._filter_btn_group = QButtonGroup(self)
        self._filter_btn_group.setExclusive(True)
        for idx, label in enumerate(
            [
                _tr_db(self._db, "dashboard.filter.this_month", "This month"),
                _tr_db(self._db, "dashboard.filter.last_3_months", "Last 3 months"),
                _tr_db(self._db, "dashboard.filter.last_6_months", "Last 6 months"),
            ]
        ):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(idx == 0)
            btn.clicked.connect(lambda checked, i=idx: self._on_filter(i))
            self._filter_btn_group.addButton(btn, idx)
            self._filter_btns.append(btn)
            filter_row.addWidget(btn)
        filter_row.addStretch()
        self._update_filter_styles()
        layout.addLayout(filter_row)

        # KPI summary cards
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        self._income_card = CardWidget(_tr_db(self._db, "dashboard.card.income", "Income"), "$0.00")
        self._expense_card = CardWidget(_tr_db(self._db, "dashboard.card.expense", "Expense"), "$0.00")
        self._net_card = CardWidget(_tr_db(self._db, "dashboard.card.net", "Net"), "$0.00")
        self._savings_card = CardWidget(_tr_db(self._db, "dashboard.card.savings", "Savings"), "$0.00")
        cards_row.addWidget(self._income_card)
        cards_row.addWidget(self._expense_card)
        cards_row.addWidget(self._net_card)
        cards_row.addWidget(self._savings_card)
        layout.addLayout(cards_row)

        # Recent transactions
        layout.addWidget(_sub_title(_tr_db(self._db, "dashboard.recent.title", "Recent transactions")))
        self._tx_table = QTableWidget(0, 5)
        self._tx_table.setHorizontalHeaderLabels(
            [
                _tr_db(self._db, "col.date", "Date"),
                _tr_db(self._db, "col.type", "Type"),
                _tr_db(self._db, "col.amount", "Amount"),
                _tr_db(self._db, "col.category", "Category"),
                _tr_db(self._db, "col.description", "Description"),
            ]
        )
        self._tx_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._tx_table.verticalHeader().setVisible(False)
        self._tx_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tx_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tx_table.setAlternatingRowColors(True)
        self._tx_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tx_table.setStyleSheet(_TABLE_STYLE)
        self._tx_table.setItemDelegateForColumn(1, _TypeBadgeDelegate(self._tx_table))
        layout.addWidget(self._tx_table, 1)

        self._tx_table.doubleClicked.connect(self._on_recent_edit)
        self._tx_table.customContextMenuRequested.connect(self._open_recent_context_menu)

    # ------------------------------------------------------------------
    # Filter helpers
    # ------------------------------------------------------------------

    def _on_filter(self, idx: int) -> None:
        self._filter_idx = idx
        self._update_filter_styles()
        self.refresh()

    def _update_filter_styles(self) -> None:
        active = (
            "QPushButton{border:2px solid palette(mid);border-radius:4px;padding:3px 11px;"
            "font-size:12px;font-weight:700;}"
        )
        inactive = (
            "QPushButton{border:1px solid palette(mid);border-radius:4px;padding:4px 12px;font-size:12px;}"
            "QPushButton:hover{border:1px solid palette(text);}"
        )
        for i, btn in enumerate(self._filter_btns):
            btn.setStyleSheet(active if i == self._filter_idx else inactive)

    def _get_since_date(self) -> str:
        today = date.today()
        months = self._FILTER_MONTHS[self._filter_idx]
        if months == 0:
            return today.replace(day=1).isoformat()
        month = today.month - months
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        return date(year, month, 1).isoformat()

    def _get_selected_recent_tx(self) -> dict | None:
        row = self._tx_table.currentRow()
        if row < 0 or row >= len(self._recent_txs):
            return None
        return self._recent_txs[row]

    def _on_recent_edit(self) -> None:
        from mira.ui.dialogs import TransactionDialog

        tx = self._get_selected_recent_tx()
        if tx is None:
            _notify_info(
                self,
                _tr_db(self._db, "transactions.edit.title", "Edit Transaction"),
                _tr_db(self._db, "selection.transaction_required", "Select a transaction first."),
            )
            return
        dlg = TransactionDialog(self._db, tx=tx, parent=self)
        if dlg.exec() != TransactionDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        self._db.transaction.update(
            tx["id"],
            account_id=data["account_id"],
            tx_type=data["tx_type"],
            amount=data.get("stored_amount", data["amount"]),
            description=data["description"],
            category=data["category"],
            tx_date=data["tx_date"],
            note=data["note"],
            subcategory=data.get("subcategory"),
            payment_method=data.get("payment_method") or "cash",
            receipt_path=data.get("receipt_path"),
            exchange_rate=data.get("exchange_rate"),
            converted_amount=data.get("converted_amount"),
        )
        self._db.tag.set_for_transaction(tx["id"], data.get("tags", []))
        self.refresh()

    def _on_recent_delete(self) -> None:
        tx = self._get_selected_recent_tx()
        if tx is None:
            _notify_info(
                self,
                _tr_db(self._db, "transactions.delete.title", "Delete Transaction"),
                _tr_db(self._db, "selection.transaction_required", "Select a transaction first."),
            )
            return
        reply = QMessageBox.question(
            self,
            "Delete Transaction",
            f"Delete transaction of {_fmt_amount(self._db, tx['amount'])} on {tx['date']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._db.transaction.delete(tx["id"])
            self.refresh()

    def _open_recent_context_menu(self, pos: QPoint) -> None:
        if not _select_row_at_pos(self._tx_table, pos):
            return
        menu = QMenu(self)
        act_edit = menu.addAction("Edit")
        act_delete = menu.addAction("Delete")
        chosen = menu.exec(self._tx_table.viewport().mapToGlobal(pos))
        if chosen is act_edit:
            self._on_recent_edit()
        elif chosen is act_delete:
            self._on_recent_delete()

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        since_date = self._get_since_date()
        summary = self._db.report.get_summary(since_date=since_date)

        currency = self._db.setting.get("default_currency") or ""
        prefix = f"{currency} " if currency else "$"

        income = float(summary["total_income"])
        expense = abs(float(summary["total_expenses"]))
        net = float(summary["net"])
        savings_categories = _savings_category_names(self._db)
        savings_total = float(summary.get("savings") or 0.0)

        self._income_card.set_value(f"{prefix}{_fmt_amount(self._db, income)}")
        self._expense_card.set_value(f"{prefix}{_fmt_amount(self._db, expense)}")
        self._net_card.set_value(f"{prefix}{_fmt_amount(self._db, net)}")
        self._savings_card.set_value(f"{prefix}{_fmt_amount(self._db, savings_total)}")

        self._income_card.set_color("#4EC9B0")
        self._expense_card.set_color("#F48771")
        self._net_card.set_color("#4EC9B0" if net >= 0 else "#F48771")
        self._savings_card.set_color("#569CD6")

        txs = self._db.transaction.list(limit=10, since_date=since_date)
        self._recent_txs = txs
        self._tx_table.setRowCount(len(txs))
        for row, tx in enumerate(txs):
            self._tx_table.setItem(row, 0, QTableWidgetItem(tx.get("date", "")))
            ti = _make_tx_type_item(tx, savings_categories)
            self._tx_table.setItem(row, 1, ti)
            amt = QTableWidgetItem(_fmt_amount(self._db, tx.get("amount", 0)))
            amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._tx_table.setItem(row, 2, amt)
            self._tx_table.setItem(row, 3, QTableWidgetItem(tx.get("category") or ""))
            desc = tx.get("description") or ""
            tag_badges = []
            for tag in self._db.tag.list_for_transaction(tx["id"]):
                tag_badges.append(_make_tag_badge(tag))
            desc_widget = QWidget()
            desc_layout = QHBoxLayout(desc_widget)
            desc_layout.setContentsMargins(0, 0, 0, 0)
            desc_layout.setSpacing(2)
            desc_layout.addWidget(QLabel(desc))
            for badge in tag_badges:
                desc_layout.addWidget(badge)
            self._tx_table.setCellWidget(row, 4, desc_widget)


# ---------------------------------------------------------------------------
# TransactionsView
# ---------------------------------------------------------------------------
