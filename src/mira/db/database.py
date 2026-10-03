# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""SQLite database layer for MIRA.

One ``Database`` object owns the shared Peewee/sqlite runtime plus every
repository mixin, and exposes the public area APIs (``db.account``,
``db.transaction``, ...) as thin attribute namespaces over that single object.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from mira.db import helpers as db_helpers
from mira.db.repositories.account_repository import AccountRepository
from mira.db.repositories.backup_repository import BackupRepository
from mira.db.repositories.bucket_repository import BucketRepository
from mira.db.repositories.budget_repository import BudgetRepository
from mira.db.repositories.category_repository import CategoryRepository
from mira.db.repositories.feedback_repository import FeedbackRepository
from mira.db.repositories.reconciliation_repository import ReconciliationRepository
from mira.db.repositories.recurring_repository import RecurringRepository
from mira.db.repositories.report_repository import ReportRepository
from mira.db.repositories.savings_goal_repository import SavingsGoalRepository
from mira.db.repositories.setting_repository import SettingRepository
from mira.db.repositories.sync_repository import SyncRepository
from mira.db.repositories.tag_repository import TagRepository
from mira.db.repositories.transaction_repository import TransactionRepository
from mira.db.runtime import DatabaseRuntime
from mira.services.database_io import DatabaseIOService

CURRENCY_CODES = db_helpers.CURRENCY_CODES

ApiEntry = str | Callable[..., Any]


class _Namespace:
    """Attribute namespace exposing one area's public API (``db.account``, ...).

    Entries are resolved on every access so tests can still patch a repository
    method on the live ``Database`` instance.
    """

    def __init__(self, target: Any, entries: Mapping[str, ApiEntry], aliases: Mapping[str, Mapping[str, str]] | None = None) -> None:
        self._target = target
        self._entries = dict(entries)
        self._aliases = {name: dict(mapping) for name, mapping in (aliases or {}).items()}

    def __getattr__(self, name: str) -> Any:
        try:
            entry = self._entries[name]
        except KeyError:
            raise AttributeError(f"{type(self).__name__} has no attribute {name!r}") from None
        if isinstance(entry, str):
            resolved = getattr(self._target, entry)
        else:
            resolved = functools.partial(entry, self._target)
        legacy = self._aliases.get(name)
        return _with_legacy_keywords(resolved, legacy) if legacy else resolved

    def __dir__(self) -> list[str]:
        return sorted({*self._entries, *super().__dir__()})


def _with_legacy_keywords(method: Callable[..., Any], aliases: Mapping[str, str]) -> Callable[..., Any]:
    """Accept the pre-collapse keyword names for a facade method.

    Repositories use ``cat_id``/``rec_id`` while the facades this replaced
    exposed ``cat_id``/``recurring_id``. Callers that used keywords must keep
    working across the collapse.
    """

    @functools.wraps(method)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        for legacy_name, current_name in aliases.items():
            if legacy_name in kwargs and current_name not in kwargs:
                kwargs[current_name] = kwargs.pop(legacy_name)
        return method(*args, **kwargs)

    return wrapper


_LEGACY_KEYWORD_ALIASES: dict[str, dict[str, dict[str, str]]] = {
    "category": {"update": {"cat_id": "category_id"}},
    "recurring": {
        "get": {"recurring_id": "rec_id"},
        "update": {"recurring_id": "rec_id"},
        "delete": {"recurring_id": "rec_id"},
    },
}


def _update_category(
    db: Any,
    category_id: int,
    name: str,
    cat_type: str,
    color: str = "#888888",
    is_savings: bool = False,
    parent_id: int | None = None,
    icon: str = "",
    device_id: str | None = None,
) -> None:
    db.update_category(
        category_id,
        name,
        cat_type,
        color=color,
        is_savings=is_savings,
        parent_id=parent_id,
        icon=icon,
        device_id=device_id,
    )


def _export_budget_comparison_excel(
    db: Any,
    filepath: str | Path,
    budget_id: int,
    *,
    granularity: str = "quarterly",
) -> int:
    return db._io_service.export_budget_comparison_excel(filepath, budget_id, granularity=granularity)


