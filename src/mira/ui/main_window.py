# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Main window for MIRA Personal Finance Assistant."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from sqlite3 import Error
from typing import cast
import webbrowser

from PySide6.QtCore import QThread, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from mira import __version__ as APP_VERSION
from mira.app import ApplicationController, ModelDownloadService
from mira.app.view_services import (
    AccountsViewService,
    CategoriesViewService,
    MiraAnalysisMessageBuilder,
    MiraAnalysisService,
    RecurringViewService,
    ReportsViewService,
    SavingsGoalsViewService,
    SettingsViewService,
    TagsViewService,
    TransactionsViewService,
)
from mira.ai.executor import ActionResult
from mira.ai.pipeline import Pipeline
from mira.db.database import Database
from mira.error_policy import describe as describe_error
from mira.number_format import validate_number_format_config
from mira.services import ModelLifecycle
from mira.ui.dialogs import InitialSetupDialog
from mira.ui.dialogs.financial.compound_interest import (
    CompoundInterestDialog as _CompoundInterestDialog,
)
from mira.ui.dialogs.financial.goal_simulator import (
    GoalScenarioDialog as _GoalScenarioDialog,
)
from mira.ui.dialogs.financial.loan_amortization import (
    LoanAmortizationDialog as _LoanAmortizationDialog,
)
from mira.ui.i18n import normalize_language, tr
from mira.ui.menu_builder import MenuBuilder
from mira.ui.coordinators import ChatState
from mira.ui.coordinators.command_coordinator import CommandCoordinator
from mira.ui.coordinators.model_download_coordinator import ModelDownloadCoordinator
from mira.ui.coordinators.model_download_flow import ModelDownloadFlow, ModelDownloadSession
from mira.ui.coordinators.navigation_coordinator import NavigationCoordinator
from mira.ui.notification_service import NotificationService
from mira.ui.notifications import show_user_message
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SIDEBAR_WIDTH = 190
_FOOTER_HEIGHT = 180  # collapsed prompt drawer
_LOGO_BG = "#0F2A40"
_SIDEBAR_BG = "#252526"
_FOOTER_BG = "#1A1A1A"
_APP_VERSION_FALLBACK = APP_VERSION
_APP_LICENSE = "GPL-3.0-or-later"
_DOCS_URL = "https://mira.bmogroup.solutions"
_INITIAL_SETUP_PREVIEW_THEME = "light_blue.xml"


# ---------------------------------------------------------------------------
# Command-history-aware QLineEdit
# ---------------------------------------------------------------------------


