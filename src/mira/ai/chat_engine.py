# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""GGUF-backed chat engine implementation."""

from __future__ import annotations

import json
import importlib
import logging
from pathlib import Path
from typing import Any

from mira.ai.base_engine import BaseEngine
from mira.ai.prompt_assets import PromptAssets
from mira.ai.schema_contract import build_chat_system_prompt

logger = logging.getLogger(__name__)


def _normalize_chat_language(language: str | None) -> str:
    normalized = str(language or "en").strip().lower()
    return "es" if normalized == "es" else "en"


def _load_llama_class() -> type[Any]:
    try:
        llama_module = importlib.import_module("llama_cpp")
    except ImportError as exc:
        raise ImportError("llama-cpp-python is required to use LlamaCppEngine") from exc
    return getattr(llama_module, "Llama")


class LlamaCppEngine(BaseEngine):
    """Engine backed by a local GGUF model via ``llama-cpp-python``."""

    def __init__(
        self,
        model_path: str | Path,
        prompts: PromptAssets | None = None,
        *,
        language: str = "en",
        **kwargs: Any,
    ) -> None:
        self._model_path = Path(model_path)
        self._prompts = prompts or PromptAssets()
        self._language = _normalize_chat_language(language)
        llama_class = _load_llama_class()
        logger.info("Loading model from %s", self._model_path)
        self._llm = llama_class(
            model_path=str(self._model_path),
            n_ctx=kwargs.get("n_ctx", 2048),
            n_threads=kwargs.get("n_threads", None),
            n_batch=kwargs.get("n_batch", 256),
            n_gpu_layers=kwargs.get("n_gpu_layers", 0),
            verbose=kwargs.get("verbose", False),
        )
        logger.info("Model loaded.")

    def parse(self, user_input: str) -> dict[str, Any]:
        prompt = self._prompts.build_parser_prompt(user_input)
        output = self._llm(
            prompt,
            max_tokens=128,
            temperature=0.0,
            stop=["\n", "User:"],
        )
        raw = output["choices"][0]["text"].strip()
        logger.debug("LLM raw output: %r", raw)
        return json.loads(raw)

    def set_language(self, language: str) -> None:
        self._language = _normalize_chat_language(language)

    def chat(self, user_input: str) -> str:
        prompt = (
            build_chat_system_prompt(self._language) + " Reply conversationally in the user's language. "
            "Do not force JSON in this mode.\n"
            f"User: {user_input}\nAssistant:"
        )
        output = self._llm(prompt, max_tokens=256, temperature=0.5, stop=["User:"])
        return output["choices"][0]["text"].strip()