_ACCOUNT_API: dict[str, ApiEntry] = {
    "balance_as_of": "get_account_balance_as_of",
    "create": "add_account",
    "delete": "delete_account",
    "find_by_global_id": "get_account_by_global_id",
    "find_by_name": "get_account_by_name",
    "find_mentions": "find_account_mentions",
    "get": "get_account_by_id",
    "get_balance_report": "get_account_balance_report",
    "get_default": "get_default_account",
    "get_or_create": "get_or_create_account",
    "is_credit": "is_credit_account",
    "list": "get_accounts",
    "list_credit": "get_credit_accounts",
    "set_default": "set_default_account",
    "update": "update_account",
    "update_balance": "update_account_balance",
}

_CATEGORY_API: dict[str, ApiEntry] = {
    "create": "add_category",
    "create_relation": "create_category_relation",
    "delete": "delete_category",
    "delete_relation": "delete_category_relation",
    "descendant_ids": "get_category_with_descendants",
    "descendant_names": "get_descendant_category_names",
    "find_by_global_id": "get_category_by_global_id",
    "find_by_name": "get_category_by_name",
    "get": "get_category_by_id",
    "get_or_create": "get_or_create_category",
    "linked_expense_ids": "get_linked_expense_category_ids",
    "list": "get_categories",
    "list_relations": "list_category_relations",
    "list_subcategories": "get_subcategories",
    "merge": "merge_categories",
    "tree": "get_categories_tree",
    "update": _update_category,
}

_TAG_API: dict[str, ApiEntry] = {
    "add_to_transaction": "add_transaction_tag",
    "create": "add_tag",
    "delete": "delete_tag",
    "find_by_global_id": "get_tag_by_global_id",
    "find_by_name": "get_tag_by_name",
    "get": "get_tag_by_id",
    "list": "get_tags",
    "list_bulk_for_recurring": "get_recurring_tags_bulk",
    "list_bulk_for_transactions": "get_transactions_tags_bulk",
    "list_for_recurring": "get_recurring_tags",
    "list_for_transaction": "get_transaction_tags",
    "remove_from_transaction": "remove_transaction_tag",
    "set_for_recurring": "set_recurring_tags",
    "set_for_transaction": "set_transaction_tags",
    "update": "update_tag",
}

_TRANSACTION_API: dict[str, ApiEntry] = {
    "build_monthly_context": "build_monthly_context",
    "create": "add_transaction",
    "delete": "delete_transaction",
    "get": "get_transaction_by_id",
    "get_by_sync_id": "get_transaction_by_sync_id",
    "list": "get_transactions",
    "record_balance_adjustment": "record_balance_adjustment",
    "record_credit_card_payment": "record_credit_card_payment",
    "transfer_between_accounts": "transfer_between_accounts",
    "update": "update_transaction",
    "update_account": "update_transaction_account",
    "update_balance_adjustment": "update_balance_adjustment",
    "update_category": "update_transaction_category",
}

_RECONCILIATION_API: dict[str, ApiEntry] = {
    "clear_for_transactions": "clear_reconciliation_for_transactions",
    "clear_groups": "clear_reconciliation_groups",
    "list_groups": "list_reconciliation_groups",
    "list_matches": "list_reconciliation_matches",
    "reconcile": "reconcile_transactions",
}

_RECURRING_API: dict[str, ApiEntry] = {
    "apply_for_month": "apply_recurring_for_month",
    "create": "add_recurring",
    "delete": "delete_recurring",
    "get": "get_recurring_by_id",
    "list": "get_recurring",
    "update": "update_recurring",
}

_SAVINGS_GOAL_API: dict[str, ApiEntry] = {
    "contribute": "contribute_to_goal",
    "create": "add_savings_goal",
    "delete": "delete_savings_goal",
    "find_by_name": "get_savings_goal_by_name",
    "get": "get_savings_goal",
    "get_or_create": "get_or_create_savings_goal",
    "list": "get_savings_goals",
    "update": "update_savings_goal",
}

_SETTING_API: dict[str, ApiEntry] = {
    "get": "get_setting",
    "get_default_currency": "get_default_currency",
    "get_local_desktop_device_id": "get_local_desktop_device_id",
    "get_master_data_updated_at": "get_master_data_updated_at",
    "get_savings_goals_parent_name": "get_savings_goals_parent_name",
    "list_currencies": "get_currencies",
    "seed_demo_data": "seed_demo_data",
    "seed_initial_data": "seed_initial_data",
    "set": "set_setting",
    "touch_master_data_updated_at": "touch_master_data_updated_at",
}

