# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import pytest

from mira.number_format import (
    NumberFormatConfig,
    coerce_number_format_config,
    format_number,
    get_number_format_config,
    parse_number,
    validate_number_format_config,
)


class _SettingsStub:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, key: str) -> str | None:
        return self._values.get(key)


def test_validate_number_format_config_accepts_valid_pairs() -> None:
    config = validate_number_format_config(".", ",")

    assert config == NumberFormatConfig(thousands_sep=".", decimal_sep=",")


@pytest.mark.parametrize("thousands_sep, decimal_sep", [(".", "."), (",", ","), (" ", " ")])
def test_validate_number_format_config_rejects_ambiguous_pairs(thousands_sep: str, decimal_sep: str) -> None:
    with pytest.raises(ValueError, match="different"):
        validate_number_format_config(thousands_sep, decimal_sep)


def test_coerce_number_format_config_repairs_legacy_ambiguous_pair() -> None:
    assert coerce_number_format_config(".", ".") == NumberFormatConfig(thousands_sep=".", decimal_sep=",")
    assert coerce_number_format_config(",", ",") == NumberFormatConfig(thousands_sep=",", decimal_sep=".")


def test_parse_number_supports_valid_pairs_and_rejects_ambiguous_configs() -> None:
    assert parse_number("1.234,56", NumberFormatConfig(thousands_sep=".", decimal_sep=",")) == pytest.approx(1234.56)
    assert parse_number("1,234.56", NumberFormatConfig(thousands_sep=",", decimal_sep=".")) == pytest.approx(1234.56)

    with pytest.raises(ValueError, match="different"):
        parse_number("1.000", NumberFormatConfig(thousands_sep=".", decimal_sep="."))


def test_get_number_format_config_coerces_legacy_settings() -> None:
    settings = _SettingsStub(
        {
            "number_thousands_separator": ".",
            "number_decimal_separator": ".",
        }
    )

    assert get_number_format_config(settings) == NumberFormatConfig(thousands_sep=".", decimal_sep=",")
    assert format_number(1234.56, get_number_format_config(settings)) == "1.234,56"
