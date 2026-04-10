# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Lifecycle and onboarding mixin for the main window."""

from __future__ import annotations

from pathlib import Path
import sys
import webbrowser
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QProgressDialog, QVBoxLayout, QWidget

from mira import __version__ as APP_VERSION
from mira.number_format import validate_number_format_config
from mira.ui.dialogs import InitialSetupDialog
from mira.ui.dialogs.financial.compound_interest import CompoundInterestDialog as _CompoundInterestDialog
from mira.ui.dialogs.financial.goal_simulator import GoalScenarioDialog as _GoalScenarioDialog
from mira.ui.dialogs.financial.loan_amortization import LoanAmortizationDialog as _LoanAmortizationDialog
from mira.ui.i18n import normalize_language, tr
from mira.ui.notifications import show_user_message

_APP_VERSION_FALLBACK = APP_VERSION
_APP_LICENSE = "GPL-3.0-or-later"
_DOCS_URL = "https://mira.bmogroup.solutions"
_INITIAL_SETUP_PREVIEW_THEME = "light_blue.xml"


class MainWindowLifecycleMixin:
    def _run_initial_setup_if_needed(self) -> None:
        main_window_module = sys.modules.get("mira.ui.main_window")
        dialog_cls = getattr(main_window_module, "InitialSetupDialog", InitialSetupDialog)
        show_message = getattr(main_window_module, "show_user_message", show_user_message)
        completed = self._db.setting.get("onboarding_completed")
        if completed == "1":
            return

        self._apply_theme(self._normalize_theme(_INITIAL_SETUP_PREVIEW_THEME))
        dlg = dialog_cls(self._db, self)
        if dlg.exec() == dialog_cls.DialogCode.Accepted:
            data = dlg.get_data()
            language = normalize_language(data.get("language"))
            try:
                number_format = validate_number_format_config(data.get("thousands_sep"), data.get("decimal_sep"))
            except ValueError:
                show_message(
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
            username = str(data.get("username") or tr("settings.saved_default_user", language)).strip()
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
            self.notify_user_message(tr("setup.welcome.title", language), tr("setup.welcome.body", language))
        else:
            self._startup_cancelled = True

    def _on_download_default_model(self) -> None:
        session = self._model_download_flow.start_default_download()
        self._download_session = session
        self._download_worker = session.handle.worker

    def _application_version(self) -> str:
        app = QApplication.instance()
        if app is None:
            return _APP_VERSION_FALLBACK
        return app.applicationVersion() or _APP_VERSION_FALLBACK

    def _resolve_ui_icon_path(self, *candidates: str) -> Path | None:
        icons_dir = Path(__file__).resolve().parent / "icons"
        for name in candidates:
            if (candidate := icons_dir / name).is_file():
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
        label.setPixmap(pixmap.scaledToHeight(max_height, Qt.TransformationMode.SmoothTransformation))
        return label

    def _on_about(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("dialog.about.title", self._language, default="MIRA Information"))
        dialog.setModal(True)
        dialog.setMinimumWidth(480)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        layout.addWidget(
            self._build_about_logo_label(
                self._resolve_ui_icon_path("256x256.png", "mira.ico", "scalable.svg"), max_height=88
            )
        )

        title = QLabel("<b>MIRA</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:22px;")
        layout.addWidget(title)

        subtitle = QLabel(tr("dialog.about.subtitle", self._language, default="Manage Income & Resources Allocations"))
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
            tr("dialog.about.license", self._language, default="License: {license}", params={"license": _APP_LICENSE})
        )
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(license_label)

        details = QLabel(
            tr("dialog.about.details", self._language, default="100% offline • No telemetry • SQLite + PySide6")
        )
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details.setWordWrap(True)
        details.setStyleSheet("color:#9FB3C8;")
        layout.addWidget(details)

        company_caption = QLabel(
            tr("dialog.about.company", self._language, default="Developed by BMO Soluciones, S.A.")
        )
        company_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        company_caption.setWordWrap(True)
        company_caption.setStyleSheet("font-size:12px;color:#C7D0DA;padding-top:4px;")
        layout.addWidget(company_caption)

        layout.addWidget(self._build_about_logo_label(self._resolve_ui_icon_path("BMOLogoSmall.png"), max_height=48))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def _menu_open_compound_interest(self) -> None:
        main_window_module = sys.modules.get("mira.ui.main_window")
        dialog_cls = getattr(main_window_module, "_CompoundInterestDialog", _CompoundInterestDialog)
        currency = self._db.setting.get("default_currency") or "USD"
        dialog_cls(self._language, currency, self).exec()

    def _menu_open_loan_amortization(self) -> None:
        main_window_module = sys.modules.get("mira.ui.main_window")
        dialog_cls = getattr(main_window_module, "_LoanAmortizationDialog", _LoanAmortizationDialog)
        currency = self._db.setting.get("default_currency") or "USD"
        dialog_cls(self._language, currency, self).exec()

    def _menu_open_goal_simulator(self) -> None:
        main_window_module = sys.modules.get("mira.ui.main_window")
        dialog_cls = getattr(main_window_module, "_GoalScenarioDialog", _GoalScenarioDialog)
        db = getattr(self, "_db", None)
        currency = "USD" if db is None else db.setting.get("default_currency") or "USD"
        dialog = dialog_cls(self._language, currency, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.should_open_goal_form:
            self._navigate(getattr(self, "VIEW_GOALS", 9))
            self._view_goals.open_add_dialog(prefill=dialog.goal_prefill)

    def _on_open_documentation(self) -> None:
        webbrowser.open(_DOCS_URL)

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
        progress.setWindowTitle(tr("app.name", self._language, default="MIRA"))
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
            tr("settings.saved.body", self._language, default="Configuration was saved successfully."),
        )

    def _on_theme_changed(self, theme: str) -> None:
        self._theme = self._normalize_theme(theme)
        self._apply_theme(self._theme)
        self._refresh_sidebar_style()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._pipeline.shutdown()
        super().closeEvent(event)