_BUDGET_API: dict[str, ApiEntry] = {
    "compare": "get_budget_comparison",
    "create": "create_budget",
    "delete": "delete_budget",
    "export_comparison_excel": _export_budget_comparison_excel,
    "find_by_code": "get_budget_by_code",
    "get": "get_budget_by_id",
    "get_current": "get_active_budget",
    "get_default_for_year": "get_default_budget_for_year",
    "get_matrix": "get_budget_matrix",
    "get_monthly_tracking": "get_monthly_budget_tracking",
    "has_values": "budget_has_values",
    "list": "list_budgets",
    "propose": "propose_budget",
    "reassign_monthly": "reassign_monthly_budget",
    "set_default_for_year": "set_default_budget_for_year",
    "upsert_amount": "upsert_budget_amount",
}

_REPORT_API: dict[str, ApiEntry] = {
    "budget_period_snapshot": "get_budget_period_snapshot",
    "category_summary": "get_category_summary",
    "category_transaction_counts": "get_category_transaction_counts",
    "get_budget_alerts": "get_budget_alerts",
    "get_category_summary": "get_category_summary",
    "get_mira_master_report": "get_mira_master_report",
    "get_summary": "get_summary",
    "summarize_financials": "summarize_financials",
    "summarize_financials_filtered": "summarize_financials_filtered",
    "summary": "get_summary",
    "tag_transaction_counts": "get_tag_transaction_counts",
}

_BUCKET_API: dict[str, ApiEntry] = {
    "delete": "delete_bucket",
    "find_by_name": "get_bucket_by_name",
    "list": "get_buckets",
    "update_spent": "update_bucket_spent",
    "upsert": "upsert_bucket",
}

_BACKUP_API: dict[str, ApiEntry] = {
    "create": "create_backup",
    "restore": "restore",
}

_FEEDBACK_API: dict[str, ApiEntry] = {
    "evaluate_expense_kpis": "evaluate_expense_kpis",
    "evaluate_income_kpis": "evaluate_income_kpis",
    "get_achievement_counter": "get_achievement_counter",
    "increment_achievement_counter": "increment_achievement_counter",
    "month_savings_amount": "get_month_savings_amount",
    "pop_daily_contextual_message": "pop_daily_contextual_message",
    "resolve_single_message": "resolve_single_message",
    "select_best_operation_message": "select_best_operation_message",
}

_SYNC_API: dict[str, ApiEntry] = {
    "ack_device_cursor": "ack_sync_device_cursor",
    "get_device": "get_sync_device",
    "get_tombstone": "get_transaction_tombstone",
    "get_transaction_by_sync_id": "get_transaction_by_sync_id",
    "list_transaction_changes": "list_transaction_changes",
    "register_device": "register_sync_device",
}

_IO_API: dict[str, ApiEntry] = {
    "export_budget_comparison_excel": "export_budget_comparison_excel",
    "export_transactions_csv": "export_transactions_csv",
    "export_transactions_file": "export_transactions_file",
    "import_transactions_csv": "import_transactions_csv",
    "import_transactions_file": "import_transactions_file",
}


class Database(
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
    """SQLite database: connection runtime plus every repository mixin."""

    def __init__(self, path: str | Path | None = None) -> None:
        """Initialize the Database instance."""
        super().__init__(path=path)
        self._io_service = DatabaseIOService(self)
        self.account = _Namespace(self, _ACCOUNT_API)
        self.category = _Namespace(self, _CATEGORY_API, _LEGACY_KEYWORD_ALIASES["category"])
        self.tag = _Namespace(self, _TAG_API)
        self.transaction = _Namespace(self, _TRANSACTION_API)
        self.reconciliation = _Namespace(self, _RECONCILIATION_API)
        self.recurring = _Namespace(self, _RECURRING_API, _LEGACY_KEYWORD_ALIASES["recurring"])
        self.savings_goal = _Namespace(self, _SAVINGS_GOAL_API)
        self.setting = _Namespace(self, _SETTING_API)
        self.budget = _Namespace(self, _BUDGET_API)
        self.report = _Namespace(self, _REPORT_API)
        self.bucket = _Namespace(self, _BUCKET_API)
        self.backup = _Namespace(self, _BACKUP_API)
        self.feedback = _Namespace(self, _FEEDBACK_API)
        self.sync = _Namespace(self, _SYNC_API)
        self.io = _Namespace(self._io_service, _IO_API)
