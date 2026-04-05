# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Recurring transactions feature view."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QMessageBox,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mira.app.view_services import RecurringViewService, RecurringViewState
from mira.db.database import Database
from mira.ui.i18n import normalize_language, tr
from mira.ui.views._shared import (
    _TABLE_STYLE,
    _fmt_amount,
    _make_toolbar_btn,
    _notify_info,
    _section_title,
    _select_row_at_pos,
    _tr_db,
)


class _RecurringApplyDialog(QDialog):
    """Dialog to choose target month/year for applying recurring rules."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            tr("recurring.apply.title", normalize_language("en"), default="Apply recurring transactions")
        )

        layout = QVBoxLayout(self)
        form = QFormLayout()

        today = date.today()
        self._month = QSpinBox()
        self._month.setRange(1, 12)
        self._month.setValue(today.month)

        self._year = QSpinBox()
        self._year.setRange(1900, 9999)
        self._year.setValue(today.year)

        form.addRow(tr("recurring.apply.month", normalize_language("en"), default="Month (1-12)"), self._month)
        form.addRow(tr("recurring.apply.year", normalize_language("en"), default="Year"), self._year)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_period(self) -> tuple[int, int]:
        return self._year.value(), self._month.value()


# ---------------------------------------------------------------------------
# RecurringView
# ---------------------------------------------------------------------------


class RecurringView(QWidget):
    """Recurring transactions management."""

    def __init__(
        self,
        db: Database,
        parent: QWidget | None = None,
        service: RecurringViewService | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._service = service or RecurringViewService(db)
        self._recurring: list[dict] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        layout.addWidget(_section_title(_tr_db(self._db, "recurring.title", "Recurring Transactions")))

        # Toolbar
        tb = QHBoxLayout()
        self._btn_add = _make_toolbar_btn(_tr_db(self._db, "btn.add", "+ Add"))
        self._btn_edit = _make_toolbar_btn(_tr_db(self._db, "btn.edit", "✏ Edit"))
        self._btn_delete = _make_toolbar_btn(_tr_db(self._db, "btn.delete", "🗑 Delete"))
        self._btn_apply = _make_toolbar_btn(_tr_db(self._db, "menu.recurring.apply", "✅ Apply recurring…"))
        for btn in [self._btn_add, self._btn_edit, self._btn_delete, self._btn_apply]:
            tb.addWidget(btn)
        tb.addStretch()
        layout.addLayout(tb)

        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels(
            [
                _tr_db(self._db, "col.account", "Account"),
                _tr_db(self._db, "col.type", "Type"),
                _tr_db(self._db, "col.amount", "Amount"),
                _tr_db(self._db, "col.description", "Description"),
                _tr_db(self._db, "col.category", "Category"),
                _tr_db(self._db, "reports.col.tags", "Tags"),
                _tr_db(self._db, "col.note", "Note"),
                _tr_db(self._db, "recurring.col.day", "Day"),
            ]
        )
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
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
        self._btn_apply.clicked.connect(self._on_apply)
        self._table.doubleClicked.connect(self._on_edit)
        self._table.customContextMenuRequested.connect(self._open_context_menu)

    def _get_selected(self) -> dict | None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._recurring):
            return None
        return self._recurring[row]

    def _on_add(self) -> None:
        from mira.ui.dialogs import RecurringDialog

        dlg = RecurringDialog(self._db, parent=self)
        if dlg.exec() == RecurringDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self._service.create(data)
            self.refresh()

    def _on_delete(self) -> None:
        rec = self._get_selected()
        if rec is None:
            return
        reply = QMessageBox.question(
            self,
            "Delete Recurring",
            f"Delete recurring transaction '{rec.get('description', '')}' ({_fmt_amount(self._db, rec['amount'])})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._service.delete(int(rec["id"]))
            self.refresh()

    def _on_edit(self) -> None:
        from mira.ui.dialogs import RecurringDialog

        rec = self._get_selected()
        if rec is None:
            _notify_info(
                self,
                _tr_db(self._db, "recurring.edit.title", "Edit Recurring"),
                _tr_db(self._db, "selection.recurring_required", "Select a recurring transaction first."),
            )
            return
        dlg = RecurringDialog(self._db, recurring=rec, parent=self)
        if dlg.exec() != RecurringDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        self._service.update(int(rec["id"]), data)
        self.refresh()

    def _on_apply(self) -> None:
        dlg = _RecurringApplyDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        year, month = dlg.get_period()
        feedback = self._service.apply_for_month(year, month)
        period_label = f"{year:04d}-{month:02d}"
        created_count = int(feedback.payload.get("created_count") or 0)
        if created_count:
            _notify_info(
                self,
                "Applied",
                f"Created {created_count} recurring transaction(s) for {period_label}.",
            )
        else:
            _notify_info(
                self,
                "Already Applied",
                f"Recurring transactions have already been applied for {period_label}.",
            )
        self.refresh()

    def _open_context_menu(self, pos: QPoint) -> None:
        if not _select_row_at_pos(self._table, pos):
            return
        menu = QMenu(self)
        act_edit = menu.addAction("Edit")
        act_delete = menu.addAction("Delete")
        menu.addSeparator()
        act_apply = menu.addAction("Apply recurring…")
        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is act_edit:
            self._on_edit()
        elif chosen is act_delete:
            self._on_delete()
        elif chosen is act_apply:
            self._on_apply()

    def open_add_dialog(self) -> None:
        """Public helper used by the main menu to add a recurring transaction."""
        self._on_add()

    def apply_this_month(self) -> None:
        """Public helper used by the main menu to apply recurring transactions."""
        self._on_apply()

    def refresh(self) -> None:
        self._apply_state(self._service.load_state())

    def _apply_state(self, state: RecurringViewState) -> None:
        self._recurring = list(state.recurring)
        self._table.setRowCount(len(self._recurring))
        for row, rec in enumerate(self._recurring):
            self._table.setItem(row, 0, QTableWidgetItem(rec.get("account_name") or ""))
            t = rec.get("type", "")
            ti = QTableWidgetItem(t)
            self._table.setItem(row, 1, ti)
            amt = QTableWidgetItem(_fmt_amount(self._db, rec.get("amount", 0)))
            amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 2, amt)
            self._table.setItem(row, 3, QTableWidgetItem(rec.get("description") or ""))
            self._table.setItem(row, 4, QTableWidgetItem(rec.get("category_name") or rec.get("category") or ""))
            self._table.setItem(row, 5, QTableWidgetItem(rec.get("tag_names") or ""))
            self._table.setItem(row, 6, QTableWidgetItem(rec.get("note") or ""))
            self._table.setItem(row, 7, QTableWidgetItem(str(rec.get("day_of_month", 1))))


# ---------------------------------------------------------------------------
# SettingsView
# ---------------------------------------------------------------------------
