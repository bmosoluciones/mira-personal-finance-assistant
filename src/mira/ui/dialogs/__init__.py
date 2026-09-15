# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Dialog package with stable compatibility re-exports."""

from PySide6.QtWidgets import QColorDialog

from . import financial as _financial
from .accounts import AccountDialog
from .budget import BudgetCreateDialog
from .categories import CategoryDialog, MergeCategoryDialog
from .goals import ContributeGoalDialog, SavingsGoalDialog
from .mobile_sync import MobileSyncSessionDialog
from .reconciliation import ReconciliationDialog
from .recurring import RecurringDialog
from .setup import InitialSetupDialog
from .tags import TagDialog
from .transactions import BalanceAdjustmentDialog, TransactionDialog, TransferDialog

CompoundInterestDialog = _financial.CompoundInterestDialog
GoalScenarioDialog = _financial.GoalScenarioDialog
LoanAmortizationDialog = _financial.LoanAmortizationDialog

__all__ = [
    "AccountDialog",
    "BalanceAdjustmentDialog",
    "BudgetCreateDialog",
    "CategoryDialog",
    "CompoundInterestDialog",
    "ContributeGoalDialog",
    "GoalScenarioDialog",
    "InitialSetupDialog",
    "LoanAmortizationDialog",
    "MergeCategoryDialog",
    "MobileSyncSessionDialog",
    "QColorDialog",
    "ReconciliationDialog",
    "RecurringDialog",
    "SavingsGoalDialog",
    "TagDialog",
    "TransactionDialog",
    "TransferDialog",
]
