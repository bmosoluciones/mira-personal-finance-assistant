# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from mira.ai.base_engine import BaseEngine


class _ParseOnlyEngine(BaseEngine):
    def parse(self, user_input: str) -> dict[str, str]:
        return {"input": user_input}


def test_base_engine_default_chat_raises_not_implemented() -> None:
    engine = _ParseOnlyEngine()

    with pytest.raises(NotImplementedError, match="does not support chat mode"):
        engine.chat("hola")

    assert engine.parse("hola") == {"input": "hola"}
    assert engine.set_language("es") is None


def test_llama_cpp_engine_parses_and_chats_with_language_normalization(monkeypatch, tmp_path) -> None:
    instances: list[object] = []

    class FakeLlama:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.calls: list[tuple[str, dict[str, object]]] = []
            instances.append(self)

        def __call__(self, prompt: str, **kwargs):
            self.calls.append((prompt, kwargs))
            if prompt.startswith("PARSE::"):
                return {"choices": [{"text": ' {"action": "add_income", "amount": 50} '}]}
            return {"choices": [{"text": " Chat reply "}]}

    monkeypatch.setitem(sys.modules, "llama_cpp", SimpleNamespace(Llama=FakeLlama))
    module = __import__("mira.ai.chat_engine", fromlist=["dummy"])

    monkeypatch.setattr(module, "build_chat_system_prompt", lambda language: f"SYSTEM[{language}]")

    class FakePrompts:
        def build_parser_prompt(self, user_input: str) -> str:
            return f"PARSE::{user_input}"

    engine = module.LlamaCppEngine(
        tmp_path / "finance.gguf",
        prompts=FakePrompts(),
        language="ES",
        n_ctx=4096,
        n_batch=64,
        verbose=True,
    )

    parsed = engine.parse("Registrar ingreso")
    first_reply = engine.chat("Hola")
    engine.set_language("pt")
    second_reply = engine.chat("Hello")

    assert parsed == {"action": "add_income", "amount": 50}
    assert first_reply == "Chat reply"
    assert second_reply == "Chat reply"

    llm = instances[0]
    assert llm.kwargs["model_path"].endswith("finance.gguf")
    assert llm.kwargs["n_ctx"] == 4096
    assert llm.kwargs["n_batch"] == 64
    assert llm.kwargs["verbose"] is True
    assert llm.calls[0][0] == "PARSE::Registrar ingreso"
    assert llm.calls[1][0].startswith("SYSTEM[es]")
    assert "User: Hola" in llm.calls[1][0]
    assert llm.calls[2][0].startswith("SYSTEM[en]")
    assert llm.calls[0][1]["temperature"] == 0.0
    assert llm.calls[1][1]["temperature"] == 0.5
