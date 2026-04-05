# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Dialog package with compatibility re-exports."""

from .crud import *  # noqa: F401,F403
from . import financial as _financial

CompoundInterestDialog = _financial.CompoundInterestDialog
GoalScenarioDialog = _financial.GoalScenarioDialog
LoanAmortizationDialog = _financial.LoanAmortizationDialog

__all__ = [name for name in globals() if not name.startswith("_")]
