# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""A searchable/filterable QComboBox that keeps typing in the line edit."""

from __future__ import annotations

import re

from PySide6.QtCore import QEvent, QObject, QRegularExpression, QSortFilterProxyModel, Qt
from PySide6.QtGui import QKeyEvent, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QComboBox, QCompleter, QWidget


class SearchableComboBox(QComboBox):
    """A QComboBox that filters suggestions in real time as the user types.

    The combo box keeps the full source model attached so the editor remains
    focused while typing. A proxy-backed completer provides the filtered popup.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the SearchableComboBox instance."""
        super().__init__(parent)
        self._source_model = QStandardItemModel(0, 1, self)
        self._proxy_model = QSortFilterProxyModel(self)
        self._proxy_model.setSourceModel(self._source_model)
        self._proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy_model.setFilterKeyColumn(0)
        super(SearchableComboBox, self).setModel(self._source_model)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        _le = self.lineEdit()
        assert _le is not None, "SearchableComboBox requires an editable line-edit"
        self._line_edit = _le
        self._line_edit.installEventFilter(self)

        self._completer = QCompleter(self._proxy_model, self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self.setCompleter(self._completer)

        self._line_edit.textEdited.connect(self._apply_filter)
        self._completer.activated.connect(
            lambda *_args: self._on_completion_activated(self._completer.currentCompletion())
        )
        self.activated.connect(lambda _index: self._clear_filter())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_filter(self, text: str) -> None:
        """Update the filtered suggestions without stealing focus."""
        self._proxy_model.setFilterRegularExpression(
            QRegularExpression(
                re.escape(text),
                QRegularExpression.PatternOption.CaseInsensitiveOption,
            )
        )
        if not text:
            self._hide_completion_popup()
            return

        self._completer.setCompletionPrefix(text)
        if self._proxy_model.rowCount() > 0:
            self._completer.complete()
        else:
            self._hide_completion_popup()

    def _clear_filter(self) -> None:
        """Restore the full suggestion list for the next interaction."""
        self._proxy_model.setFilterRegularExpression("")
        self._hide_completion_popup()

    def _hide_completion_popup(self) -> None:
        """Hide the completion popup when it exists."""
        popup = self._completer.popup()
        if popup is not None:
            popup.hide()

    def _on_completion_activated(self, text: str) -> None:
        """Sync the combo-box selection after a filtered completion is chosen."""
        if (source_row := super(SearchableComboBox, self).findText(text)) >= 0:
            super(SearchableComboBox, self).setCurrentIndex(source_row)
        self._clear_filter()

    def _should_replace_current_value(self, event: QKeyEvent) -> bool:
        """Return whether typing should replace the currently selected value."""
        if not event.text():
            return False
        if event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier
        ):
            return False
        if self._line_edit.hasSelectedText():
            return False
        current_index = self.currentIndex()
        if current_index < 0:
            return False
        current_text = self._line_edit.text()
        return bool(current_text) and current_text == self.itemText(current_index)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Select the current value before the first typed search character."""
        if watched is self._line_edit and event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            if self._should_replace_current_value(event):
                self._line_edit.selectAll()
        return super(SearchableComboBox, self).eventFilter(watched, event)

    # ------------------------------------------------------------------
    # Public convenience API
    # ------------------------------------------------------------------

    def setPlaceholderText(self, text: str) -> None:
        """Set placeholder text on the embedded line-edit."""
        self._line_edit.setPlaceholderText(text)

    def showPopup(self) -> None:
        """Open the full dropdown list when the arrow button is used."""
        self._clear_filter()
        super(SearchableComboBox, self).showPopup()

    # ------------------------------------------------------------------
    # QComboBox API overrides routed through the source model
    # ------------------------------------------------------------------

    def addItem(self, text: str, userData: object = None) -> None:  # type: ignore[override]
        """Return addItem."""
        item = QStandardItem(text)
        if userData is not None:
            item.setData(userData, Qt.ItemDataRole.UserRole)
        self._source_model.appendRow(item)

    def addItems(self, texts: list[str]) -> None:  # type: ignore[override]
        """Return addItems."""
        for text in texts:
            self.addItem(str(text))

    def clear(self) -> None:
        """Return clear."""
        self._source_model.clear()
        self._clear_filter()
        self._line_edit.clear()

    def count(self) -> int:
        """Return the total number of items."""
        return self._source_model.rowCount()

    def currentData(self, role: int = Qt.ItemDataRole.UserRole) -> object:  # type: ignore[override]
        """Return currentData."""
        return super(SearchableComboBox, self).currentData(role)

    def itemData(self, index: int, role: int = Qt.ItemDataRole.UserRole) -> object:  # type: ignore[override]
        """Return itemData."""
        return super(SearchableComboBox, self).itemData(index, role)

    def findData(  # type: ignore[override]
        self,
        value: object,
        role: int = Qt.ItemDataRole.UserRole,
        flags: Qt.MatchFlag = Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchCaseSensitive,
    ) -> int:
        """Search all source items for *value*; return the source row index."""
        return super(SearchableComboBox, self).findData(value, role, flags)

    def findText(  # type: ignore[override]
        self,
        text: str,
        flags: Qt.MatchFlag = Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchCaseSensitive,
    ) -> int:
        """Search all source items for *text*; return the source row index."""
        return super(SearchableComboBox, self).findText(text, flags)


__all__ = ["SearchableComboBox"]
