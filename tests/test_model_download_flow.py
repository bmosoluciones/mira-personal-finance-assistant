# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import importlib

import pytest

from conftest import opengl_import_error
from mira.ui.i18n import tr

pytestmark = pytest.mark.skipif(
    opengl_import_error(),
    reason="PySide6.QtWidgets requires libEGL (not available in headless environments)",
)


def _get_qapplication(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    qtwidgets = importlib.import_module("PySide6.QtWidgets")
    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


class _DummySignal:
    def __init__(self) -> None:
        self.callbacks: list[object] = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)


class _FakeProgressDialog:
    def __init__(self, label: str, cancel: str, minimum: int, maximum: int, parent) -> None:
        self.label = label
        self.cancel_text = cancel
        self.minimum = minimum
        self.maximum = maximum
        self.parent = parent
        self.window_title = ""
        self.window_modality = None
        self.minimum_duration = None
        self.value = None
        self.closed = False
        self.shown = False
        self.cancel_button = object()
        self.canceled = _DummySignal()

    def setWindowTitle(self, title: str) -> None:
        self.window_title = title

    def setWindowModality(self, modality) -> None:
        self.window_modality = modality

    def setMinimumDuration(self, duration: int) -> None:
        self.minimum_duration = duration

    def setValue(self, value: int) -> None:
        self.value = value

    def show(self) -> None:
        self.shown = True

    def close(self) -> None:
        self.closed = True

    def setCancelButton(self, button) -> None:
        self.cancel_button = button

    def setLabelText(self, text: str) -> None:
        self.label = text


class _FakeWorker:
    pass


class _FakeHandle:
    def __init__(self, filename: str = "model.gguf") -> None:
        self.filename = filename
        self.worker = _FakeWorker()
        self.cancel_calls = 0

    def cancel(self) -> None:
        self.cancel_calls += 1


class _FakeCoordinator:
    def __init__(self, handle: _FakeHandle | None = None) -> None:
        self.handle = handle or _FakeHandle()
        self.progress_callback = None
        self.finished_callback = None
        self.error_callback = None

    def start_default_download(self, on_progress, on_finished, on_error):
        self.progress_callback = on_progress
        self.finished_callback = on_finished
        self.error_callback = on_error
        return self.handle


class _FakeDownloadService:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, str, str | None, str]] = []

    def complete_default_download(
        self,
        filename: str,
        downloaded_path: str,
        active_runtime_path: str | None,
        interaction_mode: str,
    ):
        self.calls.append((filename, downloaded_path, active_runtime_path, interaction_mode))
        if self.error is not None:
            raise self.error
        return self.result


class _FakeNotifications:
    def __init__(self) -> None:
        self.info_calls: list[tuple[str, str, object | None]] = []
        self.error_calls: list[tuple[str, str, object | None]] = []

    def info(self, title: str, message: str, widget=None) -> None:
        self.info_calls.append((title, message, widget))

    def error(self, title: str, message: str, widget=None) -> None:
        self.error_calls.append((title, message, widget))


def test_model_download_flow_updates_progress_and_applies_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _get_qapplication(monkeypatch)
    module = importlib.import_module("mira.ui.coordinators.model_download_flow")
    monkeypatch.setattr(module, "QProgressDialog", _FakeProgressDialog)
    monkeypatch.setattr(module.QApplication, "processEvents", lambda: None)

    lifecycle_state = object()
    service_result = type(
        "Result",
        (),
        {
            "downloaded_path": "C:/models/model.gguf",
            "preferred_model_name": "model.gguf",
            "lifecycle_state": lifecycle_state,
            "refresh_settings": True,
        },
    )()
    coordinator = _FakeCoordinator()
    download_service = _FakeDownloadService(result=service_result)
    notifications = _FakeNotifications()
    applied_states: list[object] = []
    refresh_calls: list[str] = []
    statuses: list[str] = []
    flow = module.ModelDownloadFlow(
        parent=None,
        language="en",
        db=object(),
        download_coordinator=coordinator,
        download_service=download_service,
        notification_service=notifications,
        apply_model_lifecycle_state=applied_states.append,
        refresh_settings_view=lambda: refresh_calls.append("refresh"),
        get_active_runtime_path=lambda: "C:/runtime/old.gguf",
        get_interaction_mode=lambda: "assistant",
        get_username=lambda: "User",
        set_status=statuses.append,
    )

    session = flow.start_default_download()
    coordinator.progress_callback(1, 2)
    coordinator.finished_callback("C:/models/model.gguf")

    assert isinstance(session.progress_dialog, _FakeProgressDialog)
    assert session.progress_dialog.value == 50
    assert session.progress_dialog.closed is True
    assert download_service.calls == [("model.gguf", "C:/models/model.gguf", "C:/runtime/old.gguf", "assistant")]
    assert applied_states == [lifecycle_state]
    assert refresh_calls == ["refresh"]
    assert notifications.info_calls == [("MIRA", "Model downloaded:\nC:/models/model.gguf", None)]
    assert notifications.error_calls == []
    assert statuses[0].startswith("Updating model for mode")
    assert statuses[-1] == "●  Ready"


