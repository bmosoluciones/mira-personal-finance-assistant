# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Loan amortization projections (French and German methods)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from mira.finance.enums import AmortizationMethod, PaymentFrequency


@dataclass(slots=True)
class LoanAmortizationInput:
    loan_amount: float
    annual_rate_percent: float
    payment_frequency: PaymentFrequency
    years: float
    method: AmortizationMethod


@dataclass(slots=True)
class LoanAmortizationRow:
    period: int
    label: str
    initial_balance: float
    payment: float
    interest: float
    principal_amortization: float
    ending_balance: float
    cumulative_interest: float
    cumulative_principal: float


@dataclass(slots=True)
class LoanAmortizationProjection:
    loan_amount: float
    annual_rate_percent: float
    payment_frequency: PaymentFrequency
    years: float
    method: AmortizationMethod
    periods_per_year: int
    total_periods: int
    payment_initial: float
    payment_final: float
    total_paid: float
    total_interest: float
    total_principal: float
    rows: list[LoanAmortizationRow]


def calculate_loan_amortization(payload: LoanAmortizationInput) -> LoanAmortizationProjection:
    """Calculate complete amortization table for French or German method."""
    if payload.loan_amount <= 0:
        raise ValueError("loan_amount must be greater than 0")
    if payload.annual_rate_percent < 0:
        raise ValueError("annual_rate_percent must be greater than or equal to 0")
    if payload.years <= 0:
        raise ValueError("years must be greater than 0")
    if payload.years > 50:
        raise ValueError("years must be less than or equal to 50")

    periods_per_year = int(payload.payment_frequency)

    years = _dec(payload.years)
    annual_rate = _dec(payload.annual_rate_percent)
    loan_amount = _dec(payload.loan_amount)

    total_periods = max(1, int((years * Decimal(periods_per_year)).to_integral_value(rounding=ROUND_HALF_UP)))
    rate_per_period = (annual_rate / Decimal("100")) / Decimal(periods_per_year)

    if payload.method == AmortizationMethod.FRENCH:
        base_payment = _french_payment(loan_amount, rate_per_period, total_periods)
        return _build_french_projection(
            payload, loan_amount, rate_per_period, total_periods, base_payment, periods_per_year
        )

    return _build_german_projection(payload, loan_amount, rate_per_period, total_periods, periods_per_year)


def _build_french_projection(
    payload: LoanAmortizationInput,
    loan_amount: Decimal,
    rate_per_period: Decimal,
    total_periods: int,
    payment: Decimal,
    periods_per_year: int,
) -> LoanAmortizationProjection:
    rows: list[LoanAmortizationRow] = []
    balance = loan_amount
    cumulative_interest = Decimal("0")
    cumulative_principal = Decimal("0")

    for period in range(1, total_periods + 1):
        initial_balance = balance
        interest = initial_balance * rate_per_period
        principal = payment - interest

        if period == total_periods:
            principal = initial_balance
            payment_for_period = principal + interest
        else:
            payment_for_period = payment

        ending_balance = initial_balance - principal
        cumulative_interest += interest
        cumulative_principal += principal

        rows.append(
            LoanAmortizationRow(
                period=period,
                label=_period_label(period, periods_per_year),
                initial_balance=float(initial_balance),
                payment=float(payment_for_period),
                interest=float(interest),
                principal_amortization=float(principal),
                ending_balance=float(max(ending_balance, Decimal("0"))),
                cumulative_interest=float(cumulative_interest),
                cumulative_principal=float(cumulative_principal),
            )
        )
        balance = ending_balance

    total_paid = sum(_dec(row.payment) for row in rows)
    return LoanAmortizationProjection(
        loan_amount=float(loan_amount),
        annual_rate_percent=payload.annual_rate_percent,
        payment_frequency=payload.payment_frequency,
        years=float(_dec(payload.years)),
        method=payload.method,
        periods_per_year=periods_per_year,
        total_periods=total_periods,
        payment_initial=rows[0].payment,
        payment_final=rows[-1].payment,
        total_paid=float(total_paid),
        total_interest=float(cumulative_interest),
        total_principal=float(cumulative_principal),
        rows=rows,
    )


def _build_german_projection(
    payload: LoanAmortizationInput,
    loan_amount: Decimal,
    rate_per_period: Decimal,
    total_periods: int,
    periods_per_year: int,
) -> LoanAmortizationProjection:
    rows: list[LoanAmortizationRow] = []
    balance = loan_amount
    principal_constant = loan_amount / Decimal(total_periods)
    cumulative_interest = Decimal("0")
    cumulative_principal = Decimal("0")

    for period in range(1, total_periods + 1):
        initial_balance = balance
        principal = principal_constant if period < total_periods else initial_balance
        interest = initial_balance * rate_per_period
        payment = principal + interest
        ending_balance = initial_balance - principal

        cumulative_interest += interest
        cumulative_principal += principal

        rows.append(
            LoanAmortizationRow(
                period=period,
                label=_period_label(period, periods_per_year),
                initial_balance=float(initial_balance),
                payment=float(payment),
                interest=float(interest),
                principal_amortization=float(principal),
                ending_balance=float(max(ending_balance, Decimal("0"))),
                cumulative_interest=float(cumulative_interest),
                cumulative_principal=float(cumulative_principal),
            )
        )
        balance = ending_balance

    total_paid = sum(_dec(row.payment) for row in rows)
    return LoanAmortizationProjection(
        loan_amount=float(loan_amount),
        annual_rate_percent=payload.annual_rate_percent,
        payment_frequency=payload.payment_frequency,
        years=float(_dec(payload.years)),
        method=payload.method,
        periods_per_year=periods_per_year,
        total_periods=total_periods,
        payment_initial=rows[0].payment,
        payment_final=rows[-1].payment,
        total_paid=float(total_paid),
        total_interest=float(cumulative_interest),
        total_principal=float(cumulative_principal),
        rows=rows,
    )


def _french_payment(principal: Decimal, rate_per_period: Decimal, total_periods: int) -> Decimal:
    if rate_per_period == 0:
        return principal / Decimal(total_periods)
    factor = (Decimal("1") + rate_per_period) ** Decimal(-total_periods)
    return principal * (rate_per_period / (Decimal("1") - factor))


def _period_label(period: int, periods_per_year: int) -> str:
    year = ((period - 1) // periods_per_year) + 1
    position = ((period - 1) % periods_per_year) + 1
    return f"Año {year} / Período {position}"


def _dec(value: float) -> Decimal:
    return Decimal(str(value))
