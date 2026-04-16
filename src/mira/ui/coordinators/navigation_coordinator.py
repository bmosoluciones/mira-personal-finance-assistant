# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Navigation helpers for the main stacked UI."""

from __future__ import annotations

from PySide6.QtWidgets import QListWidget, QStackedWidget, QWidget


class NavigationCoordinator:
    """Keep sidebar selection and stacked widget in sync."""

    def __init__(self, stack: QStackedWidget, nav_list: QListWidget) -> None:
        """Initialize the NavigationCoordinator instance."""
        self._stack = stack
        self._nav_list = nav_list

    def go(self, index: int) -> QWidget | None:
        """Return go."""
        self._stack.setCurrentIndex(index)
        if self._nav_list.currentRow() != index:
            self._nav_list.blockSignals(True)
            self._nav_list.setCurrentRow(index)
            self._nav_list.blockSignals(False)
        view = self._stack.currentWidget()
        if hasattr(view, "refresh"):
            view.refresh()
        return view
