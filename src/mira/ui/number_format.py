# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Qt-specific numeric widgets built on top of shared formatting helpers."""

from __future__ import annotations

from typing import Protocol

from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QDoubleSpinBox, QWidget

from mira.number_format import (
    NumberFormatConfig,
    format_number,
    get_number_format_config,
    parse_number,
    separator_options,
    validate_number_format_config,
)


class _SettingsProvider(Protocol):
    def get(self, key: str) -> str | None: ...


def _strip_prefix_suffix(text: str, prefix: str, suffix: str) -> str:
    value = text.strip()
    if prefix and value.startswith(prefix):
        value = value[len(prefix) :]
    if suffix and value.endswith(suffix):
        value = value[: -len(suffix)]
    return value.strip()


class NumberMaskedSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that formats/parses values using app numeric settings."""

    def __init__(self, settings: _SettingsProvider, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings

    def _config(self) -> NumberFormatConfig:
        return get_number_format_config(self._settings)

    def _strip_affixes(self, text: str) -> str:
        return _strip_prefix_suffix(text, self.prefix(), self.suffix())

    def textFromValue(self, value: float) -> str:  # type: ignore[override]
        return format_number(value, self._config(), decimals=self.decimals(), grouping=True)

    def valueFromText(self, text: str) -> float:  # type: ignore[override]
        stripped = self._strip_affixes(text)
        return parse_number(stripped, self._config())

    def validate(self, text: str, pos: int) -> tuple[QValidator.State, str, int]:  # type: ignore[override]
        stripped = self._strip_affixes(text)
        if stripped in {"", "+", "-"}:
            return (QValidator.State.Intermediate, text, pos)

        cfg = self._config()
        allowed = set("0123456789+-") | {cfg.thousands_sep, cfg.decimal_sep, " ", "\u00a0"}
        if any(ch not in allowed for ch in stripped):
            return (QValidator.State.Invalid, text, pos)

        try:
            parse_number(stripped, cfg)
        except ValueError:
            return (QValidator.State.Intermediate, text, pos)
        return (QValidator.State.Acceptable, text, pos)


__all__ = [
    "NumberFormatConfig",
    "NumberMaskedSpinBox",
    "format_number",
    "get_number_format_config",
    "parse_number",
    "separator_options",
    "validate_number_format_config",
]
