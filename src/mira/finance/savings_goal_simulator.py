# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Savings goal simulator used by tools before creating real goals."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from mira.finance.enums import PaymentFrequency


@dataclass(slots=True)
class SavingsGoalSimulationInput:
    """Represent the SavingsGoalSimulationInput class."""

    target_amount: float

    years: float
    frequency: PaymentFrequency
    initial_amount: float = 0.0
    annual_rate_percent: float = 0.0
    periodic_contribution: float | None = None


@dataclass(slots=True)
class SavingsGoalSimulationRow:
    """Represent the SavingsGoalSimulationRow class."""

    period: int

    label: str
    initial_balance: float
    interest: float
    contribution: float
    ending_balance: float
    progress_percent: float


@dataclass(slots=True)
class SavingsGoalSimulation:
    """Represent the SavingsGoalSimulation class."""

    target_amount: float

    years: float
    frequency: PaymentFrequency
    initial_amount: float
    annual_rate_percent: float
    periods_per_year: int
    total_periods: int
    periodic_contribution: float
    required_contribution: float
    final_amount: float
    gap_amount: float
    completion_percent: float
    is_reachable: bool
    rows: list[SavingsGoalSimulationRow]


def simulate_savings_goal(payload: SavingsGoalSimulationInput) -> SavingsGoalSimulation:
    """Simulate a savings path and optionally compute required contribution."""
    if payload.target_amount <= 0:
        raise ValueError("target_amount must be greater than 0")
    if payload.years <= 0:
        raise ValueError("years must be greater than 0")
    if payload.years > 100:
        raise ValueError("years must be less than or equal to 100")
    if payload.initial_amount < 0:
        raise ValueError("initial_amount must be greater than or equal to 0")
    if payload.annual_rate_percent < 0:
        raise ValueError("annual_rate_percent must be greater than or equal to 0")
    if payload.periodic_contribution is not None and payload.periodic_contribution < 0:
        raise ValueError("periodic_contribution must be greater than or equal to 0")

    periods_per_year = int(payload.frequency)

    years = _dec(payload.years)
    target_amount = _dec(payload.target_amount)
    initial_amount = _dec(payload.initial_amount)
    annual_rate = _dec(payload.annual_rate_percent)

    total_periods = max(1, int((years * Decimal(periods_per_year)).to_integral_value(rounding=ROUND_HALF_UP)))
    rate_per_period = (annual_rate / Decimal("100")) / Decimal(periods_per_year)

    required_contribution = _required_periodic_contribution(
        target_amount=target_amount,
        initial_amount=initial_amount,
        rate_per_period=rate_per_period,
        total_periods=total_periods,
    )
    contribution = (
        required_contribution if payload.periodic_contribution is None else _dec(payload.periodic_contribution)
    )

    rows = _build_rows(
        target_amount=target_amount,
        initial_amount=initial_amount,
        contribution=contribution,
        rate_per_period=rate_per_period,
        periods_per_year=periods_per_year,
        total_periods=total_periods,
    )

    final_amount = _dec(rows[-1].ending_balance)
    gap_amount = target_amount - final_amount
    completion_percent = float((final_amount / target_amount) * Decimal("100"))

    return SavingsGoalSimulation(
        target_amount=float(target_amount),
        years=float(years),
        frequency=payload.frequency,
        initial_amount=float(initial_amount),
        annual_rate_percent=float(annual_rate),
        periods_per_year=periods_per_year,
        total_periods=total_periods,
        periodic_contribution=float(contribution),
        required_contribution=float(required_contribution),
        final_amount=float(final_amount),
        gap_amount=float(gap_amount),
        completion_percent=completion_percent,
        is_reachable=final_amount >= target_amount,
        rows=rows,
    )


def _required_periodic_contribution(
    *,
    target_amount: Decimal,
    initial_amount: Decimal,
    rate_per_period: Decimal,
    total_periods: int,
) -> Decimal:
    """Return required periodic contribution."""
    if total_periods <= 0:
        return Decimal("0")

    if rate_per_period == 0:
        return max(Decimal("0"), (target_amount - initial_amount) / Decimal(total_periods))

    growth = (Decimal("1") + rate_per_period) ** Decimal(total_periods)
    future_initial = initial_amount * growth
    annuity_factor = (growth - Decimal("1")) / rate_per_period
    if annuity_factor <= 0:
        return Decimal("0")
    return max(Decimal("0"), (target_amount - future_initial) / annuity_factor)


def _build_rows(
    *,
    target_amount: Decimal,
    initial_amount: Decimal,
    contribution: Decimal,
    rate_per_period: Decimal,
    periods_per_year: int,
    total_periods: int,
) -> list[SavingsGoalSimulationRow]:
    """Return build rows."""
    rows: list[SavingsGoalSimulationRow] = []
    balance = initial_amount

    for period in range(1, total_periods + 1):
        period_initial = balance
        interest = period_initial * rate_per_period
        balance = period_initial + interest + contribution
        progress = Decimal("0") if target_amount == 0 else (balance / target_amount) * Decimal("100")

        rows.append(
            SavingsGoalSimulationRow(
                period=period,
                label=_period_label(period, periods_per_year),
                initial_balance=float(period_initial),
                interest=float(interest),
                contribution=float(contribution),
                ending_balance=float(balance),
                progress_percent=float(progress),
            )
        )

    return rows


def _period_label(period: int, periods_per_year: int) -> str:
    """Return period label."""
    year = ((period - 1) // periods_per_year) + 1
    position = ((period - 1) % periods_per_year) + 1
    return f"Año {year} / Período {position}"


def _dec(value: float) -> Decimal:
    """Return dec."""
    return Decimal(str(value))
