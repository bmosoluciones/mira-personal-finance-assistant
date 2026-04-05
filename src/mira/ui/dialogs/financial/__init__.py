# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Financial utility dialogs."""

from .compound_interest import CompoundInterestDialog
from .goal_simulator import GoalScenarioDialog
from .loan_amortization import LoanAmortizationDialog

__all__ = [
    "CompoundInterestDialog",
    "GoalScenarioDialog",
    "LoanAmortizationDialog",
]
