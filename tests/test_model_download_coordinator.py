# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import importlib
from pathlib import Path

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


def test_model_download_worker_emits_progress_and_finished(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _get_qapplication(monkeypatch)
    module = importlib.import_module("mira.ui.coordinators.model_download_coordinator")

    def fake_download(url: str, dest_dir: Path, progress_callback, **_kwargs) -> Path:
        assert url == "https://example.invalid/model.gguf"
        assert dest_dir == tmp_path
        progress_callback(4, 8)
        progress_callback(8, 8)
        return dest_dir / "model.gguf"

    monkeypatch.setattr(module, "download_model_to", fake_download)

    worker = module.ModelDownloadWorker("https://example.invalid/model.gguf", tmp_path)
    progress: list[tuple[int, int]] = []
    finished: list[str] = []
    worker.progress.connect(lambda received, total: progress.append((received, total)))
    worker.finished_path.connect(finished.append)

    worker.run()

    assert progress == [(4, 8), (8, 8)]
    assert finished == [str(tmp_path / "model.gguf")]


def test_model_download_worker_emits_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _get_qapplication(monkeypatch)
    module = importlib.import_module("mira.ui.coordinators.model_download_coordinator")

    def fake_download(_url: str, _dest_dir: Path, progress_callback, **_kwargs) -> Path:
        progress_callback(1, 2)
        raise RuntimeError("network down")

    monkeypatch.setattr(module, "download_model_to", fake_download)

    worker = module.ModelDownloadWorker("https://example.invalid/model.gguf", tmp_path)
    errors: list[str] = []
    worker.error.connect(errors.append)

    worker.run()

    assert errors == ["network down"]


def test_model_download_worker_cancel_closes_response_and_suppresses_signals(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _get_qapplication(monkeypatch)
    module = importlib.import_module("mira.ui.coordinators.model_download_coordinator")

    class _FakeResponse:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    holder: dict[str, object] = {}
    response = _FakeResponse()

    def fake_download(
        _url: str, _dest_dir: Path, progress_callback, is_cancelled, on_response_opened, **_kwargs
    ) -> Path:
        on_response_opened(response)
        progress_callback(1, 2)
        worker = holder["worker"]
        worker.cancel()
        assert is_cancelled() is True
        raise module.DownloadCancelledError("cancelled")

    monkeypatch.setattr(module, "download_model_to", fake_download)

    worker = module.ModelDownloadWorker("https://example.invalid/model.gguf", tmp_path)
    holder["worker"] = worker
    errors: list[str] = []
    finished: list[str] = []
    worker.error.connect(errors.append)
    worker.finished_path.connect(finished.append)

    worker.run()

    assert response.close_calls == 1
    assert errors == []
    assert finished == []


def test_model_download_coordinator_returns_started_handle_and_cancel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = importlib.import_module("mira.ui.coordinators.model_download_coordinator")

    class DummySignal:
        def __init__(self) -> None:
            self.callbacks: list[object] = []

        def connect(self, callback) -> None:
            self.callbacks.append(callback)

    class FakeWorker:
        def __init__(self, url: str, dest_dir: Path) -> None:
            self.url = url
            self.dest_dir = dest_dir
            self.progress = DummySignal()
            self.finished_path = DummySignal()
            self.error = DummySignal()
            self.started = False
            self.cancel_calls = 0

        def start(self) -> None:
            self.started = True

        def cancel(self) -> None:
            self.cancel_calls += 1

    monkeypatch.setattr(module, "get_default_model_download_url", lambda: "https://example.invalid/model.gguf")
    monkeypatch.setattr(module, "model_filename_from_url", lambda _url: "model.gguf")
    monkeypatch.setattr(module, "get_writable_models_dir", lambda: tmp_path)
    monkeypatch.setattr(module, "ModelDownloadWorker", FakeWorker)

    progress_calls: list[tuple[int, int]] = []
    finish_calls: list[str] = []
    error_calls: list[str] = []
    coordinator = module.ModelDownloadCoordinator()

    handle = coordinator.start_default_download(progress_calls.append, finish_calls.append, error_calls.append)

    assert handle.filename == "model.gguf"
    assert handle.dest_dir == tmp_path
    assert handle.worker.started is True
    assert handle.worker.progress.callbacks == [progress_calls.append]
    assert handle.worker.finished_path.callbacks == [finish_calls.append]
    assert handle.worker.error.callbacks == [error_calls.append]

    handle.cancel()
    assert handle.worker.cancel_calls == 1
