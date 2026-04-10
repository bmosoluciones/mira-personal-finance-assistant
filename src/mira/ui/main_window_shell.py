# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Shell and refresh mixin for the main window."""

from __future__ import annotations

import os

from PySide6.QtWidgets import QApplication

from mira.ui.i18n import tr


class MainWindowShellMixin:
    def _resize_to_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(1180, 720)
            return
        available = screen.availableGeometry()
        self.resize(min(1180, int(available.width() * 0.85)), min(720, int(available.height() * 0.88)))

    def _toggle_sidebar(self) -> None:
        if self._act_sidebar is None:
            return
        visible = self._act_sidebar.isChecked()
        self._sidebar_panel.setVisible(visible)
        if hasattr(self, "_logo_panel"):
            self._logo_panel.setVisible(visible)

    def _toggle_prompt_panel(self) -> None:
        if self._act_prompt is None:
            return
        self._footer.setVisible(self._act_prompt.isChecked())

    def _toggle_chat_content(self) -> None:
        visible = not self._chat_content.isVisible()
        self._chat_content.setVisible(visible)
        if hasattr(self, "_chat_toggle_btn"):
            self._chat_toggle_btn.setText("▼" if visible else "▲")

    def _refresh_all(self) -> None:
        self._view_dashboard.refresh()
        if hasattr((view := self._stack.currentWidget()), "refresh") and view is not self._view_dashboard:
            view.refresh()

    def _show_daily_contextual_message_if_needed(self) -> None:
        if (payload := self._db.feedback.pop_daily_contextual_message()) is None:
            return
        self.notify_user_message(
            tr("mira.analysis.advisor", self._language, default="MIRA Advisor"),
            str(payload.get("message") or ""),
        )

    @staticmethod
    def _normalize_theme(theme: str | None) -> str:
        valid = set(MainWindowShellMixin._qt_material_themes())
        return theme if theme in valid else "dark_teal.xml"

    @staticmethod
    def _qt_material_themes() -> list[str]:
        import qt_material  # noqa: PLC0415

        return qt_material.list_themes()

    @staticmethod
    def _apply_theme(theme: str) -> None:
        if (app := QApplication.instance()) is None:
            return
        import qt_material  # noqa: PLC0415

        qt_material.apply_stylesheet(app, theme=theme)

    @staticmethod
    def _qt_material_color(name: str, fallback: str) -> str:
        return os.environ.get(f"QTMATERIAL_{name.upper()}", fallback)

    def _sidebar_nav_stylesheet(self) -> str:
        background = self._qt_material_color("secondaryDarkColor", "#31363b")
        hover_background = self._qt_material_color("secondaryLightColor", "#4f5b62")
        text = self._qt_material_color("secondaryTextColor", "#ffffff")
        selected_background = self._qt_material_color("primaryColor", "#1de9b6")
        selected_text = self._qt_material_color("primaryTextColor", "#000000")
        return f"""
            QListWidget {{
                background-color:{background};
                border:none;
                color:{text};
                font-size:12px;
                outline:none;
            }}
            QListWidget::item {{
                color:{text};
                padding:7px 12px;
                border-left:3px solid transparent;
            }}
            QListWidget::item:selected {{
                background-color:{selected_background};
                selection-background-color:{selected_background};
                color:{selected_text};
                selection-color:{selected_text};
                border-left:3px solid {selected_text};
            }}
            QListWidget::item:hover:!selected {{
                background-color:{hover_background};
                color:{text};
            }}
            """

    def _refresh_sidebar_style(self) -> None:
        """Regenerate sidebar colors from the active qt-material theme."""
        nav_list = getattr(self, "_nav_list", None)
        if nav_list is not None:
            nav_list.setStyleSheet(self._sidebar_nav_stylesheet())
