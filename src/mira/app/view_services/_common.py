# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Shared contracts for UI-facing application services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mira.db.database import Database
from mira.number_format import (
    NumberFormatConfig,
    format_number as _format_number,
    get_number_format_config as _get_number_format_config,
)
from mira.ui.i18n import normalize_language, tr


@dataclass(frozen=True)
class OperationFeedback:
    """Minimal result contract for view command operations."""

    selected_id: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PresentationContext:
    """Snapshot of user-facing formatting and translation preferences."""

    language: str
    number_format: NumberFormatConfig
    default_currency: str
    account_type_labels: dict[str, str]

    @classmethod
    def from_db(cls, db: Database) -> PresentationContext:
        language = normalize_language(db.setting.get("language"))
        return cls(
            language=language,
            number_format=_get_number_format_config(db.setting),
            default_currency=str(db.setting.get_default_currency() or "").strip().upper(),
            account_type_labels={
                "bank": tr("accounts.type.bank", language, default="bank"),
                "cash": tr("accounts.type.cash", language, default="cash"),
                "credit": tr("accounts.type.credit", language, default="credit"),
            },
        )

    def translate(
        self,
        key: str,
        default: str,
        *,
        params: dict[str, object] | None = None,
    ) -> str:
        return tr(key, self.language, default=default, params=params)

    def format_amount(self, amount: float, *, decimals: int = 2) -> str:
        return _format_number(float(amount), self.number_format, decimals=decimals, grouping=True)

    def format_amount_with_currency(self, amount: float, currency: str | None, *, decimals: int = 2) -> str:
        normalized_currency = str(currency or "").strip().upper()
        formatted_amount = self.format_amount(amount, decimals=decimals)
        return f"{normalized_currency} {formatted_amount}" if normalized_currency else formatted_amount

    def account_type_label(self, account_type: str) -> str:
        normalized = str(account_type or "bank").strip().lower()
        if normalized == "card":
            normalized = "credit"
        return self.account_type_labels.get(normalized, normalized)
