# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Layout builder mixin for the main window."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from mira.ui.coordinators.navigation_coordinator import NavigationCoordinator
from mira.ui.i18n import tr
from mira.ui.main_window_support import build_view_services
from mira.ui.views.accounts import AccountsView
from mira.ui.views.budget import BudgetView
from mira.ui.views.categories import CategoriesView
from mira.ui.views.dashboard import DashboardView
from mira.ui.views.mira_analysis import MiraAnalysisView
from mira.ui.views.recurring import RecurringView
from mira.ui.views.reports import ReportsView
from mira.ui.views.savings_goals import SavingsGoalsView
from mira.ui.views.settings import SettingsView
from mira.ui.views.tags import TagsView
from mira.ui.views.transactions import TransactionsView

_SIDEBAR_WIDTH = 170


class MainWindowLayoutMixin:
    def _build_ui(self) -> None:
        root_widget = self._build_central_widget()
        self.setCentralWidget(root_widget)
        self._build_status_bar()

    def _build_central_widget(self) -> QWidget:
        root_widget = QWidget()
        root_layout = QVBoxLayout(root_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addLayout(self._build_content_row(), 1)

        footer_sep = QFrame()
        footer_sep.setFrameShape(QFrame.Shape.HLine)
        footer_sep.setStyleSheet("color:palette(mid);")
        root_layout.addWidget(footer_sep)

        self._footer = self._make_footer()
        root_layout.addWidget(self._footer)
        return root_widget

    def _build_content_row(self) -> QHBoxLayout:
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)
        self._sidebar_panel = self._make_sidebar()
        content_row.addWidget(self._sidebar_panel)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color:palette(mid);")
        content_row.addWidget(sep)
        self._stack = self._make_stack()
        self._navigation = NavigationCoordinator(self._stack, self._nav_list)
        content_row.addWidget(self._stack, 1)
        return content_row

    def _build_status_bar(self) -> None:
        status = QStatusBar()
        status.setStyleSheet("font-size:10px;")
        self.setStatusBar(status)
        username = self._db.setting.get("username") or tr(
            "settings.saved_default_user", self._language, default="Usuario"
        )
        status.showMessage(
            tr(
                "status.welcome",
                self._language,
                params={"username": username},
                default=f"Welcome, {username}\u2003|\u2003100% offline \u2013 no data leaves your device.",
            )
        )
        self._status_bar = status

    @staticmethod
    def _sidebar_nav_stylesheet() -> str:
        """Return the stylesheet for the sidebar navigation list.

        Only overrides the widget-level background and border; sub-element rules
        (``::item``, ``::item:selected``) are intentionally omitted so that
        qt-material's app-level stylesheet controls item colours and selection
        states correctly for both dark and light themes.

        ``background: transparent`` is the key fix: without it QListWidget renders
        with Qt's default Base colour (usually white), which clashes with dark themes.
        ``_refresh_sidebar_style()`` re-applies this stylesheet after every theme
        switch to force Qt to redraw the widget against the new app-level stylesheet.
        """
        return "QListWidget{border:none;background:transparent;outline:0;}"

    def _make_sidebar(self) -> QFrame:
        panel = QFrame()
        panel.setFixedWidth(_SIDEBAR_WIDTH)
        panel.setStyleSheet("")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel(tr("app.name", self._language, default="MIRA"))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        header.setStyleSheet("padding:10px 0;")
        layout.addWidget(header)

        self._nav_list = QListWidget()
        self._nav_list.setStyleSheet(self._sidebar_nav_stylesheet())
        self._nav_list.setSpacing(1)
        for label in [
            tr("nav.dashboard", self._language, default="🏠  Dashboard"),
            tr("nav.transactions", self._language, default="📋  Transactions"),
            tr("nav.accounts", self._language, default="🏦  Accounts"),
            tr("nav.budget", self._language, default="🪣  Budgets"),
            tr("nav.categories", self._language, default="📁  Categories"),
            tr("nav.tags", self._language, default="🔖  Tags"),
            tr("nav.recurring", self._language, default="🔄  Recurring"),
            tr("nav.reports", self._language, default="📊  Reports"),
            tr("nav.mira_analysis", self._language, default="📈  MIRA Analysis"),
            tr("nav.goals", self._language, default="🎯  Goals"),
            tr("nav.settings", self._language, default="⚙️  Settings"),
        ]:
            self._nav_list.addItem(QListWidgetItem(label))
        self._nav_list.setCurrentRow(0)
        self._nav_list.currentRowChanged.connect(self._navigate)
        layout.addWidget(self._nav_list, 1)
        return panel

    def _make_stack(self) -> QStackedWidget:
        stack = QStackedWidget()
        stack.setStyleSheet("")
        services = build_view_services(self._db)
        self._view_dashboard = DashboardView(self._db)
        self._view_transactions = TransactionsView(self._db, service=services.transactions)
        self._view_accounts = AccountsView(self._db, service=services.accounts)
        self._view_budget = BudgetView(self._db)
        self._view_categories = CategoriesView(self._db, service=services.categories)
        self._view_tags = TagsView(self._db, service=services.tags)
        self._view_recurring = RecurringView(self._db, service=services.recurring)
        self._view_reports = ReportsView(self._db, service=services.reports)
        self._view_reports.assistant_message_requested.connect(self._append_chat_assistant)
        self._view_mira_analysis = MiraAnalysisView(
            self._db,
            service=services.mira_analysis,
            message_builder=services.mira_message_builder,
        )
        self._view_mira_analysis.assistant_message_requested.connect(self._append_chat_assistant)
        self._view_goals = SavingsGoalsView(self._db, service=services.goals)
        self._view_settings = SettingsView(self._db, service=services.settings)
        self._view_settings.settings_saved.connect(self._on_settings_saved)
        self._view_settings.language_changed.connect(self._on_language_changed)
        self._view_settings.theme_changed.connect(self._on_theme_changed)
        self._view_settings.download_default_model_requested.connect(self._on_download_default_model)

        for view in [
            self._view_dashboard,
            self._view_transactions,
            self._view_accounts,
            self._view_budget,
            self._view_categories,
            self._view_tags,
            self._view_recurring,
            self._view_reports,
            self._view_mira_analysis,
            self._view_goals,
            self._view_settings,
        ]:
            stack.addWidget(view)
        return stack

    def _make_footer(self) -> QFrame:
        footer = QFrame()
        footer.setStyleSheet("")
        footer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        footer.setMaximumHeight(140)
        row = QHBoxLayout(footer)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._logo_panel = self._make_logo_panel()
        row.addWidget(self._logo_panel)
        vsep = QFrame()
        vsep.setFrameShape(QFrame.Shape.VLine)
        vsep.setStyleSheet("color:palette(mid);")
        row.addWidget(vsep)
        row.addWidget(self._make_prompt_panel(), 1)
        return footer

    def _make_logo_panel(self) -> QFrame:
        panel = QFrame()
        panel.setFixedWidth(_SIDEBAR_WIDTH)
        panel.setStyleSheet("")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar = QLabel("\U0001f916")
        avatar.setFont(QFont("Arial", 22))
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet("background:transparent;")
        layout.addWidget(avatar)
        title = QLabel(tr("chat.assistant.title", self._language, default="MIRA Assistant"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("background:transparent;font-size:11px;font-weight:bold;")
        layout.addWidget(title)
        self._status_label = QLabel(tr("status.ready", self._language, default="●  Ready"))
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet("background:transparent;font-size:10px;")
        layout.addWidget(self._status_label)
        return panel

    def _make_prompt_panel(self) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet("")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._mode_switch = QComboBox()
        self._mode_switch.setStyleSheet(
            "QComboBox{border:1px solid palette(mid);border-radius:3px;padding:2px 6px;font-size:11px;}"
        )
        self._mode_switch.addItem(tr("settings.mode.assistant", self._language, default="Assistant mode"), "assistant")
        self._mode_switch.addItem(tr("settings.mode.chat", self._language, default="Chat mode"), "chat")
        saved_mode = self._db.setting.get("llm_interaction_mode") or "assistant"
        if (mode_idx := self._mode_switch.findData(saved_mode)) >= 0:
            self._mode_switch.setCurrentIndex(mode_idx)
        self._mode_switch.currentIndexChanged.connect(self._on_mode_changed)
        self._mode_switch.setVisible(self._model_lifecycle.sync_engine_info(self._active_model_path).mode_visible)

        self._chat_content = QFrame()
        self._chat_content.setStyleSheet("")
        content_layout = QVBoxLayout(self._chat_content)
        content_layout.setContentsMargins(10, 6, 10, 6)
        content_layout.setSpacing(4)

        response_frame = QFrame()
        response_frame.setStyleSheet(
            "QFrame{border:1px solid palette(mid);border-radius:4px;background:palette(base);padding:6px;}"
        )
        response_layout = QVBoxLayout(response_frame)
        response_layout.setContentsMargins(0, 0, 0, 0)
        response_layout.setSpacing(6)
        self._response_browser = QTextBrowser()
        self._response_browser.setStyleSheet(
            "QTextBrowser{border:none;font-size:12px;padding:4px;background:transparent;color:palette(text);}"
        )
        self._response_browser.setMinimumHeight(50)
        self._response_browser.setMaximumHeight(70)
        self._response_browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._response_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._response_placeholder_text = tr(
            "prompt.response_placeholder",
            self._language,
            default="La respuesta aparecerá aquí...",
        )
        self._response_browser.setHtml(self._placeholder_chat_html())
        response_layout.addWidget(self._response_browser)
        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(0, 0, 0, 0)
        nav_row.setSpacing(6)
        nav_row.addStretch()
        self._chat_clear_btn = QPushButton(tr("chat.clear", self._language, default="Clear"))
        self._chat_clear_btn.setStyleSheet(
            "QPushButton{border:1px solid palette(mid);border-radius:4px;padding:3px 10px;font-size:11px;}"
        )
        self._chat_clear_btn.clicked.connect(self._clear_chat_messages)
        nav_row.addWidget(self._chat_clear_btn)
        self._chat_prev_btn = QPushButton(tr("chat.prev", self._language, default="Previous"))
        self._chat_prev_btn.setStyleSheet(
            "QPushButton{border:1px solid palette(mid);border-radius:4px;padding:3px 10px;font-size:11px;}"
        )
        self._chat_prev_btn.clicked.connect(self._show_previous_chat_message)
        nav_row.addWidget(self._chat_prev_btn)
        self._chat_counter_lbl = QLabel("0 / 0")
        self._chat_counter_lbl.setStyleSheet("background:transparent;font-size:11px;min-width:52px;")
        self._chat_counter_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_row.addWidget(self._chat_counter_lbl)
        self._chat_next_btn = QPushButton(tr("chat.next", self._language, default="Next"))
        self._chat_next_btn.setStyleSheet(
            "QPushButton{border:1px solid palette(mid);border-radius:4px;padding:3px 10px;font-size:11px;}"
        )
        self._chat_next_btn.clicked.connect(self._show_next_chat_message)
        nav_row.addWidget(self._chat_next_btn)
        response_layout.addLayout(nav_row)
        content_layout.addWidget(response_frame)
        self._update_chat_navigation()

        self._quick_btns_frame = QFrame()
        self._quick_btns_frame.setStyleSheet("background:transparent;")
        qb_row = QHBoxLayout(self._quick_btns_frame)
        qb_row.setContentsMargins(0, 0, 0, 0)
        qb_row.setSpacing(6)
        for label, template in [
            (tr("quick.add_income", self._language, default="➕ Add Income"), "received 0 from "),
            (tr("quick.add_expense", self._language, default="➖ Add Expense"), "spent 0 on "),
            (tr("quick.report", self._language, default="📊 View Report"), "report"),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(
                "QPushButton{border:1px solid palette(mid);border-radius:4px;padding:4px 10px;font-size:11px;}"
            )
            btn.clicked.connect(lambda checked, t=template: self._prefill(t))
            qb_row.addWidget(btn)
        qb_row.addStretch()
        self._quick_btns_frame.setVisible(False)
        content_layout.addWidget(self._quick_btns_frame)

        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        self._input = self._history_line_edit_class()()
        self._input.setPlaceholderText(
            tr(
                "prompt.placeholder",
                self._language,
                default='Introduce un comando... p.ej. "recibí 500 de salario" o "gasté 30 en comestibles"',
            )
        )
        self._input.setStyleSheet(
            "QLineEdit{border:1px solid palette(mid);border-radius:4px;padding:6px 10px;font-size:13px;}"
        )
        self._input.returnPressed.connect(self._send)
        input_row.addWidget(self._mode_switch)
        input_row.addWidget(self._input, 1)
        self._send_btn = QPushButton(tr("prompt.send", self._language, default="Enviar"))
        self._send_btn.setFixedWidth(80)
        self._send_btn.setStyleSheet(
            "QPushButton{border:1px solid palette(mid);border-radius:4px;padding:6px;font-size:13px;}"
            "QPushButton:hover{border:1px solid palette(text);}"
            "QPushButton:disabled{color:palette(mid);}"
        )
        self._send_btn.clicked.connect(self._send)
        input_row.addWidget(self._send_btn)
        content_layout.addLayout(input_row)
        layout.addWidget(self._chat_content)
        return panel
