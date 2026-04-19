# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Support helpers for :mod:`mira.ui.main_window`."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from sqlite3 import Error
from typing import Any

from PySide6.QtCore import QTimer
from mira.app.view_services import (
    AccountsViewService,
    CategoriesViewService,
    MiraAnalysisMessageBuilder,
    MiraAnalysisService,
    ReconciliationViewService,
    RecurringViewService,
    ReportsViewService,
    SavingsGoalsViewService,
    SettingsViewService,
    TagsViewService,
    TransactionsViewService,
)
from mira.error_policy import describe as describe_error
from mira.ui.i18n import tr


def resolve_transaction_export_path(path: str, selected_filter: str) -> str:
    """Append a default transaction export extension when the user omits one."""
    if Path(path).suffix:
        return path
    normalized_filter = selected_filter.casefold()
    extension = ".xlsx" if "*.xlsx" in normalized_filter and "*.csv" not in normalized_filter else ".csv"
    return f"{path}{extension}"


def _transaction_column_label(language: str, column_name: str) -> str:
    """Translate a canonical transaction column label for user-facing errors."""
    return tr(f"transactions.column.{column_name}", language, default=column_name)


def _translate_transaction_file_error(language: str, exc: Exception) -> str | None:
    """Translate known transaction-file ValueError messages into localized UI copy."""
    if not isinstance(exc, ValueError):
        return None

    message = str(exc)
    if message == "Transaction file is empty.":
        return tr("transactions.file_error.empty", language, default="The transactions file is empty.")

    unsupported_prefix = "Unsupported transaction file extension: "
    if message.startswith(unsupported_prefix):
        extension = message.removeprefix(unsupported_prefix).split(" Supported extensions are", 1)[0].strip()
        return tr(
            "transactions.file_error.unsupported_extension",
            language,
            default="Unsupported transaction file extension: {extension}. Use .csv or .xlsx.",
            params={"extension": extension},
        )

    missing_prefix = "Missing required transaction columns: "
    if message.startswith(missing_prefix):
        raw_columns = [item.strip().rstrip(".") for item in message.removeprefix(missing_prefix).split(",")]
        translated_columns = ", ".join(_transaction_column_label(language, column) for column in raw_columns if column)
        return tr(
            "transactions.file_error.missing_columns",
            language,
            default="Missing required columns: {columns}.",
            params={"columns": translated_columns},
        )

    ambiguous_prefix = "Ambiguous transaction headers for '"
    if message.startswith(ambiguous_prefix):
        column_name, _, remainder = message.removeprefix(ambiguous_prefix).partition("': ")
        parts = remainder.split(" and ")
        if len(parts) == 2:
            first = parts[0].strip().rstrip(".")
            second = parts[1].strip().rstrip(".")
            return tr(
                "transactions.file_error.ambiguous_headers",
                language,
                default="Headers {first} and {second} map to the same field: {column}.",
                params={
                    "first": first,
                    "second": second,
                    "column": _transaction_column_label(language, column_name),
                },
            )

    return None


@dataclass(frozen=True)
class MainWindowServices:
    """Represent the MainWindowServices class."""

    accounts: AccountsViewService

    transactions: TransactionsViewService
    categories: CategoriesViewService
    tags: TagsViewService
    reconciliation: ReconciliationViewService
    recurring: RecurringViewService
    reports: ReportsViewService
    mira_analysis: MiraAnalysisService
    mira_message_builder: MiraAnalysisMessageBuilder
    goals: SavingsGoalsViewService
    settings: SettingsViewService


def build_view_services(db) -> MainWindowServices:
    """Return build view services."""
    return MainWindowServices(
        accounts=AccountsViewService(db),
        transactions=TransactionsViewService(db),
        categories=CategoriesViewService(db),
        tags=TagsViewService(db),
        reconciliation=ReconciliationViewService(db),
        recurring=RecurringViewService(db),
        reports=ReportsViewService(db),
        mira_analysis=MiraAnalysisService(db),
        mira_message_builder=MiraAnalysisMessageBuilder(db),
        goals=SavingsGoalsViewService(db),
        settings=SettingsViewService(db),
    )


class MainWindowChatPresenter:
    """Represent the MainWindowChatPresenter class."""

    def __init__(self, window) -> None:
        """Initialize the MainWindowChatPresenter instance."""
        self._window = window

    def append_assistant(self, text: str) -> None:
        """Return append assistant."""
        block = text.strip()
        if not block:
            return
        started_new_batch = self._window._chat_state.append_block(block)
        if started_new_batch:
            QTimer.singleShot(0, self._window._clear_pending_chat_batch)
        self.show_current_message()

    def show_current_message(self) -> None:
        """Return show current message."""
        current_message = self._window._chat_state.current_message()
        if current_message is None:
            if hasattr(self._window._response_browser, "setHtml"):
                self._window._response_browser.setHtml(self._window._placeholder_chat_html())
            elif hasattr(self._window._response_browser, "clear"):
                self._window._response_browser.clear()
            self._window._update_chat_navigation()
            return

        text_color = self._window._chat_theme_primary_color()
        escaped_message = current_message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if hasattr(self._window._response_browser, "setHtml"):
            self._window._response_browser.setHtml(
                f'<div style="color:{text_color}; white-space:pre-wrap;">{escaped_message}</div>'
            )
        elif hasattr(self._window._response_browser, "setPlainText"):
            self._window._response_browser.setPlainText(current_message)
        self._window._update_chat_navigation()


