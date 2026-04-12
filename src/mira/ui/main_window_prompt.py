# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Prompt, chat, and command-flow mixin for the main window."""

from __future__ import annotations

from mira.ai.executor import ActionResult
from mira.ui.i18n import tr
from mira.ui.notification_service import NotificationService


class MainWindowPromptMixin:
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
        del title
        presenter = getattr(self, "_chat_presenter", None)
        if presenter is not None:
            presenter.append_assistant(text)
            return

        block = text.strip()
        if not block:
            return
        started_new_batch = self._chat_state.append_block(block)
        if started_new_batch:
            from mira.ui import main_window as main_window_module

            main_window_module.QTimer.singleShot(0, self._clear_pending_chat_batch)
        self._show_chat_message()

    def notify_user_message(self, *args: object, level: str = "info") -> None:
        proxy = getattr(self, "_notification_proxy", None)
        if proxy is None:
            from mira.ui.main_window_support import MainWindowNotificationProxy

            proxy = MainWindowNotificationProxy(self)
            self._notification_proxy = proxy
        proxy.notify(*args, level=level)

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
        proxy = getattr(self, "_notification_proxy", None)
        if proxy is None:
            from mira.ui.main_window_support import MainWindowNotificationProxy

            proxy = MainWindowNotificationProxy(self)
            self._notification_proxy = proxy
        proxy.notify_exception(title, exc, prefix=prefix)

    def _clear_pending_chat_batch(self) -> None:
        self._chat_state.reset_pending_batch()

    def _show_chat_message(self) -> None:
        presenter = getattr(self, "_chat_presenter", None)
        if presenter is not None:
            presenter.show_current_message()
            return

        current_message = self._chat_state.current_message()
        browser = getattr(self, "_response_browser", None)
        if current_message is None:
            if hasattr(browser, "setHtml") and hasattr(self, "_placeholder_chat_html"):
                browser.setHtml(self._placeholder_chat_html())
            elif hasattr(browser, "clear"):
                browser.clear()
        elif hasattr(browser, "setPlainText"):
            browser.setPlainText(current_message)
        elif hasattr(browser, "setHtml"):
            escaped_message = current_message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            browser.setHtml(f'<div style="white-space:pre-wrap;">{escaped_message}</div>')
        update_navigation = getattr(self, "_update_chat_navigation", None)
        if callable(update_navigation):
            update_navigation()

    def _placeholder_chat_html(self) -> str:
        placeholder_color = self._chat_theme_primary_color()
        return f'<div style="color:{placeholder_color}; white-space:pre-wrap;">{self._response_placeholder_text}</div>'

    def _chat_theme_primary_color(self) -> str:
        return self._response_browser.palette().color(self._chat_palette_role()).name()

    def _chat_palette_role(self):
        from PySide6.QtGui import QPalette

        return QPalette.ColorRole.Link

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
            self._navigate(getattr(self, "VIEW_MIRA_ANALYSIS", 8))
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
            str(error).strip()
            or tr(
                "chat.error.generic",
                self._language,
                default="I couldn't complete the request. Review the details and try again.",
            ),
        )
        self._finish_command()

    def _prefill(self, template: str) -> None:
        self._input.setText(template)
        self._input.setFocus()
        self._input.end(False)
        self._quick_btns_frame.setVisible(False)

    def _set_status(self, text: str, color: str | None = None) -> None:
        del color
        self._status_label.setText(text)
        self._status_label.setStyleSheet("background:transparent;font-size:10px;")
