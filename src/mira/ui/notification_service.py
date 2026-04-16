# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Presentation helpers for user notifications across chat and modal channels."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMessageBox, QWidget

from mira.ui.i18n import tr


class NotificationService:
    """Show user notifications through the message bar or QMessageBox plus status-bar hints."""

    def __init__(self, ui: Any) -> None:
        """Initialize the NotificationService instance."""
        self._ui = ui

    def info(self, title: str, message: str, widget: QWidget | None = None) -> None:
        """Return info."""
        self._show("info", title, message, widget=widget)

    def warning(self, title: str, message: str, widget: QWidget | None = None) -> None:
        """Return warning."""
        self._show("warning", title, message, widget=widget)

    def error(self, title: str, message: str, widget: QWidget | None = None) -> None:
        """Return error."""
        self._show("error", title, message, widget=widget)

    def _show(self, level: str, title: str, message: str, *, widget: QWidget | None) -> None:
        """Return show."""
        text = str(message or "").strip()
        if not text:
            return

        self._update_status(level, text)
        if self._should_route_to_message_bar(title) and self._show_in_message_bar(str(title), text):
            return

        parent = widget if isinstance(widget, QWidget) else self._widget_parent()
        if level == "error":
            QMessageBox.critical(parent, str(title), text)
        elif level == "warning":
            QMessageBox.warning(parent, str(title), text)
        else:
            QMessageBox.information(parent, str(title), text)

    def _widget_parent(self) -> QWidget | None:
        """Return widget parent."""
        return self._ui if isinstance(self._ui, QWidget) else None

    def _should_route_to_message_bar(self, title: str) -> bool:
        """Return whether should route to message bar."""
        normalized_title = " ".join(str(title or "").split()).casefold()
        return "mira" in normalized_title

    def _show_in_message_bar(self, title: str, message: str) -> bool:
        """Return show in message bar."""
        append = getattr(self._ui, "_append_chat_assistant", None)
        if not callable(append):
            return False

        self._ensure_message_bar_visible()
        append(message, title=title)
        return True

    def _ensure_message_bar_visible(self) -> None:
        """Return ensure message bar visible."""
        footer = getattr(self._ui, "_footer", None)
        if hasattr(footer, "setVisible"):
            footer.setVisible(True)  # type: ignore[union-attr]

        action = getattr(self._ui, "_act_prompt", None)
        if hasattr(action, "setChecked"):
            action.setChecked(True)  # type: ignore[union-attr]

        expand_panel = getattr(self._ui, "_set_chat_panel_expanded", None)
        if callable(expand_panel):
            expand_panel(True)
            return

        chat_content = getattr(self._ui, "_chat_content", None)
        if hasattr(chat_content, "setVisible"):
            chat_content.setVisible(True)  # type: ignore[union-attr]

        toggle = getattr(self._ui, "_chat_toggle_btn", None)
        if hasattr(toggle, "setText"):
            toggle.setText("\u25bc")  # type: ignore[union-attr]

    def _update_status(self, level: str, text: str) -> None:
        """Return update status."""
        status_bar = getattr(self._ui, "_status_bar", None)
        if status_bar is not None:
            timeout = 7000 if level == "error" else 5000
            status_bar.showMessage(text, timeout)

        set_status = getattr(self._ui, "_set_status", None)
        if not callable(set_status):
            return

        language = getattr(self._ui, "_language", "en")
        if level == "error":
            set_status(tr("status.notification_error", language, default="●  Attention required"))
            return
        if level == "warning":
            set_status(tr("status.notification_warning", language, default="●  Review latest message"))
