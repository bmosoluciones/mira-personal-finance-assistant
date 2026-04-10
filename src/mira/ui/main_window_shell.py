# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Shell and refresh mixin for the main window."""

from __future__ import annotations

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

    def _refresh_sidebar_style(self) -> None:
        """Re-polish sidebar widgets so that palette() references pick up the new theme colours.

        Qt caches resolved stylesheet values; after a theme switch the palette updates but
        widget-level stylesheets that reference ``palette(...)`` are not automatically
        re-evaluated.  Clearing and restoring each stylesheet forces re-evaluation.
        """
        for attr in ("_nav_list", "_sidebar_panel"):
            widget = getattr(self, attr, None)
            if widget is None:
                continue
            ss = widget.styleSheet()
            widget.setStyleSheet("")
            widget.setStyleSheet(ss)
