# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""UI flow for downloading and activating the default GGUF model."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QProgressDialog, QWidget

from mira.app import ModelDownloadService
from mira.db.database import Database
from mira.services import ModelLifecycleState
from mira.ui.coordinators.model_download_coordinator import ModelDownloadCoordinator, ModelDownloadHandle
from mira.ui.i18n import tr
from mira.ui.notification_service import NotificationService


@dataclass
class ModelDownloadSession:
    """Track the live UI objects involved in a model download."""

    handle: ModelDownloadHandle
    progress_dialog: QProgressDialog
    cancelled: bool = False

    def cancel(self) -> None:
        if self.cancelled:
            return
        self.cancelled = True
        self.handle.cancel()
        self.progress_dialog.close()


class ModelDownloadFlow:
    """Drive the default-model download UX from the desktop window."""

    def __init__(
        self,
        *,
        parent: QWidget,
        language: str,
        db: Database,
        download_coordinator: ModelDownloadCoordinator,
        download_service: ModelDownloadService,
        notification_service: NotificationService,
        apply_model_lifecycle_state: Callable[[ModelLifecycleState], None],
        refresh_settings_view: Callable[[], None],
        get_active_runtime_path: Callable[[], str | None],
        get_interaction_mode: Callable[[], str],
        get_username: Callable[[], str],
        set_status: Callable[[str], None],
    ) -> None:
        self._parent = parent
        self._language = language
        self._db = db
        self._download_coordinator = download_coordinator
        self._download_service = download_service
        self._notification_service = notification_service
        self._apply_model_lifecycle_state = apply_model_lifecycle_state
        self._refresh_settings_view = refresh_settings_view
        self._get_active_runtime_path = get_active_runtime_path
        self._get_interaction_mode = get_interaction_mode
        self._get_username = get_username
        self._set_status = set_status

    def start_default_download(self) -> ModelDownloadSession:
        session_holder: dict[str, ModelDownloadSession] = {}

        def _on_progress(received: int, total: int) -> None:
            session = session_holder.get("session")
            if session is not None and total > 0:
                session.progress_dialog.setValue(int(received * 100 / total))
            QApplication.processEvents()

        def _on_finished(downloaded_path: str) -> None:
            session = session_holder["session"]
            if session.cancelled:
                return
            self._show_reloading_state(session)
            try:
                result = self._download_service.complete_default_download(
                    filename=session.handle.filename,
                    downloaded_path=downloaded_path,
                    active_runtime_path=self._get_active_runtime_path(),
                    interaction_mode=self._get_interaction_mode(),
                )
            except Exception as exc:  # noqa: BLE001
                del exc
                session.progress_dialog.close()
                self._notification_service.error(
                    tr("model.download.error.title", self._language, default="MIRA - Download Error"),
                    tr(
                        "model.download.error.body_generic",
                        self._language,
                        default="The model could not be downloaded or activated. Please try again.",
                    ),
                    widget=self._parent,
                )
                return

            session.progress_dialog.close()
            if result.refresh_settings:
                self._refresh_settings_view()
            self._apply_model_lifecycle_state(result.lifecycle_state)
            self._set_status(tr("status.ready", self._language, default="●  Ready"))
            self._notification_service.info(
                tr("app.name", self._language, default="MIRA"),
                tr(
                    "model.download.success",
                    self._language,
                    default="Model downloaded:\n{path}",
                    params={"path": downloaded_path},
                ),
                widget=self._parent,
            )

        def _on_error(message: str) -> None:
            del message
            session = session_holder["session"]
            session.progress_dialog.close()
            if session.cancelled:
                return
            self._notification_service.error(
                tr("model.download.error.title", self._language, default="MIRA - Download Error"),
                tr(
                    "model.download.error.body_generic",
                    self._language,
                    default="The model could not be downloaded or activated. Please try again.",
                ),
                widget=self._parent,
            )

        handle = self._download_coordinator.start_default_download(
            on_progress=_on_progress,
            on_finished=_on_finished,
            on_error=_on_error,
        )
        progress_dialog = self._build_progress_dialog(handle.filename)
        session = ModelDownloadSession(handle=handle, progress_dialog=progress_dialog)
        progress_dialog.canceled.connect(session.cancel)
        session_holder["session"] = session
        return session

    def _build_progress_dialog(self, filename: str) -> QProgressDialog:
        progress = QProgressDialog(
            tr(
                "model.download.progress",
                self._language,
                default="Downloading {filename}...",
                params={"filename": filename},
            ),
            tr("common.cancel", self._language, default="Cancel"),
            0,
            100,
            self._parent,
        )
        progress.setWindowTitle(tr("model.download.title", self._language, default="MIRA - Model Download"))
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        return progress

    def _show_reloading_state(self, session: ModelDownloadSession) -> None:
        mode = self._get_interaction_mode()
        if mode == "chat":
            mode_label = tr("settings.mode.chat", self._language, default="Chat mode")
        else:
            mode_label = tr("settings.mode.assistant", self._language, default="Assistant mode")
        status = tr(
            "status.reloading_model",
            self._language,
            default="Updating model for mode {mode}...",
            params={"mode": mode_label},
        )
        session.progress_dialog.setCancelButton(None)
        session.progress_dialog.setLabelText(status)
        self._set_status(status)
        QApplication.processEvents()
