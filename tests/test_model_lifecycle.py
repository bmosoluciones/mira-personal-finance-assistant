# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import importlib
from pathlib import Path


class _FakeDb:
    def __init__(
        self,
        *,
        mode: str = "assistant",
        language: str = "es",
        provider: str = "none",
        model: str = "",
        base_url: str = "http://localhost:1234/v1",
        ack: str = "0",
        ack_host: str = "",
    ) -> None:
        self.path = Path("/tmp/mira-lifecycle.db")
        self._settings = {
            "llm_interaction_mode": mode,
            "language": language,
            "llm_provider": provider,
            "llm_model": model,
            "llm_base_url": base_url,
            "llm_third_party_ack": ack,
            "llm_ack_host": ack_host,
        }
        self.setting = self._SettingFacade(self)

    class _SettingFacade:
        def __init__(self, db: _FakeDb) -> None:
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
        self.reload_calls: list[None] = []

    def reload_engine(self) -> None:
        self.reload_calls.append(None)


def test_model_lifecycle_uses_local_provider_when_configured() -> None:
    module = importlib.import_module("mira.services.model_lifecycle")
    db = _FakeDb(provider="openai_compatible", model="local-model", base_url="http://127.0.0.1:1234/v1")
    pipeline = _FakePipeline(llm_ready=True, chat_engine=type("RemoteChatEngine", (), {})())
    lifecycle = module.ModelLifecycle(db, pipeline)

    state = lifecycle.reload_selected_model("assistant")

    assert pipeline.reload_calls == [None]
    assert state.active_model_name == "local-model"
    assert state.mode_visible is True


def test_model_lifecycle_ignores_cloud_provider_without_ack() -> None:
    module = importlib.import_module("mira.services.model_lifecycle")
    db = _FakeDb(provider="anthropic", model="claude", mode="chat")
    pipeline = _FakePipeline(llm_ready=False)
    lifecycle = module.ModelLifecycle(db, pipeline)

    state = lifecycle.sync_engine_info(None)

    assert state.mode_visible is False
    assert state.forced_mode == "assistant"
    assert db.setting.get("llm_interaction_mode") == "assistant"


def test_model_lifecycle_shows_chat_when_cloud_ack_matches_host() -> None:
    module = importlib.import_module("mira.services.model_lifecycle")
    db = _FakeDb(provider="anthropic", model="claude", ack="1", ack_host="api.anthropic.com", language="en")
    pipeline = _FakePipeline(llm_ready=True, chat_engine=type("RemoteChatEngine", (), {})())
    lifecycle = module.ModelLifecycle(db, pipeline)

    state = lifecycle.sync_engine_info(None)

    assert state.active_model_name == "claude"
    assert state.mode_visible is True
    assert state.forced_mode is None
