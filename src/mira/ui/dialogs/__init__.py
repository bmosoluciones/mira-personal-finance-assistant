# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Dialog package with stable compatibility re-exports."""

from .accounts import AccountDialog
from .budget import BudgetCreateDialog
from .categories import CategoryDialog, MergeCategoryDialog
from .goals import ContributeGoalDialog, SavingsGoalDialog
from .recurring import RecurringDialog
from .reconciliation import ReconciliationDialog
from .setup import InitialSetupDialog
from .tags import TagDialog
from .transactions import BalanceAdjustmentDialog, TransactionDialog, TransferDialog
from . import financial as _financial
from PySide6.QtWidgets import QColorDialog

CompoundInterestDialog = _financial.CompoundInterestDialog
GoalScenarioDialog = _financial.GoalScenarioDialog
LoanAmortizationDialog = _financial.LoanAmortizationDialog

__all__ = [
    "AccountDialog",
    "BalanceAdjustmentDialog",
    "BudgetCreateDialog",
    "CategoryDialog",
    "QColorDialog",
    "CompoundInterestDialog",
    "ContributeGoalDialog",
    "GoalScenarioDialog",
    "InitialSetupDialog",
    "LoanAmortizationDialog",
    "MergeCategoryDialog",
    "RecurringDialog",
    "ReconciliationDialog",
    "SavingsGoalDialog",
    "TagDialog",
    "TransactionDialog",
    "TransferDialog",
]
