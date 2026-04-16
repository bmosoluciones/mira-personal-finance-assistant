# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Application service for the Settings view."""

from __future__ import annotations

from dataclasses import dataclass

from mira.db.database import Database
from mira.number_format import get_number_format_config, validate_number_format_config


@dataclass(frozen=True)
class SettingsViewState:
    username: str
    language: str
    theme: str
    default_currency: str
    thousands_sep: str
    decimal_sep: str
    preferred_model: str
    interaction_mode: str


class SettingsViewService:
    """Centralize settings persistence for the QWidget."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def load_state(self) -> SettingsViewState:
        number_format = get_number_format_config(self._db.setting)
        return SettingsViewState(
            username=str(self._db.setting.get("username") or ""),
            language=str(self._db.setting.get("language") or "es"),
            theme=str(self._db.setting.get("theme") or "dark_teal.xml"),
            default_currency=str(self._db.setting.get_default_currency() or "USD").strip().upper() or "USD",
            thousands_sep=number_format.thousands_sep,
            decimal_sep=number_format.decimal_sep,
            preferred_model=str(self._db.setting.get("preferred_model") or ""),
            interaction_mode=str(self._db.setting.get("llm_interaction_mode") or "assistant"),
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
    ) -> SettingsViewState:
        number_format = validate_number_format_config(thousands_sep, decimal_sep)
        self._db.setting.set("username", username)
        self._db.setting.set("language", language)
        self._db.setting.set("theme", theme)
        self._db.setting.set("default_currency", default_currency.strip().upper() or "USD")
        self._db.setting.set("number_thousands_separator", number_format.thousands_sep)
        self._db.setting.set("number_decimal_separator", number_format.decimal_sep)
        self._db.setting.set("preferred_model", preferred_model)
        self._db.setting.set("llm_interaction_mode", interaction_mode)
        return self.load_state()
