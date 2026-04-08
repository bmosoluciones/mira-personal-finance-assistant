# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Legacy compatibility re-exports for CRUD dialogs.

This module remains as a transitional import surface while the concrete
implementations live in their domain-specific modules under
``mira.ui.dialogs``.
"""

from __future__ import annotations

from mira.ui.dialogs._shared import show_user_message
from mira.ui.dialogs.accounts import AccountDialog
from mira.ui.dialogs.budget import BudgetCreateDialog
from mira.ui.dialogs.categories import CategoryDialog, MergeCategoryDialog
from mira.ui.dialogs.goals import ContributeGoalDialog, SavingsGoalDialog
from mira.ui.dialogs.recurring import RecurringDialog
from mira.ui.dialogs.setup import InitialSetupDialog
from mira.ui.dialogs.tags import TagDialog
from mira.ui.dialogs.transactions import BalanceAdjustmentDialog, TransactionDialog, TransferDialog, _transfer_tr

__all__ = [
    "AccountDialog",
    "BalanceAdjustmentDialog",
    "BudgetCreateDialog",
    "CategoryDialog",
    "ContributeGoalDialog",
    "InitialSetupDialog",
    "MergeCategoryDialog",
    "RecurringDialog",
    "SavingsGoalDialog",
    "TagDialog",
    "TransactionDialog",
    "TransferDialog",
    "_transfer_tr",
    "show_user_message",
]
