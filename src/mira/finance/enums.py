# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Shared enums for finance calculation modules."""

from __future__ import annotations

from enum import Enum, IntEnum


class PaymentFrequency(IntEnum):
    """Number of payment or compounding periods per year.

    The integer value of each member equals the periods per year, so it can be
    used directly wherever ``periods_per_year`` is needed without a lookup table.
    """

    MONTHLY = 12
    QUARTERLY = 4
    SEMIANNUAL = 2
    ANNUAL = 1


class AmortizationMethod(Enum):
    """Loan amortization method."""

    FRENCH = "french"
    GERMAN = "german"
