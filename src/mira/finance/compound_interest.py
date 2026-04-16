# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Compound interest projections for personal finance tools."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from mira.finance.enums import PaymentFrequency


@dataclass(slots=True)
class CompoundInterestInput:
    """Represent the CompoundInterestInput class."""

    initial_fund: float

    annual_rate_percent: float
    capitalization: PaymentFrequency
    years: float
    periodic_contribution: float = 0.0


@dataclass(slots=True)
class CompoundInterestRow:
    """Represent the CompoundInterestRow class."""

    period: int

    label: str
    initial_balance: float
    interest: float
    periodic_contribution: float
    final_balance: float
    cumulative_contribution: float
    cumulative_interest: float


@dataclass(slots=True)
class CompoundInterestProjection:
    """Represent the CompoundInterestProjection class."""

    initial_fund: float

    annual_rate_percent: float
    capitalization: PaymentFrequency
    years: float
    periodic_contribution: float
    periods_per_year: int
    total_periods: int
    total_contributed: float
    own_capital: float
    interest_earned: float
    final_balance: float
    rows: list[CompoundInterestRow]


def calculate_compound_interest_projection(payload: CompoundInterestInput) -> CompoundInterestProjection:
    """Calculate a projection with end-of-period contributions."""
    if payload.initial_fund < 0:
        raise ValueError("initial_fund must be greater than or equal to 0")
    if payload.annual_rate_percent < 0:
        raise ValueError("annual_rate_percent must be greater than or equal to 0")
    if payload.years <= 0:
        raise ValueError("years must be greater than 0")
    if payload.years > 100:
        raise ValueError("years must be less than or equal to 100")
    if payload.periodic_contribution < 0:
        raise ValueError("periodic_contribution must be greater than or equal to 0")

    periods_per_year = int(payload.capitalization)

    years = _dec(payload.years)
    annual_rate = _dec(payload.annual_rate_percent)
    initial_fund = _dec(payload.initial_fund)
    periodic_contribution = _dec(payload.periodic_contribution)

    total_periods = max(1, int((years * Decimal(periods_per_year)).to_integral_value(rounding=ROUND_HALF_UP)))
    rate_per_period = (annual_rate / Decimal("100")) / Decimal(periods_per_year)

    balance = initial_fund
    cumulative_contribution = initial_fund
    rows: list[CompoundInterestRow] = []

    for period in range(1, total_periods + 1):
        initial_balance = balance
        interest = initial_balance * rate_per_period
        balance = initial_balance + interest + periodic_contribution
        cumulative_contribution += periodic_contribution
        cumulative_interest = balance - cumulative_contribution

        rows.append(
            CompoundInterestRow(
                period=period,
                label=_period_label(period, periods_per_year),
                initial_balance=float(initial_balance),
                interest=float(interest),
                periodic_contribution=float(periodic_contribution),
                final_balance=float(balance),
                cumulative_contribution=float(cumulative_contribution),
                cumulative_interest=float(cumulative_interest),
            )
        )

    total_contributed = cumulative_contribution
    own_capital = initial_fund + (periodic_contribution * Decimal(total_periods))
    interest_earned = balance - own_capital

    return CompoundInterestProjection(
        initial_fund=float(initial_fund),
        annual_rate_percent=float(annual_rate),
        capitalization=payload.capitalization,
        years=float(years),
        periodic_contribution=float(periodic_contribution),
        periods_per_year=periods_per_year,
        total_periods=total_periods,
        total_contributed=float(total_contributed),
        own_capital=float(own_capital),
        interest_earned=float(interest_earned),
        final_balance=float(balance),
        rows=rows,
    )


def _period_label(period: int, periods_per_year: int) -> str:
    """Return period label."""
    year = ((period - 1) // periods_per_year) + 1
    position = ((period - 1) % periods_per_year) + 1
    return f"Año {year} / Período {position}"


def _dec(value: float) -> Decimal:
    """Return dec."""
    return Decimal(str(value))
