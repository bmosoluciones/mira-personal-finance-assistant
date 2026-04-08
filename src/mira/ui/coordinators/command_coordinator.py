# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Background execution coordinator for the assistant pipeline."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from PySide6.QtCore import QThread, Qt, Signal

from mira.ai.executor import ActionResult
from mira.ai.pipeline import Pipeline


class PipelineCommandWorker(QThread):
    """Run the pipeline in the background so the UI stays responsive."""

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, pipeline: Pipeline, user_input: str, mode: str = "assistant") -> None:
        super().__init__()
        self._pipeline = pipeline
        self._user_input = user_input
        self._mode = mode

    def run(self) -> None:
        try:
            result: ActionResult
            if self._mode == "chat":
                result = self._pipeline.process_chat(self._user_input)
            else:
                result = self._pipeline.process(self._user_input)
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


class CommandCoordinator:
    """Create, connect, and start pipeline workers."""

    def __init__(self, pipeline: Pipeline) -> None:
        self._pipeline = pipeline

    def execute(
        self,
        text: str,
        mode: str,
        on_success: Callable[[ActionResult], None],
        on_error: Callable[[str], None],
    ) -> QThread:
        worker = PipelineCommandWorker(self._pipeline, text, mode)

        def success_handler(result: object) -> None:
            on_success(cast(ActionResult, result))

        try:
            worker.finished.connect(success_handler, Qt.ConnectionType.QueuedConnection)
        except TypeError:
            worker.finished.connect(success_handler)
        try:
            worker.error.connect(on_error, Qt.ConnectionType.QueuedConnection)
        except TypeError:
            worker.error.connect(on_error)
        worker.start()
        return worker
