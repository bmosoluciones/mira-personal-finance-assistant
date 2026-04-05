# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import importlib
from pathlib import Path


class _FakeDb:
    def __init__(
        self,
        *,
        preferred_model: str = "",
        mode: str = "assistant",
        language: str = "es",
    ) -> None:
        self._settings = {
            "preferred_model": preferred_model,
            "llm_interaction_mode": mode,
            "language": language,
        }
        self.setting = self._SettingFacade(self)

    class _SettingFacade:
        def __init__(self, db: "_FakeDb") -> None:
            self._db = db

        def get(self, key: str) -> str:
            return self._db._settings.get(key, "")

        def set(self, key: str, value: str) -> None:
            self._db._settings[key] = value


class _FakePipeline:
    def __init__(self, *, llm_ready: bool, chat_engine: object | None = None) -> None:
        self.engine = type("ParserEngine", (), {})()
        self.chat_engine = chat_engine
        self.llm_ready = llm_ready
        self.reload_calls: list[str | None] = []

    def reload_engine(self, model_path: str | None) -> None:
        self.reload_calls.append(model_path)


def test_model_lifecycle_uses_selected_model_when_found(monkeypatch, tmp_path: Path) -> None:
    module = importlib.import_module("mira.services.model_lifecycle")
    selected_path = tmp_path / "selected.gguf"
    selected_path.write_text("x", encoding="utf-8")
    monkeypatch.setattr(module, "find_model_path_by_name", lambda _name: selected_path)

    db = _FakeDb(preferred_model="selected.gguf")
    pipeline = _FakePipeline(llm_ready=True, chat_engine=type("ChatEngine", (), {})())
    lifecycle = module.ModelLifecycle(db, pipeline)

    state = lifecycle.reload_selected_model(None, "assistant")

    assert pipeline.reload_calls == [str(selected_path)]
    assert state.active_model_name == "selected.gguf"
    assert state.active_model_path == str(selected_path)
    assert state.engine_info == "ParserEngine + ChatEngine (selected.gguf)"
    assert state.mode_visible is True
    assert state.status_message == "Cargando modelo LLM seleccionado: selected.gguf"


def test_model_lifecycle_falls_back_to_runtime_model_when_selected_is_missing(
    monkeypatch,
) -> None:
    module = importlib.import_module("mira.services.model_lifecycle")
    monkeypatch.setattr(module, "find_model_path_by_name", lambda _name: None)

    db = _FakeDb(preferred_model="missing.gguf")
    pipeline = _FakePipeline(llm_ready=True, chat_engine=type("ChatEngine", (), {})())
    lifecycle = module.ModelLifecycle(db, pipeline)

    state = lifecycle.sync_engine_info("C:/runtime/model.gguf")

    assert state.active_model_name == ""
    assert state.active_model_path == "C:/runtime/model.gguf"
    assert state.engine_info == "ParserEngine + ChatEngine (C:/runtime/model.gguf)"
    assert state.status_message == "Usando modelo LLM definido por CLI."


def test_model_lifecycle_forces_chat_mode_back_to_assistant_when_llm_is_unavailable(
    monkeypatch,
) -> None:
    module = importlib.import_module("mira.services.model_lifecycle")
    monkeypatch.setattr(module, "find_model_path_by_name", lambda _name: None)

    db = _FakeDb(mode="chat")
    pipeline = _FakePipeline(llm_ready=False)
    lifecycle = module.ModelLifecycle(db, pipeline)

    state = lifecycle.sync_engine_info(None)

    assert state.engine_info == "ParserEngine"
    assert state.mode_visible is False
    assert state.forced_mode == "assistant"
    assert state.mode_warning == "El modo chat requiere un modelo GGUF activo. Regresando a modo asistente."
    assert db.setting.get("llm_interaction_mode") == "assistant"


def test_model_lifecycle_syncs_engine_info_without_selected_model(monkeypatch) -> None:
    module = importlib.import_module("mira.services.model_lifecycle")
    monkeypatch.setattr(module, "find_model_path_by_name", lambda _name: None)

    db = _FakeDb(preferred_model="", language="en")
    pipeline = _FakePipeline(llm_ready=True, chat_engine=type("ChatEngine", (), {})())
    lifecycle = module.ModelLifecycle(db, pipeline)

    state = lifecycle.sync_engine_info(None)

    assert state.engine_info == "ParserEngine + ChatEngine"
    assert state.status_message is None
