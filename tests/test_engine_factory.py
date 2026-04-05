# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tests for AI engine factory and llama runtime selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from mira.ai import engine as engine_module
from mira.ai.engine import _recommended_llama_kwargs, get_chat_engine, get_engine, is_llama_cpp_available
from mira.ai.parser_engine import TransactionParserEngine


def test_get_engine_without_model_uses_transaction_parser() -> None:
    engine = get_engine(model_path=None)
    assert isinstance(engine, TransactionParserEngine)


def test_get_chat_engine_without_model_returns_none() -> None:
    assert get_chat_engine(model_path=None) is None


def test_is_llama_cpp_available_uses_module_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    is_llama_cpp_available.cache_clear()
    monkeypatch.setattr(
        engine_module.importlib.util,
        "find_spec",
        lambda name: object() if name == "llama_cpp" else None,
    )

    assert is_llama_cpp_available() is True

    is_llama_cpp_available.cache_clear()


def test_get_chat_engine_returns_none_when_model_path_is_missing(tmp_path: Path) -> None:
    engine = get_chat_engine(model_path=tmp_path / "missing.gguf")
    assert engine is None


def test_get_chat_engine_returns_none_when_llama_cpp_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_text("stub", encoding="utf-8")

    monkeypatch.setattr(engine_module, "is_llama_cpp_available", lambda: False)

    assert get_chat_engine(model_path=model) is None


def test_get_chat_engine_uses_llama_cpp_engine_when_available(monkeypatch, tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_text("stub", encoding="utf-8")

    class DummyLlamaEngine:
        def __init__(self, model_path: str | Path, prompts=None, **kwargs: object) -> None:
            self.model_path = Path(model_path)
            self.prompts = prompts
            self.kwargs = kwargs

    monkeypatch.setattr(engine_module.chat_engine_module, "LlamaCppEngine", DummyLlamaEngine)
    monkeypatch.setattr(engine_module, "is_llama_cpp_available", lambda: True)

    engine = get_chat_engine(model_path=model)

    assert isinstance(engine, DummyLlamaEngine)
    assert engine.model_path == model
    assert engine.prompts is not None


def test_get_chat_engine_returns_none_when_llama_init_fails(monkeypatch, tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_text("stub", encoding="utf-8")

    class BrokenLlama:
        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError("llama-fail")

    monkeypatch.setattr(engine_module.chat_engine_module, "LlamaCppEngine", BrokenLlama)
    monkeypatch.setattr(engine_module, "is_llama_cpp_available", lambda: True)

    assert get_chat_engine(model_path=model) is None


def test_get_chat_engine_raises_unexpected_llama_init_errors(monkeypatch, tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_text("stub", encoding="utf-8")

    class BrokenLlama:
        def __init__(self, *_args, **_kwargs) -> None:
            raise AssertionError("unexpected-llama-fail")

    monkeypatch.setattr(engine_module.chat_engine_module, "LlamaCppEngine", BrokenLlama)
    monkeypatch.setattr(engine_module, "is_llama_cpp_available", lambda: True)

    with pytest.raises(AssertionError, match="unexpected-llama-fail"):
        get_chat_engine(model_path=model)


def test_recommended_llama_kwargs_raspberry_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIRA_LLAMA_PROFILE", "rpi")
    monkeypatch.setattr(engine_module.os, "cpu_count", lambda: 4)

    kwargs = _recommended_llama_kwargs({"n_ctx": 2048})

    assert kwargs["n_gpu_layers"] == 0
    assert kwargs["n_batch"] == 128
    assert kwargs["n_ctx"] == 2048
    assert kwargs["n_threads"] == 3


def test_recommended_llama_kwargs_uses_gpu_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MIRA_LLAMA_PROFILE", raising=False)
    monkeypatch.setattr(engine_module, "_looks_like_raspberry_pi", lambda: False)
    monkeypatch.setattr(engine_module, "_detect_gpu_layers_for_llama", lambda: -1)

    kwargs = _recommended_llama_kwargs({})

    assert kwargs["n_gpu_layers"] == -1


def test_recommended_llama_kwargs_gpu_override_on_rpi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIRA_LLAMA_PROFILE", "rpi")
    monkeypatch.setenv("MIRA_LLAMA_GPU_LAYERS", "12")
    monkeypatch.setattr(engine_module.os, "cpu_count", lambda: 4)

    kwargs = _recommended_llama_kwargs({})

    assert kwargs["n_gpu_layers"] == 12
    assert kwargs["n_threads"] == 3


def test_recommended_llama_kwargs_invalid_gpu_override_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIRA_LLAMA_GPU_LAYERS", "invalid")
    monkeypatch.setattr(engine_module, "_looks_like_raspberry_pi", lambda: False)

    kwargs = _recommended_llama_kwargs({})

    assert kwargs["n_gpu_layers"] in {0, -1}
