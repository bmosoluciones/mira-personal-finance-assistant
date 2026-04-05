# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import importlib

import pytest

from conftest import opengl_import_error

pytestmark = pytest.mark.skipif(
    opengl_import_error(),
    reason="PySide6.QtWidgets requires libEGL (not available in headless environments)",
)


class _DummyStatusBar:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def showMessage(self, message: str, timeout: int = 0) -> None:
        self.calls.append((message, timeout))


class _DummyToggleTarget:
    def __init__(self) -> None:
        self.visible_calls: list[bool] = []
        self.checked_calls: list[bool] = []
        self.texts: list[str] = []

    def setVisible(self, visible: bool) -> None:
        self.visible_calls.append(visible)

    def setChecked(self, checked: bool) -> None:
        self.checked_calls.append(checked)

    def setText(self, text: str) -> None:
        self.texts.append(text)


class _DummyUi:
    def __init__(self) -> None:
        self._language = "en"
        self._status_bar = _DummyStatusBar()
        self.statuses: list[str] = []
        self.chat_calls: list[tuple[str, str]] = []
        self._footer = _DummyToggleTarget()
        self._act_prompt = _DummyToggleTarget()
        self._chat_content = _DummyToggleTarget()
        self._chat_toggle_btn = _DummyToggleTarget()

    def _set_status(self, text: str, color: str | None = None) -> None:
        self.statuses.append(text)

    def _append_chat_assistant(self, text: str, title: str | None = None) -> None:
        self.chat_calls.append((title or "", text))


def test_notification_service_routes_warning_to_message_box_and_status(monkeypatch) -> None:
    module = importlib.import_module("mira.ui.notification_service")
    calls: list[tuple[object | None, str, str]] = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda parent, title, text: calls.append((parent, title, text)))

    ui = _DummyUi()
    service = module.NotificationService(ui)
    service.warning("Heads up", "Review this")

    assert calls == [(None, "Heads up", "Review this")]
    assert ui._status_bar.calls == [("Review this", 5000)]
    assert ui.statuses == [module.tr("status.notification_warning", "en", default="\u25cf  Review latest message")]
    assert ui.chat_calls == []


def test_notification_service_routes_mira_messages_to_message_bar(monkeypatch) -> None:
    module = importlib.import_module("mira.ui.notification_service")
    info_calls: list[tuple[object | None, str, str]] = []
    error_calls: list[tuple[object | None, str, str]] = []
    monkeypatch.setattr(
        module.QMessageBox,
        "information",
        lambda parent, title, text: info_calls.append((parent, title, text)),
    )
    monkeypatch.setattr(
        module.QMessageBox,
        "critical",
        lambda parent, title, text: error_calls.append((parent, title, text)),
    )

    ui = _DummyUi()
    service = module.NotificationService(ui)
    service.info("MIRA Advisor", "Review your budget")
    service.error("MIRA - Download Error", "Model download failed")

    assert info_calls == []
    assert error_calls == []
    assert ui.chat_calls == [
        ("MIRA Advisor", "Review your budget"),
        ("MIRA - Download Error", "Model download failed"),
    ]
    assert ui._footer.visible_calls == [True, True]
    assert ui._act_prompt.checked_calls == [True, True]
    assert ui._chat_content.visible_calls == [True, True]
    assert ui._chat_toggle_btn.texts == ["\u25bc", "\u25bc"]
    assert ui._status_bar.calls == [
        ("Review your budget", 5000),
        ("Model download failed", 7000),
    ]
    assert ui.statuses == [module.tr("status.notification_error", "en", default="\u25cf  Attention required")]


def test_show_user_message_uses_window_notification_interface(monkeypatch) -> None:
    module = importlib.import_module("mira.ui.notifications")

    class DummyTarget:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []
            self.chat_calls: list[str] = []

        def notify_user_message(self, title: str, message: str, *, level: str = "info") -> None:
            self.calls.append((title, message, level))

        def _append_chat_assistant(self, text: str) -> None:
            self.chat_calls.append(text)

    target = DummyTarget()
    module.show_user_message(target, "Done", "Saved", level="info")

    assert target.calls == [("Done", "Saved", "info")]
    assert target.chat_calls == []
