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


def _get_qapplication(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    qtwidgets = importlib.import_module("PySide6.QtWidgets")
    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


def test_pipeline_worker_routes_chat_and_success_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    _get_qapplication(monkeypatch)
    module = importlib.import_module("mira.ui.coordinators.command_coordinator")

    class DummyPipeline:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def process(self, text: str) -> str:
            self.calls.append(("assistant", text))
            return "assistant-result"

        def process_chat(self, text: str) -> str:
            self.calls.append(("chat", text))
            return "chat-result"

    pipeline = DummyPipeline()
    worker = module.PipelineCommandWorker(pipeline, "hola", "chat")
    results: list[object] = []
    worker.finished.connect(results.append)

    worker.run()

    assert pipeline.calls == [("chat", "hola")]
    assert results == ["chat-result"]


def test_pipeline_worker_emits_error_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    _get_qapplication(monkeypatch)
    module = importlib.import_module("mira.ui.coordinators.command_coordinator")

    class DummyPipeline:
        def process(self, _text: str) -> str:
            raise ValueError("boom")

        def process_chat(self, _text: str) -> str:
            raise AssertionError("should not use chat mode")

    worker = module.PipelineCommandWorker(DummyPipeline(), "hola", "assistant")
    errors: list[str] = []
    worker.error.connect(errors.append)

    worker.run()

    assert errors == ["boom"]


def test_command_coordinator_connects_callbacks_and_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("mira.ui.coordinators.command_coordinator")

    class DummySignal:
        def __init__(self) -> None:
            self.callbacks: list[object] = []

        def connect(self, callback) -> None:
            self.callbacks.append(callback)

    class FakeWorker:
        def __init__(self, pipeline, user_input: str, mode: str) -> None:
            self.pipeline = pipeline
            self.user_input = user_input
            self.mode = mode
            self.finished = DummySignal()
            self.error = DummySignal()
            self.started = False

        def start(self) -> None:
            self.started = True

    monkeypatch.setattr(module, "PipelineCommandWorker", FakeWorker)

    pipeline = object()
    coordinator = module.CommandCoordinator(pipeline)
    success_calls: list[object] = []
    error_calls: list[str] = []

    worker = coordinator.execute("hola", "assistant", success_calls.append, error_calls.append)

    assert worker.pipeline is pipeline
    assert worker.user_input == "hola"
    assert worker.mode == "assistant"
    assert len(worker.finished.callbacks) == 1
    worker.finished.callbacks[0]("assistant-result")
    assert success_calls == ["assistant-result"]
    assert worker.error.callbacks == [error_calls.append]
    assert worker.started is True
