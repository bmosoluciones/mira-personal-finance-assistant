# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Dialog for managing income↔expense category relations."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mira.app.view_services import CategoriesViewService
from mira.db.database import Database
from mira.ui.i18n import tr


class LinkCategoriesDialog(QDialog):
    """Modal dialog to view, add and delete income↔expense category relations."""

    def __init__(
        self,
        db: Database,
        service: CategoriesViewService,
        language: str,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the LinkCategoriesDialog instance."""
        super().__init__(parent)
        self._db = db
        self._service = service
        self._language = language
        self.setWindowTitle(self._t("categories.link.title", "Link Categories"))
        self.setMinimumSize(560, 400)
        self._build_ui()
        self._refresh_table()

    def _t(self, key: str, default: str, *, params: dict[str, object] | None = None) -> str:
        """Return t."""
        return tr(key, self._language, default=default, params=params)

    def _build_ui(self) -> None:
        """Return build ui."""
        layout = QVBoxLayout(self)

        # Relations table
        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(
            [
                self._t("categories.link.col.income", "Income Category"),
                self._t("categories.link.col.expense", "Expense Category"),
            ]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, 1)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_add = QPushButton(self._t("categories.link.add", "Add Relation"))
        self._btn_delete = QPushButton(self._t("categories.link.delete", "Delete Relation"))
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_delete)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._btn_add.clicked.connect(self._on_add)
        self._btn_delete.clicked.connect(self._on_delete)

    def _refresh_table(self) -> None:
        """Return refresh table."""
        relations = self._service.list_relations()
        self._table.setRowCount(len(relations))
        for row_idx, rel in enumerate(relations):
            income_item = QTableWidgetItem(str(rel.get("income_category_name", "")))
            income_item.setData(Qt.ItemDataRole.UserRole, int(rel["id"]))
            expense_item = QTableWidgetItem(str(rel.get("expense_category_name", "")))
            self._table.setItem(row_idx, 0, income_item)
            self._table.setItem(row_idx, 1, expense_item)

    def _on_add(self) -> None:
        """Return on add."""
        income_cats = self._service.parent_income_categories()
        expense_cats = self._service.available_parent_expense_categories()

        if not income_cats:
            QMessageBox.information(
                self,
                self._t("categories.link.title", "Link Categories"),
                self._t("categories.link.no_income", "No level-1 income categories available."),
            )
            return
        if not expense_cats:
            QMessageBox.information(
                self,
                self._t("categories.link.title", "Link Categories"),
                self._t("categories.link.no_expense", "No level-1 expense categories available."),
            )
            return

        dlg = _AddRelationDialog(
            income_cats,
            expense_cats,
            self._language,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            try:
                self._service.create_relation(data["income_id"], data["expense_id"])
            except ValueError as exc:
                QMessageBox.warning(
                    self,
                    self._t("categories.link.title", "Link Categories"),
                    str(exc),
                )
                return
            self._refresh_table()

    def _on_delete(self) -> None:
        """Return on delete."""
        row = self._table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                self._t("categories.link.title", "Link Categories"),
                self._t("categories.link.select_required", "Please select a relation first."),
            )
            return

        income_item = self._table.item(row, 0)
        expense_item = self._table.item(row, 1)
        if income_item is None or expense_item is None:
            return
        relation_id = income_item.data(Qt.ItemDataRole.UserRole)

        reply = QMessageBox.question(
            self,
            self._t("categories.link.delete.title", "Delete Relation"),
            self._t(
                "categories.link.delete.body",
                "Delete relation between '{income}' and '{expense}'?",
                params={"income": income_item.text(), "expense": expense_item.text()},
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._service.delete_relation(int(relation_id))
            except ValueError as exc:
                QMessageBox.warning(
                    self,
                    self._t("categories.link.title", "Link Categories"),
                    str(exc),
                )
                return
            self._refresh_table()


class _AddRelationDialog(QDialog):
    """Simple form with two combo boxes for income and expense categories."""

    def __init__(
        self,
        income_categories: list[dict[str, Any]],
        expense_categories: list[dict[str, Any]],
        language: str,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the _AddRelationDialog instance."""
        super().__init__(parent)
        self._language = language
        self.setWindowTitle(self._t("categories.link.add", "Add Relation"))

        form = QFormLayout(self)

        self._income_combo = QComboBox()
        for cat in income_categories:
            self._income_combo.addItem(str(cat["name"]), int(cat["id"]))
        form.addRow(
            QLabel(self._t("categories.link.income_label", "Income Category:")),
            self._income_combo,
        )

        self._expense_combo = QComboBox()
        for cat in expense_categories:
            self._expense_combo.addItem(str(cat["name"]), int(cat["id"]))
        form.addRow(
            QLabel(self._t("categories.link.expense_label", "Expense Category:")),
            self._expense_combo,
        )

        btn_row = QHBoxLayout()
        self._btn_save = QPushButton(self._t("categories.link.save", "Save"))
        self._btn_cancel = QPushButton(self._t("categories.link.cancel", "Cancel"))
        btn_row.addStretch()
        btn_row.addWidget(self._btn_save)
        btn_row.addWidget(self._btn_cancel)
        form.addRow(btn_row)

        self._btn_save.clicked.connect(self.accept)
        self._btn_cancel.clicked.connect(self.reject)

    def _t(self, key: str, default: str, *, params: dict[str, object] | None = None) -> str:
        """Return t."""
        return tr(key, self._language, default=default, params=params)

    def get_data(self) -> dict[str, int]:
        """Return get data."""
        return {
            "income_id": int(self._income_combo.currentData()),
            "expense_id": int(self._expense_combo.currentData()),
        }
