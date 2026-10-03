# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Application service for the Settings view."""

from __future__ import annotations

from dataclasses import dataclass

from mira.ai.llm_config import clear_api_key, load_llm_config, write_api_key
from mira.db.database import Database
from mira.number_format import get_number_format_config, validate_number_format_config


@dataclass(frozen=True)
class SettingsViewState:
    """Represent the SettingsViewState class."""

    username: str

    language: str
    theme: str
    default_currency: str
    thousands_sep: str
    decimal_sep: str
    preferred_model: str
    interaction_mode: str
    llm_provider: str = "none"
    llm_base_url: str = "http://localhost:1234/v1"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_third_party_ack: bool = False
    llm_ack_host: str = ""
    mcp_enabled: bool = False


class SettingsViewService:
    """Centralize settings persistence for the QWidget."""

    def __init__(self, db: Database) -> None:
        """Initialize the SettingsViewService instance."""
        self._db = db

    def load_state(self) -> SettingsViewState:
        """Return load state."""
        number_format = get_number_format_config(self._db.setting)
        llm = load_llm_config(self._db)
        return SettingsViewState(
            username=str(self._db.setting.get("username") or ""),
            language=str(self._db.setting.get("language") or "es"),
            theme=str(self._db.setting.get("theme") or "dark_teal.xml"),
            default_currency=str(self._db.setting.get_default_currency() or "USD").strip().upper() or "USD",
            thousands_sep=number_format.thousands_sep,
            decimal_sep=number_format.decimal_sep,
            preferred_model=str(self._db.setting.get("preferred_model") or ""),
            interaction_mode=str(self._db.setting.get("llm_interaction_mode") or "assistant"),
            llm_provider=llm.provider,
            llm_base_url=llm.base_url,
            llm_model=llm.model,
            llm_api_key=llm.api_key,
            llm_third_party_ack=llm.third_party_ack,
            llm_ack_host=llm.ack_host,
            mcp_enabled=str(self._db.setting.get("mcp_enabled") or "0") == "1",
        )

    def save(
        self,
        *,
        username: str,
        language: str,
        theme: str,
        default_currency: str,
        thousands_sep: str,
        decimal_sep: str,
        preferred_model: str,
        interaction_mode: str,
        llm_provider: str = "none",
        llm_base_url: str = "http://localhost:1234/v1",
        llm_model: str = "",
        llm_api_key: str | None = None,
        llm_third_party_ack: bool = False,
        llm_ack_host: str = "",
        mcp_enabled: bool = False,
        mcp_third_party_ack: bool = False,
    ) -> SettingsViewState:
        """Return save."""
        number_format = validate_number_format_config(thousands_sep, decimal_sep)
        self._db.setting.set("username", username)
        self._db.setting.set("language", language)
        self._db.setting.set("theme", theme)
        self._db.setting.set("default_currency", default_currency.strip().upper() or "USD")
        self._db.setting.set("number_thousands_separator", number_format.thousands_sep)
        self._db.setting.set("number_decimal_separator", number_format.decimal_sep)
        self._db.setting.set("preferred_model", preferred_model)
        self._db.setting.set("llm_interaction_mode", interaction_mode)
        provider = llm_provider if llm_provider in {"none", "openai_compatible", "anthropic"} else "none"
        self._db.setting.set("llm_provider", provider)
        self._db.setting.set("llm_base_url", llm_base_url.strip() or "http://localhost:1234/v1")
        self._db.setting.set("llm_model", llm_model.strip())
        self._db.setting.set("llm_third_party_ack", "1" if llm_third_party_ack else "0")
        self._db.setting.set("llm_ack_host", llm_ack_host.strip().lower())
        self._db.setting.set("mcp_enabled", "1" if mcp_enabled else "0")
        self._db.setting.set("mcp_third_party_ack", "1" if mcp_third_party_ack else "0")
        if llm_api_key is not None:
            write_api_key(self._db.path, llm_api_key)
        return self.load_state()

    def forget_api_key(self) -> SettingsViewState:
        """Delete the stored API key and return the resulting state."""
        clear_api_key(self._db.path)
        return self.load_state()
