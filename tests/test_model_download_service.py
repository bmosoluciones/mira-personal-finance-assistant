# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import importlib


class _FakeDb:
    def __init__(self) -> None:
        self.saved: list[tuple[str, str]] = []
        self.setting = self._SettingFacade(self)

    class _SettingFacade:
        def __init__(self, db: "_FakeDb") -> None:
            self._db = db

        def set(self, key: str, value: str) -> None:
            self._db.saved.append((key, value))


class _FakeModelLifecycle:
    def __init__(self, state) -> None:
        self.state = state
        self.calls: list[tuple[str | None, str]] = []

    def reload_selected_model(self, active_runtime_path: str | None, interaction_mode: str):
        self.calls.append((active_runtime_path, interaction_mode))
        return self.state


def test_model_download_service_persists_selection_and_reload_state() -> None:
    module = importlib.import_module("mira.app.model_download_service")
    lifecycle_state = object()
    db = _FakeDb()
    lifecycle = _FakeModelLifecycle(lifecycle_state)
    service = module.ModelDownloadService(db, lifecycle)

    result = service.complete_default_download(
        filename="model.gguf",
        downloaded_path="C:/models/model.gguf",
        active_runtime_path="C:/runtime/old.gguf",
        interaction_mode="chat",
    )

    assert db.saved == [("preferred_model", "model.gguf")]
    assert lifecycle.calls == [("C:/runtime/old.gguf", "chat")]
    assert result.downloaded_path == "C:/models/model.gguf"
    assert result.preferred_model_name == "model.gguf"
    assert result.lifecycle_state is lifecycle_state
    assert result.refresh_settings is True
