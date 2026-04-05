# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import importlib

import pytest


def _get_qapplication_or_xfail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        qtwidgets = importlib.import_module("PySide6.QtWidgets")
    except (ImportError, OSError) as exc:
        pytest.xfail(f"Qt runtime unavailable for menu builder test: {exc}")

    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


def test_menu_builder_creates_expected_menus_and_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    _get_qapplication_or_xfail(monkeypatch)
    qtwidgets = importlib.import_module("PySide6.QtWidgets")
    builder_module = importlib.import_module("mira.ui.menu_builder")

    class DummyWindow(qtwidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self._language = "es"
            self.open_tags_calls = 0

        def _on_import_csv(self) -> None:
            return None

        def _on_export_csv(self) -> None:
            return None

        def _on_backup(self) -> None:
            return None

        def _on_restore(self) -> None:
            return None

        def _menu_add_account(self) -> None:
            return None

        def _menu_open_accounts(self) -> None:
            return None

        def _menu_add_transaction(self) -> None:
            return None

        def _menu_open_transactions(self) -> None:
            return None

        def _menu_transfer(self) -> None:
            return None

        def _menu_credit_payment(self) -> None:
            return None

        def _menu_add_budget(self) -> None:
            return None

        def _menu_open_budget(self) -> None:
            return None

        def _menu_add_income_category(self) -> None:
            return None

        def _menu_add_expense_category(self) -> None:
            return None

        def _menu_open_categories(self) -> None:
            return None

        def _menu_open_tags(self) -> None:
            self.open_tags_calls += 1

        def _menu_add_tag(self) -> None:
            return None

        def _menu_add_recurring(self) -> None:
            return None

        def _menu_open_recurring(self) -> None:
            return None

        def _menu_apply_recurring(self) -> None:
            return None

        def _open_report_type(self, _report_type: int) -> None:
            return None

        def _menu_open_mira_analysis(self) -> None:
            return None

        def _menu_add_goal(self) -> None:
            return None

        def _menu_open_goals(self) -> None:
            return None

        def _menu_contribute_goal(self) -> None:
            return None

        def _menu_open_compound_interest(self) -> None:
            return None

        def _menu_open_loan_amortization(self) -> None:
            return None

        def _menu_open_goal_simulator(self) -> None:
            return None

        def _toggle_sidebar(self) -> None:
            return None

        def _toggle_prompt_panel(self) -> None:
            return None

        def _menu_open_settings(self) -> None:
            return None

        def _on_about(self) -> None:
            return None

        def _on_open_documentation(self) -> None:
            return None

    window = DummyWindow()
    try:
        builder_module.MenuBuilder().build(window)

        menu_labels = [action.text() for action in window.menuBar().actions()]
        menus = {menu.title(): menu for menu in window.findChildren(qtwidgets.QMenu)}
        assert "Etiquetas" in menu_labels
        assert any("Archivo" in label or "File" in label for label in menu_labels)
        assert window._act_sidebar.isCheckable() is True
        assert window._act_prompt.isCheckable() is True

        tags_menu = menus["Etiquetas"]
        tags_menu.actions()[0].trigger()

        assert window.open_tags_calls == 1
    finally:
        window.close()
