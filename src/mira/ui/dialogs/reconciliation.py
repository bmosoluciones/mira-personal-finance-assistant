# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Module documentation."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mira.app.view_services import ReconciliationExternalRow, ReconciliationViewService
from mira.db.database import Database
from mira.ui.views._shared import (
    _DATE_STYLE,
    _TABLE_STYLE,
    _date_to_qdate,
    _fmt_amount,
    _notify_info,
    _notify_warning,
    _tr_db,
)


class ReconciliationDialog(QDialog):
    """Represent the ReconciliationDialog class."""

    _REQUIRED_COLUMN_LABEL_KEYS = {
        "date": "reconciliation.required_column.date",
        "reference": "reconciliation.required_column.reference",
        "description": "reconciliation.required_column.description",
        "income": "reconciliation.required_column.income",
        "expense": "reconciliation.required_column.expense",
    }

    def __init__(
        self,
        db: Database,
        parent: QWidget | None = None,
        *,
        account_id: int | None = None,
        service: ReconciliationViewService | None = None,
    ) -> None:
        """Initialize the ReconciliationDialog instance."""
        super().__init__(parent)
        self._db = db
        self._service = service or ReconciliationViewService(db)
        self._account_id = account_id
        self._external_rows: tuple[ReconciliationExternalRow, ...] = ()
        self._external_opening_balance = 0.0
        self.setWindowTitle(_tr_db(self._db, "reconciliation.title", "Reconciliation"))
        self.resize(1180, 720)
        self._build_ui()
        self._populate_accounts()
        self._refresh_state()

    def _build_ui(self) -> None:
        """Return build ui."""
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        filters = QFormLayout()
        filters.setSpacing(8)
        self._account_combo = QComboBox()
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDisplayFormat("yyyy-MM-dd")
        self._date_from.setStyleSheet(_DATE_STYLE)
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDisplayFormat("yyyy-MM-dd")
        self._date_to.setStyleSheet(_DATE_STYLE)
        today = date.today()
        self._date_from.setDate(_date_to_qdate(today.replace(day=1)))
        self._date_to.setDate(_date_to_qdate(today))
        filters.addRow(_tr_db(self._db, "reconciliation.account", "Account:"), self._account_combo)
        filters.addRow(_tr_db(self._db, "reconciliation.date_from", "From:"), self._date_from)
        filters.addRow(_tr_db(self._db, "reconciliation.date_to", "To:"), self._date_to)
        root.addLayout(filters)

        actions = QHBoxLayout()
        self._btn_load_excel = QPushButton(_tr_db(self._db, "reconciliation.load_excel", "Load Excel"))
        self._btn_refresh = QPushButton(_tr_db(self._db, "reconciliation.refresh", "Refresh"))
        self._btn_reconcile = QPushButton(_tr_db(self._db, "reconciliation.action.reconcile", "Reconcile"))
        self._btn_clear = QPushButton(_tr_db(self._db, "reconciliation.action.clear", "Clear Reconciliation"))
        for button in (self._btn_load_excel, self._btn_refresh, self._btn_reconcile, self._btn_clear):
            actions.addWidget(button)
        actions.addStretch(1)
        root.addLayout(actions)

        summary_row = QHBoxLayout()
        self._summary_external = QLabel()
        self._summary_system = QLabel()
        self._summary_difference = QLabel()
        summary_row.addWidget(self._summary_external, 1)
        summary_row.addWidget(self._summary_system, 1)
        summary_row.addWidget(self._summary_difference, 1)
        root.addLayout(summary_row)

        panels = QHBoxLayout()
        self._external_table = QTableWidget(0, 6)
        self._external_table.setHorizontalHeaderLabels(
            [
                _tr_db(self._db, "reconciliation.col.date", "Date"),
                _tr_db(self._db, "reconciliation.col.reference", "Reference"),
                _tr_db(self._db, "reconciliation.col.description", "Description"),
                _tr_db(self._db, "reconciliation.col.amount", "Amount"),
                _tr_db(self._db, "reconciliation.col.status", "Status"),
                _tr_db(self._db, "reconciliation.col.suggestion", "Suggestion"),
            ]
        )
        self._external_table.setStyleSheet(_TABLE_STYLE)
        self._external_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._external_table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
        self._external_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._external_table.verticalHeader().setVisible(False)

        self._system_table = QTableWidget(0, 6)
        self._system_table.setHorizontalHeaderLabels(
            [
                _tr_db(self._db, "reconciliation.col.date", "Date"),
                _tr_db(self._db, "reconciliation.col.description", "Description"),
                _tr_db(self._db, "reconciliation.col.amount", "Amount"),
                _tr_db(self._db, "reconciliation.col.type", "Type"),
                _tr_db(self._db, "reconciliation.col.selectable", "Selectable"),
                _tr_db(self._db, "reconciliation.col.status", "Status"),
            ]
        )
        self._system_table.setStyleSheet(_TABLE_STYLE)
        self._system_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._system_table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
        self._system_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._system_table.verticalHeader().setVisible(False)

        panels.addWidget(self._external_table, 1)
        panels.addWidget(self._system_table, 1)
        root.addLayout(panels, 1)

        self._account_combo.currentIndexChanged.connect(self._refresh_state)
        self._date_from.dateChanged.connect(self._refresh_state)
        self._date_to.dateChanged.connect(self._refresh_state)
        self._btn_refresh.clicked.connect(self._refresh_state)
        self._btn_load_excel.clicked.connect(self._load_excel)
        self._btn_reconcile.clicked.connect(self._reconcile_selected)
        self._btn_clear.clicked.connect(self._clear_selected)

    def _populate_accounts(self) -> None:
        """Return populate accounts."""
        self._account_combo.blockSignals(True)
        self._account_combo.clear()
        for account in self._service.list_accounts():
            name = str(account.get("name") or "")
            code = str(account.get("currency") or "").strip().upper()
            self._account_combo.addItem(f"{name} ({code})", int(account["id"]))
        if self._account_id is not None and (idx := self._account_combo.findData(int(self._account_id))) >= 0:
            self._account_combo.setCurrentIndex(idx)
        self._account_combo.blockSignals(False)

    def _current_account_id(self) -> int | None:
        """Return current account id."""
        data = self._account_combo.currentData()
        return int(data) if data is not None else None

    def _current_date_from(self) -> str:
        """Return current date from."""
        return self._date_from.date().toString("yyyy-MM-dd")

    def _current_date_to(self) -> str:
        """Return current date to."""
        return self._date_to.date().toString("yyyy-MM-dd")

    def _refresh_state(self) -> None:
        """Return refresh state."""
        account_id = self._current_account_id()
        if account_id is None:
            return
        state = self._service.load_state(
            account_id=account_id,
            date_from=self._current_date_from(),
            date_to=self._current_date_to(),
            external_rows=self._external_rows,
            external_opening_balance=self._external_opening_balance,
        )

        self._external_table.setRowCount(len(state.external_rows))
        for row, item in enumerate(state.external_rows):
            self._external_table.setItem(row, 0, QTableWidgetItem(item.date))
            self._external_table.setItem(row, 1, QTableWidgetItem(item.reference))
            self._external_table.setItem(row, 2, QTableWidgetItem(item.description))
            amount_item = QTableWidgetItem(_fmt_amount(self._db, item.amount))
            amount_item.setData(Qt.ItemDataRole.UserRole, float(item.amount))
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._external_table.setItem(row, 3, amount_item)
            status = (
                _tr_db(self._db, "reconciliation.status.reconciled", "reconciled")
                if item.is_reconciled
                else _tr_db(
                    self._db,
                    "reconciliation.status.pending",
                    "pending",
                )
            )
            self._external_table.setItem(row, 4, QTableWidgetItem(status))
            suggestion = ", ".join(str(tx_id) for tx_id in item.suggested_transaction_ids)
            self._external_table.setItem(row, 5, QTableWidgetItem(suggestion))

        self._system_table.setRowCount(len(state.system_rows))
        for row, sys_item in enumerate(state.system_rows):
            date_item = QTableWidgetItem(sys_item.date)
            date_item.setData(Qt.ItemDataRole.UserRole, int(sys_item.transaction_id))
            self._system_table.setItem(row, 0, date_item)
            self._system_table.setItem(row, 1, QTableWidgetItem(sys_item.description))
            amount_item = QTableWidgetItem(_fmt_amount(self._db, sys_item.amount))
            amount_item.setData(Qt.ItemDataRole.UserRole, float(sys_item.amount))
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._system_table.setItem(row, 2, amount_item)
            self._system_table.setItem(row, 3, QTableWidgetItem(sys_item.tx_type))
            selectable_text = (
                _tr_db(self._db, "reconciliation.selectable.yes", "yes")
                if sys_item.selectable
                else _tr_db(
                    self._db,
                    "reconciliation.selectable.no",
                    "no",
                )
            )
            self._system_table.setItem(row, 4, QTableWidgetItem(selectable_text))
            status = (
                _tr_db(self._db, "reconciliation.status.reconciled", "reconciled")
                if sys_item.is_reconciled
                else _tr_db(
                    self._db,
                    "reconciliation.status.pending",
                    "pending",
                )
            )
            self._system_table.setItem(row, 5, QTableWidgetItem(status))

        self._summary_external.setText(
            _tr_db(
                self._db,
                "reconciliation.summary.external",
                "External: opening {opening} | income {income} | expense {expense} | closing {closing}",
                params={
                    "opening": _fmt_amount(self._db, state.external_summary.opening_balance),
                    "income": _fmt_amount(self._db, state.external_summary.total_income),
                    "expense": _fmt_amount(self._db, state.external_summary.total_expense),
                    "closing": _fmt_amount(self._db, state.external_summary.closing_balance),
                },
            )
        )
        self._summary_system.setText(
            _tr_db(
                self._db,
                "reconciliation.summary.system",
                "System: opening {opening} | income {income} | expense {expense} | closing {closing}",
                params={
                    "opening": _fmt_amount(self._db, state.system_summary.opening_balance),
                    "income": _fmt_amount(self._db, state.system_summary.total_income),
                    "expense": _fmt_amount(self._db, state.system_summary.total_expense),
                    "closing": _fmt_amount(self._db, state.system_summary.closing_balance),
                },
            )
        )
        self._summary_difference.setText(
            _tr_db(
                self._db,
                "reconciliation.summary.difference",
                "Current matched difference: {difference}",
                params={"difference": _fmt_amount(self._db, state.amount_difference)},
            )
        )

    def _load_excel(self) -> None:
        """Return load excel."""
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self,
            _tr_db(self._db, "reconciliation.load_excel", "Load Excel"),
            "",
            _tr_db(self._db, "reconciliation.file_filter", "Excel Files (*.xlsx);;All Files (*)"),
        )
        if not path:
            return

        preview = self._service.parse_excel(path)
        if preview.has_blocking_error:
            translated_columns = ", ".join(
                self._translate_required_column(column) for column in preview.missing_columns
            )
            _notify_warning(
                self,
                _tr_db(self._db, "reconciliation.load_error.title", "Excel validation"),
                _tr_db(
                    self._db,
                    "reconciliation.load_error.missing_columns",
                    "Missing required columns: {columns}",
                    params={"columns": translated_columns},
                ),
            )
            return

        if preview.invalid_rows and preview.valid_rows:
            keep_valid = QMessageBox.question(
                self,
                _tr_db(self._db, "reconciliation.invalid_rows.title", "Invalid rows detected"),
                _tr_db(
                    self._db,
                    "reconciliation.invalid_rows.body",
                    "{invalid} row(s) are invalid and will be skipped. Continue with {valid} valid row(s)?",
                    params={"invalid": len(preview.invalid_rows), "valid": len(preview.valid_rows)},
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if keep_valid != QMessageBox.StandardButton.Yes:
                return

        if not preview.valid_rows:
            _notify_warning(
                self,
                _tr_db(self._db, "reconciliation.load_error.title", "Excel validation"),
                _tr_db(self._db, "reconciliation.invalid_rows.empty", "The file has no valid rows to reconcile."),
            )
            return

        self._external_rows = preview.valid_rows
        _notify_info(
            self,
            _tr_db(self._db, "reconciliation.load_success.title", "Excel loaded"),
            _tr_db(
                self._db,
                "reconciliation.load_success.body",
                "Loaded {valid} valid row(s).",
                params={"valid": len(preview.valid_rows)},
            ),
        )
        self._refresh_state()

    def _translate_required_column(self, column_name: str) -> str:
        """Return a translated label for a reconciliation-required column."""
        key = self._REQUIRED_COLUMN_LABEL_KEYS.get(column_name)
        if key is None:
            return column_name
        return _tr_db(self._db, key, column_name)

    def _selected_external_rows(self) -> tuple[ReconciliationExternalRow, ...]:
        """Return selected external rows."""
        selected = sorted({idx.row() for idx in self._external_table.selectionModel().selectedRows()})
        return tuple(self._external_rows[index] for index in selected if 0 <= index < len(self._external_rows))

    def _selected_system_transaction_ids(self) -> list[int]:
        """Return selected system transaction ids."""
        selected = sorted({idx.row() for idx in self._system_table.selectionModel().selectedRows()})
        tx_ids: list[int] = []
        for row in selected:
            item = self._system_table.item(row, 0)
            if item is not None:
                tx_id = item.data(Qt.ItemDataRole.UserRole)
                if tx_id is not None:
                    tx_ids.append(int(tx_id))
        return tx_ids

    def _reconcile_selected(self) -> None:
        """Return reconcile selected."""
        account_id = self._current_account_id()
        if account_id is None:
            return
        external_rows = self._selected_external_rows()
        tx_ids = self._selected_system_transaction_ids()
        if not external_rows or not tx_ids:
            _notify_warning(
                self,
                _tr_db(self._db, "reconciliation.select_required.title", "Selection required"),
                _tr_db(
                    self._db,
                    "reconciliation.select_required.body",
                    "Select at least one external row and one system transaction.",
                ),
            )
            return

        external_total = round(sum(row.amount for row in external_rows), 2)
        system_total = 0.0
        for row in range(self._system_table.rowCount()):
            item = self._system_table.item(row, 0)
            if item is None:
                continue
            tx_id = int(item.data(Qt.ItemDataRole.UserRole) or 0)
            if tx_id in tx_ids:
                amount_item = self._system_table.item(row, 2)
                system_total += (
                    float(amount_item.data(Qt.ItemDataRole.UserRole) or 0.0) if amount_item is not None else 0.0
                )
        difference = round(external_total - system_total, 2)
        if abs(difference) > 0.0:
            proceed = QMessageBox.question(
                self,
                _tr_db(self._db, "reconciliation.difference.title", "Difference warning"),
                _tr_db(
                    self._db,
                    "reconciliation.difference.body",
                    "Selected sums do not match (difference: {difference}). Continue?",
                    params={"difference": _fmt_amount(self._db, difference)},
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if proceed != QMessageBox.StandardButton.Yes:
                return

        self._service.reconcile_selection(
            account_id=account_id,
            date_from=self._current_date_from(),
            date_to=self._current_date_to(),
            system_transaction_ids=tx_ids,
            external_rows=external_rows,
        )
        _notify_info(
            self,
            _tr_db(self._db, "reconciliation.success.title", "Reconciliation completed"),
            _tr_db(self._db, "reconciliation.success.body", "Selected rows were reconciled successfully."),
        )
        self._refresh_state()

    def _clear_selected(self) -> None:
        """Return clear selected."""
        tx_ids = self._selected_system_transaction_ids()
        if not tx_ids:
            _notify_warning(
                self,
                _tr_db(self._db, "reconciliation.select_required.title", "Selection required"),
                _tr_db(self._db, "reconciliation.clear.select_transactions", "Select at least one system transaction."),
            )
            return
        deleted = self._service.clear_reconciliation_for_transactions(tx_ids)
        _notify_info(
            self,
            _tr_db(self._db, "reconciliation.clear.title", "Reconciliation cleared"),
            _tr_db(
                self._db,
                "reconciliation.clear.body",
                "Removed {count} reconciliation match(es).",
                params={"count": deleted},
            ),
        )
        self._refresh_state()


__all__ = ["ReconciliationDialog"]
