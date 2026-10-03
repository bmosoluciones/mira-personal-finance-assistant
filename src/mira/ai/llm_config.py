# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Remote chat configuration. API keys stay outside the SQLite backup."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from mira.db.database import Database

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_SECRET_NAME = "llm-secrets.json"


@dataclass(frozen=True)
class LlmConfig:
    """Provider settings used by the optional chat client."""

    provider: str
    base_url: str
    model: str
    api_key: str
    interaction_mode: str
    third_party_ack: bool
    ack_host: str

    @property
    def enabled(self) -> bool:
        """Return whether a provider and model are configured."""
        return self.provider in {"openai_compatible", "anthropic"} and bool(self.model.strip())

    @property
    def shares_with_third_party(self) -> bool:
        """Return whether chat text leaves this machine."""
        if not self.enabled:
            return False
        if self.provider == "anthropic":
            return True
        return not is_loopback_url(self.base_url)

    @property
    def chat_allowed(self) -> bool:
        """Return whether chat mode may run with the current consent."""
        if not self.enabled:
            return False
        if not self.shares_with_third_party:
            return True
        return self.third_party_ack and self.ack_host == endpoint_host(self)


def endpoint_host(config: LlmConfig) -> str:
    """Return the host that must be acknowledged before chat leaves the machine."""
    return endpoint_host_for(config.provider, config.base_url)


def endpoint_host_for(provider: str, base_url: str) -> str:
    """Return the host chat requests reach for a provider and base URL."""
    if str(provider or "").strip().lower() == "anthropic":
        return "api.anthropic.com"
    return url_host(base_url)


def url_host(url: str) -> str:
    """Return the hostname of a chat endpoint."""
    parsed = urlparse(url if "://" in url else f"http://{url}")
    return (parsed.hostname or "").strip().lower()


def is_loopback_host(host: str) -> bool:
    """Return whether a bare hostname stays on this machine."""
    return str(host or "").strip().lower() in _LOOPBACK_HOSTS


def is_loopback_url(url: str) -> bool:
    """Return whether the endpoint stays on this machine."""
    return is_loopback_host(url_host(url))


def secrets_path_for(db_path: Path) -> Path:
    """Return the sidecar path that stores the API key."""
    return db_path.parent / _SECRET_NAME


def read_api_key(db_path: Path) -> str:
    """Return the stored API key, or an empty string."""
    path = secrets_path_for(db_path)
    if not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("api_key") or "")


def write_api_key(db_path: Path, api_key: str) -> None:
    """Store the API key beside the database, not inside it."""
    path = secrets_path_for(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"api_key": api_key}).encode("utf-8")
    # Create the file already private: chmod after the fact would leave a
    # window where a freshly written key is readable by any local user.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        return


def clear_api_key(db_path: Path) -> None:
    """Forget the stored API key by removing the sidecar file."""
    try:
        secrets_path_for(db_path).unlink(missing_ok=True)
    except OSError:
        return


def load_llm_config(db: Database) -> LlmConfig:
    """Return the persisted remote-chat configuration."""
    provider = str(db.setting.get("llm_provider") or "none").strip().lower()
    if provider not in {"none", "openai_compatible", "anthropic"}:
        provider = "none"
    return LlmConfig(
        provider=provider,
        base_url=str(db.setting.get("llm_base_url") or "http://localhost:1234/v1").strip(),
        model=str(db.setting.get("llm_model") or "").strip(),
        api_key=read_api_key(db.path) if getattr(db, "path", None) else "",
        interaction_mode=str(db.setting.get("llm_interaction_mode") or "assistant").strip() or "assistant",
        third_party_ack=str(db.setting.get("llm_third_party_ack") or "0") == "1",
        ack_host=str(db.setting.get("llm_ack_host") or "").strip().lower(),
    )


def mcp_enabled(db: Database) -> bool:
    """Return whether the user accepted the MCP third-party warning."""
    return str(db.setting.get("mcp_enabled") or "0") == "1" and str(db.setting.get("mcp_third_party_ack") or "0") == "1"
