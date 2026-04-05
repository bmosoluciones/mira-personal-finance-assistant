# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import pytest

from mira.finance.enums import AmortizationMethod, PaymentFrequency
from mira.finance.loan_amortization import LoanAmortizationInput, calculate_loan_amortization


def test_french_method_keeps_quota_almost_constant() -> None:
    projection = calculate_loan_amortization(
        LoanAmortizationInput(
            loan_amount=10_000,
            annual_rate_percent=12,
            payment_frequency=PaymentFrequency.MONTHLY,
            years=5,
            method=AmortizationMethod.FRENCH,
        )
    )

    assert projection.total_periods == 60
    assert projection.payment_initial == pytest.approx(222.44447, rel=1e-6)
    assert projection.payment_final == pytest.approx(projection.payment_initial, rel=1e-6)
    assert projection.rows[0].interest == pytest.approx(100)
    assert projection.rows[-1].ending_balance == pytest.approx(0, abs=1e-9)


def test_german_method_uses_constant_principal_and_decreasing_payments() -> None:
    projection = calculate_loan_amortization(
        LoanAmortizationInput(
            loan_amount=10_000,
            annual_rate_percent=12,
            payment_frequency=PaymentFrequency.MONTHLY,
            years=5,
            method=AmortizationMethod.GERMAN,
        )
    )

    assert projection.rows[0].principal_amortization == pytest.approx(
        projection.rows[1].principal_amortization,
        rel=1e-9,
    )
    assert projection.payment_initial > projection.payment_final
    assert projection.total_interest < 3500
    assert projection.rows[-1].ending_balance == pytest.approx(0, abs=1e-9)


def test_projection_stores_enum_types() -> None:
    projection = calculate_loan_amortization(
        LoanAmortizationInput(
            loan_amount=5000,
            annual_rate_percent=8,
            payment_frequency=PaymentFrequency.QUARTERLY,
            years=2,
            method=AmortizationMethod.FRENCH,
        )
    )

    assert projection.payment_frequency is PaymentFrequency.QUARTERLY
    assert projection.method is AmortizationMethod.FRENCH
    assert projection.periods_per_year == 4
    assert projection.total_periods == 8


def test_all_frequencies_and_methods_are_accepted() -> None:
    for freq in PaymentFrequency:
        for method in AmortizationMethod:
            projection = calculate_loan_amortization(
                LoanAmortizationInput(
                    loan_amount=1000,
                    annual_rate_percent=5,
                    payment_frequency=freq,
                    years=1,
                    method=method,
                )
            )
            assert projection.periods_per_year == int(freq)
            assert projection.method is method


def test_validates_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="loan_amount"):
        calculate_loan_amortization(
            LoanAmortizationInput(
                loan_amount=0,
                annual_rate_percent=12,
                payment_frequency=PaymentFrequency.MONTHLY,
                years=1,
                method=AmortizationMethod.FRENCH,
            )
        )

    with pytest.raises(ValueError, match="years"):
        calculate_loan_amortization(
            LoanAmortizationInput(
                loan_amount=1000,
                annual_rate_percent=12,
                payment_frequency=PaymentFrequency.MONTHLY,
                years=0,
                method=AmortizationMethod.FRENCH,
            )
        )
