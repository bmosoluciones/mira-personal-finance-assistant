# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tests for the AI engine factory (local parser + optional remote chat)."""

from __future__ import annotations

from pathlib import Path

from mira.ai.engine import get_chat_engine, get_engine
from mira.ai.llm_config import LlmConfig
from mira.ai.parser_engine import TransactionParserEngine
from mira.ai.remote_chat import RemoteChatEngine


def _config(
    *,
    provider: str = "openai_compatible",
    base_url: str = "http://localhost:1234/v1",
    model: str = "local-model",
    third_party_ack: bool = False,
    ack_host: str = "",
) -> LlmConfig:
    return LlmConfig(
        provider=provider,
        base_url=base_url,
        model=model,
        api_key="",
        interaction_mode="chat",
        third_party_ack=third_party_ack,
        ack_host=ack_host,
    )


def test_get_engine_without_model_uses_transaction_parser() -> None:
    engine = get_engine(model_path=None)
    assert isinstance(engine, TransactionParserEngine)


def test_get_engine_ignores_model_path() -> None:
    engine = get_engine(model_path=Path("/tmp/any.gguf"))
    assert isinstance(engine, TransactionParserEngine)


def test_get_chat_engine_returns_none_without_config() -> None:
    assert get_chat_engine(None) is None


def test_get_chat_engine_returns_none_when_provider_is_disabled() -> None:
    assert get_chat_engine(_config(provider="none", model="")) is None


def test_get_chat_engine_returns_none_when_model_is_missing() -> None:
    assert get_chat_engine(_config(model="")) is None


def test_get_chat_engine_returns_remote_engine_for_loopback_endpoint() -> None:
    engine = get_chat_engine(_config(), language="es")

    assert isinstance(engine, RemoteChatEngine)


def test_get_chat_engine_returns_none_for_cloud_endpoint_without_ack() -> None:
    config = _config(base_url="https://api.openai.com/v1", model="gpt-4o-mini")

    assert config.shares_with_third_party is True
    assert get_chat_engine(config) is None


def test_get_chat_engine_returns_remote_engine_for_acknowledged_cloud_endpoint() -> None:
    config = _config(
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        third_party_ack=True,
        ack_host="api.openai.com",
    )

    engine = get_chat_engine(config, language="en")

    assert isinstance(engine, RemoteChatEngine)


def test_get_chat_engine_returns_none_for_anthropic_without_ack() -> None:
    config = _config(provider="anthropic", base_url="", model="claude-3-5-haiku-latest")

    assert get_chat_engine(config) is None


def test_get_chat_engine_returns_remote_engine_for_acknowledged_anthropic() -> None:
    config = _config(
        provider="anthropic",
        base_url="",
        model="claude-3-5-haiku-latest",
        third_party_ack=True,
        ack_host="api.anthropic.com",
    )

    assert isinstance(get_chat_engine(config), RemoteChatEngine)


def test_get_chat_engine_rejects_stale_ack_for_a_different_host() -> None:
    config = _config(
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        third_party_ack=True,
        ack_host="some-other-host.example",
    )

    assert get_chat_engine(config) is None
