# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import pytest

from conftest import opengl_import_error

pytest.importorskip(
    "PySide6.QtWidgets",
    reason="PySide6.QtWidgets requires libEGL (not available in headless environments)",
)

pytestmark = pytest.mark.skipif(
    opengl_import_error(),
    reason="PySide6.QtWidgets requires libEGL (not available in headless environments)",
)

from mira.ui.coordinators.navigation_coordinator import NavigationCoordinator  # noqa: E402


class _DummyView:
    def __init__(self) -> None:
        self.refresh_calls = 0

    def refresh(self) -> None:
        self.refresh_calls += 1


class _DummyStack:
    def __init__(self, views: list[object]) -> None:
        self._views = views
        self.current_index = 0

    def setCurrentIndex(self, index: int) -> None:
        self.current_index = index

    def currentWidget(self):
        return self._views[self.current_index]


class _DummyNavList:
    def __init__(self, row: int = 0) -> None:
        self._row = row
        self.block_calls: list[bool] = []

    def currentRow(self) -> int:
        return self._row

    def blockSignals(self, value: bool) -> None:
        self.block_calls.append(value)

    def setCurrentRow(self, row: int) -> None:
        self._row = row


def test_go_updates_stack_nav_and_refreshes_visible_view() -> None:
    views = [_DummyView(), _DummyView()]
    stack = _DummyStack(views)
    nav_list = _DummyNavList(row=0)
    coordinator = NavigationCoordinator(stack, nav_list)

    visible = coordinator.go(1)

    assert visible is views[1]
    assert stack.current_index == 1
    assert nav_list.currentRow() == 1
    assert nav_list.block_calls == [True, False]
    assert views[1].refresh_calls == 1


def test_go_skips_nav_sync_when_row_already_matches() -> None:
    view = _DummyView()
    stack = _DummyStack([view])
    nav_list = _DummyNavList(row=0)
    coordinator = NavigationCoordinator(stack, nav_list)

    coordinator.go(0)

    assert nav_list.block_calls == []
    assert view.refresh_calls == 1
