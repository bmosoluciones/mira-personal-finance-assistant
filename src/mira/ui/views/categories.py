# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Categories feature view."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mira.app.view_services import CategoriesViewService, CategoriesViewState
from mira.db.database import Database
from mira.db.errors import DuplicateCategoryNameError
from mira.ui.i18n import normalize_language, tr
from mira.ui.views._shared import (
    _CATEGORY_BASE_LABEL_ROLE,
    _TABLE_STYLE,
    _make_toolbar_btn,
    _notify_info,
    _notify_warning,
    _section_title,
    _sub_title,
    _tr_db,
)


class _CategoryTreeWidget(QTreeWidget):
    """Tree widget that uses a single click to select and toggle parent categories."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._consume_parent_release = False
        self.viewport().installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.viewport() and isinstance(event, QMouseEvent):
            item = self.itemAt(event.position().toPoint())
            if item is not None and item.childCount() > 0:
                if event.type() == QEvent.Type.MouseButtonPress:
                    self.setCurrentItem(item)
                    expanded_ids = self._expanded_item_ids()
                    item_id = item.data(0, Qt.ItemDataRole.UserRole)
                    if item.isExpanded():
                        expanded_ids.discard(item_id)
                    else:
                        expanded_ids.add(item_id)
                    self._restore_expanded_items(expanded_ids)
                    self._consume_parent_release = True
                    event.accept()
                    return True
                if event.type() == QEvent.Type.MouseButtonRelease and self._consume_parent_release:
                    self._consume_parent_release = False
                    event.accept()
                    return True

        if event.type() == QEvent.Type.MouseButtonRelease:
            self._consume_parent_release = False
        return super().eventFilter(watched, event)

    def _expanded_item_ids(self) -> set[object]:
        expanded_ids: set[object] = set()

        def collect(item: QTreeWidgetItem) -> None:
            item_id = item.data(0, Qt.ItemDataRole.UserRole)
            if item.childCount() > 0 and item.isExpanded() and item_id is not None:
                expanded_ids.add(item_id)
            for index in range(item.childCount()):
                child_item = item.child(index)
                if child_item is not None:
                    collect(child_item)

        for index in range(self.topLevelItemCount()):
            top_level_item = self.topLevelItem(index)
            if top_level_item is not None:
                collect(top_level_item)
        return expanded_ids

    def _restore_expanded_items(self, expanded_ids: set[object]) -> None:
        self.collapseAll()

        def restore(item: QTreeWidgetItem) -> None:
            item_id = item.data(0, Qt.ItemDataRole.UserRole)
            if item.childCount() > 0 and item_id in expanded_ids:
                item.setExpanded(True)
            for index in range(item.childCount()):
                child_item = item.child(index)
                if child_item is not None:
                    restore(child_item)

        for index in range(self.topLevelItemCount()):
            top_level_item = self.topLevelItem(index)
            if top_level_item is not None:
                restore(top_level_item)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class CategoriesView(QWidget):
    """Income and expense categories management."""

    def __init__(
        self,
        db: Database,
        parent: QWidget | None = None,
        service: CategoriesViewService | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._service = service or CategoriesViewService(db)
        self._language = normalize_language(self._db.setting.get("language"))
        self._income_cats: list[dict] = []
        self._expense_cats: list[dict] = []
        self._build_ui()
        self.refresh()

    def _t(self, key: str, default: str, *, params: dict[str, object] | None = None) -> str:
        return tr(key, self._language, default=default, params=params)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._title_label = _section_title(self._t("categories.title", "Categories"))
        layout.addWidget(self._title_label)

        # Two columns side by side
        cols = QHBoxLayout()
        cols.setSpacing(16)

        # Income categories
        income_frame = QFrame()
        income_frame.setStyleSheet("QFrame{border-radius:6px;border:none;}")
        income_layout = QVBoxLayout(income_frame)
        income_layout.setContentsMargins(12, 10, 12, 10)
        income_layout.setSpacing(6)

        income_header = QHBoxLayout()
        self._income_subtitle = _sub_title(self._t("categories.income.title", "Income Categories"))
        income_header.addWidget(self._income_subtitle)
        income_header.addStretch()
        self._btn_add_income = _make_toolbar_btn(self._t("btn.add", "+ Add"))
        self._btn_edit_income = _make_toolbar_btn(self._t("btn.edit", "✏ Edit"))
        self._btn_del_income = _make_toolbar_btn(self._t("btn.delete", "🗑 Delete"))
        self._btn_merge_income = _make_toolbar_btn(self._t("categories.merge", "⇄ Merge"))
        for b in [
            self._btn_add_income,
            self._btn_edit_income,
            self._btn_del_income,
            self._btn_merge_income,
        ]:
            income_header.addWidget(b)
        income_layout.addLayout(income_header)

        self._income_table = self._build_category_tree()
        income_layout.addWidget(self._income_table, 1)
        cols.addWidget(income_frame, 1)

        # Expense categories
        expense_frame = QFrame()
        expense_frame.setStyleSheet("QFrame{border-radius:6px;border:none;}")
        expense_layout = QVBoxLayout(expense_frame)
        expense_layout.setContentsMargins(12, 10, 12, 10)
        expense_layout.setSpacing(6)

        expense_header = QHBoxLayout()
        self._expense_subtitle = _sub_title(self._t("categories.expense.title", "Expense Categories"))
        expense_header.addWidget(self._expense_subtitle)
        expense_header.addStretch()
        self._btn_add_expense = _make_toolbar_btn(self._t("btn.add", "+ Add"))
        self._btn_edit_expense = _make_toolbar_btn(self._t("btn.edit", "✏ Edit"))
        self._btn_del_expense = _make_toolbar_btn(self._t("btn.delete", "🗑 Delete"))
        self._btn_merge_expense = _make_toolbar_btn(self._t("categories.merge", "⇄ Merge"))
        for b in [
            self._btn_add_expense,
            self._btn_edit_expense,
            self._btn_del_expense,
            self._btn_merge_expense,
        ]:
            expense_header.addWidget(b)
        expense_layout.addLayout(expense_header)

        self._expense_table = self._build_category_tree()
        expense_layout.addWidget(self._expense_table, 1)
        cols.addWidget(expense_frame, 1)

        layout.addLayout(cols, 1)

        # Connect
        self._btn_add_income.clicked.connect(lambda: self._on_add("income"))
        self._btn_edit_income.clicked.connect(lambda: self._on_edit("income"))
        self._btn_del_income.clicked.connect(lambda: self._on_delete("income"))
        self._btn_merge_income.clicked.connect(lambda: self._on_merge("income"))
        self._income_table.customContextMenuRequested.connect(lambda pos: self._open_context_menu("income", pos))

        self._btn_add_expense.clicked.connect(lambda: self._on_add("expense"))
        self._btn_edit_expense.clicked.connect(lambda: self._on_edit("expense"))
        self._btn_del_expense.clicked.connect(lambda: self._on_delete("expense"))
        self._btn_merge_expense.clicked.connect(lambda: self._on_merge("expense"))
        self._expense_table.customContextMenuRequested.connect(lambda pos: self._open_context_menu("expense", pos))

    def _build_category_tree(self) -> QTreeWidget:
        tree = _CategoryTreeWidget()
        tree.setColumnCount(3)
        tree.setRootIsDecorated(True)
        tree.setAlternatingRowColors(True)
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.setStyleSheet(_TABLE_STYLE)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tree.setItemsExpandable(True)
        tree.setExpandsOnDoubleClick(False)
        tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tree.header().setStretchLastSection(False)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tree.itemExpanded.connect(self._update_category_item_indicator)
        tree.itemCollapsed.connect(self._update_category_item_indicator)
        return tree

    def _update_category_item_indicator(self, item: QTreeWidgetItem) -> None:
        base_label = item.data(0, _CATEGORY_BASE_LABEL_ROLE)
        if not isinstance(base_label, str):
            base_label = item.text(0).strip()
            item.setData(0, _CATEGORY_BASE_LABEL_ROLE, base_label)

        if item.childCount() > 0:
            prefix = "[-] " if item.isExpanded() else "[+] "
        else:
            prefix = "    "
        item.setText(0, f"{prefix}{base_label}")

    def _sync_category_tree_indicators(self, tree: QTreeWidget) -> None:
        for index in range(tree.topLevelItemCount()):
            top_level_item = tree.topLevelItem(index)
            if top_level_item is not None:
                self._sync_category_item_indicators(top_level_item)

    def _sync_category_item_indicators(self, item: QTreeWidgetItem) -> None:
        self._update_category_item_indicator(item)
        for index in range(item.childCount()):
            self._sync_category_item_indicators(item.child(index))

    def _selected_category(self, cat_type: str) -> dict | None:
        tree = self._income_table if cat_type == "income" else self._expense_table
        item = tree.currentItem()
        if item is None:
            return None
        cat_id = item.data(0, Qt.ItemDataRole.UserRole)
        if cat_id is None:
            return None
        return self._service.get(int(cat_id))

    def _on_add(self, cat_type: str) -> None:
        from mira.ui.dialogs import CategoryDialog

        dlg = CategoryDialog(self._db, default_type=cat_type, parent=self)
        if dlg.exec() == CategoryDialog.DialogCode.Accepted:
            data = dlg.get_data()
            try:
                feedback = self._service.create(
                    name=data["name"],
                    cat_type=data["cat_type"],
                    color=data["color"],
                    icon=str(data.get("icon") or ""),
                    parent_id=data.get("parent_id"),
                )
            except DuplicateCategoryNameError:
                _notify_warning(
                    self,
                    _tr_db(self._db, "validation.title", "Validation"),
                    _tr_db(self._db, "categories.validation.exists", "Category already exists."),
                )
                return
            except ValueError as exc:
                _notify_warning(self, _tr_db(self._db, "validation.title", "Validation"), str(exc))
                return
            self.refresh()
            if feedback.selected_id is not None:
                self._select_category(int(feedback.selected_id))

    def _on_edit(self, cat_type: str) -> None:
        from mira.ui.dialogs import CategoryDialog

        cat = self._selected_category(cat_type)
        if cat is None:
            return
        dlg = CategoryDialog(self._db, category=cat, parent=self)
        if dlg.exec() == CategoryDialog.DialogCode.Accepted:
            data = dlg.get_data()
            try:
                feedback = self._service.update(
                    int(cat["id"]),
                    name=data["name"],
                    cat_type=data["cat_type"],
                    color=data["color"],
                    icon=str(data.get("icon") or ""),
                    parent_id=data.get("parent_id"),
                )
            except DuplicateCategoryNameError:
                _notify_warning(
                    self,
                    _tr_db(self._db, "validation.title", "Validation"),
                    _tr_db(self._db, "categories.validation.exists", "Category already exists."),
                )
                return
            except ValueError as exc:
                _notify_warning(self, _tr_db(self._db, "validation.title", "Validation"), str(exc))
                return
            self.refresh()
            if feedback.selected_id is not None:
                self._select_category(int(feedback.selected_id))

    def _on_delete(self, cat_type: str) -> None:
        cat = self._selected_category(cat_type)
        if cat is None:
            return
        reply = QMessageBox.question(
            self,
            self._t("categories.delete.title", "Delete Category"),
            self._t(
                "categories.delete.body",
                "Delete category '{name}'?\n\nThis action cannot be undone.",
                params={"name": cat["name"]},
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._service.delete(int(cat["id"]))
            except ValueError as exc:
                _notify_warning(self, _tr_db(self._db, "validation.title", "Validation"), str(exc))
                return
            self.refresh()

    def _on_merge(self, cat_type: str) -> None:
        from mira.ui.dialogs import MergeCategoryDialog

        categories = self._income_cats if cat_type == "income" else self._expense_cats
        if len(categories) < 2:
            _notify_info(
                self,
                self._t("categories.merge.title", "Merge Categories"),
                self._t("categories.merge.minimum", "You need at least two categories to merge."),
            )
            return

        dlg = MergeCategoryDialog(self._db, cat_type=cat_type, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        try:
            feedback = self._service.merge(data["source_id"], data["target_id"])
        except ValueError as exc:
            _notify_warning(self, self._t("categories.merge.title", "Merge Categories"), str(exc))
            return
        self.refresh()
        if feedback.selected_id is not None:
            self._select_category(int(feedback.selected_id))

    def _open_context_menu(self, cat_type: str, pos: QPoint) -> None:
        tree = self._income_table if cat_type == "income" else self._expense_table
        selected_item = tree.itemAt(pos)
        if selected_item is None:
            return
        tree.setCurrentItem(selected_item)
        menu = QMenu(self)
        act_edit = menu.addAction(self._t("btn.edit", "✏ Edit"))
        act_delete = menu.addAction(self._t("btn.delete", "🗑 Delete"))
        act_merge = menu.addAction(self._t("categories.merge", "⇄ Merge"))
        chosen = menu.exec(tree.viewport().mapToGlobal(pos))
        if chosen is act_edit:
            self._on_edit(cat_type)
        elif chosen is act_delete:
            self._on_delete(cat_type)
        elif chosen is act_merge:
            self._on_merge(cat_type)

    def open_add_income_dialog(self) -> None:
        """Public helper used by the main menu to add an income category."""
        self._on_add("income")

    def open_add_expense_dialog(self) -> None:
        """Public helper used by the main menu to add an expense category."""
        self._on_add("expense")

    def refresh(self) -> None:
        self._language = normalize_language(self._db.setting.get("language"))
        self._apply_state(self._service.load_state())

    def _apply_state(self, state: CategoriesViewState) -> None:
        self._income_cats = list(state.income_categories)
        self._expense_cats = list(state.expense_categories)
        cat_counts = dict(state.monthly_counts)

        self._title_label.setText(self._t("categories.title", "Categories"))
        self._income_subtitle.setText(self._t("categories.income.title", "Income Categories"))
        self._expense_subtitle.setText(self._t("categories.expense.title", "Expense Categories"))
        self._btn_add_income.setText(self._t("btn.add", "+ Add"))
        self._btn_edit_income.setText(self._t("btn.edit", "✏ Edit"))
        self._btn_del_income.setText(self._t("btn.delete", "🗑 Delete"))
        self._btn_merge_income.setText(self._t("categories.merge", "⇄ Merge"))
        self._btn_add_expense.setText(self._t("btn.add", "+ Add"))
        self._btn_edit_expense.setText(self._t("btn.edit", "✏ Edit"))
        self._btn_del_expense.setText(self._t("btn.delete", "🗑 Delete"))
        self._btn_merge_expense.setText(self._t("categories.merge", "⇄ Merge"))

        def fill_tree(tree: QTreeWidget, roots: list[dict[str, object]]) -> None:
            tree.clear()
            tree.setHeaderLabels(
                [
                    self._t("categories.col.name", "Category"),
                    self._t("categories.col.txns_month", "Txns (month)"),
                    self._t("categories.col.flags", "Flags"),
                ]
            )

            def add_node(parent_item: QTreeWidgetItem | None, cat: dict) -> int:
                icon = str(cat.get("icon") or "")
                label = f"{icon} {cat['name']}".strip()
                own_count = cat_counts.get(str(cat["name"]), 0)
                flags: list[str] = []
                if int(cat.get("is_savings") or 0) == 1:
                    flags.append(self._t("categories.flag.savings", "Savings"))
                if cat.get("children"):
                    flags.append(self._t("categories.flag.group", "Group"))
                item = QTreeWidgetItem([label, "", " · ".join(flags)])
                item.setData(0, Qt.ItemDataRole.UserRole, int(cat["id"]))
                item.setData(0, _CATEGORY_BASE_LABEL_ROLE, label)
                if parent_item is None:
                    tree.addTopLevelItem(item)
                else:
                    parent_item.addChild(item)
                total_count = own_count
                for child in list(cat.get("children") or []):
                    total_count += add_node(item, child)
                item.setText(1, str(total_count) if total_count > 0 else "0")
                return total_count

            for root in roots:
                add_node(None, root)
            tree.expandAll()
            self._sync_category_tree_indicators(tree)

        fill_tree(self._income_table, list(state.income_tree))
        fill_tree(self._expense_table, list(state.expense_tree))

    def _select_category(self, category_id: int) -> None:
        for tree in [self._income_table, self._expense_table]:
            pending = [tree.topLevelItem(index) for index in range(tree.topLevelItemCount())]
            while pending:
                item = pending.pop(0)
                if item is None:
                    continue
                if item.data(0, Qt.ItemDataRole.UserRole) == category_id:
                    tree.setCurrentItem(item)
                    return
                pending.extend(
                    child_item for index in range(item.childCount()) if (child_item := item.child(index)) is not None
                )


# ---------------------------------------------------------------------------
# MiraAnalysisView
# ---------------------------------------------------------------------------
