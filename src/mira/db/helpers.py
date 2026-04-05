# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Shared constants and helper utilities for the database layer."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
import unicodedata

_UNSET = object()  # sentinel for "parameter not provided"
_ICON_MAX_LENGTH = 32
_ACCOUNT_TYPE_ALIASES = {"card": "credit"}
_VALID_ACCOUNT_TYPES = frozenset({"bank", "cash", "credit"})
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


_CURRENCY_SEED: list[tuple[str, str, str]] = [
    ("USD", "US Dollar", "americas"),
    ("CAD", "Canadian Dollar", "americas"),
    ("MXN", "Mexican Peso", "americas"),
    ("GTQ", "Guatemalan Quetzal", "americas"),
    ("BZD", "Belize Dollar", "americas"),
    ("HNL", "Honduran Lempira", "americas"),
    ("SVC", "Salvadoran Colon", "americas"),
    ("NIO", "Nicaraguan Cordoba", "americas"),
    ("CRC", "Costa Rican Colon", "americas"),
    ("PAB", "Panamanian Balboa", "americas"),
    ("CUP", "Cuban Peso", "americas"),
    ("DOP", "Dominican Peso", "americas"),
    ("HTG", "Haitian Gourde", "americas"),
    ("JMD", "Jamaican Dollar", "americas"),
    ("BSD", "Bahamian Dollar", "americas"),
    ("BBD", "Barbadian Dollar", "americas"),
    ("TTD", "Trinidad and Tobago Dollar", "americas"),
    ("XCD", "East Caribbean Dollar", "americas"),
    ("COP", "Colombian Peso", "americas"),
    ("VES", "Venezuelan Bolivar", "americas"),
    ("GYD", "Guyanese Dollar", "americas"),
    ("SRD", "Surinamese Dollar", "americas"),
    ("BRL", "Brazilian Real", "americas"),
    ("ARS", "Argentine Peso", "americas"),
    ("CLP", "Chilean Peso", "americas"),
    ("PYG", "Paraguayan Guarani", "americas"),
    ("UYU", "Uruguayan Peso", "americas"),
    ("BOB", "Bolivian Boliviano", "americas"),
    ("PEN", "Peruvian Sol", "americas"),
    ("EUR", "Euro", "europe"),
]

CURRENCY_CODES = tuple(code for code, _name, _region in _CURRENCY_SEED)
_SAVINGS_GOALS_PARENT_NAMES = {
    "es": "Metas de ahorro",
    "en": "Savings Goals",
}
_SAVINGS_GOALS_PARENT_COLOR = "#2E8B57"
_MILESTONES_NL_TRANSACTIONS = (100, 500, 1000, 3000, 5000)
_MILESTONES_MIRA_REPORT_VIEWS = (10, 100, 500, 1000)
_MILESTONES_SAVINGS_CONTRIBUTIONS = (1, 10, 50, 100)
MESSAGE_PRIORITY = {
    "ACHIEVEMENT_CRITICAL": 320,
    "ACHIEVEMENT_HIGH": 300,
    "ACHIEVEMENT_MEDIUM": 230,
    "ACHIEVEMENT_LOW": 210,
    "INSIGHT_CRITICAL": 100,
    "INSIGHT_WARNING": 80,
    "INSIGHT_INFO": 60,
}

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


def canonical_account_type(account_type: str | None) -> str:
    normalized = str(account_type or "bank").strip().lower() or "bank"
    normalized = _ACCOUNT_TYPE_ALIASES.get(normalized, normalized)
    if normalized not in _VALID_ACCOUNT_TYPES:
        raise ValueError(f"Unsupported account type: {account_type!r}")
    return normalized


def normalize_language(language: str | None) -> str:
    normalized = str(language or "").strip().lower()
    return "es" if normalized == "es" else "en"


def localized_default_account_name(language: str | None) -> str:
    return "Cuenta principal" if normalize_language(language) == "es" else "Main account"


def localized_default_savings_name(language: str | None) -> str:
    return "Ahorro" if normalize_language(language) == "es" else "Savings"


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
