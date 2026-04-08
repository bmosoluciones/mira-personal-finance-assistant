# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Accounts feature view."""

from __future__ import annotations


from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mira.app.view_services import AccountsViewService, AccountsViewState
from mira.db.database import Database
from mira.ui.views._shared import (
    _TABLE_STYLE,
    _account_type_label,
    _fmt_amount,
    _make_toolbar_btn,
    _section_title,
    _select_row_at_pos,
    _tr_db,
)


class AccountsView(QWidget):
    """Accounts management view with CRUD toolbar."""

    def __init__(
        self,
        db: Database,
        parent: QWidget | None = None,
        service: AccountsViewService | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._service = service or AccountsViewService(db)
        self._accounts: list[dict] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        layout.addWidget(_section_title("Accounts"))

        # Toolbar
        tb = QHBoxLayout()
        self._btn_add = _make_toolbar_btn("+ Add Account")
        self._btn_edit = _make_toolbar_btn(_tr_db(self._db, "btn.edit", "✏ Edit"))
        self._btn_delete = _make_toolbar_btn(_tr_db(self._db, "btn.delete", "🗑 Delete"))
        self._btn_set_default = _make_toolbar_btn("⭐ Set as Default")
        self._btn_balance_adjustment = _make_toolbar_btn(
            _tr_db(self._db, "btn.balance_adjustment", "~ Balance Adjustment")
        )
        for btn in [
            self._btn_add,
            self._btn_edit,
            self._btn_delete,
            self._btn_set_default,
            self._btn_balance_adjustment,
        ]:
            tb.addWidget(btn)
        tb.addStretch()
        layout.addLayout(tb)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(["Account Name", "Type", "Currency", "Balance", "Default", "Created"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.setStyleSheet(_TABLE_STYLE)
        layout.addWidget(self._table, 1)

        self._btn_add.clicked.connect(self._on_add)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_set_default.clicked.connect(self._on_set_default)
        self._btn_balance_adjustment.clicked.connect(self._on_balance_adjustment)
        self._table.doubleClicked.connect(self._on_edit)
        self._table.customContextMenuRequested.connect(self._open_context_menu)

    def _get_selected(self) -> dict | None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._accounts):
            return None
        return self._accounts[row]

    @staticmethod
    def _format_created_at(value: object) -> str:
        if value is None:
            return ""
        if hasattr(value, "strftime"):
            try:
                return str(value.strftime("%Y-%m-%d"))
            except (TypeError, ValueError):
                pass
        return str(value)[:10]

    def _find_row_by_account_id(self, account_id: int) -> int:
        for row, account in enumerate(self._accounts):
            if int(account["id"]) == int(account_id):
                return row
        return -1

    def _select_row(self, row: int) -> None:
        if row < 0 or row >= self._table.rowCount():
            return
        self._table.setCurrentCell(row, 0)
        self._table.selectRow(row)

    def _select_account(self, account_id: int) -> None:
        row = self._find_row_by_account_id(account_id)
        if row >= 0:
            self._select_row(row)

    def _on_add(self) -> None:
        from mira.ui.dialogs import AccountDialog

        dlg = AccountDialog(self._db, parent=self)
        if dlg.exec() == AccountDialog.DialogCode.Accepted:
            data = dlg.get_data()
            feedback = self._service.create(
                name=data["name"],
                account_type=data["account_type"],
                opening_balance=data["opening_balance"],
                currency=data["currency"],
            )
            self.refresh(selected_account_id=feedback.selected_id)

    def _on_edit(self) -> None:
        from mira.ui.dialogs import AccountDialog

        acc = self._get_selected()
        if acc is None:
            return
        dlg = AccountDialog(self._db, account=acc, parent=self)
        if dlg.exec() == AccountDialog.DialogCode.Accepted:
            data = dlg.get_data()
            feedback = self._service.update(
                int(acc["id"]),
                name=data["name"],
                account_type=data["account_type"],
                currency=data["currency"],
            )
            self.refresh(selected_account_id=feedback.selected_id)

    def _on_delete(self) -> None:
        acc = self._get_selected()
        if acc is None:
            return
        next_row = self._table.currentRow()
        reply = QMessageBox.question(
            self,
            "Delete Account",
            f"Delete account '{acc['name']}'? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._service.delete(int(acc["id"]))
            self.refresh()
            if self._table.rowCount() > 0:
                self._select_row(min(next_row, self._table.rowCount() - 1))

    def _on_set_default(self) -> None:
        acc = self._get_selected()
        if acc is None:
            return
        feedback = self._service.set_default(int(acc["id"]))
        self.refresh(selected_account_id=feedback.selected_id)

    @staticmethod
    def _is_adjustable_account(account: dict | None) -> bool:
        return str((account or {}).get("account_type") or "") in {"bank", "credit"}

    def _on_balance_adjustment(self) -> None:
        from mira.ui.dialogs import BalanceAdjustmentDialog

        selected = self._get_selected()
        initial_account_id = int(selected["id"]) if self._is_adjustable_account(selected) and selected else None
        dlg = BalanceAdjustmentDialog(self._db, parent=self, account_id=initial_account_id, service=self._service)
        if dlg.exec() == BalanceAdjustmentDialog.DialogCode.Accepted:
            feedback = self._service.record_balance_adjustment(dlg.get_data())
            self.refresh(selected_account_id=feedback.selected_id)

    def _open_context_menu(self, pos: QPoint) -> None:
        if not _select_row_at_pos(self._table, pos):
            return
        account = self._get_selected()
        menu = QMenu(self)
        act_edit = menu.addAction("Edit")
        act_set_default = menu.addAction("⭐ Set as Default")
        act_adjust = menu.addAction(_tr_db(self._db, "btn.balance_adjustment", "~ Balance Adjustment"))
        act_adjust.setEnabled(self._is_adjustable_account(account))
        act_delete = menu.addAction("Delete")
        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is act_edit:
            self._on_edit()
        elif chosen is act_set_default:
            self._on_set_default()
        elif chosen is act_adjust:
            self._on_balance_adjustment()
        elif chosen is act_delete:
            self._on_delete()

    def open_add_dialog(self) -> None:
        """Public helper used by the main menu to add an account."""
        self._on_add()

    def refresh(self, *, selected_account_id: int | None = None) -> None:
        if selected_account_id is None:
            current = self._get_selected()
            selected_account_id = int(current["id"]) if current is not None else None
        state = self._service.load_state()
        self._apply_state(state)
        if selected_account_id is not None:
            self._select_account(selected_account_id)

    def _apply_state(self, state: AccountsViewState) -> None:
        self._accounts = list(state.accounts)
        self._table.setRowCount(len(self._accounts))
        for row, acc in enumerate(self._accounts):
            name_item = QTableWidgetItem(acc["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, int(acc["id"]))
            self._table.setItem(row, 0, name_item)
            self._table.setItem(
                row, 1, QTableWidgetItem(_account_type_label(self._db, str(acc.get("account_type", "bank"))))
            )
            self._table.setItem(row, 2, QTableWidgetItem(acc.get("currency", "NIO")))
            bal = QTableWidgetItem(_fmt_amount(self._db, acc["balance"]))
            bal.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 3, bal)
            default_item = QTableWidgetItem("⭐" if acc.get("is_default") else "")
            default_item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 4, default_item)
            self._table.setItem(row, 5, QTableWidgetItem(self._format_created_at(acc.get("created_at"))))
