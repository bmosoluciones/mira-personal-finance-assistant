# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Build the main menu bar for the desktop window."""

from __future__ import annotations

from PySide6.QtGui import QAction

from mira.ui.i18n import tr
from mira.ui.views.report_types import REPORT_ACCOUNT_TREND, REPORT_CASH_FLOW, REPORT_CATEGORY, REPORT_TOTAL


HIDE_MOBILE: bool = True


class MenuBuilder:
    """Extracted menu construction for MainWindow."""

    def build(self, window) -> None:
        """Return build."""
        mb = window.menuBar()
        mb.clear()

        file_menu = mb.addMenu(tr("menu.file", window._language, default="File"))
        act_import = QAction(tr("menu.file.import_csv", window._language, default="Import CSV..."), window)
        act_import.triggered.connect(window._on_import_csv)
        file_menu.addAction(act_import)

        act_export = QAction(tr("menu.file.export_csv", window._language, default="Export CSV..."), window)
        act_export.triggered.connect(window._on_export_csv)
        file_menu.addAction(act_export)
        file_menu.addSeparator()

        act_backup = QAction(tr("menu.file.backup", window._language, default="Backup Database..."), window)
        act_backup.triggered.connect(window._on_backup)
        file_menu.addAction(act_backup)

        act_restore = QAction(tr("menu.file.restore", window._language, default="Restore Database..."), window)
        act_restore.triggered.connect(window._on_restore)
        file_menu.addAction(act_restore)
        file_menu.addSeparator()

        act_exit = QAction(tr("menu.file.exit", window._language, default="Exit"), window)
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(window.close)
        file_menu.addAction(act_exit)

        accounts_menu = mb.addMenu(tr("menu.accounts", window._language, default="Accounts"))
        act_view_accounts = QAction(tr("menu.accounts.view", window._language, default="View Accounts"), window)
        act_view_accounts.triggered.connect(window._menu_open_accounts)
        accounts_menu.addAction(act_view_accounts)
        act_add_account = QAction(tr("menu.accounts.add", window._language, default="Add Account"), window)
        act_add_account.triggered.connect(window._menu_add_account)
        accounts_menu.addAction(act_add_account)
        act_reconcile = QAction(
            tr("menu.accounts.reconcile", window._language, default="Reconcile Account"),
            window,
        )
        act_reconcile.triggered.connect(window._menu_open_reconciliation)
        accounts_menu.addAction(act_reconcile)

        tx_menu = mb.addMenu(tr("menu.transactions", window._language, default="Transactions"))
        act_view_tx = QAction(tr("menu.transactions.view", window._language, default="View Transactions"), window)
        act_view_tx.triggered.connect(window._menu_open_transactions)
        tx_menu.addAction(act_view_tx)
        act_add_tx = QAction(tr("menu.transactions.add", window._language, default="Add Transaction"), window)
        act_add_tx.triggered.connect(window._menu_add_transaction)
        tx_menu.addAction(act_add_tx)
        act_transfer = QAction(
            tr("menu.transactions.transfer", window._language, default="Transfer Between Accounts"),
            window,
        )
        act_transfer.triggered.connect(window._menu_transfer)
        tx_menu.addAction(act_transfer)
        act_card_payment = QAction(
            tr("menu.transactions.card_payment", window._language, default="Credit Card Payment"),
            window,
        )
        act_card_payment.triggered.connect(window._menu_credit_payment)
        tx_menu.addAction(act_card_payment)

        budget_menu = mb.addMenu(tr("menu.budget", window._language, default="Budget"))
        act_view_budget = QAction(tr("menu.budget.view", window._language, default="View Budget"), window)
        act_view_budget.triggered.connect(window._menu_open_budget)
        budget_menu.addAction(act_view_budget)
        act_add_budget = QAction(tr("menu.budget.add", window._language, default="New Budget"), window)
        act_add_budget.triggered.connect(window._menu_add_budget)
        budget_menu.addAction(act_add_budget)

        categories_menu = mb.addMenu(tr("menu.categories", window._language, default="Categories"))
        act_view_categories = QAction(
            tr("menu.categories.view", window._language, default="View Categories"),
            window,
        )
        act_view_categories.triggered.connect(window._menu_open_categories)
        categories_menu.addAction(act_view_categories)
        act_add_income_cat = QAction(
            tr("menu.categories.add_income", window._language, default="Add Income Category"),
            window,
        )
        act_add_income_cat.triggered.connect(window._menu_add_income_category)
        categories_menu.addAction(act_add_income_cat)
        act_add_expense_cat = QAction(
            tr("menu.categories.add_expense", window._language, default="Add Expense Category"),
            window,
        )
        act_add_expense_cat.triggered.connect(window._menu_add_expense_category)
        categories_menu.addAction(act_add_expense_cat)

        tags_menu = mb.addMenu(tr("menu.tags", window._language, default="Tags"))
        act_view_tags = QAction(tr("menu.tags.view", window._language, default="View Tags"), window)
        act_view_tags.triggered.connect(window._menu_open_tags)
        tags_menu.addAction(act_view_tags)
        act_add_tag = QAction(tr("menu.tags.add", window._language, default="Create Tag"), window)
        act_add_tag.triggered.connect(window._menu_add_tag)
        tags_menu.addAction(act_add_tag)

        recurring_menu = mb.addMenu(tr("menu.recurring", window._language, default="Recurring"))
        act_view_recurring = QAction(
            tr("menu.recurring.view", window._language, default="View Recurring Transactions"),
            window,
        )
        act_view_recurring.triggered.connect(window._menu_open_recurring)
        recurring_menu.addAction(act_view_recurring)
        act_add_rec = QAction(
            tr("menu.recurring.add", window._language, default="Add Recurring Transaction"),
            window,
        )
        act_add_rec.triggered.connect(window._menu_add_recurring)
        recurring_menu.addAction(act_add_rec)
        act_apply_rec = QAction(tr("menu.recurring.apply", window._language, default="Apply recurring..."), window)
        act_apply_rec.triggered.connect(window._menu_apply_recurring)
        recurring_menu.addAction(act_apply_rec)

        reports_menu = mb.addMenu(tr("menu.reports", window._language, default="Reports"))
        act_total_report = QAction(
            tr("menu.reports.total", window._language, default="Total Income and Expenses"),
            window,
        )
        act_total_report.triggered.connect(lambda: window._open_report_type(REPORT_TOTAL))
        reports_menu.addAction(act_total_report)
        act_category_report = QAction(
            tr("menu.reports.category", window._language, default="Category Breakdown"),
            window,
        )
        act_category_report.triggered.connect(lambda: window._open_report_type(REPORT_CATEGORY))
        reports_menu.addAction(act_category_report)
        act_account_report = QAction(
            tr("menu.reports.account_trend", window._language, default="Account Trend"),
            window,
        )
        act_account_report.triggered.connect(lambda: window._open_report_type(REPORT_ACCOUNT_TREND))
        reports_menu.addAction(act_account_report)
        act_cash_report = QAction(tr("menu.reports.cash_flow", window._language, default="Cash Flow"), window)
        act_cash_report.triggered.connect(lambda: window._open_report_type(REPORT_CASH_FLOW))
        reports_menu.addAction(act_cash_report)
        reports_menu.addSeparator()
        act_mira_analysis = QAction(
            tr("menu.reports.mira_analysis", window._language, default="MIRA Analysis"),
            window,
        )
        act_mira_analysis.triggered.connect(window._menu_open_mira_analysis)
        reports_menu.addAction(act_mira_analysis)

        goals_menu = mb.addMenu(tr("menu.goals", window._language, default="Goals"))
        act_view_goals = QAction(tr("menu.goals.view", window._language, default="View Goals"), window)
        act_view_goals.triggered.connect(window._menu_open_goals)
        goals_menu.addAction(act_view_goals)
        act_add_goal = QAction(tr("menu.goals.add", window._language, default="Add Goal"), window)
        act_add_goal.triggered.connect(window._menu_add_goal)
        goals_menu.addAction(act_add_goal)
        act_contribute_goal = QAction(
            tr("menu.goals.contribute", window._language, default="Contribute to Goal"),
            window,
        )
        act_contribute_goal.triggered.connect(window._menu_contribute_goal)
        goals_menu.addAction(act_contribute_goal)

        tools_menu = mb.addMenu(tr("menu.tools", window._language, default="Tools"))
        act_compound_interest = QAction(
            tr("menu.tools.compound_interest", window._language, default="Compound Interest Calculator"),
            window,
        )
        act_compound_interest.triggered.connect(window._menu_open_compound_interest)
        tools_menu.addAction(act_compound_interest)
        act_loan_calculator = QAction(
            tr("menu.tools.loan_amortization", window._language, default="Loan Calculator"),
            window,
        )
        act_loan_calculator.triggered.connect(window._menu_open_loan_amortization)
        tools_menu.addAction(act_loan_calculator)
        act_goal_simulator = QAction(
            tr("menu.tools.goal_simulator", window._language, default="Savings Goal Simulator"),
            window,
        )
        act_goal_simulator.triggered.connect(window._menu_open_goal_simulator)
        tools_menu.addAction(act_goal_simulator)

        if not HIDE_MOBILE:
            mobile_menu = mb.addMenu(tr("menu.mobile", window._language, default="Mobile"))
            act_mobile_sync = QAction(tr("menu.mobile.sync", window._language, default="Sync"), window)
            act_mobile_sync.triggered.connect(window._on_mobile_sync)
            mobile_menu.addAction(act_mobile_sync)

        view_menu = mb.addMenu(tr("menu.view", window._language, default="View"))
        window._act_sidebar = QAction(
            tr("menu.view.toggle_sidebar", window._language, default="Show / Hide Sidebar"),
            window,
        )
        window._act_sidebar.setShortcut("Ctrl+B")
        window._act_sidebar.setCheckable(True)
        window._act_sidebar.setChecked(True)
        window._act_sidebar.triggered.connect(window._toggle_sidebar)
        view_menu.addAction(window._act_sidebar)

        window._act_prompt = QAction(
            tr("menu.view.toggle_prompt", window._language, default="Show / Hide Prompt Panel"),
            window,
        )
        window._act_prompt.setShortcut("Ctrl+P")
        window._act_prompt.setCheckable(True)
        window._act_prompt.setChecked(True)
        window._act_prompt.triggered.connect(window._toggle_prompt_panel)
        view_menu.addAction(window._act_prompt)

        settings_menu = mb.addMenu(tr("menu.settings", window._language, default="Settings"))
        act_open_settings = QAction(
            tr("menu.settings.open", window._language, default="Open Main Settings"),
            window,
        )
        act_open_settings.setShortcut("Ctrl+,")
        act_open_settings.triggered.connect(window._menu_open_settings)
        settings_menu.addAction(act_open_settings)

        help_menu = mb.addMenu(tr("menu.help", window._language, default="Help"))
        act_about = QAction(tr("menu.help.info", window._language, default="Information"), window)
        act_about.triggered.connect(window._on_about)
        help_menu.addAction(act_about)
        act_docs = QAction(tr("menu.help.docs", window._language, default="Documentation"), window)
        act_docs.triggered.connect(window._on_open_documentation)
        help_menu.addAction(act_docs)
