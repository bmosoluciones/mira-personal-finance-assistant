# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Coordinator for background model downloads."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import threading

from PySide6.QtCore import QThread, Signal

from mira.ai.model_registry import (
    DownloadCancelledError,
    download_model_to,
    get_default_model_download_url,
    get_writable_models_dir,
    model_filename_from_url,
)


class ModelDownloadWorker(QThread):
    """Download a GGUF model in the background."""

    progress = Signal(int, int)
    finished_path = Signal(str)
    error = Signal(str)

    def __init__(self, url: str, dest_dir: Path) -> None:
        """Initialize the ModelDownloadWorker instance."""
        super().__init__()
        self._url = url
        self._dest_dir = dest_dir
        self._cancel_event = threading.Event()
        self._response_lock = threading.Lock()
        self._active_response: object | None = None

    def _set_active_response(self, response: object | None) -> None:
        """Return set active response."""
        with self._response_lock:
            self._active_response = response

    def cancel(self) -> None:
        """Return cancel."""
        self._cancel_event.set()
        with self._response_lock:
            response = self._active_response
        if response is None:
            return
        close = getattr(response, "close", None)
        if callable(close):
            close()

    def run(self) -> None:
        """Return run."""
        try:

            def _cb(received: int, total: int) -> None:
                """Return cb."""
                self.progress.emit(received, total)

            path = download_model_to(
                self._url,
                self._dest_dir,
                progress_callback=_cb,
                is_cancelled=self._cancel_event.is_set,
                on_response_opened=self._set_active_response,
            )
            if not self._cancel_event.is_set():
                self.finished_path.emit(str(path))
        except DownloadCancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            if self._cancel_event.is_set():
                return
            self.error.emit(str(exc))


class ModelDownloadHandle:
    """Bundle download metadata with the active worker."""

    def __init__(self, *, url: str, filename: str, dest_dir: Path, worker: ModelDownloadWorker) -> None:
        """Initialize the ModelDownloadHandle instance."""
        self.url = url
        self.filename = filename
        self.dest_dir = dest_dir
        self.worker = worker

    def cancel(self) -> None:
        """Return cancel."""
        self.worker.cancel()


class ModelDownloadCoordinator:
    """Start downloads for the configured default model."""

    def start_default_download(
        self,
        on_progress: Callable[[int, int], None],
        on_finished: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> ModelDownloadHandle:
        """Return start default download."""
        url = get_default_model_download_url()
        filename = model_filename_from_url(url)
        dest_dir = get_writable_models_dir()
        worker = ModelDownloadWorker(url, dest_dir)
        worker.progress.connect(on_progress)
        worker.finished_path.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()
        return ModelDownloadHandle(url=url, filename=filename, dest_dir=dest_dir, worker=worker)
