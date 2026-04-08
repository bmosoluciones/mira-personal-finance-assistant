# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""UI-facing application services used by MIRA views."""

from ._common import OperationFeedback, PresentationContext
from .accounts import AccountsViewService, AccountsViewState, BalanceAdjustmentPreview
from .categories import CategoriesViewService, CategoriesViewState
from .mira_analysis import (
    MiraAnalysisCardState,
    MiraAnalysisComparisonBadge,
    MiraAnalysisDrilldownRow,
    MiraAnalysisDrilldownSection,
    MiraAnalysisLineChartState,
    MiraAnalysisMessageBuilder,
    MiraAnalysisService,
    MiraAnalysisStackedBarChartState,
    MiraAnalysisViewState,
    MiraAnalysisViewStateBuilder,
    MiraAnalysisWaterfallState,
    MiraAnalysisWaterfallStep,
)
from .recurring import RecurringViewService, RecurringViewState
from .reports import (
    PresentationCell,
    PresentationRow,
    ReportFilterOptions,
    ReportsAccountBalanceSection,
    ReportsBudgetSection,
    ReportsCashFlowSection,
    ReportsCategorySection,
    ReportsComparisonState,
    ReportsLoadedState,
    ReportsPresentationState,
    ReportsTableSection,
    ReportsTagSection,
    ReportsTransactionItem,
    ReportsTransactionPage,
    ReportsViewService,
    ReportsViewStateBuilder,
)
from .savings_goals import SavingsGoalsViewService, SavingsGoalsViewState
from .settings import SettingsViewService, SettingsViewState
from .tags import TagsViewService, TagsViewState
from .transactions import TransactionsFilterOptions, TransactionsViewService, TransactionsViewState

__all__ = [
    "AccountsViewService",
    "AccountsViewState",
    "BalanceAdjustmentPreview",
    "CategoriesViewService",
    "CategoriesViewState",
    "MiraAnalysisCardState",
    "MiraAnalysisComparisonBadge",
    "MiraAnalysisDrilldownRow",
    "MiraAnalysisDrilldownSection",
    "MiraAnalysisLineChartState",
    "MiraAnalysisMessageBuilder",
    "MiraAnalysisService",
    "MiraAnalysisStackedBarChartState",
    "MiraAnalysisViewState",
    "MiraAnalysisViewStateBuilder",
    "MiraAnalysisWaterfallState",
    "MiraAnalysisWaterfallStep",
    "OperationFeedback",
    "PresentationCell",
    "PresentationContext",
    "PresentationRow",
    "RecurringViewService",
    "RecurringViewState",
    "ReportsAccountBalanceSection",
    "ReportsBudgetSection",
    "ReportsCashFlowSection",
    "ReportsCategorySection",
    "ReportsComparisonState",
    "ReportFilterOptions",
    "ReportsLoadedState",
    "ReportsPresentationState",
    "ReportsTableSection",
    "ReportsTagSection",
    "ReportsTransactionItem",
    "ReportsTransactionPage",
    "ReportsViewService",
    "ReportsViewStateBuilder",
    "SavingsGoalsViewService",
    "SavingsGoalsViewState",
    "SettingsViewService",
    "SettingsViewState",
    "TagsViewService",
    "TagsViewState",
    "TransactionsFilterOptions",
    "TransactionsViewService",
    "TransactionsViewState",
]
