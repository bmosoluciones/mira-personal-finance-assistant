# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import pytest

from mira.finance.enums import PaymentFrequency
from mira.finance.savings_goal_simulator import SavingsGoalSimulationInput, simulate_savings_goal


def test_auto_mode_calculates_required_periodic_contribution() -> None:
    projection = simulate_savings_goal(
        SavingsGoalSimulationInput(
            target_amount=5000,
            years=2,
            frequency=PaymentFrequency.MONTHLY,
            initial_amount=0,
            annual_rate_percent=0,
            periodic_contribution=None,
        )
    )

    assert projection.total_periods == 24
    assert projection.required_contribution == pytest.approx(208.333333, rel=1e-6)
    assert projection.periodic_contribution == pytest.approx(projection.required_contribution, rel=1e-9)
    assert projection.final_amount == pytest.approx(5000, rel=1e-9)
    assert projection.is_reachable is True


def test_manual_mode_marks_unreachable_scenario() -> None:
    projection = simulate_savings_goal(
        SavingsGoalSimulationInput(
            target_amount=5000,
            years=2,
            frequency=PaymentFrequency.MONTHLY,
            initial_amount=0,
            annual_rate_percent=0,
            periodic_contribution=100,
        )
    )

    assert projection.final_amount == pytest.approx(2400, rel=1e-9)
    assert projection.gap_amount == pytest.approx(2600, rel=1e-9)
    assert projection.completion_percent == pytest.approx(48.0, rel=1e-9)
    assert projection.is_reachable is False


def test_projection_stores_frequency_as_enum() -> None:
    projection = simulate_savings_goal(
        SavingsGoalSimulationInput(
            target_amount=1000,
            years=1,
            frequency=PaymentFrequency.ANNUAL,
        )
    )

    assert projection.frequency is PaymentFrequency.ANNUAL
    assert projection.periods_per_year == 1
    assert projection.total_periods == 1


def test_all_frequencies_are_accepted() -> None:
    for freq in PaymentFrequency:
        projection = simulate_savings_goal(
            SavingsGoalSimulationInput(
                target_amount=1200,
                years=1,
                frequency=freq,
            )
        )
        assert projection.periods_per_year == int(freq)


def test_validation_errors_for_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="target_amount"):
        simulate_savings_goal(
            SavingsGoalSimulationInput(
                target_amount=0,
                years=1,
                frequency=PaymentFrequency.MONTHLY,
            )
        )

    with pytest.raises(ValueError, match="periodic_contribution"):
        simulate_savings_goal(
            SavingsGoalSimulationInput(
                target_amount=1000,
                years=1,
                frequency=PaymentFrequency.MONTHLY,
                periodic_contribution=-1,
            )
        )