class MainWindowNotificationProxy:
    """Represent the MainWindowNotificationProxy class."""

    def __init__(self, window) -> None:
        """Initialize the MainWindowNotificationProxy instance."""
        self._window = window

    def notify(self, *args: object, level: str = "info") -> None:
        """Return notify."""
        from PySide6.QtWidgets import QWidget

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
        service = self._window._notification_handler()
        match level:
            case "error":
                service.error(str(title), str(message), widget=widget)
            case "warning":
                service.warning(str(title), str(message), widget=widget)
            case _:
                service.info(str(title), str(message), widget=widget)

    def notify_exception(self, title: str, exc: Exception, *, prefix: str | None = None) -> None:
        """Return notify exception."""
        descriptor = describe_error(exc, language=getattr(self._window, "_language", "en"))
        message = descriptor.message if prefix is None else f"{prefix}\n{descriptor.message}"
        self.notify(self._window, title, message, level=descriptor.level)


class MainWindowFileActions:
    """Represent the MainWindowFileActions class."""

    def __init__(self, window) -> None:
        """Initialize the MainWindowFileActions instance."""
        self._window = window

    def _notify_transaction_file_exception(
        self,
        *,
        title_key: str,
        title_default: str,
        body_key: str,
        body_default: str,
        exc: Exception,
    ) -> None:
        """Show a localized transaction file error message."""
        language = self._window._language
        descriptor = describe_error(exc, language=language)
        error_message = _translate_transaction_file_error(language, exc) or descriptor.message
        self._window.notify_user_message(
            self._window,
            tr(title_key, language, default=title_default),
            tr(body_key, language, default=body_default, params={"error": error_message}),
            level=descriptor.level,
        )

    def import_transactions_file(self, path: str) -> None:
        """Import transactions from a CSV or XLSX file."""
        try:
            imported, errors = self._window._db.io.import_transactions_file(path)
            self._window._refresh_all()
            self._window.notify_user_info(
                self._window,
                tr("import.complete.title", self._window._language, default="Import Complete"),
                tr(
                    "import.complete.body",
                    self._window._language,
                    default="Imported: {imported} transaction(s)\nSkipped (errors): {errors}",
                    params={"imported": imported, "errors": errors},
                ),
            )
        except (csv.Error, OSError, RuntimeError, TypeError, UnicodeError, ValueError, Error) as exc:
            self._notify_transaction_file_exception(
                title_key="import.error.title",
                title_default="Import Error",
                body_key="import.error.body",
                body_default="Failed to import the transactions file:\n{error}",
                exc=exc,
            )

    def export_transactions_file(self, path: str) -> None:
        """Export transactions to a CSV or XLSX file."""
        try:
            count = self._window._db.io.export_transactions_file(path)
            self._window.notify_user_info(
                self._window,
                tr("export.complete.title", self._window._language, default="Export Complete"),
                tr(
                    "export.complete.body",
                    self._window._language,
                    default="Exported {count} transaction(s) to:\n{path}",
                    params={"count": count, "path": path},
                ),
            )
        except Exception as exc:  # noqa: BLE001
            self._notify_transaction_file_exception(
                title_key="export.error.title",
                title_default="Export Error",
                body_key="export.error.body",
                body_default="Failed to export the transactions file:\n{error}",
                exc=exc,
            )

    def import_csv(self, path: str) -> None:
        """Compatibility wrapper for importing transaction CSV files."""
        self.import_transactions_file(path)

    def export_csv(self, path: str) -> None:
        """Compatibility wrapper for exporting transaction CSV files."""
        self.export_transactions_file(path)

    def backup(self, path: str) -> None:
        """Return backup."""
        try:
            backup_path = self._window._db.backup.create(path)
            self._window.notify_user_info(
                self._window,
                tr("dialog.backup.success.title", self._window._language, default="Backup completed"),
                tr(
                    "dialog.backup.success.body",
                    self._window._language,
                    default="Backup created at:\n{path}",
                    params={"path": backup_path},
                ),
            )
        except Exception as exc:  # noqa: BLE001
            self._window._notify_exception(
                tr("dialog.backup.error.title", self._window._language, default="Backup error"),
                exc,
                prefix=tr("dialog.backup.error.body", self._window._language, default="Could not create backup:"),
            )

    def restore(self, path: str) -> None:
        """Return restore."""
        try:
            restored = self._window._db.backup.restore(path)
            self._window._refresh_all()
            success_key = "dialog.restore.success.body"
            success_default = "Database restored from:\n{path}"
            success_params: dict[str, Any] = {"path": restored.restored_from}
            if restored.migration_applied:
                success_key = "dialog.restore.success.body_migrated"
                success_default = "Database restored from:\n{path}\nSchema upgraded: v{from_version} -> v{to_version}"
                success_params = {
                    "path": restored.restored_from,
                    "from_version": restored.source_schema_version,
                    "to_version": restored.target_schema_version,
                }
            self._window.notify_user_info(
                self._window,
                tr("dialog.restore.success.title", self._window._language, default="Restore completed"),
                tr(success_key, self._window._language, default=success_default, params=success_params),
            )
        except Exception as exc:  # noqa: BLE001
            self._window._notify_exception(
                tr("dialog.restore.error.title", self._window._language, default="Restore error"),
                exc,
                prefix=tr("dialog.restore.error.body", self._window._language, default="Could not restore:"),
            )


def restore_confirmation(window) -> bool:
    """Return restore confirmation."""
    from PySide6.QtWidgets import QMessageBox

    reply = QMessageBox.question(
        window,
        tr("dialog.restore.confirm.title", window._language, default="Confirm restore"),
        tr(
            "dialog.restore.confirm.body",
            window._language,
            default="This action will replace current data with the selected backup. Continue?",
        ),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    return reply == QMessageBox.StandardButton.Yes


def default_backup_name() -> str:
    """Return default backup name."""
    return f"mira-backup-{date.today().isoformat()}.db"
