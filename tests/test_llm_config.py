# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tests for remote chat configuration, consent gating, and secret storage."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from mira.ai.llm_config import (
    LlmConfig,
    clear_api_key,
    endpoint_host,
    is_loopback_url,
    load_llm_config,
    mcp_enabled,
    read_api_key,
    secrets_path_for,
    url_host,
    write_api_key,
)
from mira.db.database import Database


@pytest.fixture
def db(tmp_path: Path):
    database = Database(path=tmp_path / "llm-config.db")
    database.connect()
    yield database
    database.close()


def _config(**overrides: object) -> LlmConfig:
    payload: dict[str, object] = {
        "provider": "openai_compatible",
        "base_url": "http://localhost:1234/v1",
        "model": "local-model",
        "api_key": "",
        "interaction_mode": "chat",
        "third_party_ack": False,
        "ack_host": "",
    }
    payload.update(overrides)
    return LlmConfig(**payload)  # type: ignore[arg-type]


def test_url_host_normalizes_missing_scheme_and_case() -> None:
    assert url_host("HTTP://LocalHost:1234/v1") == "localhost"
    assert url_host("127.0.0.1:11434/v1") == "127.0.0.1"
    assert url_host("https://API.OpenAI.com/v1") == "api.openai.com"
    assert url_host("") == ""


def test_is_loopback_url_only_accepts_local_hosts() -> None:
    assert is_loopback_url("http://localhost:1234/v1") is True
    assert is_loopback_url("http://127.0.0.1:11434/v1") is True
    assert is_loopback_url("http://[::1]:8080/v1") is True
    assert is_loopback_url("https://api.openai.com/v1") is False
    assert is_loopback_url("http://192.168.1.10:1234/v1") is False


def test_endpoint_host_returns_anthropic_host_for_anthropic_provider() -> None:
    assert endpoint_host(_config(provider="anthropic")) == "api.anthropic.com"
    assert endpoint_host(_config(base_url="https://api.openai.com/v1")) == "api.openai.com"


def test_chat_allowed_matrix() -> None:
    assert _config().chat_allowed is True
    assert _config(provider="none", model="").chat_allowed is False
    assert _config(model="").chat_allowed is False

    cloud = _config(base_url="https://api.openai.com/v1")
    assert cloud.shares_with_third_party is True
    assert cloud.chat_allowed is False

    acknowledged = _config(
        base_url="https://api.openai.com/v1",
        third_party_ack=True,
        ack_host="api.openai.com",
    )
    assert acknowledged.chat_allowed is True

    stale = _config(
        base_url="https://api.openai.com/v1",
        third_party_ack=True,
        ack_host="old-host.example",
    )
    assert stale.chat_allowed is False

    anthropic = _config(provider="anthropic", base_url="", model="claude")
    assert anthropic.chat_allowed is False
    anthropic_ack = _config(
        provider="anthropic",
        base_url="",
        model="claude",
        third_party_ack=True,
        ack_host="api.anthropic.com",
    )
    assert anthropic_ack.chat_allowed is True


def test_write_api_key_stores_secret_beside_database_with_owner_only_permissions(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "data" / "mira.db"
    db_path.parent.mkdir(parents=True)

    write_api_key(db_path, "sk-123")

    secret_path = secrets_path_for(db_path)
    assert secret_path == db_path.parent / "llm-secrets.json"
    assert secret_path.is_file()
    assert read_api_key(db_path) == "sk-123"
    mode = stat.S_IMODE(secret_path.stat().st_mode)
    assert mode & (stat.S_IRWXG | stat.S_IRWXO) == 0


def test_read_api_key_returns_empty_for_missing_or_corrupt_file(tmp_path: Path) -> None:
    db_path = tmp_path / "mira.db"

    assert read_api_key(db_path) == ""

    secret_path = secrets_path_for(db_path)
    secret_path.write_text("{not json", encoding="utf-8")
    assert read_api_key(db_path) == ""

    secret_path.write_text('["not", "a", "dict"]', encoding="utf-8")
    assert read_api_key(db_path) == ""


def test_load_llm_config_reads_persisted_settings_and_secret(db: Database) -> None:
    db.setting.set("llm_provider", "openai_compatible")
    db.setting.set("llm_base_url", "http://127.0.0.1:11434/v1")
    db.setting.set("llm_model", "llama3.2")
    db.setting.set("llm_third_party_ack", "1")
    db.setting.set("llm_ack_host", "127.0.0.1")
    write_api_key(db.path, "local-key")

    config = load_llm_config(db)

    assert config.provider == "openai_compatible"
    assert config.base_url == "http://127.0.0.1:11434/v1"
    assert config.model == "llama3.2"
    assert config.api_key == "local-key"
    assert config.third_party_ack is True
    assert config.ack_host == "127.0.0.1"
    assert config.chat_allowed is True


def test_load_llm_config_rejects_unknown_provider(db: Database) -> None:
    db.setting.set("llm_provider", "made-up-provider")

    assert load_llm_config(db).provider == "none"


def test_mcp_enabled_requires_both_flags(db: Database) -> None:
    assert mcp_enabled(db) is False

    db.setting.set("mcp_enabled", "1")
    assert mcp_enabled(db) is False

    db.setting.set("mcp_third_party_ack", "1")
    assert mcp_enabled(db) is True

    db.setting.set("mcp_enabled", "0")
    assert mcp_enabled(db) is False


def test_write_api_key_creates_the_sidecar_private_from_the_start(tmp_path: Path) -> None:
    db_path = tmp_path / "mira.db"

    write_api_key(db_path, "sk-secret")

    mode = secrets_path_for(db_path).stat().st_mode
    assert stat.S_IMODE(mode) == stat.S_IRUSR | stat.S_IWUSR
    assert read_api_key(db_path) == "sk-secret"


def test_write_api_key_repairs_permissions_of_an_existing_file(tmp_path: Path) -> None:
    db_path = tmp_path / "mira.db"
    secret_path = secrets_path_for(db_path)
    secret_path.write_text('{"api_key": "old"}', encoding="utf-8")
    secret_path.chmod(0o644)

    write_api_key(db_path, "new")

    assert stat.S_IMODE(secret_path.stat().st_mode) == stat.S_IRUSR | stat.S_IWUSR
    assert read_api_key(db_path) == "new"


def test_clear_api_key_removes_the_sidecar_and_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "mira.db"
    write_api_key(db_path, "sk-secret")

    clear_api_key(db_path)

    assert not secrets_path_for(db_path).exists()
    assert read_api_key(db_path) == ""
    clear_api_key(db_path)
    assert read_api_key(db_path) == ""
