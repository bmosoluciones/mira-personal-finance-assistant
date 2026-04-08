# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Navigation and menu action mixin for the main window."""

from __future__ import annotations


class MainWindowNavigationMixin:
    def _navigate(self, index: int) -> None:
        if hasattr(self, "_navigation"):
            self._navigation.go(index)
            return
        self._stack.setCurrentIndex(index)
        if self._nav_list.currentRow() != index:
            self._nav_list.blockSignals(True)
            self._nav_list.setCurrentRow(index)
            self._nav_list.blockSignals(False)
        if hasattr((view := self._stack.currentWidget()), "refresh"):
            view.refresh()

    def _menu_add_account(self) -> None:
        self._navigate(self.VIEW_ACCOUNTS)
        self._view_accounts.open_add_dialog()

    def _menu_add_transaction(self) -> None:
        self._navigate(self.VIEW_TRANSACTIONS)
        self._view_transactions.open_add_dialog()

    def _menu_transfer(self) -> None:
        self._navigate(self.VIEW_TRANSACTIONS)
        self._view_transactions.open_transfer_dialog()

    def _menu_credit_payment(self) -> None:
        self._navigate(self.VIEW_TRANSACTIONS)
        self._view_transactions.open_credit_payment_dialog()

    def _menu_add_budget(self) -> None:
        self._navigate(self.VIEW_BUDGET)
        self._view_budget.open_create_dialog()

    def _menu_open_accounts(self) -> None:
        self._navigate(self.VIEW_ACCOUNTS)

    def _menu_open_transactions(self) -> None:
        self._navigate(self.VIEW_TRANSACTIONS)

    def _menu_open_budget(self) -> None:
        self._navigate(self.VIEW_BUDGET)

    def _menu_open_categories(self) -> None:
        self._navigate(self.VIEW_CATEGORIES)

    def _menu_add_income_category(self) -> None:
        self._navigate(self.VIEW_CATEGORIES)
        self._view_categories.open_add_income_dialog()

    def _menu_add_expense_category(self) -> None:
        self._navigate(self.VIEW_CATEGORIES)
        self._view_categories.open_add_expense_dialog()

    def _menu_open_tags(self) -> None:
        self._navigate(self.VIEW_TAGS)

    def _menu_add_tag(self) -> None:
        self._navigate(self.VIEW_TAGS)
        self._view_tags.open_add_dialog()

    def _menu_add_recurring(self) -> None:
        self._navigate(self.VIEW_RECURRING)
        self._view_recurring.open_add_dialog()

    def _menu_open_recurring(self) -> None:
        self._navigate(self.VIEW_RECURRING)

    def _menu_apply_recurring(self) -> None:
        self._navigate(self.VIEW_RECURRING)
        self._view_recurring.apply_this_month()

    def _menu_open_goals(self) -> None:
        self._navigate(self.VIEW_GOALS)

    def _menu_add_goal(self) -> None:
        self._navigate(self.VIEW_GOALS)
        self._view_goals.open_add_dialog()

    def _menu_contribute_goal(self) -> None:
        self._navigate(self.VIEW_GOALS)
        self._view_goals.open_contribute_dialog()

    def _open_report_type(self, report_type: int) -> None:
        self._navigate(self.VIEW_REPORTS)
        self._view_reports.set_report_type(report_type)

    def _menu_open_mira_analysis(self) -> None:
        self._navigate(self.VIEW_MIRA_ANALYSIS)

    def _menu_open_settings(self) -> None:
        self._navigate(self.VIEW_SETTINGS)
