# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""SQLite database layer for MIRA.

Handles connection management, schema creation, and all CRUD operations
for accounts, transactions, buckets, settings, categories, and recurring.
"""

from __future__ import annotations

import builtins
from datetime import date
from pathlib import Path
from typing import Any

from mira.db import helpers as db_helpers
from mira.db.backend import DatabaseBackend as _DatabaseBackend
from mira.db.money import Money, MoneyLike
from mira.db.repositories.backup_repository import RestoreResult
from mira.services.database_io import DatabaseIOService

CURRENCY_CODES = db_helpers.CURRENCY_CODES


class _DatabaseFacade:
    def __init__(self, db: _DatabaseBackend) -> None:
        self._db = db


class AccountFacade(_DatabaseFacade):
    def list(self, account_types: tuple[str, ...] | None = None) -> list[dict]:
        return self._db.get_accounts(account_types)

    def get(self, account_id: int) -> dict | None:
        return self._db.get_account_by_id(account_id)

    def find_by_name(self, name: str) -> dict | None:
        return self._db.get_account_by_name(name)

    def get_or_create(self, name: str) -> dict:
        return self._db.get_or_create_account(name)

    def create(
        self,
        name: str,
        account_type: str = "bank",
        opening_balance: MoneyLike = 0,
        currency: str | None = None,
    ) -> dict:
        return self._db.add_account(name, account_type, opening_balance, currency)

    def update(self, account_id: int, name: str, account_type: str, currency: str | None = None) -> None:
        self._db.update_account(account_id, name, account_type, currency)

    def delete(self, account_id: int) -> None:
        self._db.delete_account(account_id)

    def set_default(self, account_id: int) -> None:
        self._db.set_default_account(account_id)

    def get_default(self) -> dict | None:
        return self._db.get_default_account()

    def list_credit(self) -> builtins.list[dict]:
        return self._db.get_credit_accounts()

    def is_credit(self, account_id: int) -> bool:
        return self._db.is_credit_account(account_id)

    def find_mentions(self, text: str, *, account_types: tuple[str, ...] | None = None) -> builtins.list[dict]:
        return self._db.find_account_mentions(text, account_types=account_types)

    def get_balance_report(self) -> dict[str, Any]:
        return self._db.get_account_balance_report()

    def balance_as_of(
        self,
        account_id: int,
        on_date: str,
        *,
        exclude_transaction_id: int | None = None,
    ) -> dict[str, Any]:
        return self._db.get_account_balance_as_of(
            account_id,
            on_date,
            exclude_transaction_id=exclude_transaction_id,
        )

    def update_balance(self, account_id: int, delta: MoneyLike) -> None:
        self._db.update_account_balance(account_id, delta)


class CategoryFacade(_DatabaseFacade):
    def list(self, cat_type: str | None = None, *, include_savings: bool = True) -> list[dict]:
        return self._db.get_categories(cat_type, include_savings=include_savings)

    def get(self, cat_id: int) -> dict | None:
        return self._db.get_category_by_id(cat_id)

    def find_by_name(self, name: str, cat_type: str | None = None) -> dict | None:
        return self._db.get_category_by_name(name, cat_type)

    def create(
        self,
        name: str,
        cat_type: str,
        color: str = "#888888",
        parent_id: int | None = None,
        is_savings: bool = False,
        icon: str = "",
    ) -> dict:
        return self._db.add_category(
            name,
            cat_type,
            color=color,
            parent_id=parent_id,
            is_savings=is_savings,
            icon=icon,
        )

    def get_or_create(
        self,
        name: str,
        cat_type: str,
        color: str = "#888888",
        parent_id: int | None = None,
        is_savings: bool = False,
        icon: str = "",
    ) -> dict:
        return self._db.get_or_create_category(
            name,
            cat_type,
            color=color,
            parent_id=parent_id,
            is_savings=is_savings,
            icon=icon,
        )

    def update(
        self,
        cat_id: int,
        name: str,
        cat_type: str,
        color: str = "#888888",
        is_savings: bool = False,
        parent_id: int | None = None,
        icon: str = "",
    ) -> None:
        self._db.update_category(
            cat_id,
            name,
            cat_type,
            color=color,
            is_savings=is_savings,
            parent_id=parent_id,
            icon=icon,
        )

    def list_subcategories(self, parent_id: int) -> builtins.list[dict]:
        return self._db.get_subcategories(parent_id)

    def delete(self, cat_id: int) -> None:
        self._db.delete_category(cat_id)

    def merge(self, source_cat_id: int, target_cat_id: int) -> dict:
        return self._db.merge_categories(source_cat_id, target_cat_id)

    def tree(self, cat_type: str | None = None, *, include_savings: bool = True) -> builtins.list[dict]:
        return self._db.get_categories_tree(cat_type, include_savings=include_savings)

    def descendant_ids(self, cat_id: int) -> builtins.list[int]:
        return self._db.get_category_with_descendants(cat_id)

    def descendant_names(self, cat_id: int) -> builtins.list[str]:
        return self._db.get_descendant_category_names(cat_id)


class TagFacade(_DatabaseFacade):
    def create(self, name: str, color: str = "#888888", icon: str = "") -> dict:
        return self._db.add_tag(name, color=color, icon=icon)

    def list(self) -> list[dict]:
        return self._db.get_tags()

    def get(self, tag_id: int) -> dict | None:
        return self._db.get_tag_by_id(tag_id)

    def find_by_name(self, name: str) -> dict | None:
        return self._db.get_tag_by_name(name)

    def update(self, tag_id: int, name: str, color: str, icon: str = "") -> None:
        self._db.update_tag(tag_id, name, color, icon=icon)

    def delete(self, tag_id: int) -> None:
        self._db.delete_tag(tag_id)

    def list_for_transaction(self, transaction_id: int) -> builtins.list[dict]:
        return self._db.get_transaction_tags(transaction_id)

    def set_for_transaction(self, transaction_id: int, tag_ids: builtins.list[int]) -> None:
        self._db.set_transaction_tags(transaction_id, tag_ids)

    def add_to_transaction(self, transaction_id: int, tag_id: int) -> None:
        self._db.add_transaction_tag(transaction_id, tag_id)

    def remove_from_transaction(self, transaction_id: int, tag_id: int) -> None:
        self._db.remove_transaction_tag(transaction_id, tag_id)

    def list_bulk_for_transactions(self, transaction_ids: builtins.list[int]) -> dict[int, builtins.list[dict]]:
        return self._db.get_transactions_tags_bulk(transaction_ids)

    def list_for_recurring(self, recurring_id: int) -> builtins.list[dict]:
        return self._db.get_recurring_tags(recurring_id)

    def set_for_recurring(self, recurring_id: int, tag_ids: builtins.list[int]) -> None:
        self._db.set_recurring_tags(recurring_id, tag_ids)

    def list_bulk_for_recurring(self, recurring_ids: builtins.list[int]) -> dict[int, builtins.list[dict]]:
        return self._db.get_recurring_tags_bulk(recurring_ids)


class TransactionFacade(_DatabaseFacade):
    def build_monthly_context(self, tx: dict[str, Any]) -> dict[str, Any]:
        return self._db.build_monthly_context(tx)

    def create(
        self,
        *,
        account_id: int,
        tx_type: str,
        amount: MoneyLike,
        description: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        payment_method: str = "cash",
        receipt_path: str | None = None,
        tx_date: str | None = None,
        note: str | None = None,
        to_account_id: int | None = None,
        is_transfer: int = 0,
        exchange_rate: float | None = None,
        converted_amount: MoneyLike | None = None,
        category_id: int | None = None,
        source: str | None = None,
    ) -> dict:
        return self._db.add_transaction(
            account_id=account_id,
            tx_type=tx_type,
            amount=amount,
            description=description,
            category=category,
            subcategory=subcategory,
            payment_method=payment_method,
            receipt_path=receipt_path,
            tx_date=tx_date,
            note=note,
            to_account_id=to_account_id,
            is_transfer=is_transfer,
            exchange_rate=exchange_rate,
            converted_amount=converted_amount,
            category_id=category_id,
            source=source,
        )

    def get(self, tx_id: int) -> dict | None:
        return self._db.get_transaction_by_id(tx_id)

    def list(
        self,
        *,
        limit: int = 50,
        tx_type: str | None = None,
        account_id: int | None = None,
        since_date: str | None = None,
        until_date: str | None = None,
        category: str | None = None,
        payment_method: str | None = None,
        min_amount: MoneyLike | None = None,
        max_amount: MoneyLike | None = None,
        search: str | None = None,
        tag_id: int | None = None,
        include_children: bool = False,
    ) -> list[dict]:
        return self._db.get_transactions(
            limit=limit,
            tx_type=tx_type,
            account_id=account_id,
            since_date=since_date,
            until_date=until_date,
            category=category,
            payment_method=payment_method,
            min_amount=min_amount,
            max_amount=max_amount,
            search=search,
            tag_id=tag_id,
            include_children=include_children,
        )

    def update(self, tx_id: int, **kwargs: object) -> dict:
        return self._db.update_transaction(tx_id, **kwargs)

    def delete(self, tx_id: int) -> None:
        self._db.delete_transaction(tx_id)

    def update_account(self, tx_id: int, account_id: int) -> dict:
        return self._db.update_transaction_account(tx_id, account_id)

    def update_category(self, tx_id: int, category: str | None) -> dict:
        return self._db.update_transaction_category(tx_id, category)

    def transfer_between_accounts(
        self,
        from_account_id: int,
        to_account_id: int,
        amount: MoneyLike,
        note: str | None = None,
        tx_date: str | None = None,
        exchange_rate: float | None = None,
        converted_amount: MoneyLike | None = None,
        description: str | None = None,
    ) -> tuple[dict, dict]:
        return self._db.transfer_between_accounts(
            from_account_id,
            to_account_id,
            amount,
            note=note,
            tx_date=tx_date,
            exchange_rate=exchange_rate,
            converted_amount=converted_amount,
            description=description,
        )

    def record_credit_card_payment(
        self,
        from_account_id: int,
        credit_account_id: int,
        amount: MoneyLike,
        *,
        note: str | None = None,
        tx_date: str | None = None,
        exchange_rate: float | None = None,
        converted_amount: MoneyLike | None = None,
        description: str | None = None,
    ) -> tuple[dict, dict]:
        return self._db.record_credit_card_payment(
            from_account_id,
            credit_account_id,
            amount,
            note=note,
            tx_date=tx_date,
            exchange_rate=exchange_rate,
            converted_amount=converted_amount,
            description=description,
        )

    def record_balance_adjustment(
        self,
        account_id: int,
        signed_amount: MoneyLike,
        *,
        tx_date: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        return self._db.record_balance_adjustment(
            account_id,
            signed_amount,
            tx_date=tx_date,
            note=note,
        )

    def update_balance_adjustment(
        self,
        tx_id: int,
        account_id: int,
        signed_amount: MoneyLike,
        *,
        tx_date: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        return self._db.update_balance_adjustment(
            tx_id,
            account_id,
            signed_amount,
            tx_date=tx_date,
            note=note,
        )


class RecurringFacade(_DatabaseFacade):
    def list(self) -> list[dict]:
        return self._db.get_recurring()

    def create(
        self,
        *,
        account_id: int,
        tx_type: str,
        amount: MoneyLike,
        description: str | None,
        category: str | None,
        note: str | None,
        day_of_month: int,
        category_id: int | None = None,
        tag_ids: builtins.list[int] | None = None,
    ) -> dict:
        return self._db.add_recurring(
            account_id=account_id,
            tx_type=tx_type,
            amount=amount,
            description=description,
            category=category,
            note=note,
            day_of_month=day_of_month,
            category_id=category_id,
            tag_ids=tag_ids,
        )

    def update(self, recurring_id: int, **kwargs: object) -> dict:
        return self._db.update_recurring(recurring_id, **kwargs)

    def delete(self, recurring_id: int) -> None:
        self._db.delete_recurring(recurring_id)

    def apply_for_month(self, year: int, month: int) -> builtins.list[dict]:
        return self._db.apply_recurring_for_month(year, month)


class SavingsGoalFacade(_DatabaseFacade):
    def create(
        self,
        name: str,
        target_amount: MoneyLike,
        target_date: str | None = None,
        *,
        currency: str | None = None,
        category_name: str | None = None,
    ) -> dict:
        return self._db.add_savings_goal(
            name,
            target_amount,
            target_date,
            currency=currency,
            category_name=category_name,
        )

    def get(self, goal_id: int) -> dict:
        return self._db.get_savings_goal(goal_id)

    def find_by_name(self, name: str) -> dict | None:
        return self._db.get_savings_goal_by_name(name)

    def list(self) -> list[dict]:
        return self._db.get_savings_goals()

    def get_or_create(
        self,
        name: str,
        target_amount: MoneyLike,
        target_date: str | None = None,
        *,
        currency: str | None = None,
        category_name: str | None = None,
    ) -> dict:
        return self._db.get_or_create_savings_goal(
            name,
            target_amount,
            target_date,
            currency=currency,
            category_name=category_name,
        )

    def contribute(self, goal_id: int, amount: MoneyLike) -> dict:
        return self._db.contribute_to_goal(goal_id, amount)

    def update(
        self,
        goal_id: int,
        *,
        name: str,
        target_amount: MoneyLike,
        target_date: str | None = None,
    ) -> dict:
        return self._db.update_savings_goal(
            goal_id,
            name=name,
            target_amount=target_amount,
            target_date=target_date,
        )

    def delete(self, goal_id: int) -> None:
        self._db.delete_savings_goal(goal_id)


class SettingFacade(_DatabaseFacade):
    def get(self, key: str) -> str | None:
        return self._db.get_setting(key)

    def set(self, key: str, value: str) -> None:
        self._db.set_setting(key, value)

    def get_default_currency(self) -> str:
        return self._db.get_default_currency()

    def get_savings_goals_parent_name(self) -> str:
        return self._db.get_savings_goals_parent_name()

    def list_currencies(self, region: str | None = "americas") -> list[dict]:
        return self._db.get_currencies(region=region)

    def seed_initial_data(
        self,
        *,
        include_default_categories: bool = True,
        account_names: list[str] | None = None,
        account_specs: list[dict[str, Any]] | None = None,
        language: str = "en",
        update_existing_category_metadata: bool = True,
    ) -> None:
        self._db.seed_initial_data(
            include_default_categories=include_default_categories,
            account_names=account_names,
            account_specs=account_specs,
            language=language,
            update_existing_category_metadata=update_existing_category_metadata,
        )

    def seed_demo_data(self, *, reference_date: date | None = None) -> dict[str, Any]:
        return self._db.seed_demo_data(reference_date=reference_date)


class BudgetFacade(_DatabaseFacade):
    def __init__(self, db: _DatabaseBackend, io_service: DatabaseIOService) -> None:
        super().__init__(db)
        self._io_service = io_service

    def get_current(self) -> dict | None:
        return self._db.get_active_budget()

    def list(self, year: int | None = None) -> list[dict]:
        return self._db.list_budgets(year=year)

    def get(self, budget_id: int) -> dict | None:
        return self._db.get_budget_by_id(budget_id)

    def find_by_code(self, code: str) -> dict | None:
        return self._db.get_budget_by_code(code)

    def get_default_for_year(self, year: int) -> dict | None:
        return self._db.get_default_budget_for_year(year)

    def set_default_for_year(self, budget_id: int) -> None:
        self._db.set_default_budget_for_year(budget_id)

    def create(self, code: str, year: int, currency: str | None = None) -> dict:
        return self._db.create_budget(code, year, currency=currency)

    def delete(self, budget_id: int) -> None:
        self._db.delete_budget(budget_id)

    def upsert_amount(
        self,
        budget_id: int,
        category_id: int,
        year: int,
        month: int,
        amount: MoneyLike,
    ) -> None:
        self._db.upsert_budget_amount(budget_id, category_id, year, month, amount)

    def get_matrix(self, budget_id: int) -> dict[str, object]:
        return self._db.get_budget_matrix(budget_id)

    def has_values(self, budget_id: int) -> bool:
        return self._db.budget_has_values(budget_id)

    def propose(self, budget_id: int) -> dict[str, object]:
        return self._db.propose_budget(budget_id)

    def compare(self, budget_id: int, granularity: str = "quarterly") -> dict[str, object]:
        return self._db.get_budget_comparison(budget_id, granularity=granularity)

    def get_monthly_tracking(self, budget_id: int, year: int, month: int) -> dict[str, Any]:
        return self._db.get_monthly_budget_tracking(budget_id, year, month)

    def reassign_monthly(
        self,
        budget_id: int,
        year: int,
        month: int,
        source_category_id: int,
        target_category_id: int,
        amount: float,
    ) -> dict[str, Any]:
        return self._db.reassign_monthly_budget(
            budget_id,
            year,
            month,
            source_category_id,
            target_category_id,
            amount,
        )

    def export_comparison_excel(self, filepath: str | Path, budget_id: int, *, granularity: str = "quarterly") -> int:
        return self._io_service.export_budget_comparison_excel(filepath, budget_id, granularity=granularity)


class ReportFacade(_DatabaseFacade):
    def get_summary(self, since_date: str | None = None) -> dict:
        return self.summary(since_date=since_date)

    def summary(self, since_date: str | None = None) -> dict:
        return self._db.get_summary(since_date=since_date)

    def summarize_financials(
        self,
        transactions: list[dict[str, Any]],
        *,
        categories: list[dict[str, Any]] | None = None,
    ) -> dict[str, Money]:
        return self._db.summarize_financials(transactions, categories=categories)

    def summarize_financials_filtered(
        self,
        *,
        tx_type: str | None = None,
        account_id: int | None = None,
        since_date: str | None = None,
        until_date: str | None = None,
        category: str | None = None,
        tag_id: int | None = None,
        include_children: bool = False,
    ) -> dict[str, Money]:
        return self._db.summarize_financials_filtered(
            tx_type=tx_type,
            account_id=account_id,
            since_date=since_date,
            until_date=until_date,
            category=category,
            tag_id=tag_id,
            include_children=include_children,
        )

    def get_category_summary(
        self,
        *,
        since_date: str | None = None,
        until_date: str | None = None,
        aggregate_by_parent: bool = False,
    ) -> list[dict]:
        return self.category_summary(
            since_date=since_date,
            until_date=until_date,
            aggregate_by_parent=aggregate_by_parent,
        )

    def category_summary(
        self,
        *,
        since_date: str | None = None,
        until_date: str | None = None,
        aggregate_by_parent: bool = False,
    ) -> list[dict]:
        return self._db.get_category_summary(
            since_date=since_date,
            until_date=until_date,
            aggregate_by_parent=aggregate_by_parent,
        )

    def tag_transaction_counts(
        self,
        *,
        since_date: str | None = None,
        until_date: str | None = None,
    ) -> dict[int, int]:
        return self._db.get_tag_transaction_counts(since_date=since_date, until_date=until_date)

    def category_transaction_counts(
        self,
        *,
        since_date: str | None = None,
        until_date: str | None = None,
    ) -> dict[str, int]:
        return self._db.get_category_transaction_counts(since_date=since_date, until_date=until_date)

    def get_mira_master_report(
        self,
        *,
        year: int,
        month: int,
        relevance_threshold: float = 0.10,
    ) -> dict[str, Any]:
        return self._db.get_mira_master_report(
            year=year,
            month=month,
            relevance_threshold=relevance_threshold,
        )

    def get_budget_alerts(self) -> list[dict]:
        return self._db.get_budget_alerts()

    def budget_period_snapshot(
        self,
        year: int,
        month: int,
    ) -> tuple[dict | None, dict[str, dict[str, float]] | None, list[dict[str, Any]] | None]:
        return self._db.get_budget_period_snapshot(year, month)


class BucketFacade(_DatabaseFacade):
    def list(self) -> list[dict]:
        return self._db.get_buckets()

    def find_by_name(self, name: str) -> dict | None:
        return self._db.get_bucket_by_name(name)

    def upsert(
        self,
        name: str,
        budget_amount: MoneyLike,
        period: str = "monthly",
        start_day: int = 1,
        end_day: int = 31,
        alert_threshold: float = 0.75,
    ) -> dict:
        return self._db.upsert_bucket(
            name,
            budget_amount,
            period=period,
            start_day=start_day,
            end_day=end_day,
            alert_threshold=alert_threshold,
        )

    def update_spent(self, bucket_name: str, amount: MoneyLike) -> None:
        self._db.update_bucket_spent(bucket_name, amount)

    def delete(self, name: str) -> None:
        self._db.delete_bucket(name)


class BackupFacade(_DatabaseFacade):
    def create(self, filepath: str | Path) -> Path:
        return self._db.create_backup(filepath)

    def restore(self, filepath: str | Path) -> RestoreResult:
        return self._db.restore(filepath)


class FeedbackFacade(_DatabaseFacade):
    def pop_daily_contextual_message(self, *, on_date: date | None = None) -> dict[str, Any] | None:
        return self._db.pop_daily_contextual_message(on_date=on_date)

    def get_achievement_counter(self, counter_key: str) -> int:
        return self._db.get_achievement_counter(counter_key)

    def increment_achievement_counter(self, counter_key: str, *, step: int = 1) -> tuple[int, int]:
        return self._db.increment_achievement_counter(counter_key, step=step)

    def month_savings_amount(self, year: int, month: int) -> float:
        return self._db.get_month_savings_amount(year, month)

    def resolve_single_message(
        self,
        candidates: list[dict[str, Any]],
        *,
        source_event_type: str,
        source_event_id: int | None,
        period_key: str | None = None,
        reference_date: str | None = None,
        source: str | None = None,
        persist: bool = True,
    ) -> dict[str, Any] | None:
        return self._db.resolve_single_message(
            candidates,
            source_event_type=source_event_type,
            source_event_id=source_event_id,
            period_key=period_key,
            reference_date=reference_date,
            source=source,
            persist=persist,
        )


class IOFacade:
    def __init__(self, io_service: DatabaseIOService) -> None:
        self._io_service = io_service

    def export_transactions_csv(
        self,
        filepath: str,
        *,
        tx_type: str | None = None,
        account_id: int | None = None,
        since_date: str | None = None,
        until_date: str | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> int:
        return self._io_service.export_transactions_csv(
            filepath,
            tx_type=tx_type,
            account_id=account_id,
            since_date=since_date,
            until_date=until_date,
            category=category,
            search=search,
        )

    def export_budget_comparison_excel(
        self,
        filepath: str | Path,
        budget_id: int,
        *,
        granularity: str = "quarterly",
    ) -> int:
        return self._io_service.export_budget_comparison_excel(filepath, budget_id, granularity=granularity)

    def import_transactions_csv(self, filepath: str) -> tuple[int, int]:
        return self._io_service.import_transactions_csv(filepath)


class Database:
    """Umbrella database entrypoint composed of logical public facades."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._backend = _DatabaseBackend(path=path)
        self._io_service = DatabaseIOService(self._backend)
        self.account = AccountFacade(self._backend)
        self.category = CategoryFacade(self._backend)
        self.tag = TagFacade(self._backend)
        self.transaction = TransactionFacade(self._backend)
        self.recurring = RecurringFacade(self._backend)
        self.savings_goal = SavingsGoalFacade(self._backend)
        self.setting = SettingFacade(self._backend)
        self.budget = BudgetFacade(self._backend, self._io_service)
        self.report = ReportFacade(self._backend)
        self.bucket = BucketFacade(self._backend)
        self.backup = BackupFacade(self._backend)
        self.feedback = FeedbackFacade(self._backend)
        self.io = IOFacade(self._io_service)

    @property
    def path(self) -> Path:
        return self._backend.path

    def connect(self) -> None:
        self._backend.connect()

    def close(self) -> None:
        self._backend.close()
