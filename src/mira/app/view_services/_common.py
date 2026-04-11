# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Shared contracts for UI-facing application services."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from mira.db.database import Database
from mira.number_format import (
    NumberFormatConfig,
    format_number as _format_number,
    get_number_format_config as _get_number_format_config,
)
from mira.ui.i18n import normalize_language, tr


class AnalyticsSemanticRole(StrEnum):
    """Semantic roles used across analytics charts and legends."""

    INCOME = "income"
    EXPENSE = "expense"
    NET = "net"
    SECONDARY = "secondary"
    BUDGET = "budget"
    ACTUAL = "actual"
    FINANCING = "financing"
    SAVINGS = "savings"
    FLOW_TOTAL = "flow_total"


class WaterfallStepKind(StrEnum):
    """Known step kinds emitted by the MIRA waterfall payload."""

    INCOME_TOTAL = "income_total"
    EXPENSE = "expense"
    FINANCING = "financing"
    SAVINGS_ALLOCATION = "savings_allocation"
    DEFICIT_TOTAL = "deficit_total"
    SURPLUS_TOTAL = "surplus_total"
    MONTH_BALANCE = "month_balance"
    FINAL_TOTAL = "final_total"


@dataclass(frozen=True)
class AnalyticsPalette:
    """Immutable analytics palette with typed lookup helpers."""

    multicolor: tuple[str, ...]
    semantic: Mapping[AnalyticsSemanticRole, str]
    waterfall: Mapping[WaterfallStepKind, str]

    def palette_hex(self, index: int) -> str:
        return self.multicolor[index % len(self.multicolor)]

    def semantic_hex(self, role: AnalyticsSemanticRole) -> str:
        return self.semantic[role]

    def waterfall_hex(self, kind: WaterfallStepKind) -> str:
        return self.waterfall[kind]


def try_parse_waterfall_step_kind(value: object) -> WaterfallStepKind | None:
    if not value:
        return None
    try:
        return WaterfallStepKind(str(value).strip().lower())
    except ValueError:
        return None


ANALYTICS_PALETTE = AnalyticsPalette(
    multicolor=(
        "#2EC4B6",
        "#4D96FF",
        "#FF6B6B",
        "#F4A261",
        "#8AC926",
        "#00B8D9",
        "#FF9F1C",
        "#FF4D8D",
    ),
    semantic=MappingProxyType(
        {
            AnalyticsSemanticRole.INCOME: "#2EC4B6",
            AnalyticsSemanticRole.EXPENSE: "#FF6B6B",
            AnalyticsSemanticRole.NET: "#4D96FF",
            AnalyticsSemanticRole.SECONDARY: "#00B8D9",
            AnalyticsSemanticRole.BUDGET: "#4D96FF",
            AnalyticsSemanticRole.ACTUAL: "#FF6B6B",
            AnalyticsSemanticRole.FINANCING: "#F4A261",
            AnalyticsSemanticRole.SAVINGS: "#8AC926",
            AnalyticsSemanticRole.FLOW_TOTAL: "#00B8D9",
        }
    ),
    waterfall=MappingProxyType(
        {
            WaterfallStepKind.INCOME_TOTAL: "#2EC4B6",
            WaterfallStepKind.EXPENSE: "#FF6B6B",
            WaterfallStepKind.FINANCING: "#F4A261",
            WaterfallStepKind.SAVINGS_ALLOCATION: "#8AC926",
            WaterfallStepKind.DEFICIT_TOTAL: "#FF9F1C",
            WaterfallStepKind.SURPLUS_TOTAL: "#4D96FF",
            WaterfallStepKind.MONTH_BALANCE: "#4D96FF",
            WaterfallStepKind.FINAL_TOTAL: "#00B8D9",
        }
    ),
)


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
