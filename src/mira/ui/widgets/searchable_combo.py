# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""A searchable/filterable QComboBox that shows the full list and filters as you type."""

from __future__ import annotations

import re

from PySide6.QtCore import QRegularExpression, QSortFilterProxyModel, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QComboBox, QWidget


class SearchableComboBox(QComboBox):
    """A QComboBox that shows the full item list and filters it in real-time as the user types.

    Internally uses a QStandardItemModel as the data source and a
    QSortFilterProxyModel to perform case-insensitive substring filtering.
    The dropdown popup shows all items when first opened; typing in the
    embedded line-edit narrows the visible entries. Selecting an item
    clears the filter so the next interaction starts with the full list.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source_model = QStandardItemModel(0, 1, self)
        self._proxy_model = QSortFilterProxyModel(self)
        self._proxy_model.setSourceModel(self._source_model)
        self._proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy_model.setFilterKeyColumn(0)
        # Use the proxy (filtered view) as the QComboBox model so the dropdown
        # only shows items that match the current search text.
        super(SearchableComboBox, self).setModel(self._proxy_model)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        # Remove the default QCompleter – we do filtering via the proxy model.
        self.setCompleter(None)  # type: ignore[arg-type]

        # Store the line-edit reference now (setEditable(True) guarantees it exists).
        _le = self.lineEdit()
        assert _le is not None, "SearchableComboBox requires an editable line-edit"
        self._line_edit = _le
        # textEdited fires only on user input, not on programmatic setText.
        self._line_edit.textEdited.connect(self._apply_filter)

        # When the user picks an item from the popup, clear the filter so the
        # list is restored to its full state for the next interaction.
        self.activated.connect(self._on_item_activated)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_filter(self, text: str) -> None:
        """Update the proxy filter and show the popup if it is not already open."""
        self._proxy_model.setFilterRegularExpression(
            QRegularExpression(
                re.escape(text),
                QRegularExpression.PatternOption.CaseInsensitiveOption,
            )
        )
        if not self.view().isVisible():
            self.showPopup()

    def _on_item_activated(self, proxy_row: int) -> None:
        """Restore the full list after the user selects an item."""
        proxy_idx = self._proxy_model.index(proxy_row, 0)
        source_idx = self._proxy_model.mapToSource(proxy_idx)
        # Clear the filter so all items become visible again.
        self._proxy_model.setFilterRegularExpression("")
        # Remap the selection to the new proxy position (order is preserved
        # because we do not sort, only filter).
        new_proxy_idx = self._proxy_model.mapFromSource(source_idx)
        if new_proxy_idx.isValid():
            super(SearchableComboBox, self).setCurrentIndex(new_proxy_idx.row())

    # ------------------------------------------------------------------
    # Public convenience API
    # ------------------------------------------------------------------

    def setPlaceholderText(self, text: str) -> None:
        """Set placeholder text on the embedded line-edit."""
        self._line_edit.setPlaceholderText(text)

    # ------------------------------------------------------------------
    # QComboBox API overrides – route through the source model
    # ------------------------------------------------------------------

    def addItem(self, text: str, userData: object = None) -> None:  # type: ignore[override]
        item = QStandardItem(text)
        if userData is not None:
            item.setData(userData, Qt.ItemDataRole.UserRole)
        self._source_model.appendRow(item)

    def addItems(self, texts: list[str]) -> None:  # type: ignore[override]
        for text in texts:
            self.addItem(str(text))

    def clear(self) -> None:
        self._source_model.clear()
        self._proxy_model.setFilterRegularExpression("")
        self._line_edit.clear()

    def count(self) -> int:
        """Return the total number of items (all, not just filtered)."""
        return self._source_model.rowCount()

    def currentData(self, role: int = Qt.ItemDataRole.UserRole) -> object:  # type: ignore[override]
        proxy_idx = self._proxy_model.index(self.currentIndex(), 0)
        source_idx = self._proxy_model.mapToSource(proxy_idx)
        if source_idx.isValid():
            return self._source_model.data(source_idx, role)
        return None

    def itemData(self, index: int, role: int = Qt.ItemDataRole.UserRole) -> object:  # type: ignore[override]
        proxy_idx = self._proxy_model.index(index, 0)
        if not proxy_idx.isValid():
            return None
        source_idx = self._proxy_model.mapToSource(proxy_idx)
        if source_idx.isValid():
            return self._source_model.data(source_idx, role)
        return None

    def findData(  # type: ignore[override]
        self,
        value: object,
        role: int = Qt.ItemDataRole.UserRole,
        flags: Qt.MatchFlag = Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchCaseSensitive,
    ) -> int:
        """Search all source items for *value*; return the proxy row index.

        If the matching item is currently hidden by the active filter the
        filter is cleared first so that every item is visible.
        """
        for row in range(self._source_model.rowCount()):
            source_idx = self._source_model.index(row, 0)
            if self._source_model.data(source_idx, role) == value:
                proxy_idx = self._proxy_model.mapFromSource(source_idx)
                if proxy_idx.isValid():
                    return proxy_idx.row()
                # Item is filtered out – clear filter, then remap.
                self._proxy_model.setFilterRegularExpression("")
                self._line_edit.clear()
                proxy_idx = self._proxy_model.mapFromSource(source_idx)
                return proxy_idx.row() if proxy_idx.isValid() else -1
        return -1

    def findText(  # type: ignore[override]
        self,
        text: str,
        flags: Qt.MatchFlag = Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchCaseSensitive,
    ) -> int:
        """Search all source items for *text* (display role); return proxy row.

        If the matching item is currently hidden by the active filter the
        filter is cleared first.
        """
        for row in range(self._source_model.rowCount()):
            source_idx = self._source_model.index(row, 0)
            if self._source_model.data(source_idx, Qt.ItemDataRole.DisplayRole) == text:
                proxy_idx = self._proxy_model.mapFromSource(source_idx)
                if proxy_idx.isValid():
                    return proxy_idx.row()
                self._proxy_model.setFilterRegularExpression("")
                self._line_edit.clear()
                proxy_idx = self._proxy_model.mapFromSource(source_idx)
                return proxy_idx.row() if proxy_idx.isValid() else -1
        return -1


__all__ = ["SearchableComboBox"]
