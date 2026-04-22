# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Module documentation."""

from __future__ import annotations

from mira.db.repositories.account_repository import AccountRepository
from mira.db.repositories.backup_repository import BackupRepository
from mira.db.repositories.bucket_repository import BucketRepository
from mira.db.repositories.budget_repository import BudgetRepository
from mira.db.repositories.category_repository import CategoryRepository
from mira.db.repositories.feedback_repository import FeedbackRepository
from mira.db.repositories.recurring_repository import RecurringRepository
from mira.db.repositories.reconciliation_repository import ReconciliationRepository
from mira.db.repositories.report_repository import ReportRepository
from mira.db.repositories.savings_goal_repository import SavingsGoalRepository
from mira.db.repositories.setting_repository import SettingRepository
from mira.db.repositories.sync_repository import SyncRepository
from mira.db.repositories.tag_repository import TagRepository
from mira.db.repositories.transaction_repository import TransactionRepository
from mira.db.runtime import DatabaseRuntime


class DatabaseBackend(
    DatabaseRuntime,
    AccountRepository,
    TransactionRepository,
    ReconciliationRepository,
    CategoryRepository,
    SavingsGoalRepository,
    SettingRepository,
    SyncRepository,
    TagRepository,
    RecurringRepository,
    FeedbackRepository,
    BudgetRepository,
    BucketRepository,
    ReportRepository,
    BackupRepository,
):
    """Aggregate repository mixins over a shared database runtime."""
