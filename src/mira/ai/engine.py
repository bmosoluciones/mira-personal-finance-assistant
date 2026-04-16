# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Factory and runtime helpers for MIRA AI engines."""

from __future__ import annotations

import importlib.util
import logging
import os
from functools import lru_cache
from pathlib import Path
import platform
from typing import Any

from mira.ai import chat_engine as chat_engine_module
from mira.ai import parser_engine as parser_engine_module
from mira.ai.base_engine import BaseEngine
from mira.ai.prompt_assets import PromptAssets

logger = logging.getLogger(__name__)


def _looks_like_raspberry_pi() -> bool:
    """Return looks like raspberry pi."""
    profile = os.getenv("MIRA_LLAMA_PROFILE", "").strip().lower()
    if profile in {"raspberry", "raspberry-pi", "rpi"}:
        return True

    if platform.machine().lower() not in {"armv7l", "aarch64", "arm64"}:
        return False

    model_path = Path("/proc/device-tree/model")
    if model_path.is_file():
        try:
            model = model_path.read_text(encoding="utf-8", errors="ignore").strip("\x00\n ").lower()
        except OSError:
            return False
        return "raspberry pi" in model
    return False


def _detect_gpu_layers_for_llama() -> int:
    """Detect whether llama.cpp can offload layers to GPU at runtime."""
    forced = os.getenv("MIRA_LLAMA_GPU_LAYERS", "").strip()
    if forced:
        try:
            return int(forced)
        except ValueError:
            logger.warning("Invalid MIRA_LLAMA_GPU_LAYERS=%r; using auto-detection", forced)

    try:
        from llama_cpp import llama_cpp  # type: ignore[import]

        supports_offload = getattr(llama_cpp, "llama_supports_gpu_offload", None)
        if callable(supports_offload) and bool(supports_offload()):
            return -1
    except (AttributeError, ImportError, OSError) as exc:
        logger.debug("GPU offload detection unavailable, falling back to CPU: %s", exc)

    return 0


def _recommended_llama_kwargs(overrides: dict[str, Any]) -> dict[str, Any]:
    """Return llama.cpp defaults tuned for current hardware profile."""
    tuned: dict[str, Any] = {"n_gpu_layers": _detect_gpu_layers_for_llama(), "n_batch": 128}
    if _looks_like_raspberry_pi():
        if "MIRA_LLAMA_GPU_LAYERS" not in os.environ:
            tuned["n_gpu_layers"] = 0
        tuned["n_ctx"] = 1024
        cores = os.cpu_count() or 1
        tuned["n_threads"] = max(1, cores - 1)
    for key, value in overrides.items():
        tuned[key] = value
    return tuned


@lru_cache(maxsize=1)
def is_llama_cpp_available() -> bool:
    """Return whether llama-cpp-python is installed in the current environment."""
    try:
        return importlib.util.find_spec("llama_cpp") is not None
    except (AttributeError, ImportError, ValueError) as exc:
        logger.debug("llama-cpp-python availability check failed: %s", exc)
        return False


def get_chat_engine(model_path: str | Path | None = None, **kwargs: Any) -> BaseEngine | None:
    """Return an optional local GGUF-backed engine for chat mode."""
    if model_path is None:
        logger.info("No model path provided; chat mode remains disabled.")
        return None

    if not is_llama_cpp_available():
        logger.info("llama-cpp-python is not installed; chat mode remains disabled.")
        return None

    resolved_model_path = Path(model_path)
    if not resolved_model_path.is_file():
        logger.warning("Model file not found at %s; chat mode remains disabled.", resolved_model_path)
        return None

    try:
        language = str(kwargs.pop("language", "en"))
        llama_kwargs = _recommended_llama_kwargs(kwargs)
        return chat_engine_module.LlamaCppEngine(
            model_path=resolved_model_path,
            prompts=PromptAssets(),
            language=language,
            **llama_kwargs,
        )
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        logger.warning("Could not initialize local chat engine: %s", exc)
        return None


def get_engine(model_path: str | Path | None = None, **kwargs: Any) -> BaseEngine:
    """Return the optional chat engine or the deterministic parser fallback."""
    return get_chat_engine(model_path, **kwargs) or parser_engine_module.TransactionParserEngine(prompts=PromptAssets())
