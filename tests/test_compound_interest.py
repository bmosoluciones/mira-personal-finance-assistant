# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import pytest

from mira.finance.compound_interest import CompoundInterestInput, calculate_compound_interest_projection
from mira.finance.enums import PaymentFrequency


def test_projection_without_contributions_uses_compound_growth() -> None:
    projection = calculate_compound_interest_projection(
        CompoundInterestInput(
            initial_fund=1000,
            annual_rate_percent=12,
            capitalization=PaymentFrequency.MONTHLY,
            years=1,
            periodic_contribution=0,
        )
    )

    assert projection.total_periods == 12
    assert projection.rows[0].interest == pytest.approx(10)
    assert projection.final_balance == pytest.approx(1126.82503, rel=1e-6)
    assert projection.interest_earned == pytest.approx(126.82503, rel=1e-6)


def test_projection_with_contributions_adds_end_of_each_period() -> None:
    projection = calculate_compound_interest_projection(
        CompoundInterestInput(
            initial_fund=0,
            annual_rate_percent=5,
            capitalization=PaymentFrequency.MONTHLY,
            years=1,
            periodic_contribution=100,
        )
    )

    assert projection.total_contributed == pytest.approx(1200)
    assert projection.final_balance == pytest.approx(1227.88555, rel=1e-6)
    assert projection.interest_earned == pytest.approx(27.88555, rel=1e-6)
    assert projection.rows[0].final_balance == pytest.approx(100)


def test_projection_stores_capitalization_as_enum() -> None:
    projection = calculate_compound_interest_projection(
        CompoundInterestInput(
            initial_fund=0,
            annual_rate_percent=5,
            capitalization=PaymentFrequency.ANNUAL,
            years=5,
            periodic_contribution=0,
        )
    )

    assert projection.capitalization is PaymentFrequency.ANNUAL
    assert projection.periods_per_year == 1
    assert projection.total_periods == 5


def test_all_frequencies_produce_correct_periods_per_year() -> None:
    for freq in PaymentFrequency:
        projection = calculate_compound_interest_projection(
            CompoundInterestInput(
                initial_fund=1000,
                annual_rate_percent=0,
                capitalization=freq,
                years=1,
                periodic_contribution=0,
            )
        )
        assert projection.periods_per_year == int(freq)
        assert projection.total_periods == int(freq)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ("initial_fund", "initial_fund must be greater than or equal to 0"),
        ("annual_rate_percent", "annual_rate_percent must be greater than or equal to 0"),
        ("years_zero", "years must be greater than 0"),
        ("years_large", "years must be less than or equal to 100"),
        ("periodic_contribution", "periodic_contribution must be greater than or equal to 0"),
    ],
)
def test_projection_raises_for_invalid_parameters(kwargs: str, message: str) -> None:
    params = {
        "initial_fund": 1000,
        "annual_rate_percent": 5,
        "capitalization": PaymentFrequency.ANNUAL,
        "years": 1,
        "periodic_contribution": 0,
    }

    if kwargs == "initial_fund":
        params["initial_fund"] = -1
    elif kwargs == "annual_rate_percent":
        params["annual_rate_percent"] = -0.1
    elif kwargs == "years_zero":
        params["years"] = 0
    elif kwargs == "years_large":
        params["years"] = 101
    elif kwargs == "periodic_contribution":
        params["periodic_contribution"] = -10

    with pytest.raises(ValueError, match=message):
        calculate_compound_interest_projection(CompoundInterestInput(**params))
