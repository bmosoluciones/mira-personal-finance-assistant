# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Factory and runtime helpers for MIRA AI engines."""

from __future__ import annotations

import logging
from typing import Any

from mira.ai import parser_engine as parser_engine_module
from mira.ai.base_engine import BaseEngine
from mira.ai.llm_config import LlmConfig
from mira.ai.prompt_assets import PromptAssets
from mira.ai.remote_chat import RemoteChatEngine

logger = logging.getLogger(__name__)


def get_chat_engine(config: LlmConfig | None = None, **kwargs: Any) -> BaseEngine | None:
    """Return an HTTP chat engine when the user enabled a provider."""
    if config is None or not config.chat_allowed:
        logger.info("Remote chat is not configured or not allowed; chat mode remains disabled.")
        return None
    language = str(kwargs.pop("language", "en"))
    return RemoteChatEngine(config, language=language)


def get_engine() -> BaseEngine:
    """Return the deterministic parser. Remote chat is optional and separate."""
    return parser_engine_module.TransactionParserEngine(prompts=PromptAssets())
