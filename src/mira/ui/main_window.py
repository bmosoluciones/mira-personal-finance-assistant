# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Main window for MIRA Personal Finance Assistant."""

from __future__ import annotations

try:
    from PySide6.QtCore import QThread, Qt, QTimer
    from PySide6.QtGui import QAction, QKeyEvent
    from PySide6.QtWidgets import (  # noqa: F401
        QDialog,  # noqa: F401
        QLineEdit,
        QMainWindow,
        QProgressDialog,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - exercised only on headless runtimes
    raise ImportError("Qt runtime unavailable: libEGL/PySide6 missing") from exc

from mira import __version__ as APP_VERSION
from mira.app import ApplicationController, ModelDownloadService
from mira.ai.pipeline import Pipeline
from mira.db.database import Database
from mira.services import MobileSyncServer, ModelLifecycle
from mira.ui.dialogs import InitialSetupDialog
from mira.ui.dialogs.mobile_sync import MobileSyncSessionDialog
from mira.ui.dialogs.financial.compound_interest import CompoundInterestDialog as _CompoundInterestDialog
from mira.ui.dialogs.financial.goal_simulator import GoalScenarioDialog as _GoalScenarioDialog
from mira.ui.dialogs.financial.loan_amortization import LoanAmortizationDialog as _LoanAmortizationDialog
from mira.ui.i18n import normalize_language, tr
from mira.ui.menu_builder import MenuBuilder
from mira.ui.coordinators import ChatState
from mira.ui.coordinators.command_coordinator import CommandCoordinator
from mira.ui.coordinators.model_download_coordinator import ModelDownloadCoordinator
from mira.ui.coordinators.model_download_flow import ModelDownloadFlow, ModelDownloadSession
from mira.ui.notification_service import NotificationService
from mira.ui.notifications import show_user_message
from mira.ui.main_window_layout import MainWindowLayoutMixin, _SIDEBAR_WIDTH  # noqa: F401
from mira.ui.main_window_navigation import MainWindowNavigationMixin
from mira.ui.main_window_prompt import MainWindowPromptMixin
from mira.ui.main_window_shell import MainWindowShellMixin
from mira.ui.main_window_lifecycle import MainWindowLifecycleMixin, _DOCS_URL, webbrowser  # noqa: F401
from mira.ui.main_window_support import (
    MainWindowChatPresenter,
    MainWindowFileActions,
    MainWindowNotificationProxy,
    default_backup_name,
    resolve_transaction_export_path,
    restore_confirmation,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_APP_VERSION_FALLBACK = APP_VERSION
_LIFECYCLE_DIALOG_EXPORTS = (
    InitialSetupDialog,
    _CompoundInterestDialog,
    _GoalScenarioDialog,
    _LoanAmortizationDialog,
)
_SHOW_USER_MESSAGE_EXPORT = show_user_message


# ---------------------------------------------------------------------------
# Command-history-aware QLineEdit
# ---------------------------------------------------------------------------


class _HistoryLineEdit(QLineEdit):
    """QLineEdit that navigates command history with ↑ / ↓ keys."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the _HistoryLineEdit instance."""
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
        """Return keyPressEvent."""
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


class MainWindow(
    MainWindowLifecycleMixin,
    MainWindowPromptMixin,
    MainWindowNavigationMixin,
    MainWindowLayoutMixin,
    MainWindowShellMixin,
    QMainWindow,
):
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
        """Initialize the MainWindow instance."""
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
        self._mobile_sync_server = MobileSyncServer(self._db)
        self._mobile_sync_dialog: MobileSyncSessionDialog | None = None
        self._mobile_sync_event_timer = QTimer(self)
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
        self._resize_to_screen()
        self._apply_theme(self._theme)
        self._build_menu()
        self._build_ui()
        self._notification_service = NotificationService(self)
        self._mobile_sync_event_timer.setInterval(500)
        self._mobile_sync_event_timer.timeout.connect(self._flush_mobile_sync_events)
        self._mobile_sync_event_timer.start()
        self._chat_presenter = MainWindowChatPresenter(self)
        self._notification_proxy = MainWindowNotificationProxy(self)
        self._file_actions = MainWindowFileActions(self)
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
        """Return build menu."""
        MenuBuilder().build(self)

    def _history_line_edit_class(self) -> type[_HistoryLineEdit]:
        """Return history line edit class."""
        return _HistoryLineEdit

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------

    def _on_import_csv(self) -> None:
        """Return on import csv."""
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("menu.file.import_csv", self._language, default="Import transactions..."),
            "",
            tr(
                "file.filter.transactions_all",
                self._language,
                default="Transaction Files (*.csv *.xlsx);;CSV Files (*.csv);;Excel Files (*.xlsx);;All Files (*)",
            ),
        )
        if not path:
            return
        self._file_actions.import_transactions_file(path)

    def _on_export_csv(self) -> None:
        """Return on export csv."""
        from PySide6.QtWidgets import QFileDialog

        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            tr("menu.file.export_csv", self._language, default="Export transactions..."),
            "transactions.csv",
            tr(
                "file.filter.transactions_all",
                self._language,
                default="Transaction Files (*.csv *.xlsx);;CSV Files (*.csv);;Excel Files (*.xlsx);;All Files (*)",
            ),
        )
        if not path:
            return
        self._file_actions.export_transactions_file(resolve_transaction_export_path(path, selected_filter))

    def _on_backup(self) -> None:
        """Return on backup."""
        from PySide6.QtWidgets import QFileDialog

        default_name = default_backup_name()
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("dialog.backup.title", self._language, default="Backup Database"),
            default_name,
            tr("file.filter.sqlite_db", self._language, default="SQLite DB (*.db);;All Files (*)"),
        )
        if not path:
            return
        self._file_actions.backup(path)

    def _on_restore(self) -> None:
        """Return on restore."""
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dialog.restore.title", self._language, default="Restore Database"),
            "",
            tr("file.filter.sqlite_db", self._language, default="SQLite DB (*.db);;All Files (*)"),
        )
        if not path:
            return

        if not restore_confirmation(self):
            return

        self._file_actions.restore(path)

    def _on_diagnostics(self) -> None:
        """Return on diagnostics."""
        parser_type = type(self._pipeline.engine).__name__
        chat_engine = getattr(self._pipeline, "chat_engine", None)
        chat_type = type(chat_engine).__name__ if chat_engine is not None else "Disabled"
        self.notify_user_info(
            self,
            tr("chat.diagnostics.title", self._language, default="AI Diagnostics"),
            tr(
                "chat.diagnostics.body",
                self._language,
                default=(
                    "Assistant parser: <b>{parser}</b><br>"
                    "Chat engine: <b>{chat}</b><br><br>"
                    "Assistant mode always uses the deterministic parser.<br>"
                    "Optional local chat mode can be enabled with:<br>"
                    "<code>mira --model /path/to/model.gguf</code>"
                ),
                params={"parser": parser_type, "chat": chat_type},
            ),
        )

    def _on_mobile_sync(self) -> None:
        try:
            status = self._mobile_sync_server.start()
        except Exception as exc:  # noqa: BLE001
            self._notify_exception(
                tr("mobile.sync.error.title", self._language, default="Mobile sync error"),
                exc,
                prefix=tr(
                    "mobile.sync.error.body",
                    self._language,
                    default="The local mobile sync service could not be started.",
                ),
            )
            return
        self._mobile_sync_session_dialog().set_status(status)
        self._mobile_sync_session_dialog().show()
        self._mobile_sync_session_dialog().raise_()
        self._mobile_sync_session_dialog().activateWindow()
        self._flush_mobile_sync_events()

    def _mobile_sync_session_dialog(self) -> MobileSyncSessionDialog:
        dialog = self._mobile_sync_dialog
        if dialog is None:
            dialog = MobileSyncSessionDialog(language=self._language, parent=self)
            dialog.refresh_button.clicked.connect(self._restart_mobile_sync_session)
            dialog.stop_button.clicked.connect(self._stop_mobile_sync_session)
            self._mobile_sync_dialog = dialog
        return dialog

    def _restart_mobile_sync_session(self) -> None:
        self._on_mobile_sync()

    def _stop_mobile_sync_session(self) -> None:
        self._mobile_sync_server.stop()
        if self._mobile_sync_dialog is not None:
            self._mobile_sync_dialog.set_status(None)
        self.notify_user_info(
            self,
            tr("app.name", self._language, default="MIRA"),
            tr(
                "mobile.sync.stopped",
                self._language,
                default="The local mobile sync service was stopped.",
            ),
        )

    def _flush_mobile_sync_events(self) -> None:
        dialog = self._mobile_sync_dialog
        if dialog is not None:
            dialog.set_status(self._mobile_sync_server.status)
        for event in self._mobile_sync_server.drain_events():
            match event.level:
                case "warning":
                    self.notify_user_warning(self, event.title, event.message)
                case "error":
                    self.notify_user_error(self, event.title, event.message)
                case _:
                    self.notify_user_info(self, event.title, event.message)
