# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Helpers to route user-facing notifications through the active UI channel."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMessageBox, QWidget


def _notification_target(widget: QWidget | None) -> Any | None:
    """Return notification target."""
    current = widget
    while current is not None:
        if hasattr(current, "notify_user_message"):
            return current
        parent_getter = getattr(current, "parentWidget", None)
        current = parent_getter() if callable(parent_getter) else None
    if widget is None:
        return None
    window_getter = getattr(widget, "window", None)
    window = window_getter() if callable(window_getter) else None
    if isinstance(window, QWidget) and hasattr(window, "notify_user_message"):
        return window
    return None


def show_user_message(widget: QWidget | None, title: str, message: str, *, level: str = "info") -> None:
    """Return show user message."""
    text = str(message or "").strip()
    if not text:
        return

    target = _notification_target(widget)
    if target is not None:
        target.notify_user_message(title, text, level=level)
        return

    if level == "error":
        QMessageBox.critical(widget, title, text)
    elif level == "warning":
        QMessageBox.warning(widget, title, text)
    else:
        QMessageBox.information(widget, title, text)
