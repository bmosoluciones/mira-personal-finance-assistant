# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Shared constants and helper utilities for the database layer."""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

_UNSET = object()  # sentinel for "parameter not provided"
_ICON_MAX_LENGTH = 32
_ACCOUNT_ALIAS_STOPWORDS = frozenset(
    {
        "account",
        "cuenta",
        "bank",
        "banco",
        "cash",
        "efectivo",
        "credit",
        "credito",
        "crédito",
        "card",
        "tarjeta",
        "de",
        "del",
        "la",
        "el",
        "my",
        "mi",
    }
)


class AccountType(StrEnum):
    BANK = "bank"
    CASH = "cash"
    CREDIT = "credit"


class CurrencyRegion(StrEnum):
    AMERICAS = "americas"
    EUROPE = "europe"


class MessagePriority(IntEnum):
    ACHIEVEMENT_CRITICAL = 320
    ACHIEVEMENT_HIGH = 300
    ACHIEVEMENT_MEDIUM = 230
    ACHIEVEMENT_LOW = 210
    INSIGHT_CRITICAL = 100
    INSIGHT_WARNING = 80
    INSIGHT_INFO = 60


@dataclass(frozen=True, slots=True)
class CurrencySeedEntry:
    code: str
    name: str
    region: CurrencyRegion


@dataclass(frozen=True, slots=True)
class SavingsGoalsDefaults:
    names: Mapping[str, str]
    color: str

    def name_for(self, language: str | None) -> str:
        return self.names[normalize_language(language)]

    def all_names(self) -> tuple[str, ...]:
        return tuple(self.names.values())


@dataclass(frozen=True, slots=True)
class FeedbackMilestones:
    nl_transactions: tuple[int, ...]
    mira_report_views: tuple[int, ...]
    savings_contributions: tuple[int, ...]


_ACCOUNT_TYPE_ALIASES = MappingProxyType({"card": AccountType.CREDIT})

CURRENCY_SEED: tuple[CurrencySeedEntry, ...] = (
    CurrencySeedEntry("USD", "US Dollar", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("CAD", "Canadian Dollar", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("MXN", "Mexican Peso", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("GTQ", "Guatemalan Quetzal", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("BZD", "Belize Dollar", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("HNL", "Honduran Lempira", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("SVC", "Salvadoran Colon", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("NIO", "Nicaraguan Cordoba", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("CRC", "Costa Rican Colon", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("PAB", "Panamanian Balboa", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("CUP", "Cuban Peso", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("DOP", "Dominican Peso", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("HTG", "Haitian Gourde", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("JMD", "Jamaican Dollar", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("BSD", "Bahamian Dollar", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("BBD", "Barbadian Dollar", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("TTD", "Trinidad and Tobago Dollar", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("XCD", "East Caribbean Dollar", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("COP", "Colombian Peso", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("VES", "Venezuelan Bolivar", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("GYD", "Guyanese Dollar", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("SRD", "Surinamese Dollar", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("BRL", "Brazilian Real", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("ARS", "Argentine Peso", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("CLP", "Chilean Peso", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("PYG", "Paraguayan Guarani", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("UYU", "Uruguayan Peso", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("BOB", "Bolivian Boliviano", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("PEN", "Peruvian Sol", CurrencyRegion.AMERICAS),
    CurrencySeedEntry("EUR", "Euro", CurrencyRegion.EUROPE),
)
_CURRENCY_SEED = CURRENCY_SEED

CURRENCY_CODES = tuple(entry.code for entry in CURRENCY_SEED)

SAVINGS_GOALS_DEFAULTS = SavingsGoalsDefaults(
    names=MappingProxyType(
        {
            "es": "Metas de ahorro",
            "en": "Savings Goals",
        }
    ),
    color="#2E8B57",
)
_SAVINGS_GOALS_PARENT_NAMES = SAVINGS_GOALS_DEFAULTS.names
_SAVINGS_GOALS_PARENT_COLOR = SAVINGS_GOALS_DEFAULTS.color

FEEDBACK_MILESTONES = FeedbackMilestones(
    nl_transactions=(100, 500, 1000, 3000, 5000),
    mira_report_views=(10, 100, 500, 1000),
    savings_contributions=(1, 10, 50, 100),
)
_MILESTONES_NL_TRANSACTIONS = FEEDBACK_MILESTONES.nl_transactions
_MILESTONES_MIRA_REPORT_VIEWS = FEEDBACK_MILESTONES.mira_report_views
_MILESTONES_SAVINGS_CONTRIBUTIONS = FEEDBACK_MILESTONES.savings_contributions
MESSAGE_PRIORITY = MessagePriority

_FLATPAK_DB_DIRNAME = "mira"
_DEFAULT_DB_FILENAME = "mira.db"


def _resolve_data_home() -> Path:
    """Resolve the user data directory following XDG conventions when available."""
    if xdg_data_home := os.environ.get("XDG_DATA_HOME", "").strip():
        return Path(xdg_data_home).expanduser()

    if sys.platform == "win32":
        if appdata := os.environ.get("APPDATA", "").strip():
            return Path(appdata).expanduser()
        return Path.home() / "AppData" / "Roaming"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"

    return Path.home() / ".local" / "share"


def default_db_path_for_display() -> Path:
    """Return the default database path without creating directories."""
    return _resolve_data_home() / _FLATPAK_DB_DIRNAME / _DEFAULT_DB_FILENAME


def parse_account_type(account_type: str | None) -> AccountType:
    normalized = str(account_type or AccountType.BANK.value).strip().lower() or AccountType.BANK.value
    resolved = _ACCOUNT_TYPE_ALIASES.get(normalized, normalized)
    if isinstance(resolved, AccountType):
        return resolved
    try:
        return AccountType(resolved)
    except ValueError as exc:
        raise ValueError(f"Unsupported account type: {account_type!r}") from exc


def canonical_account_type(account_type: str | None) -> str:
    return parse_account_type(account_type).value


def normalize_language(language: str | None) -> str:
    normalized = str(language or "").strip().lower()
    return "es" if normalized == "es" else "en"


def _translated_db_label(key: str, language: str | None, default: str) -> str:
    from mira.ui.i18n import tr

    return tr(key, normalize_language(language), default=default)


def localized_default_account_name(language: str | None) -> str:
    return _translated_db_label("db.default_account_name", language, "Main account")


def localized_default_savings_name(language: str | None) -> str:
    return _translated_db_label("db.default_savings_name", language, "Savings")


def localized_savings_goals_parent_name(language: str | None) -> str:
    return _translated_db_label("db.savings_goals_parent_name", language, "Savings Goals")


def fold_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    collapsed = re.sub(r"[^a-z0-9]+", " ", without_accents.casefold())
    return " ".join(collapsed.split())


def get_default_db_path() -> Path:
    """Return the default database path, creating the directory if needed.

    Legacy files under ``~/.mira/`` are intentionally ignored. As of schema
    v2 / release ``0.0.1a2`` the app no longer copies or migrates databases
    from that legacy location on startup.
    """
    default_db_path = default_db_path_for_display()
    default_db_dir = default_db_path.parent
    default_db_dir.mkdir(parents=True, exist_ok=True)
    return default_db_path


def delete_database_file(path: str | Path) -> None:
    """Delete a SQLite database file and its WAL/SHM sidecars if present."""
    target = Path(path).expanduser()
    for candidate in (
        target,
        target.with_name(f"{target.name}-wal"),
        target.with_name(f"{target.name}-shm"),
    ):
        if candidate.exists():
            candidate.unlink()
