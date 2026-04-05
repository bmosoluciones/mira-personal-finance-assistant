# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Pure number formatting and parsing helpers shared across the app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class _SettingsProvider(Protocol):
    def get(self, key: str) -> str | None: ...


_SEP_DEFAULT_THOUSANDS = ","
_SEP_DEFAULT_DECIMAL = "."
_NUMBER_FORMAT_CONFIG_ERROR = "Thousands and decimal separators must be different."

_SEPARATOR_OPTIONS: tuple[tuple[str, str], ...] = (
    (",", ","),
    (".", "."),
    ("_", "_"),
    (" ", "space"),
    ("'", "'"),
)


@dataclass(frozen=True)
class NumberFormatConfig:
    thousands_sep: str = _SEP_DEFAULT_THOUSANDS
    decimal_sep: str = _SEP_DEFAULT_DECIMAL


def separator_options() -> tuple[tuple[str, str], ...]:
    """Return `(value, label)` options for separator selectors."""
    return _SEPARATOR_OPTIONS


def _normalize_separator(value: str | None, default: str) -> str:
    if value is None:
        return default
    for sep, _label in _SEPARATOR_OPTIONS:
        if value == sep:
            return sep
    return default


def validate_number_format_config(thousands_sep: str | None, decimal_sep: str | None) -> NumberFormatConfig:
    """Return a normalized config or fail if the separators are ambiguous."""
    thousands = _normalize_separator(thousands_sep, _SEP_DEFAULT_THOUSANDS)
    decimal = _normalize_separator(decimal_sep, _SEP_DEFAULT_DECIMAL)
    if thousands == decimal:
        raise ValueError(_NUMBER_FORMAT_CONFIG_ERROR)
    return NumberFormatConfig(thousands_sep=thousands, decimal_sep=decimal)


def coerce_number_format_config(thousands_sep: str | None, decimal_sep: str | None) -> NumberFormatConfig:
    """Normalize a config and make legacy ambiguous pairs safe for display/runtime."""
    thousands = _normalize_separator(thousands_sep, _SEP_DEFAULT_THOUSANDS)
    decimal = _normalize_separator(decimal_sep, _SEP_DEFAULT_DECIMAL)
    if thousands == decimal:
        decimal = "," if thousands == "." else "."
    return NumberFormatConfig(thousands_sep=thousands, decimal_sep=decimal)


def get_number_format_config(settings: _SettingsProvider) -> NumberFormatConfig:
    """Read numeric format preferences from settings with safe defaults."""
    return coerce_number_format_config(
        settings.get("number_thousands_separator"),
        settings.get("number_decimal_separator"),
    )


def format_number(value: float, config: NumberFormatConfig, *, decimals: int = 2, grouping: bool = True) -> str:
    """Format a number using custom thousands and decimal separators."""
    safe_config = coerce_number_format_config(config.thousands_sep, config.decimal_sep)
    abs_value = abs(float(value))
    base = f"{abs_value:,.{decimals}f}" if grouping else f"{abs_value:.{decimals}f}"
    base = base.replace(",", "{THOUSANDS}").replace(".", "{DECIMAL}")
    base = base.replace("{THOUSANDS}", safe_config.thousands_sep).replace("{DECIMAL}", safe_config.decimal_sep)
    if value < 0:
        return f"-{base}"
    return base


def parse_number(text: str, config: NumberFormatConfig) -> float:
    """Parse user input using configured separators into a float."""
    safe_config = validate_number_format_config(config.thousands_sep, config.decimal_sep)
    raw = text.strip()
    if not raw:
        raise ValueError("empty numeric text")

    raw = raw.replace("\u00a0", " ").strip()

    sign = 1.0
    if raw.startswith("-"):
        sign = -1.0
        raw = raw[1:].strip()
    elif raw.startswith("+"):
        raw = raw[1:].strip()

    if not raw:
        raise ValueError("missing numeric content")

    normalized = raw.replace(safe_config.thousands_sep, "")
    normalized = normalized.replace(safe_config.decimal_sep, ".")
    normalized = normalized.replace(" ", "")
    if not normalized:
        raise ValueError("missing numeric content")
    return sign * float(normalized)


__all__ = [
    "NumberFormatConfig",
    "coerce_number_format_config",
    "format_number",
    "get_number_format_config",
    "parse_number",
    "separator_options",
    "validate_number_format_config",
]