def test_model_download_flow_cancel_avoids_followup_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    _get_qapplication(monkeypatch)
    module = importlib.import_module("mira.ui.coordinators.model_download_flow")
    monkeypatch.setattr(module, "QProgressDialog", _FakeProgressDialog)
    monkeypatch.setattr(module.QApplication, "processEvents", lambda: None)

    coordinator = _FakeCoordinator()
    download_service = _FakeDownloadService(result=object())
    notifications = _FakeNotifications()
    flow = module.ModelDownloadFlow(
        parent=None,
        language="en",
        db=object(),
        download_coordinator=coordinator,
        download_service=download_service,
        notification_service=notifications,
        apply_model_lifecycle_state=lambda _state: None,
        refresh_settings_view=lambda: None,
        get_active_runtime_path=lambda: None,
        get_interaction_mode=lambda: "assistant",
        get_username=lambda: "User",
        set_status=lambda _text: None,
    )

    session = flow.start_default_download()
    session.progress_dialog.canceled.callbacks[0]()
    coordinator.finished_callback("C:/models/model.gguf")

    assert session.cancelled is True
    assert coordinator.handle.cancel_calls == 1
    assert session.progress_dialog.closed is True
    assert download_service.calls == []
    assert notifications.info_calls == []
    assert notifications.error_calls == []


def test_model_download_flow_notifies_error_and_closes_dialog(monkeypatch: pytest.MonkeyPatch) -> None:
    _get_qapplication(monkeypatch)
    module = importlib.import_module("mira.ui.coordinators.model_download_flow")
    monkeypatch.setattr(module, "QProgressDialog", _FakeProgressDialog)
    monkeypatch.setattr(module.QApplication, "processEvents", lambda: None)

    coordinator = _FakeCoordinator()
    notifications = _FakeNotifications()
    flow = module.ModelDownloadFlow(
        parent=None,
        language="en",
        db=object(),
        download_coordinator=coordinator,
        download_service=_FakeDownloadService(result=object()),
        notification_service=notifications,
        apply_model_lifecycle_state=lambda _state: None,
        refresh_settings_view=lambda: None,
        get_active_runtime_path=lambda: None,
        get_interaction_mode=lambda: "assistant",
        get_username=lambda: "User",
        set_status=lambda _text: None,
    )

    session = flow.start_default_download()
    coordinator.error_callback("network down")

    assert session.progress_dialog.closed is True
    assert len(notifications.error_calls) == 1
    title, message, widget = notifications.error_calls[0]
    assert title.endswith("Download Error")
    assert message == tr(
        "model.download.error.body_generic",
        "en",
        default="The model could not be downloaded or activated. Please try again.",
    )
    assert widget is None


def test_model_download_flow_notifies_service_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    _get_qapplication(monkeypatch)
    module = importlib.import_module("mira.ui.coordinators.model_download_flow")
    monkeypatch.setattr(module, "QProgressDialog", _FakeProgressDialog)
    monkeypatch.setattr(module.QApplication, "processEvents", lambda: None)

    coordinator = _FakeCoordinator()
    notifications = _FakeNotifications()
    flow = module.ModelDownloadFlow(
        parent=None,
        language="en",
        db=object(),
        download_coordinator=coordinator,
        download_service=_FakeDownloadService(error=RuntimeError("reload failed")),
        notification_service=notifications,
        apply_model_lifecycle_state=lambda _state: None,
        refresh_settings_view=lambda: None,
        get_active_runtime_path=lambda: None,
        get_interaction_mode=lambda: "chat",
        get_username=lambda: "User",
        set_status=lambda _text: None,
    )

    session = flow.start_default_download()
    coordinator.finished_callback("C:/models/model.gguf")

    assert session.progress_dialog.closed is True
    assert len(notifications.error_calls) == 1
    title, message, widget = notifications.error_calls[0]
    assert title.endswith("Download Error")
    assert message == tr(
        "model.download.error.body_generic",
        "en",
        default="The model could not be downloaded or activated. Please try again.",
    )
    assert widget is None
