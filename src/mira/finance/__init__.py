# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Finance calculation utilities."""

from .compound_interest import (  # noqa: F401
    CompoundInterestInput,
    CompoundInterestProjection,
    CompoundInterestRow,
    calculate_compound_interest_projection,
)
from .enums import AmortizationMethod, PaymentFrequency  # noqa: F401
from .loan_amortization import (  # noqa: F401
    LoanAmortizationInput,
    LoanAmortizationProjection,
    LoanAmortizationRow,
    calculate_loan_amortization,
)
from .savings_goal_simulator import (  # noqa: F401
    SavingsGoalSimulation,
    SavingsGoalSimulationInput,
    SavingsGoalSimulationRow,
    simulate_savings_goal,
)