class _HistoryLineEdit(QLineEdit):
    """QLineEdit that navigates command history with ↑ / ↓ keys."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history: list[str] = []
        self._cursor: int = -1  # -1 = at current (empty) input
        self._draft: str = ""  # saved draft when navigating up

    def push(self, command: str) -> None:
        """Record a submitted command into history."""
        if command and (not self._history or self._history[-1] != command):
            self._history.append(command)
        self._cursor = -1
        self._draft = ""

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Up:
            if not self._history:
                return
            if self._cursor == -1:
                self._draft = self.text()
                self._cursor = len(self._history) - 1
            elif self._cursor > 0:
                self._cursor -= 1
            self.setText(self._history[self._cursor])
            self.end(False)
        elif event.key() == Qt.Key.Key_Down:
            if self._cursor == -1:
                return
            self._cursor += 1
            if self._cursor >= len(self._history):
                self._cursor = -1
                self.setText(self._draft)
            else:
                self.setText(self._history[self._cursor])
            self.end(False)
        else:
            super().keyPressEvent(event)


class MainWindow(QMainWindow):
    """MIRA main application window."""

    VIEW_DASHBOARD = 0
    VIEW_TRANSACTIONS = 1
    VIEW_ACCOUNTS = 2
    VIEW_BUDGET = 3
    VIEW_CATEGORIES = 4
    VIEW_TAGS = 5
    VIEW_RECURRING = 6
    VIEW_REPORTS = 7
    VIEW_MIRA_ANALYSIS = 8
    VIEW_GOALS = 9
    VIEW_SETTINGS = 10

    def __init__(
        self,
        db: Database,
        pipeline: Pipeline,
        startup_alert: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._pipeline = pipeline
        self._worker: QThread | None = None
        self._download_worker: QThread | None = None
        self._act_sidebar: QAction | None = None
        self._act_prompt: QAction | None = None
        self._command_coordinator = CommandCoordinator(self._pipeline)
        self._model_download_coordinator = ModelDownloadCoordinator()
        self._controller = ApplicationController(self._db, self._pipeline)
        self._model_lifecycle = ModelLifecycle(self._db, self._pipeline)
        self._model_download_service = ModelDownloadService(self._db, self._model_lifecycle)
        self._language = normalize_language(self._db.setting.get("language"))
        self._theme = self._normalize_theme(self._db.setting.get("theme"))
        self._startup_alert = startup_alert
        self._active_model_path = getattr(self._pipeline, "_model_path", None)
        self._reload_progress: QProgressDialog | None = None
        self._download_session: ModelDownloadSession | None = None
        self._chat_state = ChatState()
        self._startup_cancelled = False

        self.setWindowTitle(tr("app.title", self._language, default="MIRA - Personal Finance Assistant"))
        self.resize(1180, 720)
        self._apply_theme(self._theme)
        self._build_menu()
        self._build_ui()
        self._notification_service = NotificationService(self)
        self._model_download_flow = ModelDownloadFlow(
            parent=self,
            language=self._language,
            db=self._db,
            download_coordinator=self._model_download_coordinator,
            download_service=self._model_download_service,
            notification_service=self._notification_service,
            apply_model_lifecycle_state=self._apply_download_model_lifecycle_state,
            refresh_settings_view=self._view_settings.refresh,
            get_active_runtime_path=lambda: self._active_model_path,
            get_interaction_mode=lambda: self._db.setting.get("llm_interaction_mode") or "assistant",
            get_username=lambda: self._db.setting.get("username")
            or tr("settings.saved_default_user", self._language, default="User"),
            set_status=self._set_status,
        )
        self._refresh_all()
        self._sync_engine_info()
        self._run_initial_setup_if_needed()
        if self._startup_alert:
            self.notify_user_message(
                tr("app.name", self._language, default="MIRA"),
                self._startup_alert,
                level="warning",
            )
        QTimer.singleShot(2000, self._show_daily_contextual_message_if_needed)

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        MenuBuilder().build(self)

    # ------------------------------------------------------------------
    # Central widget layout
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root_widget = self._build_central_widget()
        self.setCentralWidget(root_widget)
        self._build_status_bar()

    def _build_central_widget(self) -> QWidget:
        root_widget = QWidget()
        root_layout = QVBoxLayout(root_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        content_row = self._build_content_row()
        root_layout.addLayout(content_row, 1)

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

        # Vertical separator between sidebar and main area
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

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------

    def _make_sidebar(self) -> QFrame:
        panel = QFrame()
        panel.setFixedWidth(_SIDEBAR_WIDTH)
        panel.setStyleSheet("")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # App name header
        header = QLabel("MIRA")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header.setStyleSheet("padding:14px 0;")
        layout.addWidget(header)

        # Navigation list
        self._nav_list = QListWidget()
        self._nav_list.setStyleSheet("""
            QListWidget {{
                background:palette(window);
                border:none;
                color:palette(text);
                font-size:13px;
                outline:none;
            }}
            QListWidget::item {{
                padding:10px 16px;
                border-left:3px solid transparent;
            }}
            QListWidget::item:selected {{
                background:palette(highlight);
                color:palette(highlighted-text);
                border-left:3px solid palette(text);
            }}
            QListWidget::item:hover:!selected {{
                background:palette(button);
                color:palette(button-text);
            }}
            """)
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
            item = QListWidgetItem(label)
            self._nav_list.addItem(item)

        self._nav_list.setCurrentRow(0)
        self._nav_list.currentRowChanged.connect(self._navigate)
        layout.addWidget(self._nav_list, 1)

        return panel

    # ------------------------------------------------------------------
    # Stacked main area
    # ------------------------------------------------------------------

    def _make_stack(self) -> QStackedWidget:
        stack = QStackedWidget()
        stack.setStyleSheet("")

        accounts_service = AccountsViewService(self._db)
        transactions_service = TransactionsViewService(self._db)
        categories_service = CategoriesViewService(self._db)
        tags_service = TagsViewService(self._db)
        recurring_service = RecurringViewService(self._db)
        reports_service = ReportsViewService(self._db)
        mira_analysis_service = MiraAnalysisService(self._db)
        mira_analysis_builder = MiraAnalysisMessageBuilder(self._db)
        goals_service = SavingsGoalsViewService(self._db)
        settings_service = SettingsViewService(self._db)

        self._view_dashboard = DashboardView(self._db)
        self._view_transactions = TransactionsView(self._db, service=transactions_service)
        self._view_accounts = AccountsView(self._db, service=accounts_service)
        self._view_budget = BudgetView(self._db)
        self._view_categories = CategoriesView(self._db, service=categories_service)
        self._view_tags = TagsView(self._db, service=tags_service)
        self._view_recurring = RecurringView(self._db, service=recurring_service)
        self._view_reports = ReportsView(self._db, service=reports_service)
        self._view_reports.assistant_message_requested.connect(self._append_chat_assistant)
        self._view_mira_analysis = MiraAnalysisView(
            self._db,
            service=mira_analysis_service,
            message_builder=mira_analysis_builder,
        )
        self._view_mira_analysis.assistant_message_requested.connect(self._append_chat_assistant)
        self._view_goals = SavingsGoalsView(self._db, service=goals_service)
        self._view_settings = SettingsView(self._db, service=settings_service)
        self._view_settings.settings_saved.connect(self._on_settings_saved)
        self._view_settings.language_changed.connect(self._on_language_changed)
        self._view_settings.theme_changed.connect(self._on_theme_changed)
        self._view_settings.download_default_model_requested.connect(self._on_download_default_model)

        for view in [
            self._view_dashboard,  # 0
            self._view_transactions,  # 1
            self._view_accounts,  # 2
            self._view_budget,  # 3
            self._view_categories,  # 4
            self._view_tags,  # 5
            self._view_recurring,  # 6
            self._view_reports,  # 7
            self._view_mira_analysis,  # 8
            self._view_goals,  # 9
            self._view_settings,  # 10
        ]:
            stack.addWidget(view)

        return stack

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------

    def _make_footer(self) -> QFrame:
        footer = QFrame()
        footer.setStyleSheet("")
        footer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(footer)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # ---- Logo / status panel (left, aligns with sidebar) ----
        self._logo_panel = self._make_logo_panel()
        row.addWidget(self._logo_panel)

        vsep = QFrame()
        vsep.setFrameShape(QFrame.Shape.VLine)
        vsep.setStyleSheet("color:palette(mid);")
        row.addWidget(vsep)

        # ---- Prompt panel (right, aligns with main area) ----
        row.addWidget(self._make_prompt_panel(), 1)

        return footer

    def _make_logo_panel(self) -> QFrame:
        panel = QFrame()
        panel.setFixedWidth(_SIDEBAR_WIDTH)
        panel.setStyleSheet("")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        avatar = QLabel("\U0001f916")
        avatar.setFont(QFont("Arial", 28))
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

        # --- Header bar (always visible, acts as collapse toggle) ---
        header = QFrame()
        header.setStyleSheet("border-top:1px solid palette(mid);border-bottom:1px solid palette(mid);")
        header.setFixedHeight(34)
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(12, 0, 8, 0)
        header_row.setSpacing(6)

        chat_icon = QLabel("💬")
        chat_icon.setStyleSheet("background:transparent;font-size:13px;border:none;")
        header_row.addWidget(chat_icon)

        chat_title = QLabel(tr("chat.panel.title", self._language, default="MIRA Chat"))
        chat_title.setStyleSheet("background:transparent;font-size:12px;font-weight:bold;border:none;")
        header_row.addWidget(chat_title)

        self._mode_switch = QComboBox()
        self._mode_switch.setStyleSheet(
            "QComboBox{border:1px solid palette(mid);" "border-radius:3px;padding:2px 6px;font-size:11px;}"
        )
        self._mode_switch.addItem(
            tr("settings.mode.assistant", self._language, default="Assistant mode"),
            "assistant",
        )
        self._mode_switch.addItem(tr("settings.mode.chat", self._language, default="Chat mode"), "chat")
        saved_mode = self._db.setting.get("llm_interaction_mode") or "assistant"
        mode_idx = self._mode_switch.findData(saved_mode)
        if mode_idx >= 0:
            self._mode_switch.setCurrentIndex(mode_idx)
        self._mode_switch.currentIndexChanged.connect(self._on_mode_changed)
        self._mode_switch.setVisible(self._model_lifecycle.sync_engine_info(self._active_model_path).mode_visible)
        header_row.addWidget(self._mode_switch)
        header_row.addStretch()

        self._chat_toggle_btn = QPushButton("▼")
        self._chat_toggle_btn.setFixedSize(26, 26)
        self._chat_toggle_btn.setStyleSheet("QPushButton{background:transparent;border:none;font-size:11px;}")
        self._chat_toggle_btn.setToolTip(
            tr(
                "chat.panel.toggle",
                self._language,
                default="Collapse / Expand chat panel",
            )
        )
        self._chat_toggle_btn.clicked.connect(self._toggle_chat_content)
        header_row.addWidget(self._chat_toggle_btn)
        layout.addWidget(header)

        # --- Collapsible content area ---
        self._chat_content = QFrame()
        self._chat_content.setStyleSheet("")

        content_layout = QVBoxLayout(self._chat_content)
        content_layout.setContentsMargins(10, 8, 10, 8)
        content_layout.setSpacing(6)

        # Response drawer
        self._response_browser = QTextBrowser()
        self._response_browser.setStyleSheet(
            "QTextBrowser{border:1px solid palette(mid);" "border-radius:4px;font-size:12px;padding:6px;}"
        )
        self._response_browser.setMaximumHeight(130)
        self._response_browser.setPlaceholderText(
            tr(
                "prompt.response_placeholder",
                self._language,
                default="La respuesta aparecerá aquí...",
            )
        )
        content_layout.addWidget(self._response_browser)

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

        content_layout.addLayout(nav_row)
        self._update_chat_navigation()

        # Quick action buttons (shown when "none" action)
        self._quick_btns_frame = QFrame()
        self._quick_btns_frame.setStyleSheet("background:transparent;")
        qb_row = QHBoxLayout(self._quick_btns_frame)
        qb_row.setContentsMargins(0, 0, 0, 0)
        qb_row.setSpacing(6)

        for label, template in [
            (
                tr("quick.add_income", self._language, default="➕ Add Income"),
                "received 0 from ",
            ),
            (
                tr("quick.add_expense", self._language, default="➖ Add Expense"),
                "spent 0 on ",
            ),
            (tr("quick.report", self._language, default="📊 View Report"), "report"),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(
                "QPushButton{border:1px solid palette(mid);" "border-radius:4px;padding:4px 10px;font-size:11px;}"
            )
            btn.clicked.connect(lambda checked, t=template: self._prefill(t))
            qb_row.addWidget(btn)

        qb_row.addStretch()
        self._quick_btns_frame.setVisible(False)
        content_layout.addWidget(self._quick_btns_frame)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self._input = _HistoryLineEdit()
        self._input.setPlaceholderText(
            tr(
                "prompt.placeholder",
                self._language,
                default='Introduce un comando... p.ej. "recibí 500 de salario" o "gasté 30 en comestibles"',
            )
        )
        self._input.setStyleSheet(
            "QLineEdit{border:1px solid palette(mid);" "border-radius:4px;padding:6px 10px;font-size:13px;}"
        )
        self._input.returnPressed.connect(self._send)
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

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate(self, index: int) -> None:
        if hasattr(self, "_navigation"):
            self._navigation.go(index)
            return

        self._stack.setCurrentIndex(index)
        if self._nav_list.currentRow() != index:
            self._nav_list.blockSignals(True)
            self._nav_list.setCurrentRow(index)
            self._nav_list.blockSignals(False)
        view = self._stack.currentWidget()
        if hasattr(view, "refresh"):
            view.refresh()

    # ------------------------------------------------------------------
    # Prompt interaction
    # ------------------------------------------------------------------

    def _send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return

        self._input.push(text)
        self._input.clear()
        self._before_command()
        self._start_command(text, self._selected_interaction_mode())

    def _selected_interaction_mode(self) -> str:
        if hasattr(self, "_mode_switch") and self._mode_switch.isVisible():
            return self._mode_switch.currentData() or "assistant"
        return "assistant"

    def _before_command(self) -> None:
        self._set_interaction_enabled(False)
        self._quick_btns_frame.setVisible(False)
        self._set_status(tr("status.processing", self._language, default="⧗  Thinking..."))

    def _start_command(self, text: str, mode: str) -> None:
        self._worker = self._command_coordinator.execute(
            text=text,
            mode=mode,
            on_success=self._on_result,
            on_error=self._on_error,
        )

    def _append_chat_assistant(self, text: str, title: str | None = None) -> None:
        shown_title = title or tr("chat.assistant.title", self._language, default="MIRA Assistant")
        block = f"{shown_title}\n\n{text}".strip()
        started_new_batch = self._chat_state.append_block(block)
        if started_new_batch:
            QTimer.singleShot(0, self._clear_pending_chat_batch)
        self._show_chat_message()

    def notify_user_message(self, *args: object, level: str = "info") -> None:
        widget: QWidget | None
        if len(args) == 3 and isinstance(args[0], QWidget):
            widget = args[0]
            title = args[1]
            message = args[2]
        elif len(args) == 2:
            widget = None
            title = args[0]
            message = args[1]
        else:
            raise TypeError("notify_user_message expects (title, message) or (widget, title, message)")
        service = self._notification_handler()
        if level == "error":
            service.error(str(title), str(message), widget=widget)
            return
        if level == "warning":
            service.warning(str(title), str(message), widget=widget)
            return
        service.info(str(title), str(message), widget=widget)

    def _notification_handler(self) -> NotificationService:
        service = getattr(self, "_notification_service", None)
        if service is None:
            service = NotificationService(self)
            self._notification_service = service
        return service

    def notify_user_info(self, *args: object) -> None:
        self.notify_user_message(*args, level="info")

    def notify_user_warning(self, *args: object) -> None:
        self.notify_user_message(*args, level="warning")

    def notify_user_error(self, *args: object) -> None:
        self.notify_user_message(*args, level="error")

    def _notify_exception(self, title: str, exc: Exception, *, prefix: str | None = None) -> None:
        descriptor = describe_error(exc)
        message = descriptor.message if prefix is None else f"{prefix}\n{descriptor.message}"
        self.notify_user_message(self, title, message, level=descriptor.level)

    def _clear_pending_chat_batch(self) -> None:
        self._chat_state.reset_pending_batch()

    def _show_chat_message(self) -> None:
        current_message = self._chat_state.current_message()
        if current_message is None:
            self._response_browser.clear()
            self._update_chat_navigation()
            return

        self._response_browser.setPlainText(current_message)
        self._update_chat_navigation()

    def _update_chat_navigation(self) -> None:
        total = self._chat_state.message_count
        current = self._chat_state.current_index + 1 if self._chat_state.current_index >= 0 else 0
        self._chat_counter_lbl.setText(f"{current} / {total}")
        self._chat_clear_btn.setEnabled(total > 0)
        self._chat_prev_btn.setEnabled(self._chat_state.can_prev)
        self._chat_next_btn.setEnabled(self._chat_state.can_next)

    def _clear_chat_messages(self) -> None:
        self._chat_state.clear()
        self._show_chat_message()

    def _show_previous_chat_message(self) -> None:
        self._chat_state.prev()
        self._show_chat_message()

    def _show_next_chat_message(self) -> None:
        self._chat_state.next()
        self._show_chat_message()

    def _on_result(self, result: ActionResult) -> None:
        directive = self._controller.handle_result(result)
        self._after_command_success(directive)

    def _after_command_success(self, directive) -> None:
        if directive.chat_message:
            self._append_chat_assistant(directive.chat_message)
        self._quick_btns_frame.setVisible(directive.show_quick_actions)

        if directive.kind == "show_report" and directive.report_payload is not None:
            self._view_reports.set_report_payload(directive.report_payload)
        elif directive.kind == "run_analysis":
            set_requested_period = getattr(self._view_mira_analysis, "set_requested_period", None)
            if callable(set_requested_period):
                set_requested_period(directive.analysis_period)
            self._navigate(MainWindow.VIEW_MIRA_ANALYSIS)
            self._view_mira_analysis.run_report(emit_to_assistant=True)

        if directive.refresh_all:
            self._refresh_all()
        self._finish_command()

    def _finish_command(self) -> None:
        self._set_interaction_enabled(True)
        self._input.setFocus()
        self._set_status(tr("status.ready", self._language, default="●  Ready"))

    def _on_error(self, error: str) -> None:
        self._after_command_error(error)

    def _after_command_error(self, error: str) -> None:
        self.notify_user_error(
            self,
            tr("app.name", self._language, default="MIRA"),
            str(error),
        )
        self._finish_command()

    def _prefill(self, template: str) -> None:
        """Pre-fill the input field with a quick-action template."""
        self._input.setText(template)
        self._input.setFocus()
        self._input.end(False)
        self._quick_btns_frame.setVisible(False)

    def _set_status(self, text: str, color: str | None = None) -> None:
        self._status_label.setText(text)
        self._status_label.setStyleSheet("background:transparent;font-size:10px;")

    # ------------------------------------------------------------------
    # View / toggle actions
    # ------------------------------------------------------------------

    def _toggle_sidebar(self) -> None:
        if self._act_sidebar is None:
            return
        visible = self._act_sidebar.isChecked()
        self._sidebar_panel.setVisible(visible)
        self._logo_panel.setVisible(visible)

    def _toggle_prompt_panel(self) -> None:
        if self._act_prompt is None:
            return
        visible = self._act_prompt.isChecked()
        self._footer.setVisible(visible)

    def _toggle_chat_content(self) -> None:
        """Collapse or expand the MIRA Chat content area."""
        visible = not self._chat_content.isVisible()
        self._chat_content.setVisible(visible)
        self._chat_toggle_btn.setText("▼" if visible else "▲")

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh_all(self) -> None:
        """Refresh the currently visible view and the dashboard cards."""
        self._view_dashboard.refresh()
        view = self._stack.currentWidget()
        if hasattr(view, "refresh") and view is not self._view_dashboard:
            view.refresh()

    def _show_daily_contextual_message_if_needed(self) -> None:
        payload = self._db.feedback.pop_daily_contextual_message()
        if payload is None:
            return
        self.notify_user_message(
            tr("mira.analysis.advisor", self._language, default="MIRA Advisor"),
            str(payload.get("message") or ""),
        )

    # ------------------------------------------------------------------
    # Menu navigation shortcuts
    # ------------------------------------------------------------------

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

    def _run_initial_setup_if_needed(self) -> None:
        completed = self._db.setting.get("onboarding_completed")
        if completed == "1":
            return

        # The onboarding wizard previews the lighter blue theme for readability
        # before the user chooses their final theme preference.
        self._apply_theme(self._normalize_theme(_INITIAL_SETUP_PREVIEW_THEME))
        dlg = InitialSetupDialog(self._db, self)
        if dlg.exec() == InitialSetupDialog.DialogCode.Accepted:
            data = dlg.get_data()
            language = normalize_language(data.get("language"))
            try:
                number_format = validate_number_format_config(data.get("thousands_sep"), data.get("decimal_sep"))
            except ValueError:
                show_user_message(
                    cast(QWidget | None, self),
                    tr("settings.title", language, default="Settings"),
                    tr(
                        "settings.validation.number_separators_distinct",
                        language,
                        default="Thousands and decimal separators must be different.",
                    ),
                    level="warning",
                )
                self._startup_cancelled = True
                return
            theme = self._normalize_theme(data.get("theme"))
            username = str(
                data.get("username")
                or tr(
                    "settings.saved_default_user",
                    language,
                    default="Usuario" if language == "es" else "User",
                )
            ).strip()
            self._db.setting.set("language", language)
            self._db.setting.set("theme", theme)
            self._db.setting.set("username", username)
            self._db.setting.set("default_currency", str(data.get("default_currency") or "USD").upper())
            self._db.setting.set("number_decimal_separator", number_format.decimal_sep)
            self._db.setting.set("number_thousands_separator", number_format.thousands_sep)
            self._db.setting.seed_initial_data(
                include_default_categories=True,
                account_names=data.get("account_names"),
                account_specs=data.get("account_specs"),
                language=language,
            )
            self._db.setting.set("onboarding_completed", "1")
            self._language = language
            self._theme = theme
            self._apply_theme(theme)
            self._refresh_all()
            if hasattr(self, "_view_settings"):
                self._view_settings.refresh()
            if hasattr(self, "_status_bar"):
                self._status_bar.showMessage(
                    tr(
                        "status.welcome",
                        self._language,
                        params={"username": username},
                        default=f"Welcome, {username}\u2003|\u2003100% offline \u2013 no data leaves your device.",
                    )
                )
            self.notify_user_message(
                "MIRA",
                (
                    "¡Bienvenido a MIRA!\nConfiguración inicial completada."
                    if language == "es"
                    else "Welcome to MIRA!\nInitial setup completed."
                ),
            )
        else:
            self._startup_cancelled = True

    def _on_download_default_model(self) -> None:
        session = self._model_download_flow.start_default_download()
        self._download_session = session
        self._download_worker = cast(QThread, session.handle.worker)

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------

    def _on_import_csv(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("menu.file.import_csv", self._language, default="Import CSV..."),
            "",
            tr(
                "file.filter.csv_all",
                self._language,
                default="CSV Files (*.csv);;All Files (*)",
            ),
        )
        if not path:
            return
        try:
            imported, errors = self._db.io.import_transactions_csv(path)
            self._refresh_all()
            self.notify_user_info(
                self,
                tr("import.complete.title", self._language, default="Import Complete"),
                tr(
                    "import.complete.body",
                    self._language,
                    default="Imported: {imported} transaction(s)\nSkipped (errors): {errors}",
                    params={"imported": imported, "errors": errors},
                ),
            )
        except (
            csv.Error,
            OSError,
            RuntimeError,
            TypeError,
            UnicodeError,
            ValueError,
            Error,
        ) as exc:
            self._notify_exception(
                tr("import.error.title", self._language, default="Import Error"),
                exc,
                prefix=tr("import.error.body", self._language, default="Failed to import CSV:"),
            )

    def _on_export_csv(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("menu.file.export_csv", self._language, default="Export CSV..."),
            "transactions.csv",
            tr(
                "file.filter.csv_all",
                self._language,
                default="CSV Files (*.csv);;All Files (*)",
            ),
        )
        if not path:
            return
        try:
            count = self._db.io.export_transactions_csv(path)
            self.notify_user_info(
                self,
                tr("export.complete.title", self._language, default="Export Complete"),
                tr(
                    "export.complete.body",
                    self._language,
                    default="Exported {count} transaction(s) to:\n{path}",
                    params={"count": count, "path": path},
                ),
            )
        except Exception as exc:  # noqa: BLE001
            self._notify_exception(
                tr("export.error.title", self._language, default="Export Error"),
                exc,
                prefix=tr("export.error.body", self._language, default="Failed to export CSV:"),
            )

    def _on_backup(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        default_name = f"mira-backup-{date.today().isoformat()}.db"
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("dialog.backup.title", self._language, default="Backup Database"),
            default_name,
            "SQLite DB (*.db);;All Files (*)",
        )
        if not path:
            return

        try:
            backup_path = self._db.backup.create(path)
            self.notify_user_info(
                self,
                tr(
                    "dialog.backup.success.title",
                    self._language,
                    default="Backup completed",
                ),
                tr(
                    "dialog.backup.success.body",
                    self._language,
                    default="Backup created at:\n{path}",
                    params={"path": backup_path},
                ),
            )
        except Exception as exc:  # noqa: BLE001
            self._notify_exception(
                tr("dialog.backup.error.title", self._language, default="Backup error"),
                exc,
                prefix=tr(
                    "dialog.backup.error.body",
                    self._language,
                    default="Could not create backup:",
                ),
            )

    def _on_restore(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dialog.restore.title", self._language, default="Restore Database"),
            "",
            "SQLite DB (*.db);;All Files (*)",
        )
        if not path:
            return

        reply = QMessageBox.question(
            self,
            tr(
                "dialog.restore.confirm.title",
                self._language,
                default="Confirm restore",
            ),
            tr(
                "dialog.restore.confirm.body",
                self._language,
                default="This action will replace current data with the selected backup. Continue?",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            restored = self._db.backup.restore(path)
            self._refresh_all()
            success_key = "dialog.restore.success.body"
            success_default = "Database restored from:\n{path}"
            success_params = {"path": restored.restored_from}
            if restored.migration_applied:
                success_key = "dialog.restore.success.body_migrated"
                success_default = "Database restored from:\n{path}\nSchema upgraded: v{from_version} -> v{to_version}"
                success_params = {
                    "path": restored.restored_from,
                    "from_version": restored.source_schema_version,
                    "to_version": restored.target_schema_version,
                }
            self.notify_user_info(
                self,
                tr(
                    "dialog.restore.success.title",
                    self._language,
                    default="Restore completed",
                ),
                tr(
                    success_key,
                    self._language,
                    default=success_default,
                    params=success_params,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            self._notify_exception(
                tr(
                    "dialog.restore.error.title",
                    self._language,
                    default="Restore error",
                ),
                exc,
                prefix=tr(
                    "dialog.restore.error.body",
                    self._language,
                    default="Could not restore:",
                ),
            )

    def _application_version(self) -> str:
        app = QApplication.instance()
        if app is None:
            return _APP_VERSION_FALLBACK
        return app.applicationVersion() or _APP_VERSION_FALLBACK

    def _resolve_ui_icon_path(self, *candidates: str) -> Path | None:
        icons_dir = Path(__file__).resolve().parent / "icons"
        for name in candidates:
            candidate = icons_dir / name
            if candidate.is_file():
                return candidate
        return None

    def _build_about_logo_label(self, image_path: Path | None, *, max_height: int) -> QLabel:
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumHeight(max_height)
        label.setStyleSheet("background:transparent;")
        if image_path is None:
            return label

        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            return label

        label.setPixmap(
            pixmap.scaledToHeight(
                max_height,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        return label

    def _on_about(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("dialog.about.title", self._language, default="MIRA Information"))
        dialog.setModal(True)
        dialog.setMinimumWidth(480)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        mira_logo = self._build_about_logo_label(
            self._resolve_ui_icon_path("256x256.png", "mira.ico", "scalable.svg"),
            max_height=88,
        )
        layout.addWidget(mira_logo)

        title = QLabel("<b>MIRA</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:22px;")
        layout.addWidget(title)

        subtitle = QLabel(
            tr(
                "dialog.about.subtitle",
                self._language,
                default="Manage Income & Resources Allocations",
            )
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size:13px;color:#C7D0DA;")
        layout.addWidget(subtitle)

        version_label = QLabel(
            tr(
                "dialog.about.version",
                self._language,
                default="Version: {version}",
                params={"version": self._application_version()},
            )
        )
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)

        license_label = QLabel(
            tr(
                "dialog.about.license",
                self._language,
                default="License: {license}",
                params={"license": _APP_LICENSE},
            )
        )
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(license_label)

        details = QLabel(
            tr(
                "dialog.about.details",
                self._language,
                default="100% offline • No telemetry • SQLite + PySide6",
            )
        )
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details.setWordWrap(True)
        details.setStyleSheet("color:#9FB3C8;")
        layout.addWidget(details)

        company_caption = QLabel(
            tr(
                "dialog.about.company",
                self._language,
                default="Developed by BMO Soluciones, S.A.",
            )
        )
        company_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        company_caption.setWordWrap(True)
        company_caption.setStyleSheet("font-size:12px;color:#C7D0DA;padding-top:4px;")
        layout.addWidget(company_caption)

        bmo_logo = self._build_about_logo_label(
            self._resolve_ui_icon_path("BMOLogoSmall.png"),
            max_height=48,
        )
        layout.addWidget(bmo_logo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)

        dialog.exec()

    def _menu_open_compound_interest(self) -> None:
        currency = self._db.setting.get("default_currency") or "USD"
        dialog = _CompoundInterestDialog(self._language, currency, self)
        dialog.exec()

    def _menu_open_loan_amortization(self) -> None:
        currency = self._db.setting.get("default_currency") or "USD"
        dialog = _LoanAmortizationDialog(self._language, currency, self)
        dialog.exec()

    def _menu_open_goal_simulator(self) -> None:
        currency = self._db.setting.get("default_currency") or "USD"
        dialog = _GoalScenarioDialog(self._language, currency, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.should_open_goal_form:
            self._navigate(MainWindow.VIEW_GOALS)
            self._view_goals.open_add_dialog(prefill=dialog.goal_prefill)

    def _on_open_documentation(self) -> None:
        webbrowser.open(_DOCS_URL)

    def _on_diagnostics(self) -> None:
        parser_type = type(self._pipeline.engine).__name__
        chat_engine = getattr(self._pipeline, "chat_engine", None)
        chat_type = type(chat_engine).__name__ if chat_engine is not None else "Disabled"
        self.notify_user_info(
            self,
            "AI Diagnostics",
            f"Assistant parser: <b>{parser_type}</b><br>"
            f"Chat engine: <b>{chat_type}</b><br><br>"
            "Assistant mode always uses the deterministic parser.<br>"
            "Optional local chat mode can be enabled with:<br>"
            "<code>mira --model /path/to/model.gguf</code>",
        )

    def _set_mode_switch_value(self, mode: str) -> None:
        if not hasattr(self, "_mode_switch"):
            return
        idx = self._mode_switch.findData(mode)
        if idx < 0 or self._mode_switch.currentIndex() == idx:
            return
        self._mode_switch.blockSignals(True)
        self._mode_switch.setCurrentIndex(idx)
        self._mode_switch.blockSignals(False)

    def _current_mode_label(self) -> str:
        mode = self._db.setting.get("llm_interaction_mode") or "assistant"
        if mode == "assistant":
            return tr("settings.mode.assistant", self._language, default="Assistant mode")
        return tr("settings.mode.chat", self._language, default="Chat mode")

    def _set_interaction_enabled(self, enabled: bool) -> None:
        self._input.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)
        if hasattr(self, "_mode_switch"):
            self._mode_switch.setEnabled(enabled)

    def _show_reload_progress(self, mode_label: str) -> None:
        if self._reload_progress is not None:
            self._reload_progress.close()
        progress = QProgressDialog(
            tr(
                "status.reloading_model",
                self._language,
                default="Updating model for mode {mode}...",
                params={"mode": mode_label},
            ),
            "",
            0,
            0,
            self,
        )
        progress.setWindowTitle("MIRA")
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()
        self._reload_progress = progress
        QApplication.processEvents()

    def _hide_reload_progress(self) -> None:
        if self._reload_progress is None:
            return
        self._reload_progress.close()
        self._reload_progress = None

    def _on_settings_saved(self, username: str) -> None:
        mode_label = self._current_mode_label()
        self._set_status(
            tr(
                "status.reloading_model",
                self._language,
                default="Updating model for mode {mode}...",
                params={"mode": mode_label},
            )
        )
        self._status_bar.showMessage(
            tr(
                "status.welcome",
                self._language,
                params={"username": username},
                default=f"Welcome, {username} | 100% offline - no data leaves your device.",
            )
        )

        self._set_interaction_enabled(False)
        self._show_reload_progress(mode_label)
        try:
            state = self._model_lifecycle.reload_selected_model(
                self._active_model_path,
                self._db.setting.get("llm_interaction_mode") or "assistant",
            )
            self._apply_model_lifecycle_state(state, show_mode_warning=True)
        finally:
            self._hide_reload_progress()
            self._set_interaction_enabled(True)
            self._set_status(tr("status.ready", self._language, default="●  Ready"))

    def _on_mode_changed(self) -> None:
        mode = self._mode_switch.currentData() or "assistant"
        self._db.setting.set("llm_interaction_mode", mode)
        self._apply_model_lifecycle_state(
            self._model_lifecycle.sync_engine_info(self._active_model_path),
            show_mode_warning=True,
        )

    def _sync_engine_info(self) -> None:
        self._apply_model_lifecycle_state(
            self._model_lifecycle.sync_engine_info(self._active_model_path),
            show_mode_warning=False,
        )

    def _apply_model_lifecycle_state(self, state, *, show_mode_warning: bool) -> None:
        self._active_model_path = state.active_model_path
        self._view_settings.set_engine_info(state.engine_info)
        if hasattr(self, "_mode_switch"):
            self._mode_switch.setVisible(state.mode_visible)
            if state.forced_mode is not None:
                self._set_mode_switch_value(state.forced_mode)
        if state.status_message:
            self._status_bar.showMessage(state.status_message, 3500)
        if show_mode_warning and state.mode_warning:
            self._status_bar.showMessage(state.mode_warning, 4500)

    def _apply_download_model_lifecycle_state(self, state) -> None:
        self._apply_model_lifecycle_state(state, show_mode_warning=True)

    def _on_language_changed(self, language: str) -> None:
        self._language = normalize_language(language)
        self._build_menu()
        self.notify_user_info(
            self,
            "MIRA",
            tr(
                "settings.saved.body",
                self._language,
                default="Configuration was saved successfully.",
            ),
        )

    def _on_theme_changed(self, theme: str) -> None:
        self._theme = self._normalize_theme(theme)
        self._apply_theme(self._theme)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._pipeline.shutdown()
        super().closeEvent(event)

    @staticmethod
    def _normalize_theme(theme: str | None) -> str:
        valid = set(MainWindow._qt_material_themes())
        return theme if theme in valid else "dark_teal.xml"

    @staticmethod
    def _qt_material_themes() -> list[str]:
        """Return all available qt-material theme names."""
        import qt_material  # noqa: PLC0415

        return qt_material.list_themes()

    @staticmethod
    def _apply_theme(theme: str) -> None:
        app = QApplication.instance()
        if app is None:
            return

        import qt_material  # noqa: PLC0415

        qt_material.apply_stylesheet(app, theme=theme)
